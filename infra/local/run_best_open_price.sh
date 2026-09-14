#!/bin/bash
set -euo pipefail

export PYTHONIOENCODING=utf-8
REPO_DIR="${EVR_PRODUCTION_REPO_DIR:-/d/EVRCalculator}"

if [ ! -d "$REPO_DIR" ]; then
  echo "[best-open] REFUSED: repository directory does not exist: $REPO_DIR" >&2
  exit 2
fi
cd "$REPO_DIR"
mkdir -p logs

if [ ! -f backend/.venv/Scripts/activate ]; then
  echo "[best-open] REFUSED: no virtual environment at $REPO_DIR/backend/.venv" >&2
  exit 2
fi
source backend/.venv/Scripts/activate

# backend/.env is dotenv syntax, not shell syntax. Parse it exactly as the
# parent publication wrapper does and preserve environment variables supplied
# by Task Scheduler/the parent process.
if [ -f backend/.env ]; then
  ENV_EXPORTS="$(
    python - <<'PY'
import os
import re
import shlex
import sys
from dotenv import dotenv_values

try:
    values = dotenv_values("backend/.env")
except Exception as exc:
    print(f"[best-open] unable to parse backend/.env: {type(exc).__name__}: {exc}", file=sys.stderr)
    raise SystemExit(2)

for key, value in values.items():
    if value is None or key in os.environ:
        continue
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
        print(f"[best-open] invalid environment variable name: {key!r}", file=sys.stderr)
        raise SystemExit(2)
    print(f"export {key}={shlex.quote(value)}")
PY
  )" || {
    EXIT_CODE=$?
    echo "[best-open] REFUSED: unable to load backend/.env" >&2
    exit "${EXIT_CODE:-2}"
  }
  eval "$ENV_EXPORTS"
  unset ENV_EXPORTS
fi

notify_slack() {
  if [ -z "${SLACK_WEBHOOK_URL:-}" ]; then
    return 0
  fi
  local message="$1"
  # Alert transport is observability, not publication authority. A Slack
  # outage must never turn a successful/accurately-reported DB publication
  # into a failed scheduler result.
  python - "$message" <<'PY' | curl -sS -X POST -H 'Content-type: application/json' --data @- "$SLACK_WEBHOOK_URL" >/dev/null || true
import json
import sys
print(json.dumps({"text": sys.argv[1]}))
PY
}

REPORT=$(mktemp logs/best_open_price_invocation.XXXXXX.json)
trap 'rm -f "$REPORT"' EXIT
LATEST_REPORT="logs/best_open_price_publication.json"
LOG="logs/best_open_price_publication.log"
STARTED=$(date '+%Y-%m-%d %H:%M:%S')
HEAD_SHA=$(git rev-parse HEAD 2>/dev/null || true)
BRANCH=$(git symbolic-ref --short -q HEAD || true)

# Never let an import/startup failure accidentally inherit yesterday's green
# JSON report and send a false success notification.
rm -f "$REPORT"

# Exact recurring preparation can take roughly an hour on the validated 138-SKU
# cohort. The Python wrapper owns the single-run lock, exact source binding,
# source-drift check and atomic publication. This shell only supplies the daily
# scheduler/environment boundary and propagates its verdict.
RUN_EXIT=0
set +e
python -m backend.scripts.publish_best_open_price_if_ready \
  --commit \
  --quantity-batch-size 24 \
  --json-report "$REPORT" \
  2>&1 | tee -a "$LOG"
RUN_EXIT=${PIPESTATUS[0]}
set -e

STATUS=$(python - "$REPORT" <<'PY'
import json, sys
try:
    print(json.load(open(sys.argv[1], encoding="utf-8")).get("status", "REPORT_UNREADABLE"))
except Exception:
    print("REPORT_UNREADABLE")
PY
)
DETAIL=$(python - "$REPORT" <<'PY'
import json, sys
try:
    r=json.load(open(sys.argv[1], encoding="utf-8"))
    print("status=%s market_date=%s source=%s snapshot=%s resolved=%s unresolved=%s runtime_s=%s" % (
        r.get("status"), r.get("sourceMarketDate"), r.get("sourceBudgetSnapshotId"),
        r.get("bestOpenSnapshotId"), r.get("resolvedCount"), r.get("unresolvedCount"),
        r.get("engineRuntimeSeconds")))
except Exception as exc:
    print("report_error=%s" % exc)
PY
)

echo "[best-open] $DETAIL" | tee -a "$LOG"

# A previous report can never provide this invocation's verdict. Also require
# agreement between the process exit and the structured status before green.
if [ "$RUN_EXIT" -eq 0 ]; then
  case "$STATUS" in
    PUBLISHED|ALREADY_CURRENT) ;;
    *) RUN_EXIT=1 ;;
  esac
fi
if [ "$RUN_EXIT" -ne 0 ] && { [ "$STATUS" = "PUBLISHED" ] || [ "$STATUS" = "ALREADY_CURRENT" ]; }; then
  STATUS="PROCESS_FAILED_AFTER_REPORT"
fi
if [ -s "$REPORT" ]; then
  cp "$REPORT" "$LATEST_REPORT"
fi

case "$STATUS" in
  PUBLISHED)
    notify_slack "✅ Best-Open Price publication completed
Host: $(hostname)
Branch: ${BRANCH:-detached}
Commit: ${HEAD_SHA:-unknown}
Started: $STARTED
$DETAIL
Log: $LOG"
    ;;
  ALREADY_CURRENT)
    # Normal no-op: today's Budget Ranking source already has a complete
    # prepared Best-Open publication. Avoid a daily green-noise notification.
    ;;
  *)
    notify_slack "❌ Best-Open Price publication failed or was blocked
Host: $(hostname)
Branch: ${BRANCH:-detached}
Commit: ${HEAD_SHA:-unknown}
Started: $STARTED
Exit: $RUN_EXIT
$DETAIL
Log: $LOG"
    ;;
esac

exit "$RUN_EXIT"