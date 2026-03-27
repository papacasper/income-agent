#!/usr/bin/env python3
"""
Sales Agent — Polar.sh edition (full API, no dashboard required).
Creates products, syncs orders, tracks revenue.
"""
import sys
import os
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv()

import anthropic
from python.shared.db import (
    read_messages, post_message, update_agent_state, get_conn
)
import python.tools.polar as polar

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-haiku-4-5"  # Simple copywriting + API calls, Haiku is plenty

SYSTEM_PROMPT = """You are a digital product sales agent using the Polar.sh platform.

Your job: Take products from the database, write optimized listings, and publish them via the API.

Listing principles:
- Title: outcome-first, keyword-rich (e.g. "50 ChatGPT Prompts for Freelancers — Save 10h/week")
- Description: transformation → what's included → call to action
- Price: $9 simple packs | $17-27 solid guides | $47+ comprehensive kits
- Every product must look professional and solve a specific problem

Work through all pending products efficiently."""

TOOLS = [
    {
        "name": "get_pending_products",
        "description": "Get products ready to list (file created, not yet published)",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "publish_product",
        "description": "Publish a product to Lemon Squeezy and save the result",
        "input_schema": {
            "type": "object",
            "properties": {
                "db_product_id": {"type": "number", "description": "Internal DB product ID"},
                "title": {"type": "string", "description": "SEO-optimized product title"},
                "description": {"type": "string", "description": "Full sales description (markdown OK)"},
                "price_cents": {"type": "number", "description": "Price in cents (1700 = $17.00)"},
                "file_path": {"type": "string", "description": "Path to product file (optional)"}
            },
            "required": ["db_product_id", "title", "description", "price_cents"]
        }
    },
    {
        "name": "sync_orders",
        "description": "Pull latest orders from Polar and sync revenue to the database",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_store_info",
        "description": "Get Polar organization products and current listings",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_revenue_summary",
        "description": "Get total revenue and order count from Polar",
        "input_schema": {"type": "object", "properties": {}}
    }
]


def handle_tool(name: str, tool_input: dict) -> str:
    if name == "get_pending_products":
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT p.id, p.title, p.description, p.price, p.file_path,
                       o.type as opp_type, o.description as opp_desc
                FROM products p
                JOIN opportunities o ON p.opportunity_id = o.id
                WHERE p.status = 'draft'
                ORDER BY p.created_at ASC
                LIMIT 10
            """).fetchall()
        return json.dumps([dict(r) for r in rows], default=str)

    elif name == "publish_product":
        db_id = int(tool_input["db_product_id"])
        title = tool_input["title"]
        description = tool_input["description"]
        price_cents = int(tool_input["price_cents"])

        # Get file path from DB if not provided
        file_path = tool_input.get("file_path")
        if not file_path:
            with get_conn() as conn:
                row = conn.execute("SELECT file_path FROM products WHERE id = ?", (db_id,)).fetchone()
                if row:
                    file_path = row["file_path"]

        try:
            result = polar.launch_product(
                name=title,
                description=description,
                price_cents=price_cents,
                file_path=file_path if file_path and Path(file_path).exists() else None,
            )

            with get_conn() as conn:
                conn.execute("""
                    UPDATE products
                    SET status = 'listed',
                        platform_id = ?,
                        platform_url = ?,
                        title = ?,
                        description = ?,
                        price = ?
                    WHERE id = ?
                """, (
                    result["id"],
                    result["checkout_url"],
                    title,
                    description,
                    price_cents / 100,
                    db_id
                ))
                conn.execute("""
                    UPDATE opportunities SET status = 'listed'
                    WHERE id = (SELECT opportunity_id FROM products WHERE id = ?)
                """, (db_id,))

            print(f"[Sales] Published on Polar: {result['checkout_url']}")
            post_message("sales", "finance", "event", {
                "event": "product_listed",
                "productId": db_id,
                "url": result["checkout_url"],
                "price": price_cents / 100,
                "platform": "polar"
            })
            return json.dumps({"success": True, **result})

        except Exception as e:
            print(f"[Sales] Publish failed for #{db_id}: {e}")
            return json.dumps({"success": False, "error": str(e)})

    elif name == "sync_orders":
        try:
            summary = polar.get_revenue_summary()
            orders = summary["orders"]

            with get_conn() as conn:
                for order in orders:
                    existing = conn.execute(
                        "SELECT id FROM transactions WHERE transaction_id = ?",
                        (order["id"],)
                    ).fetchone()

                    if not existing:
                        amount = order["amount"] / 100
                        fee = amount * 0.04 + 0.40  # 4% + 40¢ Polar fee
                        net = amount - fee
                        conn.execute("""
                            INSERT INTO transactions
                                (product_id, amount, fee, net, type, description, platform, transaction_id, occurred_at)
                            VALUES (NULL, ?, ?, ?, 'sale', ?, 'polar', ?, ?)
                        """, (amount, fee, net, order["product_name"], order["id"], order["created_at"]))

            return json.dumps({
                "synced": len(orders),
                "gross": summary["gross_revenue_usd"],
                "net": summary["net_revenue_usd"]
            })
        except Exception as e:
            return json.dumps({"error": str(e)})

    elif name == "get_store_info":
        try:
            products = polar.list_products()
            return json.dumps({"platform": "polar.sh", "products": products})
        except Exception as e:
            return json.dumps({"error": str(e)})

    elif name == "get_revenue_summary":
        try:
            return json.dumps(polar.get_revenue_summary())
        except Exception as e:
            return json.dumps({"error": str(e)})

    return f"Unknown tool: {name}"


def main():
    sync_only = "--sync-only" in sys.argv
    update_agent_state("sales", "running")
    print(f"[Sales Agent] Starting at {datetime.now()}")

    if sync_only:
        print("[Sales] Sync-only mode")
        result = handle_tool("sync_orders", {})
        print(f"[Sales] {result}")
        update_agent_state("sales", "idle")
        return

    task = """
    Get all pending products and publish them to Lemon Squeezy:

    1. Check store info (confirm API is working)
    2. Get pending products from the database
    3. For each product, write an optimized listing and publish it
    4. Sync the latest orders
    5. Report total products listed and current revenue

    Be efficient. Publish everything that's ready.
    """

    messages = [{"role": "user", "content": task}]
    turns = 0

    while turns < 20:
        turns += 1
        response = client.messages.create(
            model=MODEL,
            max_tokens=8192,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            final = next((b.text for b in response.content if b.type == "text"), "")
            print(f"[Sales] {final[:600]}")
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

    update_agent_state("sales", "idle")
    print("[Sales Agent] Done")


if __name__ == "__main__":
    main()
