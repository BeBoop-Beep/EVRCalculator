#!/bin/bash
# Idempotently install Sentinel runtime schedules without touching other cron blocks.
set -euo pipefail
REPO="${REPO:-/home/ubuntu/repos/EVRCalculator}"
SRC="$REPO/infra/oracle/sentinel.crontab"
BEGIN="# BEGIN sentinel-runtime (managed by install_sentinel_cron.sh)"
END="# END sentinel-runtime"

test -d "$REPO/.git" || { echo "FAIL: repo missing" >&2; exit 1; }
test -x "$REPO/.venv/bin/python" || { echo "FAIL: venv missing" >&2; exit 1; }
test -f "$SRC" || { echo "FAIL: schedule source missing" >&2; exit 1; }
test -f "$REPO/backend/.env" || { echo "FAIL: backend/.env missing" >&2; exit 1; }
[ "$(timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone)" = "America/Phoenix" ] || {
  echo "FAIL: host timezone must be America/Phoenix" >&2; exit 1;
}
mkdir -p "$REPO/backend/logs"
touch "$REPO/backend/logs/alert_dispatcher.log" "$REPO/backend/logs/market_freshness_watchdog.log"       "$REPO/backend/logs/sentinel_fast.log" "$REPO/backend/logs/sentinel_public.log"

current="$(crontab -l 2>/dev/null || true)"
# Remove legacy unmanaged copies of these exact Sentinel-owned commands as well
# as any prior managed block, while preserving every unrelated line.
cleaned="$(awk -v b="$BEGIN" -v e="$END" '
  $0==b {skip=1; next}
  $0==e {skip=0; next}
  skip {next}
  /backend\.alerts\.dispatcher/ {next}
  /backend\.alerts\.market_freshness_watchdog/ {next}
  /backend\.sentinel\.operational --profile fast/ {next}
  /backend\.sentinel\.operational --profile public/ {next}
  {print}
' <<<"$current")"
block="$(sed '/^CRON_TZ=/d' "$SRC")"
if ! grep -q '^CRON_TZ=America/Phoenix' <<<"$cleaned"; then
  block="CRON_TZ=America/Phoenix"$'\n'"$block"
fi
new="$cleaned"$'\n'"$BEGIN"$'\n'"$block"$'\n'"$END"$'\n'

if [ "${1:-}" != "--apply" ]; then
  echo "VERIFY ONLY. Re-run with --apply to install."
  printf '%s\n' "$new" | grep -E 'sentinel-runtime|backend\.sentinel\.operational|backend\.alerts\.(dispatcher|market_freshness_watchdog)' || true
  exit 0
fi
crontab - <<<"$new"
installed="$(crontab -l)"
printf 'managed_blocks='; grep -cFx "$BEGIN" <<<"$installed"
printf 'fast_entries='; grep -v '^[[:space:]]*#' <<<"$installed" | grep -c 'backend.sentinel.operational --profile fast'
printf 'public_entries='; grep -v '^[[:space:]]*#' <<<"$installed" | grep -c 'backend.sentinel.operational --profile public'
printf 'dispatcher_entries='; grep -v '^[[:space:]]*#' <<<"$installed" | grep -c 'backend.alerts.dispatcher'
printf 'freshness_entries='; grep -v '^[[:space:]]*#' <<<"$installed" | grep -c 'backend.alerts.market_freshness_watchdog'
echo "SENTINEL_CRON_INSTALLED=PASS"
