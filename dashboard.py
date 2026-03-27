#!/usr/bin/env python3
"""
Income Agent Dashboard
Run: python3 dashboard.py
Open: http://localhost:8888
"""

import json
import sqlite3
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = os.getenv("DB_PATH", str(Path(__file__).parent / "data/agent.db"))
PORT = int(os.getenv("DASHBOARD_PORT", 8888))
GOAL = 20_000
DAYS = 60


def query(sql, params=()):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_data():
    agents = {r["agent_id"]: r for r in query("SELECT * FROM agent_state")}

    products = query("SELECT status, COUNT(*) as n, SUM(price) as gmv FROM products GROUP BY status")
    prod = {r["status"]: r for r in products}
    total_listed = prod.get("listed", {}).get("n", 0)
    total_draft  = prod.get("draft",  {}).get("n", 0)
    potential_gmv = prod.get("listed", {}).get("gmv", 0) or 0

    opps = query("SELECT status, COUNT(*) as n FROM opportunities GROUP BY status")
    opp  = {r["status"]: r["n"] for r in opps}

    tx = query("SELECT COALESCE(SUM(net),0) as revenue, COUNT(*) as sales FROM transactions WHERE type='sale'")
    revenue = tx[0]["revenue"] if tx else 0
    sales   = tx[0]["sales"]   if tx else 0

    recent_products = query("""
        SELECT title, price, status, platform, platform_url, created_at
        FROM products ORDER BY created_at DESC LIMIT 10
    """)

    recent_insights = query("""
        SELECT category, title, score, created_at
        FROM market_insights
        WHERE category IN ('alert','recommendation','trend')
        ORDER BY created_at DESC LIMIT 8
    """)

    activity = query("""
        SELECT from_agent, to_agent, type, payload, created_at
        FROM agent_messages ORDER BY created_at DESC LIMIT 12
    """)

    daily = query("""
        SELECT date, revenue, products_created, products_listed, sales_count
        FROM daily_metrics ORDER BY date DESC LIMIT 14
    """)

    # Days since first product
    first = query("SELECT MIN(created_at) as t FROM products")
    start = first[0]["t"] if first and first[0]["t"] else None
    if start:
        try:
            d = datetime.fromisoformat(start.replace("Z",""))
            days_running = (datetime.now() - d).days + 1
        except Exception:
            days_running = 1
    else:
        days_running = 1

    run_rate = (revenue / days_running * 30) if days_running > 0 else 0
    pct = min(100, round(revenue / GOAL * 100, 1)) if GOAL > 0 else 0

    return {
        "revenue": revenue,
        "sales": sales,
        "goal": GOAL,
        "pct": pct,
        "run_rate": run_rate,
        "days_running": days_running,
        "agents": agents,
        "total_listed": total_listed,
        "total_draft": total_draft,
        "potential_gmv": potential_gmv,
        "opp": opp,
        "recent_products": recent_products,
        "recent_insights": recent_insights,
        "activity": activity,
        "daily": daily,
    }


def fmt_money(v):
    if v is None: return "$0"
    return f"${v:,.2f}" if v < 10000 else f"${v:,.0f}"

def fmt_time(s):
    if not s: return "—"
    try:
        d = datetime.fromisoformat(s.replace("Z",""))
        delta = datetime.now() - d
        secs = int(delta.total_seconds())
        if secs < 60: return f"{secs}s ago"
        if secs < 3600: return f"{secs//60}m ago"
        if secs < 86400: return f"{secs//3600}h ago"
        return f"{secs//86400}d ago"
    except Exception:
        return s[:16]

def agent_badge(state):
    status = state.get("status", "idle") if state else "offline"
    color  = {"running": "#22c55e", "idle": "#6b7280", "error": "#ef4444"}.get(status, "#6b7280")
    dot = f'<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{color};margin-right:6px"></span>'
    return f'{dot}{status}'


