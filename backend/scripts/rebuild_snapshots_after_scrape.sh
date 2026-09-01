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
# publication order. backend/scripts/refresh_stale_public_snapshots.py is the
# canonical orchestrator and already rebuilds, in order, Sealed Market (from
# sealed ingestion alone), coordinated Cards + Market Dashboard, Explore card
# movers, Explore rankings, set pages, and desirability validation. Calling the
# individual builders from here is what let surfaces advance out of step and
# leave Explore/Sealed a day behind a promoted set page.
#
# Deliberately absent, and deliberately NOT to be added:
#   * git pull            - deployment is a separate, reviewed step
#   * --force-publish     - never publish around the batch-cohort gate
#   * --strict            - it would fail on the intentionally-stale OPvC that
#                           this phase is defined to allow; the stricter surface
#                           validation is the post-scrape audit below, and the
#                           refresh already exits nonzero on real builder failures
#   * individual builders - see above

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-${REPO_ROOT}/.venv/bin/python}"

# Single-publisher lock: covers the ENTIRE refresh + post-scrape audit below.
# Prevents the immediate post-scrape trigger, the 6:00 AM fallback, and an
# accidental manual invocation from ever running concurrent publishers. A
# held lock is a safe NO-OP (exit 0), never a failure — the caller (scrape
# batch completion or the fallback) must stay unaffected. The lock file
# descriptor is opened for the life of this process, so the lock releases
# automatically on any exit path (success, failure, or signal).
LOCK_PATH="${POST_SCRAPE_PUBLICATION_LOCK_PATH:-/tmp/pokemon-post-scrape-publication.lock}"
if ! command -v flock >/dev/null 2>&1; then
  printf '[post-scrape-publication] %s FATAL flock not available; refusing to publish unlocked\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  exit 1
fi
exec {LOCK_FD}>"${LOCK_PATH}"
if ! flock -n "${LOCK_FD}"; then
  printf '[post-scrape-publication] %s already running (lock_path=%s held); safe no-op, exiting 0\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${LOCK_PATH}"
  exit 0
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

# `set -e` would abort before the exit status could be logged and classified, so
# each stage captures its own status explicitly.
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

AUDIT_CMD=(
  "${PYTHON_BIN}" backend/scripts/audit_pokemon_market_publication.py
  --phase post-scrape
  --market-date "${MARKET_DATE}"
)
log "command: ${AUDIT_CMD[*]}"
AUDIT_STATUS=0
"${AUDIT_CMD[@]}" || AUDIT_STATUS=$?
log "audit exit_status=${AUDIT_STATUS}"

if [[ "${AUDIT_STATUS}" -ne 0 ]]; then
  log "post-scrape market audit FAILED: a market surface is not on ${MARKET_DATE}"
  log "final exit_status=${AUDIT_STATUS}"
  exit "${AUDIT_STATUS}"
fi

log "post-scrape publication COMPLETE for market_date=${MARKET_DATE}"
log "Opening Profit vs Cost remains on the previous simulation date by design;"
log "the later coordinated publication runs simulations and audits the full contract."
log "final exit_status=0"
