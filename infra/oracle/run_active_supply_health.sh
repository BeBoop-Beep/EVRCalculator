#!/bin/bash
# SHA-pinned health/missing-run materializer for the Phoenix expected date.
set -euo pipefail

RUNTIME="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_REPO="${ACTIVE_SUPPLY_ENV_REPO:-/home/ubuntu/repos/EVRCalculator}"
STATE="${ACTIVE_SUPPLY_STATE_DIR:-/home/ubuntu/state/active_supply_panel}"
HOLD="/home/ubuntu/state/db-safety/hold.json"
PY="$ENV_REPO/.venv/bin/python"

[ ! -e "$HOLD" ] && [ ! -L "$HOLD" ] || { echo "ACTIVE_SUPPLY_DB_SAFETY_HOLD"; exit 75; }
[ -r "$STATE/release.sha" ] || { echo "ACTIVE_SUPPLY_RELEASE_PIN_MISSING" >&2; exit 2; }
[ -x "$PY" ] || { echo "ACTIVE_SUPPLY_PYTHON_MISSING" >&2; exit 2; }
EXPECTED_SHA="$(tr -d '[:space:]' < "$STATE/release.sha")"
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
exec 7>/tmp/pokemon-post-scrape-publication.lock
/usr/bin/flock -n 7 || { echo "ACTIVE_SUPPLY_HEAVY_PUBLISHER_BUSY"; exit 75; }
cd "$RUNTIME"
exec "$PY" -m backend.scripts.check_market_active_supply_health \
  --expected-date "$(TZ=America/Phoenix date +%F)" --record-missing