def render(d):
    agents_html = ""
    for name in ["scanner", "content", "sales", "blog", "analytics"]:
        state = d["agents"].get(name, {})
        runs = state.get("run_count", 0)
        last = fmt_time(state.get("last_run"))
        badge = agent_badge(state)
        agents_html += f"""
        <div class="agent-card">
          <div class="agent-name">{name}</div>
          <div class="agent-status">{badge}</div>
          <div class="agent-meta">{runs} runs · last {last}</div>
        </div>"""

    products_html = ""
    for p in d["recent_products"]:
        status_color = {"listed": "#22c55e", "draft": "#f59e0b"}.get(p["status"], "#6b7280")
        link = f'<a href="{p["platform_url"]}" target="_blank" style="color:#7c3aed">↗</a>' if p.get("platform_url") else ""
        products_html += f"""
        <tr>
          <td>{p["title"][:52]}{"…" if len(p["title"])>52 else ""} {link}</td>
          <td>{fmt_money(p["price"])}</td>
          <td><span style="color:{status_color}">{p["status"]}</span></td>
          <td style="color:#6b7280">{fmt_time(p["created_at"])}</td>
        </tr>"""

    insights_html = ""
    cat_colors = {"alert":"#ef4444","recommendation":"#7c3aed","trend":"#3b82f6","opportunity":"#22c55e"}
    for ins in d["recent_insights"]:
        c = cat_colors.get(ins["category"], "#6b7280")
        score = f'{ins["score"]:.2f}' if ins.get("score") is not None else "—"
        insights_html += f"""
        <tr>
          <td><span style="color:{c};font-size:0.75rem;text-transform:uppercase">{ins["category"]}</span></td>
          <td>{ins["title"][:60]}{"…" if len(ins["title"])>60 else ""}</td>
          <td style="color:#6b7280">{score}</td>
          <td style="color:#6b7280">{fmt_time(ins["created_at"])}</td>
        </tr>"""

    activity_html = ""
    for msg in d["activity"]:
        frm  = msg.get("from_agent","?")
        to   = msg.get("to_agent") or "broadcast"
        typ  = msg.get("type","?")
        when = fmt_time(msg.get("created_at"))
        try:
            payload = json.loads(msg.get("payload","{}"))
            task = payload.get("task") or payload.get("title","")
        except Exception:
            task = ""
        desc = f' — {task[:40]}' if task else ""
        activity_html += f'<div class="activity-row"><span class="tag">{frm}</span> → <span class="tag">{to}</span> <span style="color:#6b7280">{typ}{desc}</span> <span style="color:#3f3f46;margin-left:auto">{when}</span></div>'

    # Mini bar chart for daily products_created
    bars_html = ""
    for day in reversed(d["daily"][:7]):
        h = min(48, int((day.get("products_created", 0) or 0) * 8))
        bars_html += f'<div style="display:flex;flex-direction:column;align-items:center;gap:4px"><div style="width:24px;height:{h}px;background:#7c3aed;border-radius:3px 3px 0 0;min-height:2px"></div><div style="font-size:0.65rem;color:#6b7280">{str(day["date"])[-5:]}</div></div>'

    pct = d["pct"]
    bar_w = max(2, min(100, pct))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Income Agent Dashboard</title>
