# Income Agent

Autonomous multi-agent system for digital product creation and sales. Uses Claude AI agents to scan markets, create products, publish blog content, list on sales platforms, and track revenue.

## Architecture

- **Orchestrator** (TypeScript) coordinates all agents
  - **Scanner Agent** - market research via Brave Search
  - **Content Agent** - creates digital products (prompt packs, guides, templates)
  - **Sales Agent** - lists products on Polar.sh
  - **Blog Agent** - writes SEO articles to Ghost CMS
  - **Analytics Agent** - tracks performance and recommends strategy
  - **Finance Agent** - revenue tracking and goal progress

All agents communicate through a shared SQLite database with a message queue pattern.

## Stack

- **TypeScript** – orchestrator, scanner, finance agents
- **Python** – content, sales, blog, analytics agents
- **SQLite** – shared state, message passing, transaction tracking
- **Cloudflare Worker** – free AI prompt generator tool (lead gen)
- **Integrations** – Polar.sh, Ghost CMS, Brave Search, Google Indexing, Amazon Associates

## Setup

```bash
# Install dependencies
bun install
bash scripts/setup.sh   # creates Python venv

# Configure
cp .env.example .env
# Edit .env with your API keys

# Run once (all agents)
bash scripts/blitz.sh

# Run as daemon
bash scripts/daemon.sh &

# Dashboard
python3 dashboard.py
# Open http://localhost:8888
```

## Commands

```bash
# Individual agents
.venv/bin/python3 python/agents/scanner_agent.py
.venv/bin/python3 python/agents/content_agent.py
.venv/bin/python3 python/agents/sales_agent.py
.venv/bin/python3 python/agents/blog_agent.py --articles 3
.venv/bin/python3 python/agents/analytics_agent.py

# TypeScript orchestrator
bun run dev          # single run
bun run orchestrate  # daemon mode
```

## Cloudflare Worker

The worker at `cloudflare/worker/` serves a free AI prompt generator that captures emails and upsells premium products.

```bash
cd cloudflare/worker
wrangler deploy
wrangler secret put GHOST_ADMIN_KEY
wrangler secret put ANTHROPIC_API_KEY
```
