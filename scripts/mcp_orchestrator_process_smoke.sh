#!/usr/bin/env bash
set -euo pipefail

ORCH_URL="${1:-http://127.0.0.1:8010}"
QUERY="${2:-perovskite solar cell stability}"

echo "==> list_processed_papers"
LIST_JSON="$(curl -sS -X POST "${ORCH_URL}/process-paper" \
  -H "Content-Type: application/json" \
  -d '{"action":"list_processed_papers"}')"
echo "${LIST_JSON}" | python -m json.tool

SLUG="$(python - <<'PY'
import json,sys
obj=json.loads(sys.stdin.read())
res=obj.get("result",{})
papers=[]
if isinstance(res,dict):
    papers=res.get("papers",[]) or res.get("processed_papers",[]) or []
slug=""
if papers and isinstance(papers[0],dict):
    slug=papers[0].get("paper_slug") or papers[0].get("slug") or ""
print(slug)
PY
<<< "${LIST_JSON}")"

if [[ -n "${SLUG}" ]]; then
  echo "==> get_saved_paper_output (paper_slug=${SLUG})"
  curl -sS -X POST "${ORCH_URL}/process-paper" \
    -H "Content-Type: application/json" \
    -d "{
      \"action\": \"get_saved_paper_output\",
      \"paper_slug\": \"${SLUG}\"
    }" | python -m json.tool
else
  echo "No processed paper slug found; running a small process_batch to create one..."
  BATCH_JSON="$(curl -sS -X POST "${ORCH_URL}/process-paper" \
    -H "Content-Type: application/json" \
    -d "{
      \"action\": \"process_batch\",
      \"query\": \"${QUERY}\",
      \"year_min\": 2021,
      \"year_max\": 2026,
      \"max_papers\": 1,
      \"run_mode\": \"resume\",
      \"force_reprocess\": false,
      \"reset_output\": false
    }")"
  echo "${BATCH_JSON}" | python -m json.tool

  echo "==> list_processed_papers (post-batch)"
  curl -sS -X POST "${ORCH_URL}/process-paper" \
    -H "Content-Type: application/json" \
    -d '{"action":"list_processed_papers"}' | python -m json.tool
fi

echo "Done."
