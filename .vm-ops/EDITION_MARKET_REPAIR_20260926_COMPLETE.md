# Edition Market recovery — September 26, 2026

## Outcome and scope

The Market Set Value snapshot is published through September 26. All 15 currently certified edition markets are current; six genuinely incomplete edition markets remain explicitly unavailable. The public unauthenticated Market API was verified, not just the database writer. This is Market/edition-path completion, NOT a claim that the separately held Explorer prepared generation, Set-page publication, simulations or all 14 legacy schedules have recovered.

Latest public proof: September 27 02:08:15 UTC = September 26 19:08:15 America/Phoenix. REST endpoint https://evrcalculator.onrender.com/explore/set-value-market returned HTTP 200 in 1464 ms, market date September 26, 167 market identities.

## Changes shipped

1. Complete edition-history RPC paging: ordered set_id/market_scope/market_date, bounded 256-row requests, exact total-count validation, actual returned-count cursor advancement, duplicate/order/range checks and failure on incomplete reads. No global API cap increase.
2. Explicit one-root/one-date edition history materialization. Prices and observation provenance are bounded by the requested date. A separately read raw-observation oracle must exactly equal V2 prices/provenance before history is written. Exact-date member scrape/projection provenance and approved/promoted source dates are required. No edition fallback, no source-date relabeling.
3. The canonical Market builder now refreshes edition history before reading it and requires every certified edition's last date to match the publication date. Missing-coverage and existing source-review policies remain intact.
4. Independently scheduled source-gated Market publication. It waits for all completed source/projection Sets, repairs missing canonical root histories through existing routines, runs the canonical Market index/quality path, and publishes/reads back Market and edition data. It uses the same host resource-admission lock as collection/projection, stage-local failure state and cooldowns, and physical-resource checks. A Market failure does not disable next-day raw collection.
5. Fixed Python 3.10 timestamp compatibility in the existing projection gate and the Market worker. PostgreSQL timestamps such as .13337+00:00 were valid but rejected by that Python version; the old gate caught ValueError and silently omitted affected source jobs. Fractional seconds are right-padded to six digits without changing the instant. The live gate now sees all 167 source Sets, with 167 current projections, ready=true. Count/provenance checks were not weakened.

## Repository and production deployment

PR #390 merged into main, merge SHA 71d2e97bf3bd26de97687598a07ae194e416d029. Tested edition source SHA 4ad9dad03d6d5d60f289476c57585627ad290ee4.

PR #392 merged into main, merge SHA a5c2d86583ba0ea9db073399312bcfeec8641f04. Tested timestamp source SHA 975f7276c69750fcd1af8e22c0e70eee5282e8e5.

The additive migration is applied and mirrored under its ACTUAL Supabase version:
20260927014248_add_dated_edition_history_refresh.sql in supabase/migrations and backend/db/migrations. Do not reapply the initial pre-alignment filename.

Only the reviewed application files were overlaid on the VM; unrelated working files were preserved. Production VM HEAD after the final patch is 9e53e6de923cf788da9358e242cd87270a653efb. The app changes also exist in canonical main, so a normal update to current main retains them.

Runtime Market worker: /home/ubuntu/state/db-safety/market_publication_recovery.py.
State: /home/ubuntu/state/db-safety/market-publication.
Shared lock: /home/ubuntu/state/db-safety/worker.lock.
Schedule: 3-59/5 * * * *.
Sources, tests and installation workflow are retained on vm-ops-control.

## Validation runs and corrections

- Explicit hosted CI 36286201760 initially passed 167 regression tests and 11 disposable PostgreSQL 17 tests.
- Migration-alignment rerun 36286578116 passed the same suite; SQL contents unchanged.
- Final CPython 3.10 CI 36287180177 / job 108530032751 passed 181 regression tests plus 11 disposable PostgreSQL 17 tests.
- Final VM compatibility/deployment run 36287456620 / job 108530804349 passed 23 ops tests on the VM's Python 3.10.12, then the live full-source gate and publication.
- These last suites contain 215 tests in total; repeated earlier runs are not counted again.
- Generated PR workflows showing action_required were not represented as passed. The explicit isolated workflows above supplied actual test evidence; normal merge API accepted both PRs without a policy bypass.

The first independent Market tick after schedule installation encountered the timestamp ValueError before any September 26 builder work. That failure was NOT declared success. After the reproduced compatibility fix was tested and deployed, only its known failed-command cooldown was archived for a new attempt. No resource hold, global incident hold, unrelated lane state or source record was cleared.

