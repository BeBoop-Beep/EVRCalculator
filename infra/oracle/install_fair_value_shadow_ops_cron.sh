#!/bin/bash
# Verify-first installer for the SHA-pinned FV-S3 daily shadow runtime and schedules.
set -euo pipefail

SOURCE_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_REPO="${FV_SHADOW_ENV_REPO:-/home/ubuntu/repos/EVRCalculator}"
STATE="${FV_SHADOW_STATE_DIR:-/home/ubuntu/state/fair_value_shadow}"
RUNTIME="$STATE/runtime"
PY="$ENV_REPO/.venv/bin/python"
HOLD="/home/ubuntu/state/db-safety/hold.json"
BEGIN="# BEGIN fair-value-shadow-ops (managed)"
END="# END fair-value-shadow-ops (managed)"

[ -x "$PY" ] || { echo "FAIL: shared Python runtime missing" >&2; exit 2; }
[ "$(timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone)" = "America/Phoenix" ] || {
  echo "FAIL: host timezone must be America/Phoenix" >&2; exit 2;
}
[ ! -e "$HOLD" ] && [ ! -L "$HOLD" ] || { echo "FAIL: database safety hold active" >&2; exit 75; }
git -C "$SOURCE_REPO" diff --quiet && git -C "$SOURCE_REPO" diff --cached --quiet || {
  echo "FAIL: reviewed source checkout dirty" >&2; exit 2;
}
grep -qx 'WRITE_ENABLED = True' "$SOURCE_REPO/backend/scripts/index_fair_value_shadow_ledger_v1.py" || {
  echo "FAIL: FV shadow ledger writes are not enabled" >&2; exit 2;
}

SHA="$(git -C "$SOURCE_REPO" rev-parse HEAD)"
git -C "$SOURCE_REPO" cat-file -e "$SHA^{commit}"
mkdir -p "$STATE" "$ENV_REPO/backend/logs"
touch "$ENV_REPO/backend/logs/fair_value_shadow_daily.log" "$ENV_REPO/backend/logs/fair_value_forward_outcomes.log"

set -a
. "$ENV_REPO/backend/.env"
set +a
export PYTHONPATH="$SOURCE_REPO"

echo "== source syntax and dry-run verification =="
(cd "$SOURCE_REPO" && "$PY" -m py_compile \
  backend/scripts/run_index_fair_value_prospective_shadow_v1.py \
  backend/scripts/run_index_fair_value_forward_outcomes_v1.py)
bash -n "$SOURCE_REPO/infra/oracle/run_fair_value_shadow_daily.sh"
bash -n "$SOURCE_REPO/infra/oracle/run_fair_value_shadow_daily_guarded.sh"
bash -n "$SOURCE_REPO/infra/oracle/run_fair_value_forward_outcomes.sh"
bash -n "$SOURCE_REPO/infra/oracle/run_fair_value_forward_outcomes_guarded.sh"
(cd "$SOURCE_REPO" && "$PY" -m backend.scripts.run_index_fair_value_prospective_shadow_v1 \
  --dry-run --source-commit "$SHA")
(cd "$SOURCE_REPO" && "$PY" -m backend.scripts.run_index_fair_value_forward_outcomes_v1 --dry-run)

current="$(crontab -l 2>/dev/null || true)"
outside="$(awk -v b="$BEGIN" -v e="$END" '$0==b{skip=1} !skip{print} $0==e{skip=0}' <<<"$current")"
if grep -v '^#' <<<"$outside" | grep -Eq 'run_fair_value_(shadow_daily|forward_outcomes)'; then
  echo "FAIL: conflicting FV shadow schedule exists outside managed block" >&2
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
[ "$(git -C "$RUNTIME" rev-parse HEAD)" = "$SHA" ] || { echo "FAIL: detached runtime SHA mismatch" >&2; exit 2; }
for script in \
  run_fair_value_shadow_daily.sh run_fair_value_shadow_daily_guarded.sh \
  run_fair_value_forward_outcomes.sh run_fair_value_forward_outcomes_guarded.sh; do
  [ -x "$RUNTIME/infra/oracle/$script" ] || { echo "FAIL: runtime missing $script" >&2; exit 2; }
done

export PYTHONPATH="$RUNTIME"
echo "== detached runtime dry-run verification =="
(cd "$RUNTIME" && "$PY" -m backend.scripts.run_index_fair_value_prospective_shadow_v1 \
  --dry-run --source-commit "$SHA")
(cd "$RUNTIME" && "$PY" -m backend.scripts.run_index_fair_value_forward_outcomes_v1 --dry-run)

SRC="$RUNTIME/infra/oracle/fair-value-shadow-ops.crontab"
block="$(sed '/^CRON_TZ=/d' "$SRC")"
if ! grep -q '^CRON_TZ=America/Phoenix' <<<"$current"; then
  block="CRON_TZ=America/Phoenix"$'\n'"$block"
fi
new="$outside"$'\n'"$BEGIN"$'\n'"$block"$'\n'"$END"$'\n'

printf '%s\n' "$SHA" > "$STATE/release.sha.tmp"
chmod 600 "$STATE/release.sha.tmp"
mv "$STATE/release.sha.tmp" "$STATE/release.sha"
crontab - <<<"$new"

echo "FV_SHADOW_OPS_CRON_INSTALLED source_sha=$SHA runtime=$RUNTIME"
crontab -l | grep -E 'run_fair_value_(shadow_daily|forward_outcomes)_guarded.sh'
