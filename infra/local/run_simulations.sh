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

if python backend/scripts/run_all_v2_sets.py >> logs/run_simulations.log 2>&1; then
  END_TIME=$(date '+%Y-%m-%d %H:%M:%S')

  notify_slack "✅ Simulation job completed
Host: $HOSTNAME_VALUE
Script: backend/scripts/run_all_v2_sets.py
Started: $START_TIME
Completed: $END_TIME
Log: logs/run_simulations.log"
else
  END_TIME=$(date '+%Y-%m-%d %H:%M:%S')

  notify_slack "❌ Simulation job FAILED
Host: $HOSTNAME_VALUE
Script: backend/scripts/run_all_v2_sets.py
Started: $START_TIME
Failed: $END_TIME
Log: logs/run_simulations.log"

  exit 1
fi