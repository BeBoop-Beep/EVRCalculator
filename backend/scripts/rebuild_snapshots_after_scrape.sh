#!/usr/bin/env bash
#
# Post-scrape canonical market publication (VM cron, ~6:00 AM America/Phoenix).
#
# This runs immediately after the daily scrape batch is promoted, and it is the
# FIRST of the day's two publication phases:
#
#   1. THIS phase (post-scrape) advances every market PRICING surface — Set Value,
#      Cards, Top Chase, Sealed Market, Explore rankings (incl. the Explore Top
#      Rankings Set Value), and the set-page market/header data. No simulations
#      run here, so Opening Profit vs Cost truthfully stays on the previous
#      simulation date. That is expected, and the audit reports it as DEFERRED.
#
#   2. The later Windows coordinated publication runs simulations and brings OPvC
#      current. Its audit runs in the default (full) phase, where OPvC is required.
#
# The single most important rule here: this wrapper does NOT reimplement the
# public snapshot order. backend/scripts/refresh_stale_public_snapshots.py is the
# canonical snapshot orchestrator. Price Storage V2 serving remains separately
# operator-gated and is intentionally NOT attached to this scheduled path until
# its production cutover is explicitly release-approved.
#
# Deliberately absent, and deliberately NOT to be added:
#   * git pull            - deployment is a separate, reviewed step
#   * --force-publish     - never publish around a quality/cohort gate
#   * --strict            - it would fail on the intentionally-stale OPvC that
#                           this phase is defined to allow; the stricter surface
#                           validation is the post-scrape audit below, and the
#                           refresh already exits nonzero on real builder failures
#   * individual builders - see above
#   * Price Storage V2    - remains a separate operator-gated release workstream

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-${REPO_ROOT}/.venv/bin/python}"

# Single-publisher lock: covers canonical refresh + audit + Market Explorer
# projection. Prevents the immediate post-scrape trigger, the 6:00 AM fallback,
# and an accidental manual invocation from ever running concurrent publishers.
# A held lock is a safe NO-OP (exit 0), never a failure — the caller (scrape
# batch completion or the fallback) must stay unaffected. The lock file
# descriptor is opened for the life of this process, so the lock releases
# automatically on any exit path (success, failure, or signal).
LOCK_PATH="${POST_SCRAPE_PUBLICATION_LOCK_PATH:-/tmp/pokemon-post-scrape-publication.lock}"
LOCK_HELD_EXIT_CODE=4
if ! command -v flock >/dev/null 2>&1; then
  printf '[post-scrape-publication] %s FATAL flock not available; refusing to publish unlocked\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  exit 1
fi
exec {LOCK_FD}>"${LOCK_PATH}"
if ! flock -n "${LOCK_FD}"; then
  printf '[post-scrape-publication] %s already running (lock_path=%s held); safe no-op, exit_code=%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${LOCK_PATH}" "${LOCK_HELD_EXIT_CODE}"
  exit "${LOCK_HELD_EXIT_CODE}"
fi