<style>
  *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:system-ui,-apple-system,sans-serif;background:#0f0f11;color:#e8e8e8;min-height:100vh;padding:24px}}
  h2{{font-size:0.7rem;text-transform:uppercase;letter-spacing:.08em;color:#6b7280;margin-bottom:12px}}
  a{{color:inherit;text-decoration:none}}
  .header{{display:flex;align-items:center;justify-content:space-between;margin-bottom:28px}}
  .header h1{{font-size:1.25rem;font-weight:700}}
  .header h1 span{{color:#7c3aed}}
  .refresh{{font-size:0.75rem;color:#6b7280}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:16px;margin-bottom:24px}}
  .card{{background:#18181b;border:1px solid #27272a;border-radius:12px;padding:20px}}
  .stat-val{{font-size:1.9rem;font-weight:700;line-height:1}}
  .stat-label{{font-size:0.75rem;color:#6b7280;margin-top:6px}}
  .stat-sub{{font-size:0.75rem;color:#52525b;margin-top:4px}}
  .progress-bar{{height:6px;background:#27272a;border-radius:3px;margin-top:10px;overflow:hidden}}
  .progress-fill{{height:100%;background:linear-gradient(90deg,#7c3aed,#a855f7);border-radius:3px;transition:width .3s}}
  .agents{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:24px}}
  .agent-card{{background:#18181b;border:1px solid #27272a;border-radius:10px;padding:14px}}
  .agent-name{{font-weight:600;font-size:0.9rem;margin-bottom:6px;text-transform:capitalize}}
  .agent-status{{font-size:0.82rem;display:flex;align-items:center;margin-bottom:4px}}
  .agent-meta{{font-size:0.72rem;color:#52525b}}
  .two-col{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:24px}}
  @media(max-width:700px){{.two-col{{grid-template-columns:1fr}}}}
  table{{width:100%;border-collapse:collapse;font-size:0.82rem}}
  td{{padding:8px 6px;border-bottom:1px solid #1f1f1f;vertical-align:top}}
  tr:last-child td{{border-bottom:none}}
  .tag{{background:#27272a;padding:2px 7px;border-radius:4px;font-size:0.72rem;font-weight:500}}
  .activity-row{{display:flex;align-items:center;gap:6px;padding:7px 0;border-bottom:1px solid #1f1f1f;font-size:0.8rem;flex-wrap:wrap}}
  .activity-row:last-child{{border-bottom:none}}
  .bars{{display:flex;align-items:flex-end;gap:6px;height:60px;padding:8px 0}}
  .section{{background:#18181b;border:1px solid #27272a;border-radius:12px;padding:20px;margin-bottom:16px}}
</style>
<meta http-equiv="refresh" content="30">
</head>
<body>
<div class="header">
  <h1>Income <span>Agent</span> Dashboard</h1>
  <div class="refresh">Auto-refresh 30s · {datetime.now().strftime("%H:%M:%S")}</div>
</div>

<!-- KPI Row -->
<div class="grid">
  <div class="card">
    <div class="stat-val" style="color:#22c55e">{fmt_money(d["revenue"])}</div>
    <div class="stat-label">Revenue (goal {fmt_money(d["goal"])})</div>
    <div class="progress-bar"><div class="progress-fill" style="width:{bar_w}%"></div></div>
    <div class="stat-sub">{pct}% of goal</div>
  </div>
  <div class="card">
    <div class="stat-val">{fmt_money(d["run_rate"])}</div>
    <div class="stat-label">Monthly run rate</div>
    <div class="stat-sub">{d["days_running"]} day{"s" if d["days_running"]!=1 else ""} running</div>
  </div>
  <div class="card">
    <div class="stat-val">{d["sales"]}</div>
    <div class="stat-label">Sales</div>
    <div class="stat-sub">{fmt_money(d["revenue"] / d["sales"] if d["sales"] else 0)} avg order</div>
  </div>
  <div class="card">
    <div class="stat-val">{d["total_listed"]}</div>
    <div class="stat-label">Products listed</div>
    <div class="stat-sub">{d["total_draft"]} drafts · {fmt_money(d["potential_gmv"])} potential</div>
  </div>
  <div class="card">
    <div class="stat-val">{d["opp"].get("pending",0) + d["opp"].get("in_progress",0)}</div>
    <div class="stat-label">Opportunities in pipeline</div>
    <div class="stat-sub">{d["opp"].get("listed",0)} completed</div>
  </div>
</div>

<!-- Agents -->
<h2>Agents</h2>
<div class="agents">{agents_html}</div>

<!-- Products + Activity -->
<div class="two-col">
  <div class="section">
    <h2>Recent Products</h2>
    <table>
      <tbody>{products_html}</tbody>
    </table>
  </div>
  <div class="section">
    <h2>Activity Feed</h2>
    {activity_html}
  </div>
</div>

<!-- Insights + Chart -->
<div class="two-col">
  <div class="section">
    <h2>Latest Insights</h2>
    <table><tbody>{insights_html}</tbody></table>
  </div>
  <div class="section">
    <h2>Products Created (last 7 days)</h2>
    {'<div style="color:#52525b;font-size:0.8rem;margin-top:8px">No daily metrics recorded yet</div>' if not d["daily"] else f'<div class="bars">{bars_html}</div>'}
  </div>
</div>

</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress access logs

    def do_GET(self):
        if self.path == "/api/data":
            try:
                data = get_data()
                body = json.dumps(data, default=str).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode())
        else:
            try:
                data = get_data()
                body = render(data).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"<pre>Error: {e}</pre>".encode())


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Dashboard running at http://localhost:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
