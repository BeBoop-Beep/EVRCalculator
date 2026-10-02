#!/bin/bash
# Verify-first installer for the SHA-pinned Core Panel daily increment runtime and cron.
set -euo pipefail

SOURCE_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_REPO="${CORE_PANEL_INCREMENT_ENV_REPO:-/home/ubuntu/repos/EVRCalculator}"
STATE="${CORE_PANEL_INCREMENT_STATE_DIR:-/home/ubuntu/state/core_panel_daily_increment}"
RUNTIME="$STATE/runtime"
PY="$ENV_REPO/.venv/bin/python"
HOLD="/home/ubuntu/state/db-safety/hold.json"
BEGIN="# BEGIN core-panel-daily-increment (managed)"
END="# END core-panel-daily-increment (managed)"

[ -x "$PY" ] || { echo "FAIL: shared Python runtime missing" >&2; exit 2; }
[ "$(timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone)" = "America/Phoenix" ] || {
  echo "FAIL: host timezone must be America/Phoenix" >&2; exit 2;
}
[ ! -e "$HOLD" ] && [ ! -L "$HOLD" ] || { echo "FAIL: database safety hold active" >&2; exit 75; }
git -C "$SOURCE_REPO" diff --quiet && git -C "$SOURCE_REPO" diff --cached --quiet || {
  echo "FAIL: reviewed source checkout dirty" >&2; exit 2;
}
grep -qx 'ACTIVATION_ENABLED = True' "$SOURCE_REPO/backend/scripts/run_core_panel_daily_increment.py" || {
  echo "FAIL: Core Panel increment is not activation-enabled in reviewed source" >&2; exit 2;
}

SHA="$(git -C "$SOURCE_REPO" rev-parse HEAD)"
git -C "$SOURCE_REPO" cat-file -e "$SHA^{commit}"
mkdir -p "$STATE" "$ENV_REPO/backend/logs"
touch "$ENV_REPO/backend/logs/core_panel_daily_increment.log"

set -a
. "$ENV_REPO/backend/.env"
set +a
export PYTHONPATH="$SOURCE_REPO"

echo "== Core Panel increment preflight from reviewed source (zero provider credits/writes)"
(cd "$SOURCE_REPO" && "$PY" -m backend.scripts.run_core_panel_daily_increment --preflight)

echo "== lock sanity =="
/usr/bin/flock -n /tmp/active-supply-panel.lock -c true || { echo "FAIL: active-supply lock held" >&2; exit 75; }
/usr/bin/flock -n /tmp/pkmnprices-api.lock -c true || { echo "FAIL: PkmnPrices lock held" >&2; exit 75; }
/usr/bin/flock -n /tmp/pokemon-post-scrape-publication.lock -c true || { echo "FAIL: publication lock held" >&2; exit 75; }

current="$(crontab -l 2>/dev/null || true)"
outside="$(awk -v b="$BEGIN" -v e="$END" '$0==b{skip=1} !skip{print} $0==e{skip=0}' <<<"$current")"
if grep -v '^#' <<<"$outside" | grep -q 'run_core_panel_daily_increment'; then
  echo "FAIL: conflicting Core Panel increment schedule exists outside managed block" >&2
  exit 2
fi

if [ "${1:-}" != "--apply" ]; then
  echo "VERIFY ONLY. source_sha=$SHA; runtime/crontab/pin unchanged"
  exit 0
fi

git -C "$SOURCE_REPO" worktree prune
if [ -e "$RUNTIME" ]; then
  git -C "$SOURCE_REPO" worktree remove --force "$RUNTIME" >/dev/null 2>&1 || rm -rf "$RUNTIME"
fi
git -C "$SOURCE_REPO" worktree add --detach "$RUNTIME" "$SHA"
[ "$(git -C "$RUNTIME" rev-parse HEAD)" = "$SHA" ] || {
  echo "FAIL: detached runtime SHA mismatch" >&2; exit 2;
}
[ -x "$RUNTIME/infra/oracle/run_core_panel_daily_increment.sh" ] || {
  echo "FAIL: pinned Core Panel increment wrapper missing/not executable" >&2; exit 2;
}
[ -x "$RUNTIME/infra/oracle/run_core_panel_daily_increment_guarded.sh" ] || {
  echo "FAIL: pinned Core Panel guarded wrapper missing/not executable" >&2; exit 2;
}

export PYTHONPATH="$RUNTIME"
echo "== repeat preflight from detached pinned runtime =="
(cd "$RUNTIME" && "$PY" -m backend.scripts.run_core_panel_daily_increment --preflight)

SRC="$RUNTIME/infra/oracle/core-panel-daily-increment.crontab"
block="$(sed '/^CRON_TZ=/d' "$SRC")"
if ! grep -q '^CRON_TZ=America/Phoenix' <<<"$current"; then
  block="CRON_TZ=America/Phoenix"$'\n'"$block"
fi
new="$outside"$'\n'"$BEGIN"$'\n'"$block"$'\n'"$END"$'\n'

printf '%s\n' "$SHA" > "$STATE/release.sha.tmp"
chmod 600 "$STATE/release.sha.tmp"
mv "$STATE/release.sha.tmp" "$STATE/release.sha"
crontab - <<<"$new"

echo "CORE_PANEL_INCREMENT_CRON_INSTALLED source_sha=$SHA runtime=$RUNTIME"
crontab -l | grep 'run_core_panel_daily_increment_guarded.sh'
