#!/usr/bin/env python3
"""
Market Scanner Agent
Finds profitable digital product opportunities using Brave Search.
Saves opportunities to DB and messages content agent.
"""
import sys
import os
import json
import requests
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv()

import anthropic
from python.shared.db import (
    post_message, update_agent_state, get_conn, save_market_insight
)

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-haiku-4-5"

BRAVE_KEY = os.getenv("BRAVE_API_KEY")

SYSTEM_PROMPT = """You are a market research agent finding high-demand digital products to create and sell.

Focus on:
- Prompt packs / AI workflow templates ($9-$27)
- Notion templates ($17-$47)
- PDF guides / checklists ($9-$27)
- Spreadsheet templates ($17-$47)

Ideal criteria:
- Solves a painful, specific problem
- Easy to create with AI assistance
- Searchable audience (freelancers, creators, small biz)
- Low competition in the $9-$47 price range

Use the search tool to research demand, then save 3-5 strong opportunities."""

TOOLS = [
    {
        "name": "brave_search",
        "description": "Search the web for market research data",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "count": {"type": "number", "description": "Number of results (max 10)"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "save_opportunity",
        "description": "Save a validated product opportunity to the database",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Product title"},
                "type": {"type": "string", "enum": ["prompt_pack", "notion_template", "pdf_guide", "spreadsheet_template", "swipe_file"]},
                "description": {"type": "string", "description": "What problem it solves, who buys it, what's included"},
                "estimated_revenue": {"type": "number", "description": "Estimated monthly revenue in USD"},
                "difficulty": {"type": "string", "enum": ["easy", "medium", "hard"]},
                "target_audience": {"type": "string"},
                "keywords": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["title", "type", "description", "estimated_revenue", "difficulty", "target_audience"]
        }
    }
]


def brave_search(query: str, count: int = 8) -> str:
    if not BRAVE_KEY:
        return json.dumps({"error": "BRAVE_API_KEY not set"})
    try:
        res = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={"X-Subscription-Token": BRAVE_KEY, "Accept": "application/json"},
            params={"q": query, "count": min(count, 10), "search_lang": "en"},
            timeout=10
        )
        data = res.json()
        results = data.get("web", {}).get("results", [])
        return json.dumps([{"title": r.get("title"), "url": r.get("url"), "description": r.get("description")} for r in results[:8]])
    except Exception as e:
        return json.dumps({"error": str(e)})


def save_opportunity(args: dict) -> str:
    title = args["title"]
    opp_type = args["type"]
    description = args["description"]
    estimated_revenue = float(args.get("estimated_revenue", 500))
    difficulty = args.get("difficulty", "medium")
    target_audience = args.get("target_audience", "")
    keywords = args.get("keywords", [])

    # Check if opportunity already exists
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM opportunities WHERE title = ?", (title,)
        ).fetchone()
        if existing:
            return f"Opportunity '{title}' already exists (id={existing['id']})"

        cur = conn.execute("""
            INSERT INTO opportunities
                (title, type, description, estimated_revenue, difficulty, target_audience, metadata, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
        """, (
            title, opp_type, description, estimated_revenue,
            difficulty, target_audience,
            json.dumps({"keywords": keywords})
        ))
        opp_id = cur.lastrowid

    # Message content agent
    post_message("scanner", "content", "task", {
        "task": "create_product",
        "opportunityId": opp_id,
        "title": title,
        "type": opp_type
    })

    print(f"[Scanner] Saved opportunity #{opp_id}: {title} (~${estimated_revenue}/mo)")
    save_market_insight("opportunity", title, {"type": opp_type, "audience": target_audience}, estimated_revenue / 1000, "scanner")
    return f"Saved opportunity #{opp_id}: {title}"


TOOL_HANDLERS = {
    "brave_search": lambda args: brave_search(args["query"], args.get("count", 8)),
    "save_opportunity": save_opportunity,
}


def main():
    update_agent_state("scanner", "running")
    print(f"[Scanner Agent] Starting at {datetime.now()}")

    task = """Research the market for high-demand digital products that AI can create quickly.

Search for:
1. "best notion templates for freelancers 2025" — check what sells
2. "chatgpt prompt packs etsy gumroad" — find top sellers
3. "digital products for content creators to sell" — trending niches
4. "ai productivity tools templates download" — gaps in market

Then save 3-5 specific, actionable product opportunities. Each should:
- Have a specific, keyword-rich title
- Target a clear audience (e.g., "freelance copywriters", "Notion power users")
- Be achievable in one content agent run
- Have realistic $100-$2000/month revenue potential

Focus on products that DON'T already exist in our DB."""

    messages = [{"role": "user", "content": task}]
    turns = 0

    while turns < 15:
        turns += 1
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            final = next((b.text for b in response.content if b.type == "text"), "")
            print(f"[Scanner] {final[:400]}")
            break

        if response.stop_reason == "tool_use":
            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                handler = TOOL_HANDLERS.get(block.name)
                if handler:
                    try:
                        result = handler(block.input)
                    except Exception as e:
                        result = f"Error: {e}"
                else:
                    result = f"Unknown tool: {block.name}"
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result
                })
            messages.append({"role": "user", "content": results})

    update_agent_state("scanner", "idle")
    print("[Scanner Agent] Done")


if __name__ == "__main__":
    main()
