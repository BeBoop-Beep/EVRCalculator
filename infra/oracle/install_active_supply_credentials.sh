#!/bin/bash
# Persist one externally retained seller-HMAC key without ever printing it.
set -euo pipefail

CODE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_REPO="${ACTIVE_SUPPLY_ENV_REPO:-/home/ubuntu/repos/EVRCalculator}"
PY="$ENV_REPO/.venv/bin/python"
ENV_FILE="$ENV_REPO/backend/.env"
NAME="ACTIVE_SUPPLY_SELLER_HASH_KEY"
INSTALL_NAME="ACTIVE_SUPPLY_SELLER_HASH_KEY_INSTALL"

[ -x "$PY" ] || { echo "FAIL: shared Python runtime missing" >&2; exit 2; }

probe_persisted() {
  (
    cd "$CODE_ROOT"
    env -u ACTIVE_SUPPLY_SELLER_HASH_KEY \
      PYTHONPATH="$CODE_ROOT" \
      ACTIVE_SUPPLY_ENV_REPO="$ENV_REPO" \
      "$PY" - <<'PY'
from pathlib import Path
from backend.pricing_pipeline.ebay_credentials import parse_env_file
from backend.pricing_pipeline.active_supply_credentials import ActiveSupplyCredentialUnavailable, ActiveSupplyCredentials, KEY

env_repo = Path(__import__("os").environ["ACTIVE_SUPPLY_ENV_REPO"])
values = parse_env_file(env_repo / "backend/.env")
value = str(values.get(KEY) or "").strip()
if not value:
    print("ACTIVE_SUPPLY_SELLER_HASH_CREDENTIAL_MISSING")
    raise SystemExit(4)
if len(value) < 32:
    print("ACTIVE_SUPPLY_SELLER_HASH_CREDENTIAL_INVALID")
    raise SystemExit(4)
print("ACTIVE_SUPPLY_SELLER_HASH_CREDENTIAL_PRESENT source=backend/.env")
PY
  )
}

if probe_persisted; then
  echo "credential unchanged"
  exit 0
fi

[ "${1:-}" = "--apply" ] || {
  echo "VERIFY ONLY: persistent credential missing. Provide $INSTALL_NAME from an externally retained secret, then rerun with --apply." >&2
  exit 4
}
[ -f "$ENV_FILE" ] || { echo "FAIL: $ENV_FILE missing" >&2; exit 2; }
if grep -Eq "^[[:space:]]*(export[[:space:]]+)?${NAME}=" "$ENV_FILE"; then
  echo "FAIL: existing credential assignment is invalid; refusing replacement" >&2
  exit 2
fi

VALUE="${!INSTALL_NAME:-}"
[ "${#VALUE}" -ge 32 ] || {
  echo "FAIL: $INSTALL_NAME must be supplied from an externally retained secret and contain at least 32 characters" >&2
  exit 2
}

umask 077
tmp="$(mktemp "$ENV_FILE.active-supply.XXXXXX")"
trap 'rm -f "$tmp"' EXIT
cp "$ENV_FILE" "$tmp"
printf '\n%s=%s\n' "$NAME" "$VALUE" >> "$tmp"
chmod 600 "$tmp"
mv "$tmp" "$ENV_FILE"
trap - EXIT
unset VALUE
probe_persisted
echo "ACTIVE_SUPPLY_SELLER_HASH_CREDENTIAL_INSTALLED value=<redacted> recovery_source=external"
