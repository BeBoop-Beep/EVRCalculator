#!/usr/bin/env bash
#
# Bounded recovery for an isolated global Market / Explorer date divergence.
# Selected only after market.freshness proves core pricing/publication authorities
# are current and the remaining lag is limited to Raw / Explore Set Value / Explorer V2.

set -euo pipefail

HOLD="/home/ubuntu/state/db-safety/hold.json"
if [[ -e "$HOLD" || -L "$HOLD" ]]; then
  printf '[market-divergence-repair] production_database_safety_hold_active\n'
  exit 75
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-${REPO_ROOT}/.venv/bin/python}"
DB_GUARD="/home/ubuntu/state/db-safety/db_workload_guard.py"

if [[ -f "$DB_GUARD" && "${INDEX_MARKET_DIVERGENCE_REPAIR_GUARDED:-0}" != "1" ]]; then
  ENCODED="$("${PYTHON_BIN}" - "$0" "$@" <<'GUARD_PY'
import base64, shlex, sys
print(base64.b64encode(shlex.join(['bash', *sys.argv[1:]]).encode()).decode())
GUARD_PY
)"
  export INDEX_MARKET_DIVERGENCE_REPAIR_GUARDED=1
  exec "${PYTHON_BIN}" "$DB_GUARD" --wait-lock-seconds 120 --run-encoded "$ENCODED"
fi

MARKET_DATE="${1:-}"
if [[ ! "$MARKET_DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  printf '[market-divergence-repair] invalid market date: %s\n' "$MARKET_DATE"
  exit 1
fi

LOCK_PATH="${POST_SCRAPE_PUBLICATION_LOCK_PATH:-/tmp/pokemon-post-scrape-publication.lock}"
if ! command -v flock >/dev/null 2>&1; then
  printf '[market-divergence-repair] flock unavailable; refusing unlocked repair\n'
  exit 1
fi
exec {LOCK_FD}>"${LOCK_PATH}"
if ! flock -n "${LOCK_FD}"; then
  printf '[market-divergence-repair] canonical publication already running; safe no-op\n'
  exit 4
fi

cd "$REPO_ROOT"

printf '[market-divergence-repair] target=%s stage=global_market\n' "$MARKET_DATE"
"${PYTHON_BIN}" backend/scripts/build_pokemon_explore_set_value_snapshot.py \
  --commit \
  --market-date "$MARKET_DATE"

printf '[market-divergence-repair] target=%s stage=explorer_v2\n' "$MARKET_DATE"
"${PYTHON_BIN}" -m backend.scripts.run_market_explorer_daily_publication \
  --commit \
  --market-date "$MARKET_DATE"

printf '[market-divergence-repair] target=%s status=complete\n' "$MARKET_DATE"
