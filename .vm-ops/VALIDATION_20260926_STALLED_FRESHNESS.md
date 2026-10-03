# September 26 freshness validation

Checked 2026-09-26 17:32–17:39 UTC (10:32–10:39 America/Phoenix).
Status: BLOCKED; no September 26 scrape was created. This validation did not restore the schedules or launch a new scrape.

## Live database evidence

Read-only Supabase SQL probes used 5-second statement and 1-second lock limits. Latest health probe at 17:38:32 UTC:
- PostgreSQL responds, not in recovery, and postmaster start is still 2026-09-26 03:47:00.323649 UTC (September 25 20:47 Phoenix, the compute-upgrade restart).
- No other active SQL queries at the probe. Configured max_connections remains 90.
- pokemon_scrape_batches: no market_date=2026-09-26 row. Latest is batch 63, September 25, complete/promoted, 167/167 Sets succeeded.
- scrape_jobs: zero September 26 rows and zero started rows for that date.
- scrape_job_runs: zero September 26 run rows.
- pokemon_explore_set_value_snapshot_latest, scope=market: market_date September 25, updated_at 2026-09-25 23:34:57 UTC.
- pokemon_rip_stats_snapshot_latest: market_date September 25, updated_at 2026-09-26 04:44:21 UTC. September 25 simulations cover 22 distinct Sets; no September 26 simulation cohort exists.
- Explorer serving prepared generation 60c274ea-aed6-45b5-a701-ca0d29eb5f11: comparison_as_of September 22; source_as_of sets and sealed both September 22.
- Explorer V2 daily coverage: all 167 rows still computed_through September 24.

## Cosmic Eclipse evidence

Set id dfcf6c98-1bf3-43a8-83a2-7e56b3c65d03, canonical_key cosmicEclipse.
- Last successful scrape: September 25, job 151373, completed 2026-09-25 17:25:50 UTC (10:25:50 Phoenix), one attempt, no error_code.
- Set market dashboard latest_market_date September 25.
- All ten top-chase history series end September 25; latest sourceDate September 25.
- Current-price last_observed_date, not effective_date, was inspected: newest date September 25, covering 464 price rows across 271 cards. No September 26 observations. Older rows for additional condition/variant combinations also exist; this is not a claim that all such rows are current.
- Set cards snapshot: 272 cards, updated September 25 22:12:57 UTC.
- Set page updated September 26 03:01:57 UTC = September 25 20:01:57 Phoenix. A UTC calendar date of 26 here does not mean today's Phoenix data is current.

## Exact overnight stop

Observed on production VM via run 36259725056, job 108453115339, at 17:38:13 UTC. Previous read-only receipt observation: run 36259410896, job 108452232377.

- /home/ubuntu/state/db-safety/recovery/2026-09-25/admission/hold.json exists.
- Its exact reason is memory_commitment_above_95_percent; guard version 2026-09-26.2.
- Publication receipt: started 04:11:23 UTC; stopped 04:52:47.237770 UTC on September 26 = September 25 21:52:47 Phoenix; exit_code 75, status blocked.
- Sequence receipt: blocked at 04:52:52.102425 UTC; reason phase_failed_no_automatic_retry:publication.
- No Explorer recovery receipt was present. The sequence did not advance to Explorer or schedule restoration.
- The original global hold still exists with reason recurring_database_outage_manual_clear_required.
- /home/ubuntu/state/db-safety/reactivation.json does not exist.
- All 14 guarded application cron entries are still commented out. active_guarded_schedules=0.
- No matching worker processes remain after the watchdog retry was stopped.

The finish_recovery.py design requires successful simulations, publication AND Explorer before restoring all VM jobs. Consequently a derived-data publication failure also kept next-day batch creation and scraping disabled. The recovery dependency is too broad. Refusing to publish invalid data is correct; holding the whole next day's collection behind old downstream work is not a sustainable recovery policy.

The trip is a committed-address-space ratio, not a measurement that physical RAM was 95% used. No contemporaneous physical-memory/swap-rate sample was persisted in the hold receipt, so this record does not assert either a confirmed OOM or a proven false-positive trip. No new postmaster restart occurred after the upgrade.

## Additional verified findings and changes in this validation

- The independent Opening Simulation Recovery Watchdog, run 36259380339 / job 108452146236, was occupying the sole production runner with a scheduled publication retry and did not check the persistent incident hold.
- Added explicit hold/unreadable-state checks before its DB preflight and again before recovery, in main commit 1bc9e0f3c56cd968f3cc1e5ecc0e8331a3295bb2. Its existing maintenance-push cancellation behavior stopped the current retry; job conclusion verified cancelled. No replacement recovery job was launched.
- Expanded the read-only observer to report exact global/lane holds, reactivation receipt and decoded schedule status. It performs no DB writes and no workload restoration.
- Supabase logs from 04:20–07:30 UTC show 157 undefined-column errors during 04:44–04:50, including cards.updated_at and other timestamp probes. These still require repair; they are NOT the recorded terminating condition for this publication attempt.

## Next recovery correction

Separate safe, serialized raw-data collection from derived-publication acceptance. Reassess committed-memory-only trip policy using measured physical pressure while preserving serialization, bounded work and emergency stops. Restore the date-aware scraper independently, create September 26's missing batch idempotently, verify actual fresh observations, then publish current derived surfaces and advance Explorer. Add notification/escalation for a terminal blocked sequence so a local receipt cannot be mistaken for a running recovery overnight. Do not mark old source dates fresh or clear every hold without reviewed admission checks.
