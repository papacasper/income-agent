#!/bin/bash
# Full blitz — runs all agents hard from day 1.
# Run this once to bootstrap, then let the daemon take over.
cd "$(dirname "$0")/.."

PY=".venv/bin/python3"

echo "========================================"
echo "  PAPACASPER INCOME BLITZ"
echo "  Goal: \$20,000 | Days remaining: 59"
echo "========================================"

echo ""
echo ">>> [1/4] Market scan..."
$PY python/agents/scanner_agent.py

echo ""
echo ">>> [2/4] Creating digital products from opportunities..."
$PY python/agents/content_agent.py

echo ""
echo ">>> [3/4] Writing 6 blog posts (affiliate + product traffic)..."
$PY python/agents/blog_agent.py --articles 6

echo ""
echo ">>> [4/5] Listing products on Polar.sh..."
$PY python/agents/sales_agent.py

echo ""
echo ""
echo ">>> [5/5] Financial report..."
$PY python/agents/analytics_agent.py

echo ""
echo "========================================"
echo "  BLITZ COMPLETE"
echo "  Check blog.papacasper.com for new posts"
echo "  Deploy CF worker: cd cloudflare/worker && wrangler deploy"
echo "========================================"
