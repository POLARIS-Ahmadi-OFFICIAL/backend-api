#!/usr/bin/env bash
set -euo pipefail

ORCH_URL="${1:-http://127.0.0.1:8010}"
QUERY="${2:-perovskite solar cell stability}"

echo "==> Health"
curl -sS "${ORCH_URL}/health" | python -m json.tool

echo "==> MCP Tools"
curl -sS "${ORCH_URL}/tools" | python -m json.tool

echo "==> Search Papers (hybrid)"
curl -sS -X POST "${ORCH_URL}/search-papers" \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"${QUERY}\",
    \"year_min\": 2021,
    \"year_max\": 2026,
    \"max_candidates\": 5,
    \"source_mode\": \"hybrid\"
  }" | python -m json.tool

echo "==> Propose Hypothesis (history-gated)"
curl -sS -X POST "${ORCH_URL}/propose-hypothesis" \
  -H "Content-Type: application/json" \
  -d '{
    "hypothesis_text": "Use additive engineering for improved perovskite stability under humidity stress.",
    "material_hint": "FA/Cs perovskite",
    "source": "smoke-test",
    "record_if_allowed": false
  }' | python -m json.tool

echo "Done."
