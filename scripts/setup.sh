#!/bin/bash
set -e
cd "$(dirname "$0")/.."

echo "=== Income Agent Setup ==="

echo "Creating Python venv..."
python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
echo "Python deps installed."

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Commands (run from /home/casper/income-agent):"
echo "  python3 python/agents/blog_agent.py --articles 3     # Write 3 blog posts"
echo "  python3 python/agents/content_agent.py               # Create digital products"
echo "  python3 python/agents/sales_agent.py                 # List on LemonSqueezy"
echo "  python3 python/agents/analytics_agent.py             # Run analytics"
echo ""
echo "  Note: uses .venv — run:  source .venv/bin/activate"
