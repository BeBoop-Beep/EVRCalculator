#!/bin/bash
# Sample crontab setup for Market Explorer publication + maintained-cache
# prewarm + health check, on Oracle Linux.
#
# These entries assume:
# - Project at: /home/ubuntu/repos/EVRCalculator
# - Virtualenv at: /home/ubuntu/repos/EVRCalculator/.venv
# - User: ubuntu (run as)
# - Logs: /home/ubuntu/repos/EVRCalculator/backend/logs/
#
# To install, save this as a file and run:
#   crontab -l > /tmp/current.cron && cat this-file >> /tmp/current.cron && crontab /tmp/current.cron
#
# Or add entries manually:
#   crontab -e

# =============================================================================
# WHY THREE SEPARATE JOBS, IN THIS ORDER (P0 incident, 2026-09)
# =============================================================================
# run_market_explorer_daily_publication.py used to end its run by discovering
# every maintained cache and rebuilding all of them (21, all stale that day)
# serially IN THE SAME PROCESS as the authoritative projection. That drove the
# Oracle scraper VM to memory saturation and made it unresponsive over SSH.
#
# The fix split this into three independently-scheduled, independently-lockable
# jobs that must run in THIS order and must NEVER be recombined into one
# process:
#
#   1. run_market_explorer_daily_publication.py --commit
#      Both serving projections: current-metadata refresh -> canonical/V1
#      append and reconciliation -> bounded V2 hot-shadow append/trim -> EXIT. Never
#      imports the planner/cache-build machinery. This is what advances
#      both V1 and V2 daily coverage for every authority-bearing set --
#      a maintained cache's incremental advance for large scopes silently
#      falls back onto the expensive interval RPC (real production 57014s
#      seen at Global/large-era scope) for any set this hasn't reached yet,
#      so it MUST complete, or at least run, before step 2 each day.
#
#   2. run_market_explorer_maintained_cache_prewarm.py --commit
#      Builds AT MOST ONE stale cache_kind='maintained' cache per invocation
#      then exits, releasing all process memory (default --max-caches 1).
#      Run it repeatedly (every ~15 minutes below) so an operator/scheduler
#      works through the backlog without ever holding more than one cache's
#      build memory at a time. A persistently-failing cache is automatically
#      deprioritized (not excluded) behind other stale caches via
#      --failure-cooldown-seconds (default 900s) so it cannot starve the
#      rest -- see the script's module docstring.
#
#   3. check_market_explorer_maintained_cache_health.py
#      Read-only. Reports any cache with status != ready, computed_through
#      behind the latest approved market date beyond grace, or an
#      expired/orphaned build lease. Wire its JSON output into your existing
#      alert-dispatch path (see backend/alerts/) rather than parsing cron
#      output; this file only shows the schedule, not the alert routing.
#
# Never add maintained-cache prewarm back into daily publication's own
# process, no matter how tempting a "just build them all at the end" shortcut
# looks -- that is the exact P0 incident.

# 6:15 AM Phoenix - Authoritative projection publish (after scrape/ingestion
# for the day is expected to be settled -- adjust to your actual ingestion
# cadence; this only needs to run after new price rows exist for the day).
15 6 * * * flock -n /tmp/market-explorer-publication.lock sh -c 'cd /home/ubuntu/repos/EVRCalculator && .venv/bin/python -m backend.scripts.run_market_explorer_daily_publication --commit' >> /home/ubuntu/repos/EVRCalculator/backend/logs/market_explorer_publication.log 2>&1

# Every 15 minutes, offset 5 minutes past publication's slot so publication
# gets a head start advancing coverage before prewarm reads it -- maintained
# cache prewarm (one cache per invocation; repeated calls work the backlog).
5-59/15 * * * * flock -n /tmp/market-explorer-prewarm.lock sh -c 'cd /home/ubuntu/repos/EVRCalculator && .venv/bin/python -m backend.scripts.run_market_explorer_maintained_cache_prewarm --commit' >> /home/ubuntu/repos/EVRCalculator/backend/logs/market_explorer_prewarm.log 2>&1

# Every 15 minutes, offset another 5 minutes past prewarm's slot - read-only
# health check. Route its JSON into your alert dispatcher rather than relying
# on this log alone.
10-59/15 * * * * flock -n /tmp/market-explorer-health.lock sh -c 'cd /home/ubuntu/repos/EVRCalculator && .venv/bin/python -m backend.scripts.check_market_explorer_maintained_cache_health' >> /home/ubuntu/repos/EVRCalculator/backend/logs/market_explorer_health.log 2>&1

# =============================================================================
# Monitoring & Debugging
# =============================================================================
# Tail today's activity:
#   tail -f /home/ubuntu/repos/EVRCalculator/backend/logs/market_explorer_publication.log
#   tail -f /home/ubuntu/repos/EVRCalculator/backend/logs/market_explorer_prewarm.log
#   tail -f /home/ubuntu/repos/EVRCalculator/backend/logs/market_explorer_health.log
#
# Manual one-off run of any stage (each is safe to run by hand; --dry-run
# performs no writes for the first two):
#   cd /home/ubuntu/repos/EVRCalculator
#   .venv/bin/python -m backend.scripts.run_market_explorer_daily_publication --dry-run
#   .venv/bin/python -m backend.scripts.run_market_explorer_maintained_cache_prewarm --dry-run
#   .venv/bin/python -m backend.scripts.check_market_explorer_maintained_cache_health
#
# Check current maintained-cache coverage gap directly:
#   psql "${DATABASE_URL}" -c "SELECT set_id, computed_through FROM pokemon_market_explorer_card_daily_coverage WHERE computed_through < CURRENT_DATE ORDER BY computed_through;"