## Historical repair and publication evidence

Read proof: run 36286650291 / job 108528571751 returned all 1458 rows for the formerly truncated four-root history batch. Jungle Unlimited and Neo Destiny Unlimited both had certified September 24 endpoints.

September 25 history repair: run 36286680572 / job 108528656249 completed ten roots/21 scopes with exact raw/V2 parity; 15 scopes certified, six incomplete. Market was republished at 01:50:45.756285 UTC with all certified scopes current through September 25.

September 26 final publication: run 36287456620 / job 108530804349:
- Live projection readiness: expected 167, complete 167, ready true.
- Existing canonical root coverage and rollout preparation completed.
- Canonical Market quality passed READY with 156/156 qualifying roots.
- Canonical raw/top-10 market index builder wrote two daily index rows; no warnings.
- Market snapshot persisted at 2026-09-27 02:06:07.998585 UTC.
- Readback completed at 02:06:09.102793 UTC: 21 edition entries, 15 certified/current, six unavailable; exit code zero.

Independent read-only SQL at 02:07:06.738607 UTC verified:
- September 25 receipts: 10 roots, 21 scopes, 15 certified, raw_v2_equal=true.
- September 26 receipts: 10 roots, 21 scopes, 15 certified, raw_v2_equal=true.
- Global Market date September 26, root count 156, market count 167.
- 146 Standard markets current September 26.
- Seven 1st Edition markets current September 26, three unavailable.
- Eight Unlimited markets current September 26, two unavailable.
- One Shadowless market unavailable.
- Jungle Unlimited current value 1096.71, history endpoint September 26; no May 4 truncation.
- Neo Destiny Unlimited current value 12939.01, history endpoint September 26; no false unavailability.

A separate SQL join of public edition entries to the dated history rows verified all 15 current entries have EXACTLY equal values, certified_on_date=true, and September 26 dates. All six unavailable entries have null public current values.

## Automatic continuation, not just a manual run

Observe Recovery run 36287622485 / job 108531269825 at 02:08:14 UTC confirmed:
- one collection schedule, one price-projection schedule, one Market-publication schedule;
- the Market schedule is enabled and no Market-stage hold or error file exists;
- the AUTOMATIC 02:08 Market cron invocation ran after the manual recovery;
- cron.log says stage=already_verified_current for September 26;
- its command receipt has exit_code=0, failures=0;
- no redundant historical rebuild occurred on that unchanged-source invocation;
- the public Market API exposes the same September 26 edition values/dates.

The older generic observer recognizes only the two input schedules; the added observe_market_recovery.py explicitly verifies all three. Do not mistake the older recognized-input count for total active schedules.

## Health evidence

PostgreSQL start time remained 2026-09-26 03:47:00.323649 UTC throughout recovery. SQL reported no recovery and no other active queries at the final probe.

The 01:46–02:09 UTC log query returned 950 successful edge requests, zero edge 5xx, zero statement timeouts and zero database-interruption records (latest ingested event 02:08:14.507 UTC).

Latest Market resource evidence at 02:08:01.993546 UTC: 809332736 available bytes, pg_up=1, OOM counter zero, stop_reason=null. This is successful recovery/short-window operational evidence, not a guarantee that every future workload fits or that the historical host-level outage cause is proven.

## Preserved limitations and next ownership boundary

The following six markets remain unavailable for a real coverage/identity issue, not stale-publisher or pagination failure:
- Base 1st Edition, Base Unlimited, Base Shadowless.
- Neo Destiny 1st Edition.
- Neo Revelation 1st Edition and Unlimited.

Base source inspection found 101 legacy Base variants with edition=NULL (15 holo/86 non-holo). They were not guessed into Unlimited, Shadowless or 1st Edition. Existing exact-scope metadata yielded only one priced first-edition canonical card and no Unlimited/Shadowless coverage. Other incomplete scopes lack full required coverage. A separate source-identity/coverage repair is needed; the new history writer records uncertified rows honestly and the public builder withholds their values.

Existing source-review history holds were not removed. Separate price_storage_v2_scoped_release_gate remains disabled; its unaccepted replacement pipeline was not activated. The original global incident hold and 14 paused legacy schedules remain intact. The old failed monolithic recovery receipt is historical, not an active continuation.

Broader Explorer prepared generation, individual Set-page snapshots, simulation/RIP refresh and unrelated maintenance are NOT certified current by this Market-only change. No alert automation or support request was created. Direct external SQL/Windows jobs remain outside the host-local lock unless explicitly integrated.
