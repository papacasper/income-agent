#!/bin/bash
# Daemon — runs agents on schedule without Node.js/cron.
# Usage: bash scripts/daemon.sh &
cd "$(dirname "$0")/.."

PY=".venv/bin/python3"

echo "[Daemon] Starting at $(date)"
echo "[Daemon] Goal: \$20,000 in 60 days"

SCAN_INTERVAL=1800   # 30 min
BLOG_INTERVAL=14400  # 4 hours
SELL_INTERVAL=3600   # 1 hour

last_scan=0
last_blog=0
last_sell=0
blog_articles_today=0
last_blog_date=""

while true; do
    now=$(date +%s)
    today=$(date +%Y-%m-%d)

    # Reset daily blog count
    if [ "$today" != "$last_blog_date" ]; then
        blog_articles_today=0
        last_blog_date="$today"
    fi

    # Scanner: every 30 min
    if [ $((now - last_scan)) -ge $SCAN_INTERVAL ]; then
        echo "[Daemon] Running scanner at $(date)"
        $PY python/agents/scanner_agent.py 2>&1 | tail -5
        echo "[Daemon] Running content agent at $(date)"
        $PY python/agents/content_agent.py 2>&1 | tail -5
        last_scan=$now
    fi

    # Blog: every 4 hours, max 6 articles/day
    if [ $((now - last_blog)) -ge $BLOG_INTERVAL ] && [ $blog_articles_today -lt 6 ]; then
        echo "[Daemon] Writing 3 blog posts at $(date)"
        $PY python/agents/blog_agent.py --articles 3 2>&1 | tail -5
        blog_articles_today=$((blog_articles_today + 3))
        last_blog=$now
    fi

    # Sales: every hour
    if [ $((now - last_sell)) -ge $SELL_INTERVAL ]; then
        echo "[Daemon] Running sales agent at $(date)"
        $PY python/agents/sales_agent.py 2>&1 | tail -5
        $PY python/agents/analytics_agent.py 2>&1 | tail -3
        last_sell=$now
    fi

    sleep 60
done
