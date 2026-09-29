#!/bin/bash
# Verify-first installer for the reviewed, SHA-pinned Core Panel V1 VM schedule.
set -euo pipefail

SOURCE_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_REPO="${ACTIVE_SUPPLY_ENV_REPO:-/home/ubuntu/repos/EVRCalculator}"
STATE="${ACTIVE_SUPPLY_STATE_DIR:-/home/ubuntu/state/active_supply_panel}"
RUNTIME="$STATE/runtime"
PY="$ENV_REPO/.venv/bin/python"
HOLD="/home/ubuntu/state/db-safety/hold.json"
BEGIN="# BEGIN active-supply-panel (managed by install_active_supply_panel_cron.sh)"
END="# END active-supply-panel"

[ -x "$PY" ] || { echo "FAIL: shared Python runtime missing" >&2; exit 2; }
[ "$(timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone)" = "America/Phoenix" ] || {
  echo "FAIL: host timezone must be America/Phoenix" >&2; exit 2;
}
[ ! -e "$HOLD" ] && [ ! -L "$HOLD" ] || { echo "FAIL: database safety hold active" >&2; exit 75; }
git -C "$SOURCE_REPO" diff --quiet && git -C "$SOURCE_REPO" diff --cached --quiet || {
  echo "FAIL: reviewed source checkout dirty" >&2; exit 2;
}
SHA="$(git -C "$SOURCE_REPO" rev-parse HEAD)"
git -C "$SOURCE_REPO" cat-file -e "$SHA^{commit}"
mkdir -p "$STATE" "$ENV_REPO/backend/logs"
touch "$ENV_REPO/backend/logs/active_supply_panel.log" "$ENV_REPO/backend/logs/active_supply_panel_health.log"

set -a
. "$ENV_REPO/backend/.env"
set +a
export PYTHONPATH="$SOURCE_REPO"
export ACTIVE_SUPPLY_ENV_REPO="$ENV_REPO"

echo "== full 207-card activation preflight from reviewed source (zero provider credits/writes)"
(cd "$SOURCE_REPO" && "$PY" -m backend.scripts.preflight_market_active_supply_panel --source-commit-sha "$SHA")
echo "== lock preflight"
/usr/bin/flock -n /tmp/active-supply-panel.lock -c true || { echo "FAIL: panel lock held" >&2; exit 75; }
/usr/bin/flock -n /tmp/pkmnprices-api.lock -c true || { echo "FAIL: shared PkmnPrices lock held" >&2; exit 75; }
/usr/bin/flock -n /tmp/pokemon-post-scrape-publication.lock -c true || { echo "FAIL: heavy publisher lock held" >&2; exit 75; }

current="$(crontab -l 2>/dev/null || true)"
outside="$(awk -v b="$BEGIN" -v e="$END" '$0==b{skip=1} !skip{print} $0==e{skip=0}' <<<"$current")"
if awk '$1 !~ /^#/ && (($1=="10" && $2=="21") || ($1=="40" && $2=="21") || ($1=="10" && $2=="22")) {print}' <<<"$outside" | grep -q .; then
  echo "FAIL: conflicting 21:10/21:40/22:10 schedule exists outside managed block" >&2
  exit 2
fi

if [ "${1:-}" != "--apply" ]; then
  echo "VERIFY ONLY. source_sha=$SHA; detached runtime/crontab/pin unchanged"
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
[ -x "$RUNTIME/infra/oracle/run_active_supply_panel.sh" ] || {
  echo "FAIL: pinned panel runtime missing/not executable" >&2; exit 2;
}
[ -x "$RUNTIME/infra/oracle/run_active_supply_health.sh" ] || {
  echo "FAIL: pinned health runtime missing/not executable" >&2; exit 2;
}

export PYTHONPATH="$RUNTIME"
echo "== repeat preflight from detached pinned runtime"
(cd "$RUNTIME" && "$PY" -m backend.scripts.preflight_market_active_supply_panel --source-commit-sha "$SHA")

SRC="$RUNTIME/infra/oracle/active-supply-panel.crontab"
block="$(sed '/^CRON_TZ=/d' "$SRC")"
if ! grep -q '^CRON_TZ=America/Phoenix' <<<"$current"; then
  block="CRON_TZ=America/Phoenix"$'\n'"$block"
fi
new="$outside"$'\n'"$BEGIN"$'\n'"$block"$'\n'"$END"$'\n'

printf '%s\n' "$SHA" > "$STATE/release.sha.tmp"
chmod 600 "$STATE/release.sha.tmp"
mv "$STATE/release.sha.tmp" "$STATE/release.sha"
crontab - <<<"$new"
echo "ACTIVE_SUPPLY_PANEL_CRON_INSTALLED source_sha=$SHA runtime=$RUNTIME env_repo=$ENV_REPO"
crontab -l | grep -E 'run_active_supply_panel|run_active_supply_health'
