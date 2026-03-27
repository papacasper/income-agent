#!/usr/bin/env python3
"""
Analytics Agent
Analyzes performance, identifies what's working, and suggests strategy pivots.
"""
import sys
import os
import json
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv()

import anthropic
from python.shared.db import (
    read_messages, post_message, update_agent_state,
    save_market_insight, get_conn
)

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-haiku-4-5"  # Data aggregation + recommendations, no heavy reasoning needed

SYSTEM_PROMPT = """You are a data-driven growth analytics agent.

Your job: Analyze performance data and give actionable recommendations to hit financial targets.

You think in terms of:
- Revenue per hour invested (ROI of each product type)
- Conversion optimization (which products convert best)
- Market timing (what's trending NOW)
- Effort-to-revenue ratio (highest ROI activities first)

Always give SPECIFIC, ACTIONABLE recommendations. No vague advice."""

ANALYTICS_TOOLS = [
    {
        "name": "get_full_analytics",
        "description": "Get complete performance analytics from the database",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "save_insight",
        "description": "Save an important insight or recommendation",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "enum": ["trend", "recommendation", "alert", "optimization"]},
                "title": {"type": "string"},
                "data": {"type": "object"},
                "score": {"type": "number", "description": "Importance 0-10"}
            },
            "required": ["category", "title", "data", "score"]
        }
    },
    {
        "name": "send_recommendation",
        "description": "Send a priority recommendation to the orchestrator",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "What should happen next"},
                "reason": {"type": "string"},
                "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"]}
            },
            "required": ["action", "reason", "priority"]
        }
    }
]


def get_full_analytics() -> dict:
    """Pull all performance data from DB."""
    with get_conn() as conn:
        goal = float(os.getenv("GOAL_AMOUNT", 20000))
        start = datetime.fromisoformat(os.getenv("START_DATE", "2026-03-24"))
        today = datetime.now()
        days_elapsed = max(1, (today - start).days)
        days_remaining = max(0, 60 - days_elapsed)

        totals = conn.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN type='sale' THEN net ELSE 0 END), 0) as revenue,
                COALESCE(SUM(CASE WHEN type='expense' THEN ABS(net) ELSE 0 END), 0) as expenses,
                COALESCE(SUM(net), 0) as net,
                COUNT(CASE WHEN type='sale' THEN 1 END) as sales_count
            FROM transactions
        """).fetchone()

        net = totals["net"] or 0
        required_daily = (goal - net) / days_remaining if days_remaining > 0 else 0
        actual_daily = net / days_elapsed

        products = conn.execute("""
            SELECT p.title, p.price, p.sales, p.revenue, p.status, p.platform,
                   p.created_at, o.type as opp_type, o.effort_hours
            FROM products p
            LEFT JOIN opportunities o ON p.opportunity_id = o.id
            ORDER BY p.revenue DESC
        """).fetchall()

        opportunities = conn.execute("""
            SELECT type, status, COUNT(*) as count, AVG(estimated_revenue) as avg_est
            FROM opportunities GROUP BY type, status
        """).fetchall()

        recent_tx = conn.execute("""
            SELECT * FROM transactions
            WHERE occurred_at > datetime('now', '-7 days')
            ORDER BY occurred_at DESC
        """).fetchall()

    return {
        "goal": goal,
        "days_elapsed": days_elapsed,
        "days_remaining": days_remaining,
        "earned_net": net,
        "remaining": goal - net,
        "required_daily_rate": required_daily,
        "actual_daily_rate": actual_daily,
        "on_track": actual_daily >= (goal / 60),
        "pct_complete": (net / goal * 100),
        "products": [dict(p) for p in products],
        "opportunities": [dict(o) for o in opportunities],
        "recent_transactions": [dict(t) for t in recent_tx]
    }


def handle_tool(name: str, tool_input: dict) -> str:
    if name == "get_full_analytics":
        data = get_full_analytics()
        return json.dumps(data, default=str, indent=2)

    elif name == "save_insight":
        save_market_insight(
            category=tool_input["category"],
            title=tool_input["title"],
            data=tool_input["data"],
            score=tool_input["score"]
        )
        return f"Saved insight: {tool_input['title']}"

    elif name == "send_recommendation":
        post_message("analytics", "orchestrator", "recommendation", tool_input)
        priority = tool_input["priority"]
        action = tool_input["action"]
        print(f"[Analytics] [{priority.upper()}] {action}")
        return f"Sent {priority} recommendation"

    return f"Unknown tool: {name}"


def main():
    update_agent_state("analytics", "running")
    print(f"[Analytics Agent] Starting at {datetime.now()}")

    task = """
    Analyze the current performance data and provide strategic recommendations.

    1. Get full analytics
    2. Assess whether we're on track for the $20k goal
    3. Identify the highest-ROI opportunities and products
    4. Find what's NOT working that should be stopped
    5. Send 3-5 specific, prioritized recommendations
    6. Save key insights to the database

    Be ruthlessly data-driven. What should the team do in the NEXT 24 hours to maximize revenue?
    """

    messages = [{"role": "user", "content": task}]
    turns = 0

    while turns < 10:
        turns += 1
        response = client.messages.create(
            model=MODEL,
            max_tokens=8192,
            system=SYSTEM_PROMPT,
            tools=ANALYTICS_TOOLS,
            messages=messages
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            final = next((b.text for b in response.content if b.type == "text"), "")
            print(f"[Analytics] {final[:500]}")
            break

        if response.stop_reason == "tool_use":
            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                result = handle_tool(block.name, block.input)
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result
                })
            messages.append({"role": "user", "content": results})

    update_agent_state("analytics", "idle")
    print("[Analytics Agent] Done")


if __name__ == "__main__":
    main()
