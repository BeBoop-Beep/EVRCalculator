#!/bin/bash
# Install one dedicated persistent seller-HMAC key without ever printing it.
set -euo pipefail

REPO="${REPO:-/home/ubuntu/repos/EVRCalculator}"
ENV_FILE="$REPO/backend/.env"
NAME="ACTIVE_SUPPLY_SELLER_HASH_KEY"

probe() {
  (cd "$REPO" && ./.venv/bin/python - <<'PY'
from backend.pricing_pipeline.active_supply_credentials import load_active_supply_credentials
try:
    value = load_active_supply_credentials()
    if value.source != "backend/.env":
        print("ACTIVE_SUPPLY_SELLER_HASH_CREDENTIAL_NOT_PERSISTENT source=" + value.source)
        raise SystemExit(4)
    print("ACTIVE_SUPPLY_SELLER_HASH_CREDENTIAL_PRESENT source=" + value.source)
except Exception as exc:
    print("ACTIVE_SUPPLY_SELLER_HASH_CREDENTIAL_MISSING type=" + type(exc).__name__)
    raise SystemExit(4)
PY
  )
}

if probe; then
  echo "credential unchanged"
  exit 0
fi
[ "${1:-}" = "--apply" ] && [ "${2:-}" = "--generate-if-missing" ] || {
  echo "VERIFY ONLY: credential missing. Use --apply --generate-if-missing after review." >&2
  exit 4
}
[ -f "$ENV_FILE" ] || { echo "FAIL: $ENV_FILE missing" >&2; exit 2; }
if grep -Eq "^[[:space:]]*(export[[:space:]]+)?${NAME}=" "$ENV_FILE"; then
  echo "FAIL: existing credential assignment is invalid; refusing replacement" >&2; exit 2
fi
umask 077
tmp="$(mktemp "$ENV_FILE.active-supply.XXXXXX")"
trap 'rm -f "$tmp"' EXIT
cp "$ENV_FILE" "$tmp"
printf '\n%s=%s\n' "$NAME" "$(openssl rand -hex 32)" >> "$tmp"
chmod 600 "$tmp"
mv "$tmp" "$ENV_FILE"
trap - EXIT
probe
echo "ACTIVE_SUPPLY_SELLER_HASH_CREDENTIAL_INSTALLED value=<redacted>"
