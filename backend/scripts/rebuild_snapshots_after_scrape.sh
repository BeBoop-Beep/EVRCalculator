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

# The market date is the America/Phoenix business date the batch was promoted
# for, never the VM's wall clock date, so a run that slips past midnight UTC
# still audits and publishes the date the pipeline actually promoted.
MARKET_DATE="$(TZ=America/Phoenix date +%F)"
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
GIT_SHA="$(git -C "${REPO_ROOT}" rev-parse HEAD 2>/dev/null || echo unknown)"

log() {
  printf '[post-scrape-publication] %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

log "started_at=${STARTED_AT}"
log "repo_root=${REPO_ROOT}"
log "git_sha=${GIT_SHA}"
log "python_bin=${PYTHON_BIN}"
log "market_date=${MARKET_DATE}"

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
