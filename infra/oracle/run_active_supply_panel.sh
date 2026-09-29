#!/bin/bash
# Fail-closed runtime for one exact Core Panel V1 observation date.
set -euo pipefail

RUNTIME="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_REPO="${ACTIVE_SUPPLY_ENV_REPO:-/home/ubuntu/repos/EVRCalculator}"
STATE="${ACTIVE_SUPPLY_STATE_DIR:-/home/ubuntu/state/active_supply_panel}"
HOLD="/home/ubuntu/state/db-safety/hold.json"
PIN="$STATE/release.sha"
PY="$ENV_REPO/.venv/bin/python"

[ ! -e "$HOLD" ] && [ ! -L "$HOLD" ] || { echo "ACTIVE_SUPPLY_DB_SAFETY_HOLD"; exit 75; }
[ -r "$PIN" ] || { echo "ACTIVE_SUPPLY_RELEASE_PIN_MISSING" >&2; exit 2; }
[ -x "$PY" ] || { echo "ACTIVE_SUPPLY_PYTHON_MISSING" >&2; exit 2; }
EXPECTED_SHA="$(tr -d '[:space:]' < "$PIN")"
ACTUAL_SHA="$(git -C "$RUNTIME" rev-parse HEAD)"
[ "$EXPECTED_SHA" = "$ACTUAL_SHA" ] || {
  echo "ACTIVE_SUPPLY_RELEASE_DRIFT_REFUSED expected=$EXPECTED_SHA actual=$ACTUAL_SHA" >&2
  exit 2
}

set -a
. "$ENV_REPO/backend/.env"
set +a
export PYTHONPATH="$RUNTIME"

exec 8>/tmp/active-supply-panel.lock
/usr/bin/flock -n 8 || { echo "ACTIVE_SUPPLY_PANEL_ALREADY_RUNNING"; exit 75; }
exec 9>/tmp/pkmnprices-api.lock
/usr/bin/flock -n 9 || { echo "ACTIVE_SUPPLY_PROVIDER_BUSY"; exit 75; }
exec 7>/tmp/pokemon-post-scrape-publication.lock
/usr/bin/flock -n 7 || { echo "ACTIVE_SUPPLY_HEAVY_PUBLISHER_BUSY"; exit 75; }
[ ! -e "$HOLD" ] && [ ! -L "$HOLD" ] || { echo "ACTIVE_SUPPLY_DB_SAFETY_HOLD"; exit 75; }

cd "$RUNTIME"
"$PY" -m backend.scripts.preflight_market_active_supply_panel --source-commit-sha "$EXPECTED_SHA"
exec "$PY" -m backend.scripts.run_market_active_supply_snapshot \
  --full-panel --source-commit-sha "$EXPECTED_SHA"
