#!/bin/bash
# Research-only append of mature FV-S3 +1/+7/+30 forward outcomes.
set -euo pipefail

RUNTIME="${FV_SHADOW_RUNTIME:-/home/ubuntu/state/fair_value_shadow/runtime}"
ENV_REPO="${FV_SHADOW_ENV_REPO:-/home/ubuntu/repos/EVRCalculator}"
STATE="${FV_SHADOW_STATE_DIR:-/home/ubuntu/state/fair_value_shadow}"
HOLD="/home/ubuntu/state/db-safety/hold.json"
PY="$ENV_REPO/.venv/bin/python"

[ ! -e "$HOLD" ] && [ ! -L "$HOLD" ] || { echo "FV_FORWARD_DB_SAFETY_HOLD"; exit 75; }
[ -r "$STATE/release.sha" ] || { echo "FV_FORWARD_RELEASE_PIN_MISSING" >&2; exit 2; }
[ -x "$PY" ] || { echo "FV_FORWARD_PYTHON_MISSING" >&2; exit 2; }
EXPECTED_SHA="$(tr -d '[:space:]' < "$STATE/release.sha")"
ACTUAL_SHA="$(git -C "$RUNTIME" rev-parse HEAD)"
[ "$EXPECTED_SHA" = "$ACTUAL_SHA" ] || {
  echo "FV_FORWARD_RELEASE_DRIFT_REFUSED expected=$EXPECTED_SHA actual=$ACTUAL_SHA" >&2
  exit 2
}

set -a
. "$ENV_REPO/backend/.env"
set +a
export PYTHONPATH="$RUNTIME"

exec 7>/tmp/fv-forward-outcomes.lock
/usr/bin/flock -n 7 || { echo "FV_FORWARD_OUTCOMES_BUSY"; exit 75; }

/usr/bin/flock -n /tmp/pokemon-scrape-dispatcher.lock -c true || {
  echo "FV_FORWARD_SCRAPE_DISPATCHER_BUSY"; exit 75;
}

exec 9>/tmp/pokemon-post-scrape-publication.lock
/usr/bin/flock -n 9 || { echo "FV_FORWARD_HEAVY_PUBLISHER_BUSY"; exit 75; }

[ ! -e "$HOLD" ] && [ ! -L "$HOLD" ] || { echo "FV_FORWARD_DB_SAFETY_HOLD"; exit 75; }

cd "$RUNTIME"
exec "$PY" -m backend.scripts.run_index_fair_value_forward_outcomes_v1 --commit
