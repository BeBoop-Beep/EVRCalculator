# Recovery progress — September 26, 2026, 17:34–17:36 America/Phoenix

This is a live status checkpoint, not a completion declaration. Only bounded read-only SQL/log inspection and the existing read-only VM observer were run in this pass. No job limits, holds, publication pointers, or serving dates were changed.

## Current source collection and processing

Supabase read-only SQL at 2026-09-27T00:34:34.598781Z:
- Batch 64 / market date 2026-09-26 is complete and promoted. Expected Sets 167, succeeded 167, failed 0, missing 0.
- Promoted at 2026-09-26T23:22:24.739762Z = September 26 16:22:24 America/Phoenix.
- All 167 scrape job rows are completed; first started 22:36:42.676535Z, last completed 23:22:24.032249Z.
- Price Storage V2 queue at that check: 81 complete, 86 pending, no failed rows.

A second authoritative SQL join at 2026-09-27T00:36:22.777324Z (= 17:36:22 Phoenix) verified:
- 167 distinct completed scrape Sets with nonnull source completion timestamps.
- 82 completed projection Sets, all 82 with source_completed_at covering their latest completed scrape timestamp.
- Zero missing queue rows, failed projection rows, or stale source-provenance timestamps.
- Therefore 85 Sets remained uncompleted at that checkpoint. This count comes from database rows, not the local progress summary.

At the prior throughput check, 60 Sets completed projection during the preceding 60 minutes. Mean persisted started_at-to-completed_at duration for the 81 completed Sets was 2.12 seconds. This measures per-Set staged processing, not full command startup, preflight or resource probes. The installed schedule runs once a minute and the script uses process_limit=1. The current backlog is progressing but intentionally rate-limited; these timings alone do not certify a higher sustained load.

## Serving surfaces have not caught up

- Global Market / Set Value snapshot: market_date September 25; updated_at September 25 23:34:57.604172Z.
- RIP statistics: market_date September 25; updated_at September 26 04:44:21.184696Z.
- Cosmic Eclipse dashboard: market date September 25; updated_at September 25 22:12:59.695351Z.
- Explorer's serving generation remains 60c274ea-aed6-45b5-a701-ca0d29eb5f11, comparison_as_of September 22, source_as_of sets/sealed September 22.
- Cosmic Eclipse was successfully scraped September 26 at 23:03:20.624605Z. Its projection was still pending (attempts=0); its current-price rows had no September 26 observations yet. New collection is not equivalent to updated serving prices.

## Current health

SQL confirmed PostgreSQL responding, not in recovery, seven client connections and no other active queries at the initial probe. Postmaster start remains September 26 03:47:00.323649Z, the compute-upgrade restart.

Supabase unified logs for September 26 22:36Z through September 27 00:35Z returned 12,632 successful edge requests, zero edge 5xx, zero SQLSTATE 57014, and zero database-interruption records. This supports stability during the observed input-recovery window, not a guarantee about untested publication workload.

## VM observer proof

Observe Recovery run 36282947565 / job 108518173806 completed successfully. Observation timestamp 2026-09-27T00:35:22Z.
- Collection and price projection authorizations are enabled; neither stage-local hold exists.
- Exactly two input-stage schedules are active; all 14 legacy schedules remain commented out.
- Global incident hold and the old publication recovery hold still exist.
- No reactivation.json exists. Old publication receipt is blocked/exit 75 at September 26 04:52:47Z; old finish sequence is blocked with phase_failed_no_automatic_retry:publication.
- The latest projection resource receipt was 00:34:26.901681Z: available RAM 867,074,048 bytes, pg_up=1, OOM counter=0, stop_reason=null.

## Root cause versus remaining repair

The current freshness incident is explained by the recovery implementation's all-or-nothing dependency: the September 25 publication was stopped by memory_commitment_above_95_percent, and finish_recovery.py consequently never advanced to Explorer or restored next-day collection. Collection and serving-price processing were subsequently separated and are now verified progressing.

The commitment ratio is allocation/commit accounting, not a physical-memory utilization percentage. The original stop receipt did not preserve simultaneous physical-pressure samples; it does not establish an OOM or conclusively establish a false-positive trip. The earlier host-level outage mechanism remains unproven.

The remaining public-data blocker is explicit: Market and Explorer publishers are still held and have no active recovery continuation. The two input schedules do not release them. Completing the projection queue alone will not publish new Market/Explorer snapshots.

Additional validation discrepancy: the local projection progress summary at 00:34:30Z reported 154 expected source Sets and 77 projected, while direct SQL at the near-same time showed 167 source Sets and 81 projections. Cause is not yet established. The direct SQL source-provenance join is the basis for this report. Reconcile that worker-readiness count discrepancy before certifying whole-cohort publication; do not weaken count checks.

No new public generation, gate override, compute change, workload acceleration, full reactivation or permanent-resolution claim is made by this checkpoint.
