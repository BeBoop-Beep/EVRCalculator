# September 26 autonomous-update investigation

## Status at 22:49:38 UTC / 15:49:38 America/Phoenix

PARTIAL RECOVERY. Raw collection and canonical price projection are now independently scheduled under shared host admission. Market snapshot and Explorer publishing have NOT been re-enabled or certified current by this pass. The old global incident hold and the old failed publication-lane hold remain intact.

This record distinguishes an available database, completed source collection, serving-price projection, public snapshots, and the prepared Explorer generation. None is substituted for another.

## 1. The current stale state was the same unresolved stop, not a new crash

Bounded read-only SQL at 22:25:43 UTC found PostgreSQL available, not in recovery, eight clients against max_connections=90, and zero other active SQL queries. Its postmaster start was still 2026-09-26 03:47:00.323649 UTC, the Small-upgrade restart. That start time remained unchanged at 22:49:38 UTC.

A Supabase log aggregation covering 17:30–22:29 UTC reported 1,639 edge events with zero edge 5xx, and 1,105 PostgreSQL log events with zero statement timeouts and zero database-interruption records. Three undefined-column errors remained. This observation does not certify future capacity or resolve the earlier crash's host-level cause.

VM observation run 36276268752 / job 108499514257 at 22:26:18 UTC showed:
- all 14 original application schedules still commented out;
- active guarded schedule count zero;
- the original global hold present;
- the old publication recovery-lane hold present with reason memory_commitment_above_95_percent;
- no reactivation.json and no running application workers;
- publication stopped at 04:52:47 UTC, exit 75;
- sequence stopped at 04:52:52 UTC, reason phase_failed_no_automatic_retry:publication;
- no Explorer recovery receipt.

The prior finish_recovery.py requires successful simulations, publication and Explorer before restoring ALL schedules. Consequently a failure in yesterday's derived publication prevented today's batch creation and collection. This all-or-nothing restoration dependency was an error in the recovery implementation. It also left the VM alert dispatcher disabled. Do not infer that every independent external monitoring system was disabled.

## 2. Resource evidence and the old stop policy

VM preflight run 36276352600 / job 108499749309 sampled the database twice at 22:27:53 and 22:28:13 UTC:
- usable RAM 1,835.043 MiB;
- available RAM 819.895 MiB, approximately 44.7%;
- swap used approximately 234.098 MiB of 1,023.996 MiB;
- committed memory 1,843.594 MiB against commitment limit 1,941.516 MiB;
- load1 zero, pg_up=1, host OOM counter zero;
- REST/Auth/Storage small probes all HTTP 200, approximately 84/43/94 ms.

Committed_AS/CommitLimit is address-space commitment accounting, not a physical RAM utilization percentage. The old hold receipt did not preserve simultaneous physical-pressure measurements, so this report does not declare the original trip a proven false positive or proven OOM.

The new input-processing stages retain physical available-memory and swap guards, unavailable-metrics failure handling, and the shared host lock. Commitment accounting remains recorded evidence, not a standalone process-kill criterion for those stages. The legacy heavy-publication guard has not been globally relaxed.

## 3. Initial data authority state

Before this pass's corrective changes:
- no September 26 scrape batch, queued scrape jobs or completed runs existed;
- latest promoted batch was 63 / September 25, complete, 167/167 successful;
- Global Market snapshot market_date remained September 25;
- Cosmic Eclipse dashboard market date and latest observed serving prices remained September 25;
- RIP statistics market date remained September 25;
- Explorer V2 daily coverage had 167 Sets computed through September 24;
- 37 maintained caches existed: 10 ready through September 24, 25 ready through September 22, and two failed through September 22;
- serving prepared generation 60c274ea-aed6-45b5-a701-ca0d29eb5f11 still had comparison_as_of September 22 and source_as_of sets/sealed September 22.

The prepared serving pointer was re-read during this pass. No later serving generation was found. Correctly retaining the last accepted generation is not the same as having a functioning automatic update path.

## 4. Source observations and serving prices are separate stages

After collection resumed, direct source-table checks found 735 September 26 observations for Ascended Heroes and 203 for Perfect Order, while their card_variant_price_current_v2 last_observed_date still ended September 25. At 22:42:34 UTC, September 26 had zero price_storage_v2_shadow_queue rows.

