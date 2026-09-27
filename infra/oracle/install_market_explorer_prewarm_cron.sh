#!/bin/bash
# Idempotently install the bounded Market Explorer maintained-cache schedule.
# Default is verify-only; --apply mutates only this managed crontab block.
set -euo pipefail

REPO="${REPO:-/home/ubuntu/repos/EVRCalculator}"
SRC="$REPO/infra/oracle/market-explorer-prewarm.crontab"
BEGIN="# BEGIN market-explorer-prewarm (managed by install_market_explorer_prewarm_cron.sh)"
END="# END market-explorer-prewarm"

test -d "$REPO/.git" || { echo "FAIL: repo missing at $REPO" >&2; exit 1; }
test -f "$SRC" || { echo "FAIL: schedule source missing" >&2; exit 1; }
test -f "$REPO/backend/scripts/run_market_explorer_maintained_cache_prewarm.py" || {
  echo "FAIL: maintained-cache worker missing" >&2; exit 1;
}
test -f "$REPO/backend/scripts/run_market_explorer_convergence.py" || {
  echo "FAIL: bounded convergence coordinator missing" >&2; exit 1;
}
test -f "$REPO/backend/scripts/check_market_explorer_maintained_cache_health.py" || {
  echo "FAIL: maintained-cache health checker missing" >&2; exit 1;
}
test -f "$REPO/infra/oracle/run_market_explorer_prewarm_guarded.sh" || {
  echo "FAIL: guarded wrapper missing" >&2; exit 1;
}
[ "$(timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone)" = "America/Phoenix" ] || {
  echo "FAIL: host timezone must be America/Phoenix" >&2; exit 1;
}

mkdir -p "$REPO/backend/logs"
touch "$REPO/backend/logs/market_explorer_prewarm.log" "$REPO/backend/logs/market_explorer_health.log"

echo "== runtime credential presence (values suppressed) =="
(cd "$REPO" && "$REPO/.venv/bin/python" - <<'PY'
import os
from backend.db.clients import supabase_client  # loads backend/.env
required = ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "DATABASE_URL")
missing = [key for key in required if not os.getenv(key)]
print("required_runtime_credentials_present=" + str(not missing).lower())
if missing:
    print("missing_runtime_credentials=" + ",".join(missing))
    raise SystemExit(4)
PY
)

echo "== bounded convergence dry run (no writes) =="
(cd "$REPO" && timeout 300 "$REPO/.venv/bin/python" -m backend.scripts.run_market_explorer_convergence --dry-run >/tmp/market-explorer-prewarm-install-dry-run.json)
echo "dry_run_exit=0"

current="$(crontab -l 2>/dev/null || true)"
block="$(sed '/^CRON_TZ=/d' "$SRC")"
if ! grep -q '^CRON_TZ=America/Phoenix' <<<"$current"; then
  block="CRON_TZ=America/Phoenix"$'\n'"$block"
fi

new="$(awk -v b="$BEGIN" -v e="$END" '
  $0==b {skip=1; next}
  $0==e {skip=0; next}
  !skip {print}
' <<<"$current")"
new="$new"$'\n'"$BEGIN"$'\n'"$block"$'\n'"$END"$'\n'

if [ "${1:-}" != "--apply" ]; then
  echo "VERIFY ONLY. Re-run with --apply to install."
  printf '%s\n' "$new" | grep -E 'market-explorer-prewarm|market_explorer_maintained_cache|check_market_explorer_maintained_cache_health' || true
  exit 0
fi

crontab - <<<"$new"

echo "== installed proof =="
installed="$(crontab -l)"
printf 'managed_blocks='
grep -cFx "$BEGIN" <<<"$installed"
printf 'prewarm_entries='
grep -v '^[[:space:]]*#' <<<"$installed" | grep -c 'run_market_explorer_prewarm_guarded.sh'
printf 'health_entries='
grep -v '^[[:space:]]*#' <<<"$installed" | grep -c 'check_market_explorer_maintained_cache_health'
echo "MARKET_EXPLORER_PREWARM_CRON_INSTALLED=PASS"
