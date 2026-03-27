#!/bin/bash
# Quick run script
cd "$(dirname "$0")/.."
source .env 2>/dev/null || true
npx ts-node src/orchestrator.ts "$@"
