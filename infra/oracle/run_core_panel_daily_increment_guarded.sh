#!/bin/bash
# Outer safety wrapper for scheduled Core Panel daily increment runs.
# The shared DB workload guard monitors Supabase memory continuously and stops the child
# if live pressure crosses the production admission threshold.
set -euo pipefail

RUNTIME="${CORE_PANEL_INCREMENT_RUNTIME:-/home/ubuntu/state/core_panel_daily_increment/runtime}"
ENV_REPO="${CORE_PANEL_INCREMENT_ENV_REPO:-/home/ubuntu/repos/EVRCalculator}"
PY="$ENV_REPO/.venv/bin/python"
GUARD="/home/ubuntu/state/db-safety/db_workload_guard.py"
INNER="$RUNTIME/infra/oracle/run_core_panel_daily_increment.sh"

[ -x "$PY" ] || { echo "CORE_PANEL_INCREMENT_PYTHON_MISSING" >&2; exit 2; }
[ -f "$GUARD" ] && [ ! -L "$GUARD" ] || { echo "CORE_PANEL_INCREMENT_DB_GUARD_MISSING" >&2; exit 75; }
[ -x "$INNER" ] || { echo "CORE_PANEL_INCREMENT_INNER_WRAPPER_MISSING" >&2; exit 2; }

COMMAND="/bin/bash $INNER"
ENCODED="$(printf '%s' "$COMMAND" | base64 -w0)"
exec "$PY" "$GUARD" --run-encoded "$ENCODED" --wait-lock-seconds 300
