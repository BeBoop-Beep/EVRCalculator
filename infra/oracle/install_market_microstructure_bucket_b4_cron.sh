#!/bin/bash
# Verify-first installer for the SHA-pinned Bucket B4 daily coordinator.
set -euo pipefail

SOURCE_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_REPO="${MARKET_B4_ENV_REPO:-/home/ubuntu/repos/EVRCalculator}"
STATE="${MARKET_B4_STATE_DIR:-/home/ubuntu/state/market_microstructure_b4}"
RUNTIME="$STATE/runtime"
PY="$ENV_REPO/.venv/bin/python"
HOLD="/home/ubuntu/state/db-safety/hold.json"
BEGIN="# BEGIN market-microstructure-b4 (managed)"
END="# END market-microstructure-b4 (managed)"

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
touch "$ENV_REPO/backend/logs/market_microstructure_b4.log"

set -a
. "$ENV_REPO/backend/.env"
set +a
export PYTHONPATH="$SOURCE_REPO"

echo "== B4 preflight from reviewed source (zero provider credits/writes)"
(cd "$SOURCE_REPO" && "$PY" -m backend.scripts.run_market_microstructure_bucket_b4   --preflight --credit-cap 55000)

echo "== lock preflight"
/usr/bin/flock -n /tmp/active-supply-panel.lock -c true || { echo "FAIL: active-supply lock held" >&2; exit 75; }
/usr/bin/flock -n /tmp/pokemon-scrape-dispatcher.lock -c true || { echo "FAIL: scrape dispatcher lock held" >&2; exit 75; }
/usr/bin/flock -n /tmp/pkmnprices-api.lock -c true || { echo "FAIL: PkmnPrices lock held" >&2; exit 75; }
/usr/bin/flock -n /tmp/pokemon-post-scrape-publication.lock -c true || { echo "FAIL: publication lock held" >&2; exit 75; }

current="$(crontab -l 2>/dev/null || true)"
outside="$(awk -v b="$BEGIN" -v e="$END" '$0==b{skip=1} !skip{print} $0==e{skip=0}' <<<"$current")"
if grep -v '^#' <<<"$outside" | grep -q 'run_market_microstructure_bucket_b4.sh'; then
  echo "FAIL: conflicting B4 schedule exists outside managed block" >&2
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
[ -f "$RUNTIME/infra/oracle/run_market_microstructure_bucket_b4.sh" ] || {
  echo "FAIL: pinned B4 runtime missing" >&2; exit 2;
}

export PYTHONPATH="$RUNTIME"
echo "== repeat B4 preflight from detached pinned runtime"
(cd "$RUNTIME" && "$PY" -m backend.scripts.run_market_microstructure_bucket_b4   --preflight --credit-cap 55000)

SRC="$RUNTIME/infra/oracle/market-microstructure-b4.crontab"
block="$(sed '/^CRON_TZ=/d' "$SRC")"
if ! grep -q '^CRON_TZ=America/Phoenix' <<<"$current"; then
  block="CRON_TZ=America/Phoenix"$'\n'"$block"
fi
new="$outside"$'\n'"$BEGIN"$'\n'"$block"$'\n'"$END"$'\n'

printf '%s\n' "$SHA" > "$STATE/release.sha.tmp"
chmod 600 "$STATE/release.sha.tmp"
mv "$STATE/release.sha.tmp" "$STATE/release.sha"
crontab - <<<"$new"
echo "BUCKET_B4_CRON_INSTALLED source_sha=$SHA runtime=$RUNTIME"
crontab -l | grep 'run_market_microstructure_bucket_b4.sh'
