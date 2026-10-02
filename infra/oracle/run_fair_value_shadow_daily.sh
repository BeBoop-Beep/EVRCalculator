#!/bin/bash
# Research-only daily FV-S3 prospective shadow publication at a deterministic local cutoff.
set -euo pipefail

RUNTIME="${FV_SHADOW_RUNTIME:-/home/ubuntu/state/fair_value_shadow/runtime}"
ENV_REPO="${FV_SHADOW_ENV_REPO:-/home/ubuntu/repos/EVRCalculator}"
STATE="${FV_SHADOW_STATE_DIR:-/home/ubuntu/state/fair_value_shadow}"
HOLD="/home/ubuntu/state/db-safety/hold.json"
PY="$ENV_REPO/.venv/bin/python"

[ ! -e "$HOLD" ] && [ ! -L "$HOLD" ] || { echo "FV_SHADOW_DB_SAFETY_HOLD"; exit 75; }
[ -r "$STATE/release.sha" ] || { echo "FV_SHADOW_RELEASE_PIN_MISSING" >&2; exit 2; }
[ -x "$PY" ] || { echo "FV_SHADOW_PYTHON_MISSING" >&2; exit 2; }

EXPECTED_SHA="$(tr -d '[:space:]' < "$STATE/release.sha")"
ACTUAL_SHA="$(git -C "$RUNTIME" rev-parse HEAD)"
[ "$EXPECTED_SHA" = "$ACTUAL_SHA" ] || {
  echo "FV_SHADOW_RELEASE_DRIFT_REFUSED expected=$EXPECTED_SHA actual=$ACTUAL_SHA" >&2
  exit 2
}

CUTOFF="$("$PY" - <<'PY'
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo
tz = ZoneInfo("America/Phoenix")
now = datetime.now(tz)
cutoff = datetime.combine(now.date(), time(18, 0), tzinfo=tz)
if now < cutoff:
    raise SystemExit(75)
print(cutoff.astimezone(timezone.utc).isoformat())
PY
)" || { echo "FV_SHADOW_FIXED_CUTOFF_NOT_REACHED"; exit 75; }

set -a
. "$ENV_REPO/backend/.env"
set +a
export PYTHONPATH="$RUNTIME"

exec 7>/tmp/fv-shadow-publisher.lock
/usr/bin/flock -n 7 || { echo "FV_SHADOW_PUBLISHER_BUSY"; exit 75; }

# Ensure no pre-cutoff PkmnPrices collector is still committing sold evidence.
exec 8>/tmp/pkmnprices-api.lock
/usr/bin/flock -n 8 || { echo "FV_SHADOW_PROVIDER_WRITER_BUSY"; exit 75; }

# Avoid competing with heavy canonical publication work.
exec 9>/tmp/pokemon-post-scrape-publication.lock
/usr/bin/flock -n 9 || { echo "FV_SHADOW_HEAVY_PUBLISHER_BUSY"; exit 75; }

[ ! -e "$HOLD" ] && [ ! -L "$HOLD" ] || { echo "FV_SHADOW_DB_SAFETY_HOLD"; exit 75; }

cd "$RUNTIME"
exec "$PY" -m backend.scripts.run_index_fair_value_prospective_shadow_v1 \
  --commit \
  --source-commit "$EXPECTED_SHA" \
  --information-cutoff "$CUTOFF"