The inspected canonical projection service documents that public prices resolve through V2, and requires projection provenance covering the completed scrape timestamp. advance_price_projection_once enqueues completed scrapes and processes each Set through four existing RPC stages in separate transactions. The database-native shadow cycle now delegates processing to that application worker; simply enabling its old cron would not substitute for the staged processor.

Thus restarting collection alone was not sufficient to update the prices read by the product. This is an observed remaining handoff during recovery, not a claim that projection caused the initial absence of today's scrape.

## 5. Implemented and verified corrections

### Independent bounded collection

Source: .vm-ops/collection_recovery.py and test_collection_recovery.py.
Deployment trigger commit 7efcfe7f8169a817a45076f8bff09d84e477c123.
Controlled run 36276718925 / job 108501070009 passed 21 tests and installed the new collection-only schedule at 22:36:37 UTC.

- Canonical daily-batch creation remains idempotent and performs its existing preflight.
- Each invocation claims at most five scrape jobs, with a 120-second drain budget before taking another job and a 300-second outer command limit.
- The schedule checks current Phoenix date and does not start before 01:05.
- Checkpoints, an independent collection hold, cooldowns, and the global worker.lock are used.
- No existing public-data acceptance gate was bypassed and no business data was deleted.
- Both original incident holds and all 14 legacy paused schedules were preserved.
- The original crontab and restore backup were preserved; the canonical restore backup now includes the explicitly authorized input-stage schedules without enabling the old heavy jobs.

The first invocation completed five jobs and exited zero. The 22:42:29 UTC observer (run 36277140624 / job 108501977675) showed later scheduled collection had reached 15 completed jobs, an active worker, and no collection hold. SQL at 22:42:34 UTC showed 17 completed jobs. This proves progress beyond a one-time launch.

### Independent canonical serving-price projection

Source: .vm-ops/price_projection_recovery.py and test_price_projection_recovery.py.
Deployment trigger commit 5b33593dc2f76c64ccd591ac76f32ab640df0d8d.
Controlled run 36277391782 / job 108502665235 passed all 39 combined collection/projection tests and installed the price-projection schedule at 22:47:55 UTC.

- One Set per invocation through the EXISTING advance_price_projection_once staged application worker; the old monolithic queue RPC was not substituted.
- The global host lock serializes it with raw collection.
- Projection has separate hold/cooldown/progress state, so a projection failure does not automatically disable the next day's raw collection.
- Existing per-Set retry budgets and provenance checks are retained; terminal rows are not rearmed.
- The old heavy-publication hold stays present.

The first projection invocation exited zero. It enqueued 35 rows and completed one Set through all four canonical stages, with zero failed projections. SQL independently verified 159 serving-price rows for me30thCelebration now have last_observed_date September 26. The fact that an individual projection completed is NOT a whole-cohort publication verdict.

### Latest raw/projection progress

At 22:49:38 UTC, batch 64 / September 26 was running, 43/167 scrape jobs successful, zero failed, not yet promoted. The projection queue had one complete and 34 pending rows at that check; additional newly completed scrapes are enqueued on later projection invocations. The projection's first manual tick is verified; sustained scheduled throughput still requires observation.

Exactly two new guarded schedules were installed: collection and price projection. The 14 legacy schedules remain disabled. Runtime files are outside the Git checkout under /home/ubuntu/state/db-safety; source is retained on vm-ops-control. No new application main-branch merge is claimed by this pass.

## 6. Explicit remaining gaps

- Market/Set-page/Top-10 snapshot publishers and Explorer's projection/cache/prepared-generation handoff are STILL HELD. No new public Market or Explorer date is claimed.
- The old finish-recovery sequence is still blocked and must not be mistaken for an active automatic continuation. These new input stages do not silently release it.
- Complete today's source and canonical-price cohorts, then restore market-only publication and Explorer as independently checkpointed stages with their own acceptance checks. Do not put next-day collection behind their completion again.
- Repair the remaining invalid-column probes and handle the two failed maintained caches without weakening generation/date acceptance.
- Keep lightweight blocked-stage alerting independent of the expensive builders and their pause switch. This pass has not installed an external alert or sent a support request.
- Direct MCP/Windows work can still bypass host-local admission. No distributed queue or new DB authorization boundary is claimed.
- Future deployment/cron restoration must preserve the two independent input-stage entries and the held heavy-stage state. The canonical restore backup was updated, but a deployment using an unrelated old crontab template still requires reconciliation.

No database restart, backup restore, compute change, experimental shadow-cron activation, source-date relabeling, or publication-gate bypass was performed in this pass.
