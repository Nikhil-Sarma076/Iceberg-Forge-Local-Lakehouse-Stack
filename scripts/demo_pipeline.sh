#!/usr/bin/env bash
#
# Iceberg Forge — End-to-End Demo Pipeline
# ==========================================
# Exercises all major features against the running Docker stack.
# Prerequisites: docker compose up --build -d
#
# Usage:
#   chmod +x scripts/demo_pipeline.sh
#   ./scripts/demo_pipeline.sh
#

set -euo pipefail

API="http://localhost:8000"
GREEN='\033[0;32m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

pass() { echo -e "  ${GREEN}✓ $1${NC}"; }
fail() { echo -e "  ${RED}✗ $1${NC}"; exit 1; }
step() { echo -e "\n${CYAN}▶ $1${NC}"; }

# ---------------------------------------------------------------------------
step "1. Health Check"
# ---------------------------------------------------------------------------
STATUS=$(curl -s "$API/health" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
[ "$STATUS" = "ok" ] && pass "Service healthy" || fail "Health check failed"

# ---------------------------------------------------------------------------
step "2. Create Table (synchronous, no partitions)"
# ---------------------------------------------------------------------------
CREATE_RES=$(curl -s -X POST "$API/v1/tables" \
  -H "Content-Type: application/json" \
  -d '{"name": "demo_sales", "file": "sales.csv"}')
RECORDS=$(echo "$CREATE_RES" | python3 -c "import sys,json; print(json.load(sys.stdin)['total_records'])")
[ "$RECORDS" -gt 0 ] && pass "Created demo_sales with $RECORDS records" || fail "Table creation failed"

# ---------------------------------------------------------------------------
step "3. Append Data"
# ---------------------------------------------------------------------------
APPEND_RES=$(curl -s -X POST "$API/v1/tables/demo_sales/append" \
  -H "Content-Type: application/json" \
  -d '{"file": "orders_append.csv"}')
NEW_RECORDS=$(echo "$APPEND_RES" | python3 -c "import sys,json; print(json.load(sys.stdin)['total_records'])")
[ "$NEW_RECORDS" -gt "$RECORDS" ] && pass "Appended data, now $NEW_RECORDS records" || fail "Append failed"

# ---------------------------------------------------------------------------
step "4. Schema Evolution — Add Column"
# ---------------------------------------------------------------------------
EVOLVE_RES=$(curl -s -X POST "$API/v1/tables/demo_sales/evolve-schema" \
  -H "Content-Type: application/json" \
  -d '{"add_columns": [{"name": "discount_pct", "type": "double", "doc": "Applied discount"}]}')
HAS_COL=$(echo "$EVOLVE_RES" | python3 -c "
import sys,json
fields = json.load(sys.stdin)['schema_fields']
print('yes' if any(f['name'] == 'discount_pct' for f in fields) else 'no')
")
[ "$HAS_COL" = "yes" ] && pass "Added discount_pct column" || fail "Schema evolution failed"

# ---------------------------------------------------------------------------
step "5. List Snapshots"
# ---------------------------------------------------------------------------
SNAPS=$(curl -s "$API/v1/tables/demo_sales/snapshots")
SNAP_COUNT=$(echo "$SNAPS" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
[ "$SNAP_COUNT" -ge 2 ] && pass "$SNAP_COUNT snapshots recorded" || fail "Expected >=2 snapshots"

# ---------------------------------------------------------------------------
step "6. Compact Table"
# ---------------------------------------------------------------------------
COMPACT_RES=$(curl -s -X POST "$API/v1/tables/demo_sales/compact")
FILES_BEFORE=$(echo "$COMPACT_RES" | python3 -c "import sys,json; print(json.load(sys.stdin)['files_before'])")
FILES_AFTER=$(echo "$COMPACT_RES" | python3 -c "import sys,json; print(json.load(sys.stdin)['files_after'])")
pass "Compacted: $FILES_BEFORE files → $FILES_AFTER file(s)"

# ---------------------------------------------------------------------------
step "7. Expire Snapshots"
# ---------------------------------------------------------------------------
EXPIRE_RES=$(curl -s -X POST "$API/v1/tables/demo_sales/expire-snapshots" \
  -H "Content-Type: application/json" \
  -d '{"older_than_days": 1}')
REMAINING=$(echo "$EXPIRE_RES" | python3 -c "import sys,json; print(json.load(sys.stdin)['remaining_count'])")
pass "Expire complete, $REMAINING snapshot(s) remaining"

# ---------------------------------------------------------------------------
step "8. Create Partitioned Table (async job queue)"
# ---------------------------------------------------------------------------
JOB_RES=$(curl -s -X POST "$API/v1/jobs/ingest" \
  -H "Content-Type: application/json" \
  -d '{"name": "demo_products", "file": "products.csv"}')
JOB_ID=$(echo "$JOB_RES" | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
pass "Job submitted: $JOB_ID"

# Poll until terminal state
for i in $(seq 1 20); do
  sleep 1
  JOB_STATUS=$(curl -s "$API/v1/jobs/$JOB_ID" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
  if [ "$JOB_STATUS" = "COMPLETED" ]; then
    pass "Job completed successfully"
    break
  elif [ "$JOB_STATUS" = "FAILED" ]; then
    ERROR=$(curl -s "$API/v1/jobs/$JOB_ID" | python3 -c "import sys,json; print(json.load(sys.stdin).get('error','unknown'))")
    fail "Job failed: $ERROR"
  fi
done
[ "$JOB_STATUS" = "COMPLETED" ] || fail "Job timed out in status: $JOB_STATUS"

# Verify table exists
TABLE_RES=$(curl -s "$API/v1/tables/demo_products")
PROD_RECORDS=$(echo "$TABLE_RES" | python3 -c "import sys,json; print(json.load(sys.stdin)['total_records'])")
[ "$PROD_RECORDS" -gt 0 ] && pass "Table demo_products has $PROD_RECORDS records" || fail "Table empty"

# ---------------------------------------------------------------------------
step "9. List Jobs"
# ---------------------------------------------------------------------------
JOBS_COUNT=$(curl -s "$API/v1/jobs" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
[ "$JOBS_COUNT" -ge 1 ] && pass "$JOBS_COUNT job(s) in queue history" || fail "Job list empty"

# ---------------------------------------------------------------------------
step "10. Query via Trino"
# ---------------------------------------------------------------------------
QUERY_RES=$(curl -s -X POST "$API/v1/query" \
  -H "Content-Type: application/json" \
  -d '{"query": "SELECT COUNT(*) as cnt FROM iceberg.default.demo_sales"}' 2>/dev/null || echo "TRINO_UNAVAILABLE")

if [ "$QUERY_RES" = "TRINO_UNAVAILABLE" ]; then
  echo -e "  ${CYAN}⚠ Trino query skipped (Trino may still be starting)${NC}"
else
  ROW_COUNT=$(echo "$QUERY_RES" | python3 -c "import sys,json; print(json.load(sys.stdin)['row_count'])")
  pass "Trino returned $ROW_COUNT row(s)"
fi

# ---------------------------------------------------------------------------
step "11. Cleanup"
# ---------------------------------------------------------------------------
curl -s -X DELETE "$API/v1/tables/demo_sales" > /dev/null
curl -s -X DELETE "$API/v1/tables/demo_products" > /dev/null
pass "Cleaned up demo tables"

# ---------------------------------------------------------------------------
echo -e "\n${GREEN}═══════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Demo pipeline completed successfully!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════${NC}\n"
