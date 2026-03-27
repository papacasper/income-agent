#!/usr/bin/env python3
"""
Content Creation Agent
Creates actual sellable digital products from opportunities in the database.
Products: PDF guides, Notion templates, prompt packs, Excel templates, etc.
"""
import sys
import os
import json
import re
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv()

import anthropic
from python.shared.db import (
    read_messages, post_message, get_opportunity, save_product,
    update_agent_state, get_pending_opportunities
)

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-sonnet-4-6"  # Strong writer, 60% cheaper than Opus
OUTPUT_DIR = Path("./data/products")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SYSTEM_PROMPT = """You are an expert digital product creator. Your job is to create high-quality,
sellable digital products using AI.

You create:
- PDF guides and ebooks (using markdown that gets converted to PDF)
- Notion template descriptions and structures
- Prompt packs (collections of high-value AI prompts)
- Excel/spreadsheet template descriptions
- Canva template briefs

Quality standards:
- Every product must provide REAL value — not just filler content
- Products should solve a specific, painful problem
- Include actionable frameworks, templates, checklists
- Professional presentation

Output format: Always return structured JSON with the product content."""

CONTENT_TOOLS = [
    {
        "name": "save_product_file",
        "description": "Save the created product content to a file",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Filename with extension (.md, .json, .txt)"},
                "content": {"type": "string", "description": "Full product content"},
                "product_type": {"type": "string", "enum": ["pdf_guide", "prompt_pack", "notion_template", "spreadsheet_template", "swipe_file"]},
                "title": {"type": "string"},
                "description": {"type": "string", "description": "Sales description for listing"},
                "price_usd": {"type": "number", "description": "Recommended price in USD"},
                "opportunity_id": {"type": "number"}
            },
            "required": ["filename", "content", "product_type", "title", "description", "price_usd", "opportunity_id"]
        }
    }
]


def save_product_file(args: dict) -> str:
    """Save product content to disk and database."""
    filename = args["filename"]
    # Sanitize filename
    filename = re.sub(r'[^a-zA-Z0-9_.-]', '_', filename)
    filepath = OUTPUT_DIR / filename

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(args["content"])

    product_id = save_product(
        opportunity_id=int(args["opportunity_id"]),
        title=args["title"],
        description=args["description"],
        price=float(args["price_usd"]),
        platform="gumroad",
        file_path=str(filepath)
    )

    post_message("content", "sales", "task", {
        "task": "list_product",
        "productId": product_id,
        "title": args["title"],
        "description": args["description"],
        "price": int(args["price_usd"] * 100),  # Convert to cents for Gumroad
        "filePath": str(filepath)
    })

    print(f"[Content] Created product #{product_id}: {args['title']} at ${args['price_usd']}")
    return f"Saved product #{product_id} at {filepath}"


TOOL_HANDLERS = {"save_product_file": save_product_file}


def create_product(opportunity: dict) -> str:
    """Run the content agent to create a product for an opportunity."""
    opp_type = opportunity.get("type", "digital_product")
    title = opportunity.get("title", "")
    description = opportunity.get("description", "")
    metadata = opportunity.get("metadata", {}) or {}
    opp_id = opportunity["id"]

    task = f"""Create a high-quality, sellable digital product for this opportunity:

Opportunity ID: {opp_id}
Type: {opp_type}
Title: {title}
Description: {description}
Metadata: {json.dumps(metadata, indent=2)}

Instructions:
1. Create a COMPLETE, FULL product — not an outline, not a placeholder
2. The product should be immediately usable and genuinely valuable
3. For prompt packs: include 25 actual, tested prompts with explanations (quality over quantity)
4. For PDF guides: write the FULL content (1500-3000 words)
5. For Notion templates: provide complete structure + instructions
6. Write a compelling sales description (for Gumroad listing)
7. Set an optimal price ($9-$47 range for first products)
8. Save the product using the save_product_file tool

The product MUST:
- Solve a real problem
- Be easy to use immediately
- Look professional
- Be worth the price asked

Create the full product now."""

    messages = [{"role": "user", "content": task}]

    turns = 0
    while turns < 15:
        turns += 1

        for attempt in range(4):
            try:
                with client.messages.stream(
                    model=MODEL,
                    max_tokens=32000,
                    thinking={"type": "adaptive"},
                    system=SYSTEM_PROMPT,
                    tools=CONTENT_TOOLS,
                    messages=messages
                ) as stream:
                    response = stream.get_final_message()
                break
            except anthropic.APIStatusError as e:
                if e.status_code == 529 and attempt < 3:
                    import time
                    wait = 30 * (2 ** attempt)
                    print(f"[Content] API overloaded, retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    raise

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            return next((b.text for b in response.content if b.type == "text"), "Done")

        # If we hit token limit mid-tool-call, send empty results and let model recover
        if response.stop_reason == "max_tokens":
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
            if tool_use_blocks:
                messages.append({"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": b.id,
                     "content": "Output truncated — please write a shorter version and call the tool again."}
                    for b in tool_use_blocks
                ]})
                continue
            return "Done (max tokens)"

        if response.stop_reason == "tool_use":
            tool_results = []
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

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result
                })

            messages.append({"role": "user", "content": tool_results})
            continue

        break

    return "Content creation complete"


def main():
    update_agent_state("content", "running")
    print(f"[Content Agent] Starting at {datetime.now()}")

    # Process messages from scanner
    messages = read_messages("content")
    processed = 0

    for msg in messages:
        if msg["type"] == "task" and msg["payload"].get("task") == "create_product":
            opp_id = msg["payload"].get("opportunityId")
            if opp_id:
                opp = get_opportunity(opp_id)
                if opp and opp.get("status") == "pending":
                    print(f"[Content] Creating product for opportunity #{opp_id}: {opp['title']}")
                    try:
                        result = create_product(opp)
                        print(f"[Content] Done: {result[:200]}")
                        processed += 1
                    except Exception as e:
                        print(f"[Content] Error: {e}")

    # Also pick up any pending opportunities that weren't messaged
    if processed == 0:
        pending = get_pending_opportunities()
        for opp in pending[:3]:  # Max 3 per run to control costs
            print(f"[Content] Creating product for opportunity #{opp['id']}: {opp['title']}")
            try:
                result = create_product(opp)
                print(f"[Content] Done: {result[:200]}")
                processed += 1
            except Exception as e:
                print(f"[Content] Error: {e}")

    print(f"[Content Agent] Processed {processed} opportunities")
    update_agent_state("content", "idle")


if __name__ == "__main__":
    main()
