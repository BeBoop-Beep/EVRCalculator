#!/bin/bash
# Continuous DB-pressure guard for scheduled FV-S3 forward outcomes.
set -euo pipefail
RUNTIME="${FV_SHADOW_RUNTIME:-/home/ubuntu/state/fair_value_shadow/runtime}"
ENV_REPO="${FV_SHADOW_ENV_REPO:-/home/ubuntu/repos/EVRCalculator}"
PY="$ENV_REPO/.venv/bin/python"
GUARD="/home/ubuntu/state/db-safety/db_workload_guard.py"
INNER="$RUNTIME/infra/oracle/run_fair_value_forward_outcomes.sh"
[ -x "$PY" ] || { echo "FV_FORWARD_PYTHON_MISSING" >&2; exit 2; }
[ -f "$GUARD" ] && [ ! -L "$GUARD" ] || { echo "FV_FORWARD_DB_GUARD_MISSING" >&2; exit 75; }
[ -x "$INNER" ] || { echo "FV_FORWARD_INNER_WRAPPER_MISSING" >&2; exit 2; }
ENCODED="$(printf '%s' "/bin/bash $INNER" | base64 -w0)"
exec "$PY" "$GUARD" --run-encoded "$ENCODED" --wait-lock-seconds 300
