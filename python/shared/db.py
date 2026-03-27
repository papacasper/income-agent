"""Shared database access for Python agents."""
import sqlite3
import json
import os
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "./data/agent.db")


@contextmanager
def get_conn():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def read_messages(agent_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT id, from_agent, type, payload
            FROM agent_messages
            WHERE (to_agent = ? OR to_agent IS NULL) AND read = 0
            ORDER BY created_at ASC
        """, (agent_id,)).fetchall()

        if rows:
            ids = [r["id"] for r in rows]
            conn.execute(f"UPDATE agent_messages SET read = 1 WHERE id IN ({','.join('?' * len(ids))})", ids)

        return [{"id": r["id"], "from": r["from_agent"], "type": r["type"], "payload": json.loads(r["payload"])} for r in rows]


def post_message(from_agent: str, to_agent: str | None, msg_type: str, payload: dict):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO agent_messages (from_agent, to_agent, type, payload)
            VALUES (?, ?, ?, ?)
        """, (from_agent, to_agent, msg_type, json.dumps(payload)))


def get_opportunity(opportunity_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM opportunities WHERE id = ?", (opportunity_id,)).fetchone()
        if row:
            d = dict(row)
            if d.get("metadata"):
                d["metadata"] = json.loads(d["metadata"])
            return d
        return None


def save_product(opportunity_id: int, title: str, description: str, price: float, platform: str, file_path: str) -> int:
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO products (opportunity_id, title, description, price, platform, file_path, status)
            VALUES (?, ?, ?, ?, ?, ?, 'draft')
        """, (opportunity_id, title, description, price, platform, file_path))

        conn.execute("""
            UPDATE opportunities SET status = 'in_progress' WHERE id = ?
        """, (opportunity_id,))

        return cur.lastrowid


def update_agent_state(agent_id: str, status: str, task: str = None):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO agent_state (agent_id, last_run, run_count, status, current_task)
            VALUES (?, CURRENT_TIMESTAMP, 1, ?, ?)
            ON CONFLICT(agent_id) DO UPDATE SET
                last_run = CURRENT_TIMESTAMP,
                run_count = run_count + 1,
                status = excluded.status,
                current_task = excluded.current_task
        """, (agent_id, status, task))


def get_pending_opportunities() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT * FROM opportunities
            WHERE status = 'pending'
            ORDER BY estimated_revenue DESC
            LIMIT 5
        """).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if d.get("metadata"):
                d["metadata"] = json.loads(d["metadata"])
            result.append(d)
        return result


def save_market_insight(category: str, title: str, data: dict, score: float, source: str = None):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO market_insights (category, title, data, score, source)
            VALUES (?, ?, ?, ?, ?)
        """, (category, title, json.dumps(data), score, source))
