# Small upgrade recovery — checkpoint 2026-09-26 04:22 UTC

Status: RUNNING, not yet fully current or reactivated. User explicitly authorized staged reactivation and data catch-up after upgrading compute.

## Verified
- Database restarted for the upgrade at 03:47:00 UTC; live metrics show ~1835 MiB usable total RAM, ~1376 MiB available at preflight, virtually no swap. Small-tier connection ceiling is 90.
- September 25 scrape is complete and promoted: 167/167 Sets succeeded. Do not rescrape this cohort.
- All 22 September 25 simulations now pass the opening freshness gate. Only Twilight Masquerade and White Flare were rerun. Simulation phase completed 04:09:25 UTC, exit 0. Receipt in /home/ubuntu/state/db-safety/recovery/2026-09-25/simulations.json.
- Chase Accessibility is ready for all 22 Sets on September 25.
- Multi-source pricing September 25 already completed (2,338 requests); not rerun by this recovery.
- Global Market/Set Value authority already advertises September 25.
- Logs from upgrade through 04:22 UTC: 2,825 successful 2xx edge requests, zero edge 5xx, zero SQLSTATE 57014, zero database-interruption records. This is an observation window, not a permanent stability guarantee.

## Still running / pending
- Publication worker PID 436901 started 04:11:23 UTC. It is processing the real coordinated pipeline: sealed results, representativeness, RIP statistics, snapshots, Chase economics/efficiency, audits, and Collector/history operationalization. At 04:19:27 UTC, 11 Sets had new representativeness summaries; RIP statistics still advertised September 24. Do not claim all rankings/pages are current yet.
- Explorer interval projection was through September 24; the currently serving prepared generation is September 22. Its 37 maintained caches require catch-up. The expanded v2 surface schema exists but has no serving pointer; do not silently activate that separate feature.
- Collector source/model freshness has not been certified current. Existing Collector as-of was September 11; the coordinated pipeline must truthfully refresh due evidence or report its blocker.

## Executed safety / runtime fixes
- PR #383 merged to main at 218bf2ef70874118554aecc9d458c7bae5ea24a3. Deployed runtime overlay 1058e66cc1f84e54f75f3ab9022620380ba0a8aa. Detached canonical publishers now hold shared resource admission for their whole life; full opening audit uses the existing compact reader. 59 tests passed.
- Isolated Python 3.13 recovery environment was provisioned from existing backend requirements plus the opening watchdog's scipy==1.18.1 pin. Imports and pip check passed. The missing scipy and detached libpython loader problems were fixed without modifying the scraper environment.
- Existing VM DATABASE_URL connects successfully as market_explorer_publisher; no password reset was needed.
- Recovery phases use the global host workload lock and a resource-guarded authorized recovery lane. Ordinary cron remains disabled under the persistent incident HOLD.

## Active sequence: no manual next-phase launch required
Finish Guarded Recovery run 36217465241 / job 108336195429 passed four schedule-restoration tests and launched persistent sequence PID 437068 at 04:19:10 UTC. It is waiting on the publication receipt, not issuing extra database queries.

On successful publication, it starts the pinned Explorer catch-up helper. That helper advances daily projection, builds at most one cache per fresh process, requires strict decreasing stale-cache count, and verifies the published prepared generation dates. Seven progress tests passed. A failed/no-progress build stops instead of blindly retrying.

After simulations, publication and Explorer all have successful receipts and service/resource checks pass, the sequence restores the 14 existing guarded VM schedules and adds one guarded, one-cache-at-a-time Explorer maintenance schedule. It archives/removes the incident hold last. Experimental database shadow cron job 19 stays disabled; do not duplicate its old workload.

At this checkpoint the 14 ordinary schedules are STILL PAUSED; restoration is queued, not yet completed. A phase failure blocks the sequence and preserves the hold for investigation. Do not claim workflow launch success means the detached phases completed.

## Runtime state
- /home/ubuntu/state/db-safety/recovery/2026-09-25/{simulations,publication,explorer,sequence}.json
- Corresponding .log files; Explorer per-step logs in explorer_steps/
- /home/ubuntu/state/db-safety/reactivation.json is written only after verified schedule restoration.
- All state is outside Git. Do not clear HOLD or launch parallel Windows/MCP heavy jobs during recovery.
