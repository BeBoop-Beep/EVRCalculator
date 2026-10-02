#!/bin/bash
# Managed Core Panel daily sold-increment collector for the research-only FV shadow feed.
# Runtime is detached and SHA-pinned by install_core_panel_daily_increment_cron.sh.
# Lock and DB-safety-hold ordering is intentionally identical to run_market_microstructure_bucket_b5.sh.
# Core Panel daily increment (frozen 207-card panel; never restarts backfill).
set -euo pipefail

RUNTIME="${CORE_PANEL_INCREMENT_RUNTIME:-/home/ubuntu/state/core_panel_daily_increment/runtime}"
ENV_REPO="${CORE_PANEL_INCREMENT_ENV_REPO:-/home/ubuntu/repos/EVRCalculator}"
STATE="${CORE_PANEL_INCREMENT_STATE_DIR:-/home/ubuntu/state/core_panel_daily_increment}"
HOLD="/home/ubuntu/state/db-safety/hold.json"
PY="$ENV_REPO/.venv/bin/python"

[ ! -e "$HOLD" ] && [ ! -L "$HOLD" ] || { echo "CORE_PANEL_INCREMENT_DB_SAFETY_HOLD"; exit 75; }
[ -r "$STATE/release.sha" ] || { echo "CORE_PANEL_INCREMENT_RELEASE_PIN_MISSING" >&2; exit 2; }
[ -x "$PY" ] || { echo "CORE_PANEL_INCREMENT_PYTHON_MISSING" >&2; exit 2; }

EXPECTED_SHA="$(tr -d '[:space:]' < "$STATE/release.sha")"
ACTUAL_SHA="$(git -C "$RUNTIME" rev-parse HEAD)"
[ "$EXPECTED_SHA" = "$ACTUAL_SHA" ] || {
  echo "CORE_PANEL_INCREMENT_RELEASE_DRIFT_REFUSED expected=$EXPECTED_SHA actual=$ACTUAL_SHA" >&2
  exit 2
}

set -a
. "$ENV_REPO/backend/.env"
set +a
export PYTHONPATH="$RUNTIME"

exec 6>/tmp/active-supply-panel.lock
/usr/bin/flock -n 6 || { echo "CORE_PANEL_INCREMENT_ACTIVE_SUPPLY_BUSY"; exit 75; }

/usr/bin/flock -n /tmp/pokemon-scrape-dispatcher.lock -c true || {
  echo "CORE_PANEL_INCREMENT_SCRAPE_DISPATCHER_BUSY"; exit 75;
}

exec 8>/tmp/pkmnprices-api.lock
/usr/bin/flock -n 8 || { echo "CORE_PANEL_INCREMENT_PROVIDER_BUSY"; exit 75; }

exec 9>/tmp/pokemon-post-scrape-publication.lock
/usr/bin/flock -n 9 || { echo "CORE_PANEL_INCREMENT_HEAVY_PUBLISHER_BUSY"; exit 75; }

[ ! -e "$HOLD" ] && [ ! -L "$HOLD" ] || { echo "CORE_PANEL_INCREMENT_DB_SAFETY_HOLD"; exit 75; }

cd "$RUNTIME"
exec "$PY" -m backend.scripts.run_core_panel_daily_increment --commit
