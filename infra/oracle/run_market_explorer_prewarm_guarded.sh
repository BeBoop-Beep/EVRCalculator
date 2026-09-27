#!/usr/bin/env bash
# One bounded Market Explorer V2 convergence advancement under the production
# DB workload guard. The coordinator advances only one logical stage per process
# (small card batch, one-day sealed/rarity authority, one maintained cache, or
# final atomic promotion); this wrapper deliberately does not loop.
set -euo pipefail

REPO="${REPO:-/home/ubuntu/repos/EVRCalculator}"
PY="${PYTHON_BIN:-$REPO/.venv/bin/python}"
DB_GUARD="/home/ubuntu/state/db-safety/db_workload_guard.py"
HOLD="/home/ubuntu/state/db-safety/hold.json"

cd "$REPO"
test -x "$PY"

if [[ -e "$HOLD" || -L "$HOLD" ]]; then
  echo "[market-explorer-prewarm] production_database_safety_hold_active; deferred"
  exit 75
fi

if [[ -f "$DB_GUARD" && "${INDEX_MARKET_EXPLORER_PREWARM_GUARDED:-0}" != "1" ]]; then
  ENCODED="$("$PY" - "$0" <<'PY'
import base64, shlex, sys
print(base64.b64encode(shlex.join(["bash", sys.argv[1]]).encode()).decode())
PY
)"
  export INDEX_MARKET_EXPLORER_PREWARM_GUARDED=1
  exec "$PY" "$DB_GUARD" --wait-lock-seconds 120 --run-encoded "$ENCODED"
fi

exec "$PY" -m backend.scripts.run_market_explorer_convergence \
  --commit \
  --card-set-batch 8