# Explicit market date support (recovery + the immediate post-scrape trigger):
#   rebuild_snapshots_after_scrape.sh 2026-09-01
# Backward compatible: with no argument this defaults to the America/Phoenix
# business date, exactly as before, for manual/cron use. The market date is
# NEVER derived from the VM's wall clock when an explicit batch date is known
# — a run that slips past midnight UTC must still audit and publish the date
# the pipeline actually promoted.
EXPLICIT_MARKET_DATE="${1:-}"
if [[ -n "${EXPLICIT_MARKET_DATE}" ]]; then
  if [[ ! "${EXPLICIT_MARKET_DATE}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
    printf '[post-scrape-publication] %s FATAL malformed market date argument: %s (expected YYYY-MM-DD)\n' \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${EXPLICIT_MARKET_DATE}"
    exit 1
  fi
  MARKET_DATE="${EXPLICIT_MARKET_DATE}"
else
  # No explicit date supplied: fall back to the America/Phoenix business date
  # (manual invocation / legacy behavior).
  MARKET_DATE="$(TZ=America/Phoenix date +%F)"
fi
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
GIT_SHA="$(git -C "${REPO_ROOT}" rev-parse HEAD 2>/dev/null || echo unknown)"

log() {
  printf '[post-scrape-publication] %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

log "started_at=${STARTED_AT}"
log "repo_root=${REPO_ROOT}"
log "git_sha=${GIT_SHA}"
log "python_bin=${PYTHON_BIN}"
log "lock_path=${LOCK_PATH}"
log "resolved market_date=${MARKET_DATE}"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  log "FATAL python interpreter not executable at ${PYTHON_BIN}"
  exit 1
fi

cd "${REPO_ROOT}"

# Price Storage V2 is now in the canonical selected-price lineage. A complete
# scrape batch is not publishable until that exact scrape cohort has been
# projected through card_variant_price_current_v2 / canonical selected prices.
# This check is read-only; the separate liveness watchdog advances the queue.
PROJECTION_CMD=(
  "${PYTHON_BIN}" backend/scripts/check_price_storage_v2_projection_ready.py
  --market-date "${MARKET_DATE}"
)
log "command: ${PROJECTION_CMD[*]}"
PROJECTION_STATUS=0
"${PROJECTION_CMD[@]}" || PROJECTION_STATUS=$?
log "price projection readiness exit_status=${PROJECTION_STATUS}"
if [[ "${PROJECTION_STATUS}" -eq 3 ]]; then
  log "DEFERRED Price Storage V2 projection is not ready for market_date=${MARKET_DATE}; preserving previous good snapshots"
  exit 3
fi
if [[ "${PROJECTION_STATUS}" -ne 0 ]]; then
  log "FAILED Price Storage V2 projection authority could not be verified for market_date=${MARKET_DATE}"
  exit "${PROJECTION_STATUS}"
fi

# Set Value is a derived read model. Cards ingestion deliberately treats its
# inline refresh as best-effort so a transient SQLSTATE 57014 cannot throw away
# an otherwise successful scrape. Before publication, repair ONLY canonical
# Market roots missing Standard/Top-10 rows for this exact date. This closes the
# gap between durable card prices and the Market-quality gate without rescraping.
SET_VALUE_REPAIR_CMD=(
  "${PYTHON_BIN}" -m backend.scripts.repair_missing_market_set_value_history
  --market-date "${MARKET_DATE}"
  --commit
  --max-passes 3
  --sleep-seconds 2
)
log "command: ${SET_VALUE_REPAIR_CMD[*]}"
SET_VALUE_REPAIR_STATUS=0
"${SET_VALUE_REPAIR_CMD[@]}" || SET_VALUE_REPAIR_STATUS=$?
log "set value repair exit_status=${SET_VALUE_REPAIR_STATUS}"
if [[ "${SET_VALUE_REPAIR_STATUS}" -ne 0 ]]; then
  log "FAILED canonical Market Set Value coverage could not be repaired for market_date=${MARKET_DATE}; preserving previous good snapshots"
  exit "${SET_VALUE_REPAIR_STATUS}"
fi

# `set -e` would abort before the exit status could be logged and classified, so# each stage captures its own status explicitly.
REFRESH_CMD=(
  "${PYTHON_BIN}" backend/scripts/refresh_stale_public_snapshots.py
  --commit
  --market-date "${MARKET_DATE}"
  --gate-wait-attempts 6
  --gate-wait-seconds 600
)
log "command: ${REFRESH_CMD[*]}"
REFRESH_STATUS=0
"${REFRESH_CMD[@]}" || REFRESH_STATUS=$?
log "refresh exit_status=${REFRESH_STATUS}"

# Exit code 3 is the publication gate's DEFERRED signal: the day's scrape cohort
# never completed within the bounded wait, so nothing was published. Auditing
# would then report yesterday's data as stale, which is true but not actionable,
# and running it here would obscure the real cause. Propagate the deferral.
if [[ "${REFRESH_STATUS}" -eq 3 ]]; then
  log "publication gate remained CLOSED after the bounded wait; nothing published"
  log "final exit_status=3 (deferred)"
  exit 3
fi

if [[ "${REFRESH_STATUS}" -ne 0 ]]; then
  log "refresh FAILED; skipping the post-scrape audit"
  log "final exit_status=${REFRESH_STATUS}"
  exit "${REFRESH_STATUS}"
fi

# Keep the canonical audit path explicit for deployment/Price Storage contract
# checks. The resilient runner below wraps these exact verdict semantics and only
# hardens read transport + the oversized Cards projection.
CANONICAL_AUDIT_PATH="backend/scripts/audit_pokemon_market_publication.py"
RESILIENT_AUDIT_MODULE="backend.scripts.audit_pokemon_market_publication_resilient"
AUDIT_CMD=(
  "${PYTHON_BIN}" -m "${RESILIENT_AUDIT_MODULE}"
  --phase post-scrape
  --market-date "${MARKET_DATE}"
)
log "command: ${AUDIT_CMD[*]} (canonical=${CANONICAL_AUDIT_PATH})"
AUDIT_STATUS=0
"${AUDIT_CMD[@]}" || AUDIT_STATUS=$?
log "audit exit_status=${AUDIT_STATUS}"

if [[ "${AUDIT_STATUS}" -ne 0 ]]; then
  log "post-scrape market audit FAILED or could not complete for ${MARKET_DATE}"
  log "final exit_status=${AUDIT_STATUS}"
  exit "${AUDIT_STATUS}"
fi

# Market Explorer's materialized serving projections must advance only after
# the canonical market date has been published and audited. Keeping this in
# the authoritative post-scrape handoff avoids a clock race where a fixed cron
# slot runs before pokemon_market_date_quality approves the day. This remains
# projection-only: maintained-cache prewarm is intentionally a separate,
# resource-guarded process after the P0 memory incident.
MARKET_EXPLORER_CMD=(
  "${PYTHON_BIN}" -m backend.scripts.run_market_explorer_daily_publication
  --commit
  --market-date "${MARKET_DATE}"
)
log "command: ${MARKET_EXPLORER_CMD[*]}"
MARKET_EXPLORER_STATUS=0
"${MARKET_EXPLORER_CMD[@]}" || MARKET_EXPLORER_STATUS=$?
log "market explorer projection exit_status=${MARKET_EXPLORER_STATUS}"

if [[ "${MARKET_EXPLORER_STATUS}" -ne 0 ]]; then
  log "Market Explorer V1/V2 advancement FAILED for market_date=${MARKET_DATE}"
  log "final exit_status=${MARKET_EXPLORER_STATUS}"
  exit "${MARKET_EXPLORER_STATUS}"
fi

log "post-scrape publication COMPLETE for market_date=${MARKET_DATE}"
log "Opening Profit vs Cost remains on the previous simulation date by design;"
log "the later coordinated publication runs simulations and audits the full contract."
log "final exit_status=0"
