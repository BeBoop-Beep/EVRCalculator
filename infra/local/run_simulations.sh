#!/bin/bash
set -euo pipefail

export PYTHONIOENCODING=utf-8

cd /d/EVRCalculator

if [ -f backend/.env ]; then
  set -a
  source backend/.env
  set +a
fi

source .venv/Scripts/activate
mkdir -p logs

notify_slack() {
  if [ -n "${SLACK_WEBHOOK_URL:-}" ]; then
    local message="$1"

    python - "$message" <<'PY' | curl -sS -X POST -H 'Content-type: application/json' --data @- "$SLACK_WEBHOOK_URL" >/dev/null
import json
import sys

print(json.dumps({"text": sys.argv[1]}))
PY

  else
    echo "SLACK_WEBHOOK_URL is not set; skipping Slack notification."
  fi
}

HOSTNAME_VALUE=$(hostname)
START_TIME=$(date '+%Y-%m-%d %H:%M:%S')

notify_slack "🚀 Simulation job started
Host: $HOSTNAME_VALUE
Script: backend/scripts/run_all_v2_sets.py
Started: $START_TIME
Log: logs/run_simulations.log"

SIMULATIONS_FAILED=0
if python backend/scripts/run_all_v2_sets.py >> logs/run_simulations.log 2>&1; then
  END_TIME=$(date '+%Y-%m-%d %H:%M:%S')

  notify_slack "✅ Simulation job completed
Host: $HOSTNAME_VALUE
Script: backend/scripts/run_all_v2_sets.py
Started: $START_TIME
Completed: $END_TIME
Log: logs/run_simulations.log"
else
  SIMULATIONS_FAILED=1
  END_TIME=$(date '+%Y-%m-%d %H:%M:%S')

  notify_slack "❌ Simulation job FAILED
Host: $HOSTNAME_VALUE
Script: backend/scripts/run_all_v2_sets.py
Started: $START_TIME
Failed: $END_TIME
Log: logs/run_simulations.log"
fi

# Public snapshots (market dashboards, explore rankings, set pages) are
# materialized read models — they only reflect today's simulations after this
# refresh runs. It must run AFTER the simulation batch, and it runs even when
# the batch partially failed so the sets that did complete still surface fresh
# Performance vs Cost history instead of a stale flatline. --strict makes the
# job exit nonzero (and Slack-alert) if any set page snapshot is still older
# than its simulation/market dependencies afterward.
REFRESH_START_TIME=$(date '+%Y-%m-%d %H:%M:%S')
REFRESH_FAILED=0
if python backend/scripts/refresh_stale_public_snapshots.py --commit --strict >> logs/refresh_public_snapshots.log 2>&1; then
  REFRESH_END_TIME=$(date '+%Y-%m-%d %H:%M:%S')

  notify_slack "✅ Public snapshot refresh completed
Host: $HOSTNAME_VALUE
Script: backend/scripts/refresh_stale_public_snapshots.py --commit --strict
Started: $REFRESH_START_TIME
Completed: $REFRESH_END_TIME
Log: logs/refresh_public_snapshots.log"
else
  REFRESH_FAILED=1
  REFRESH_END_TIME=$(date '+%Y-%m-%d %H:%M:%S')

  notify_slack "❌ Public snapshot refresh FAILED (stale snapshots may remain)
Host: $HOSTNAME_VALUE
Script: backend/scripts/refresh_stale_public_snapshots.py --commit --strict
Started: $REFRESH_START_TIME
Failed: $REFRESH_END_TIME
Log: logs/refresh_public_snapshots.log"
fi

if [ "$SIMULATIONS_FAILED" -ne 0 ] || [ "$REFRESH_FAILED" -ne 0 ]; then
  exit 1
fi