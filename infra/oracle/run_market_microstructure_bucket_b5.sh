#!/bin/bash
# Bucket B5 targeted sold-history expansion. Core Panel is already complete.
set -euo pipefail

RUNTIME="${MARKET_B5_RUNTIME:-/home/ubuntu/state/market_microstructure_b5/runtime}"
ENV_REPO="${MARKET_B5_ENV_REPO:-/home/ubuntu/repos/EVRCalculator}"
STATE="${MARKET_B5_STATE_DIR:-/home/ubuntu/state/market_microstructure_b5}"
HOLD="/home/ubuntu/state/db-safety/hold.json"
PY="$ENV_REPO/.venv/bin/python"

[ ! -e "$HOLD" ] && [ ! -L "$HOLD" ] || { echo "BUCKET_B5_DB_SAFETY_HOLD"; exit 75; }
[ -r "$STATE/release.sha" ] || { echo "BUCKET_B5_RELEASE_PIN_MISSING" >&2; exit 2; }
[ -x "$PY" ] || { echo "BUCKET_B5_PYTHON_MISSING" >&2; exit 2; }

EXPECTED_SHA="$(tr -d '[:space:]' < "$STATE/release.sha")"
ACTUAL_SHA="$(git -C "$RUNTIME" rev-parse HEAD)"
[ "$EXPECTED_SHA" = "$ACTUAL_SHA" ] || {
  echo "BUCKET_B5_RELEASE_DRIFT_REFUSED expected=$EXPECTED_SHA actual=$ACTUAL_SHA" >&2
  exit 2
}

set -a
. "$ENV_REPO/backend/.env"
set +a
export PYTHONPATH="$RUNTIME"

exec 6>/tmp/active-supply-panel.lock
/usr/bin/flock -n 6 || { echo "BUCKET_B5_ACTIVE_SUPPLY_BUSY"; exit 75; }

/usr/bin/flock -n /tmp/pokemon-scrape-dispatcher.lock -c true || {
  echo "BUCKET_B5_SCRAPE_DISPATCHER_BUSY"; exit 75;
}

exec 8>/tmp/pkmnprices-api.lock
/usr/bin/flock -n 8 || { echo "BUCKET_B5_PROVIDER_BUSY"; exit 75; }

exec 9>/tmp/pokemon-post-scrape-publication.lock
/usr/bin/flock -n 9 || { echo "BUCKET_B5_HEAVY_PUBLISHER_BUSY"; exit 75; }

[ ! -e "$HOLD" ] && [ ! -L "$HOLD" ] || { echo "BUCKET_B5_DB_SAFETY_HOLD"; exit 75; }

cd "$RUNTIME"
exec "$PY" -m backend.scripts.run_market_microstructure_bucket_b5 --commit
