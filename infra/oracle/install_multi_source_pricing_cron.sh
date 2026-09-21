#!/bin/bash
# Idempotently install the daily multi-source pricing schedule on the scraper VM (run AS the runtime user, e.g. ubuntu).
#
# Preconditions (checked below, install aborts if any fails):
#   * the P6 code is deployed in the VM checkout (backend/pricing_pipeline exists)
#   * host timezone is America/Phoenix
#   * the production migrations 20260921000000/010000/020000 are applied (the dry run reads the schema)
#
# Usage:  bash infra/oracle/install_multi_source_pricing_cron.sh [--apply]      (default: verify only, changes nothing)
set -euo pipefail
REPO="${REPO:-/home/ubuntu/repos/EVRCalculator}"
STATE="${EVR_PRICING_STATE_DIR:-/home/ubuntu/state/multi_source_pricing}"
SRC="$REPO/infra/oracle/multi-source-pricing.crontab"
BEGIN="# BEGIN multi-source-pricing (managed by install_multi_source_pricing_cron.sh)"
END="# END multi-source-pricing"

[ -d "$REPO/backend/pricing_pipeline" ] || { echo "FAIL: P6 code not deployed in $REPO" >&2; exit 1; }
[ "$(timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone)" = "America/Phoenix" ] || { echo "FAIL: host timezone must be America/Phoenix" >&2; exit 1; }
mkdir -p "$STATE" "$REPO/backend/logs"
touch "$REPO/backend/logs/multi_source_pricing.log" "$REPO/backend/logs/multi_source_pricing_health.log"
echo "state dir: $STATE (owner $(stat -c %U "$STATE"), mode $(stat -c %a "$STATE"))"
echo "== eBay credential presence (process env / backend/.env only; values never printed)"
(cd "$REPO" && ./.venv/bin/python -c "
from backend.pricing_pipeline.ebay_credentials import load_ebay_credentials, CredentialsUnavailable
try:
    c = load_ebay_credentials(allow_frontend_fallback=False); print('EBAY_CLIENT_ID present, EBAY_CLIENT_SECRET present, source=' + c.source + ', environment=' + c.environment)
except CredentialsUnavailable:
    print('EBAY_DAILY_PRICING_NOT_READY_VM_CREDENTIALS_MISSING'); raise SystemExit(4)
") || { echo "FAIL: eBay credentials missing on this VM; not installing a schedule known to fail" >&2; exit 4; }
echo "== manifest-only dry run as $(id -un) (no DB writes, no eBay calls; credentials never printed)"
(cd "$REPO" && EVR_PRICING_STATE_DIR="$STATE" ./.venv/bin/python -m backend.scripts.run_daily_multi_source_card_pricing --dry-run --json --no-frontend-env-fallback | head -8)
echo "== single-instance lock check"
/usr/bin/flock -n /tmp/multi-source-pricing.lock -c 'echo lock acquirable' || { echo "FAIL: lock held" >&2; exit 1; }

current="$(crontab -l 2>/dev/null || true)"
echo "== existing crontab (secrets masked)"; sed -E 's/((KEY|TOKEN|SECRET|PASSWORD)[A-Z_]*=)[^ ]+/<redacted>/g' <<<"$current"
block="$(sed '/^CRON_TZ=/d' "$SRC")"
if ! grep -q '^CRON_TZ=America/Phoenix' <<<"$current"; then block="CRON_TZ=America/Phoenix"$'\n'"$block"; fi
new="$(awk -v b="$BEGIN" -v e="$END" '$0==b{skip=1} !skip{print} $0==e{skip=0}' <<<"$current")"
new="$new"$'\n'"$BEGIN"$'\n'"$block"$'\n'"$END"$'\n'
if [ "${1:-}" != "--apply" ]; then echo "VERIFY ONLY. Re-run with --apply to install. Resulting entries:"; grep -E 'multi_source|multi-source' <<<"$new" | cut -c1-120; exit 0; fi
crontab - <<<"$new"
echo "installed. entries:"; crontab -l | grep -E 'run_daily_multi_source_card_pricing|check_multi_source_pricing_health' | cut -c1-110
