#!/usr/bin/env python3
"""
Blog Agent — writes SEO articles to blog.papacasper.com.

Revenue model:
  - Amazon Associates / affiliate links embedded in articles
  - Drives traffic to Polar.sh digital products
  - Display ads via traffic volume (future)

Strategy: 3-5 articles/day targeting low-competition, high-intent keywords.
Each article pings Google Indexing API for fast crawl.
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
from python.shared.db import update_agent_state, post_message, get_conn, save_market_insight
from python.tools.ghost import publish_article

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-haiku-4-5"  # Fast and cheap for SEO article generation
# NOTE: thinking must NOT be used with tool_use — causes "final block cannot be thinking" crash

AMAZON_TAG = "papacasper0c-20"

SYSTEM_PROMPT = f"""You are an expert SEO content writer and affiliate marketer.

You write articles for blog.papacasper.com that:
1. Target low-competition, high-purchase-intent keywords
2. Include relevant affiliate links using Amazon tag: {AMAZON_TAG}
3. Are genuinely useful — not thin filler content
4. Naturally link to our digital products on Polar.sh (use get_our_products to get live checkout URLs)

Amazon link format: https://www.amazon.com/dp/ASIN?tag={AMAZON_TAG}&ref=blog.papacasper.com
Always add this disclosure near the top of every article:
<p><em>This post contains affiliate links. If you purchase through these links, PapaCasper earns a small commission at no extra cost to you.</em></p>

Article types that convert best:
- "Best X tools for Y" (comparison → Amazon affiliate links)
- "How to do X with AI" (tutorial → product upsell + Amazon tools)
- "X templates for Y" (leads to our template products)
- "X vs Y" (comparison → affiliate commissions)

Format: Return clean HTML suitable for Ghost CMS.
Always include: title, meta_description, tags, full HTML body.
Target length: 1200-2000 words for SEO value."""

TOOLS = [
    {
        "name": "search_keywords",
        "description": "Search for low-competition, high-intent keywords to target",
        "input_schema": {
            "type": "object",
            "properties": {
                "niche": {"type": "string", "description": "Topic niche to find keywords for"}
            },
            "required": ["niche"]
        }
    },
    {
        "name": "get_existing_posts",
        "description": "Get recently published posts to avoid duplicates",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_our_products",
        "description": "Get our published Polar.sh products with live checkout URLs to link to in articles",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "publish_article",
        "description": "Publish a completed article to Ghost CMS with Google Indexing ping",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "html": {"type": "string", "description": "Full article HTML content"},
                "meta_description": {"type": "string", "description": "155-char SEO description"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "5-8 relevant tags"},
            },
            "required": ["title", "html", "meta_description", "tags"]
        }
    }
]


def handle_tool(name: str, tool_input: dict) -> str:
    if name == "search_keywords":
        import requests
        niche = tool_input["niche"]
        key = os.getenv("BRAVE_API_KEY")
        if not key:
            return json.dumps({"error": "BRAVE_API_KEY not set"})
        try:
            r = requests.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={"Accept": "application/json", "X-Subscription-Token": key},
                params={"q": f"{niche} how to guide best tools", "count": 10},
                timeout=10
            )
            results = r.json().get("web", {}).get("results", [])
            keywords = [{"title": r["title"], "url": r["url"], "snippet": r.get("description", "")} for r in results]
            return json.dumps(keywords)
        except Exception as e:
            return json.dumps({"error": str(e)})

    elif name == "get_existing_posts":
        try:
            from python.tools.ghost import list_posts
            posts = list_posts(limit=20)
            return json.dumps([{"title": p["title"], "url": p.get("url", "")} for p in posts])
        except Exception as e:
            return json.dumps({"error": str(e)})

    elif name == "get_our_products":
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT title, platform_url, price, description
                FROM products WHERE status = 'listed'
            """).fetchall()
        return json.dumps([dict(r) for r in rows])

    elif name == "publish_article":
        title = tool_input["title"]
        html = tool_input["html"]
        meta_desc = tool_input.get("meta_description", "")
        tags = tool_input.get("tags", [])

        try:
            post = publish_article(
                title=title,
                html=html,
                tags=tags,
                meta_description=meta_desc,
                ping_google=True,
            )

            # Track in DB
            with get_conn() as conn:
                conn.execute("""
                    INSERT INTO agent_messages (from_agent, to_agent, type, payload)
                    VALUES ('blog', NULL, 'published', ?)
                """, (json.dumps({"title": title, "url": post.get("url"), "tags": tags}),))

            print(f"[Blog] Published: {post.get('url')}")
            return json.dumps({"success": True, **post})

        except Exception as e:
            print(f"[Blog] Publish failed: {e}")
            return json.dumps({"success": False, "error": str(e)})

    return f"Unknown tool: {name}"


def run_blog_session(num_articles: int = 3) -> str:
    """Write and publish N articles."""
    update_agent_state("blog", "running")

    # Get what topics we should cover (from analytics/market insights)
    with get_conn() as conn:
        insights = conn.execute("""
            SELECT title, data FROM market_insights
            WHERE category IN ('trend', 'niche')
            ORDER BY score DESC, created_at DESC
            LIMIT 10
        """).fetchall()

    insight_context = ""
    if insights:
        insight_context = "\n\nMarket insights to consider:\n" + "\n".join(
            f"- {r['title']}" for r in insights
        )

    task = f"""
    Write and publish {num_articles} high-quality SEO articles for blog.papacasper.com.

    Focus niches (pick the best opportunities):
    - AI tools and prompts for specific jobs/tasks
    - Notion templates and productivity systems
    - Making money online with AI
    - Automation for freelancers and small businesses
    - Digital product creation guides
    {insight_context}

    For each article:
    1. Search for keywords in the niche to understand what's ranking
    2. Check existing posts to avoid duplicates
    3. Get our products to naturally link to them
    4. Write a COMPLETE article (1200-2000 words) with:
       - Keyword-optimized title
       - Proper H2/H3 structure
       - Real, useful information
       - 2-3 affiliate/product links where natural
       - Strong call to action
    5. Publish it immediately

    Write all {num_articles} articles before stopping. Go now.
    """

    messages = [{"role": "user", "content": task}]
    turns = 0

    while turns < 30:
        turns += 1
        for attempt in range(4):
            try:
                response = client.messages.create(
                    model=MODEL,
                    max_tokens=16000,
                    system=SYSTEM_PROMPT,
                    tools=TOOLS,
                    messages=messages
                )
                break
            except anthropic.APIStatusError as e:
                if e.status_code == 529 and attempt < 3:
                    wait = 30 * (2 ** attempt)
                    print(f"[Blog] API overloaded, retrying in {wait}s...")
                    import time; time.sleep(wait)
                else:
                    raise

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            result = next((b.text for b in response.content if b.type == "text"), "")
            print(f"[Blog] Session complete: {result[:300]}")
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

    update_agent_state("blog", "idle")
    return "Blog session complete"


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--articles", type=int, default=3, help="Number of articles to write")
    args = parser.parse_args()

    print(f"[Blog Agent] Writing {args.articles} articles to {os.getenv('GHOST_API_URL')}")
    run_blog_session(args.articles)


if __name__ == "__main__":
    main()
