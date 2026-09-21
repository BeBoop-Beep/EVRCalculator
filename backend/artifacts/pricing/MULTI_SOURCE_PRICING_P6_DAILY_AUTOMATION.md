# P6: daily eBay + multi-source shadow pipeline

Date 2026-09-20 (America/Phoenix). Policy `pokemon_multi_source_card_price_v1` and the eBay estimator `ebay_active_ask_lower3_seller_median_v1` were not modified; the pipeline calls the frozen functions. Nothing touches canonical, Set Value, simulation, Explorer or public pricing, and no Fair Value work was done.

**Outcome in one line:** the pipeline is built, tested, deployed to the database, run once in production and replayed idempotently. **The VM schedule is not installed**, because SSH to the VM refused the connection (host key changed) and the P6 code is not on the VM. Details in §9.

## 1. Applied migrations

Three migrations, each mirrored byte-identically in `backend/db/migrations` and `supabase/migrations`, exercised first on a disposable PostgreSQL (PGlite) that reproduces Supabase's inherited default privileges, then applied to production. Supabase stamps its own ledger versions when applying, so the ledger versions differ from the file prefixes (same as P5A).

| File | Adds |
|---|---|
| `20260921000000_p6_pipeline_runs_and_browse_budget_ledger.sql` | `pokemon_multi_source_pricing_runs_v1` (one run per market date and policy; stage/status checks; stores the target manifest and receipt), `ebay_browse_request_ledger_v1` and the `SECURITY DEFINER` RPC `reserve_ebay_browse_request_v1` (search_path pinned, execute for service_role only) |
| `20260921010000_p5b_multi_source_card_prices_shadow_v1.sql` | `pokemon_multi_source_card_prices_v1`, the P5B table amended before first apply with `pipeline_run_id` and `ebay_estimate_id` |
| `20260921020000_p6_restrict_ebay_estimate_privileges.sql` | P4C privilege correction (§2) |

**P6A audit of the shadow table:** the columns and states match the frozen P5B contract exactly (frozen state names are kept; the brief said to keep them if they differ). Column names are the truthful equivalents of the brief's list (`ebay_price` for `ebay_active_ask_price`, `tcgplayer_date` for `tcgplayer_observed_date`). Table checks make a blend, a THIN fallback, an eBay price without an estimate row, and a wrong-provider price unrepresentable. It is a derived table, not a provider table.

Verified immediately after applying: shadow, runs and ledger tables exist; RLS on for all four; RPC is `SECURITY DEFINER` and not executable by anon; `card_variant_price_current_v2` has 0 non-TCGPlayer rows; `pokemon_canonical_card_market_prices_latest` has 19,813 rows, all TCGPlayer.

## 2. Corrected P4C privileges

Inspection: the estimate table's only writer was the one-off P4C insert. No correction or replacement workflow exists, and the unique `(variant, condition, market_date, estimator_version)` key already makes a changed replay fail. A corrected estimate is a new estimator version, not a mutation, so **no repair RPC was added**.

Before: `service_role` held SELECT, INSERT, UPDATE, DELETE, TRUNCATE (Supabase default privileges; contradicting the P4C document's insert-only claim). After (`revoke all … from public, anon, authenticated, service_role`, then `grant select, insert`): service_role SELECT and INSERT only; UPDATE, DELETE, TRUNCATE, REFERENCES and TRIGGER denied; anon and authenticated have nothing; RLS unchanged. Confirmed in the disposable database before and after, and against production after applying.

## 3. Orchestrator

`python -m backend.scripts.run_daily_multi_source_card_pricing` (logic in `backend/pricing_pipeline/`). One command runs: resolve market date → build P1-style targets → verify budget → adaptive P2/P4A collector → P3 evidence persistence → P4C estimates → P5B multi-source rows → validate → receipt. Options: `--dry-run`, `--market-date`, `--resume` (default) / `--no-resume`, `--max-requests`, `--json`, `--state-dir`, `--no-require-tcg-ready`. Exit codes: 0 complete, 1 failed (resumable), 2 partial, 75 waiting for the TCGplayer batch, 3 already running. Credentials come from the existing env files and are never printed.

Persistence mapping: the adaptive collector's getItem decisions land in the existing P3 tables. Only `ENGLISH_PRICE_ELIGIBLE` listings (English-positive, NM-compatible, fixed price, USD landed ask) become listing rows; every hydrated decision feeds the per-card summary; raw provider responses stay in the state directory. THIN and INSUFFICIENT depth is stored as summary diagnostics and never gets a price, because the estimate table rejects non-SUFFICIENT rows.

## 4. Request-budget authority (P6G)

**The local `ebay_browse_daily_usage.sqlite3` is not adequate** as the authority: the same application key was used from this development machine and would be used from the VM, and a per-host file cannot bound the total. The authority is now the database: `reserve_ebay_browse_request_v1(day, limit)` atomically increments `ebay_browse_request_ledger_v1` before every request (search, detail, and each retry), and raises `EBAY_BROWSE_BUDGET_EXHAUSTED` at the limit. A crash or restart cannot reset it, and a second host shares it. If the database is unreachable the pipeline fails closed (`BUDGET_AUTHORITY_UNAVAILABLE`).

- Day boundary: America/Phoenix (UTC−7, no DST), the same clock as the VM crontab, the scrape batches and market dates. The ledger cap is the hard-coded 1,000; a caller cannot raise it above that.
- Ownership: service_role can only call the RPC and SELECT the table; it has no INSERT/UPDATE/DELETE.
- Resume: the per-run cap is `min(run cap, requests still unspent today)`; requests already spent by completed targets count toward it.
- Recovery: state is in the database (covered by its backups); no per-host file needs restoring. A tolerated inaccuracy: a request reserved but not sent (crash between reserve and send) is counted, which errs on the side of fewer requests.
- Seeding: the 836 requests spent on 2026-09-20 during P5B (recorded only in the dev machine's UTC-dated sqlite file) were inserted into the ledger before the first run. The sqlite ledger is a test/offline fallback (`--budget-backend sqlite`) and is gitignored.

## 5. Target allocation (P6I)

Priority tiers, each capped (35/30/10/10/10%) so none starves the rest, unused capacity then spent in priority order: (1) missing TCG price with a resolved variant, opening-eligible or chase; (2) economically important (≥ $50 or chase rarity ≥ $5, rotated by date); (3) cards with a prior MODERATE/SEVERE disagreement; (4) stale/aging ≥ $20; (5) movers; (6) rotation over opening-eligible non-low-rarity cards. Missing cards with no resolvable variant (513 promos and 59 main cards) are never targeted. Capacity is planned from the median measured requests per completed target (7.0 default; the first run measured 7.14) at 90% of the requests still available, and the 1,000 cap is enforced independently at collection time. Same inputs give the same manifest and fingerprint (tested).

## 6. State and resume contract (P6J/P6K)

`pokemon_multi_source_pricing_runs_v1` holds one run per market date and policy: stage (`INIT` → `TARGETS_BUILT` → `COLLECTION_RUNNING` → `COLLECTION_COMPLETE` → `EVIDENCE_PERSISTED` → `ESTIMATES_BUILT` → `MULTI_SOURCE_BUILT` → `VALIDATED` → `COMPLETE`), status (`RUNNING`, `WAITING`, `PARTIAL`, `FAILED`, `COMPLETE`), failure code, request counts, the manifest, and the receipt. A failure keeps its last completed stage; the next invocation resumes at the first incomplete stage. Collection writes one fsynced checkpoint line per target, so a resume re-fetches nothing that finished (a crashed target is redone; its requests stay counted). A COMPLETE date replays as a no-op returning the stored receipt.

Fail-closed gates: migration missing; TCGplayer batch not COMPLETE for the date (WAITING, no eBay calls); no budget; no targets; manifest fingerprint mismatch; collector attempted < 80% of targets or > 5% failed requests (PARTIAL, nothing persisted); evidence persistence/summary mismatch; estimator depth/summary or version mismatch; estimate not reproducible from persisted evidence; policy version/fingerprint drift; shadow row conflict; any non-TCGPlayer row in generic current pricing.

## 7. Observability (P6L)

Each run's receipt records: market date, target count and tier mix, Browse calls, failures and retries, remaining budget, raw listings, identity-qualified listings, English-qualified, NM-qualified (eligible) listings and per-state decision counts, SUFFICIENT/THIN/INSUFFICIENT counts, multi-source decision counts, gap fills, runtime, last successful stage, and a receipt fingerprint. It is stored in the run row and in the state directory.

## 8. Health checks (P6M)

`backend/pricing_pipeline/health.py` and `backend/scripts/check_multi_source_pricing_health.py`: run freshness, target freshness, request-budget health, evidence freshness, estimator freshness, shadow freshness, source guard, policy/estimator drift. A run is due after 08:00 Phoenix. eBay-side problems return `degraded_multi_source_coverage` and never mark canonical pricing unhealthy; the only CRITICAL check is a non-TCGPlayer source in canonical or generic current pricing, and the CLI exit code follows that alone. A `sentinel_results()` adapter maps checks to Sentinel `CheckResult` objects (WARNING for eBay, CRITICAL only for the source guard). **The checks are not registered in the Sentinel registry or dispatcher**: that is shared alerting code and registration is left for a deliberate change. Live result against production: all eight checks `ok`.

## 9. VM schedule (P6N/P6Q): not installed

Audit from the repository: the VM host runs America/Phoenix. The scrape batch is created at 01:05 and, in a normal week, completed by about 02:00 (batches 09-08 to 09-15 all finished 01:54–02:00). The 06:00 publication fallback and the 06:15 Market Explorer publication are the heavy window. Production scrape history since 09-17 is irregular (batches created 09:21, 14:54, 15:49, 16:59 Phoenix, and none for 09-16). The price-storage-v2 projector (pg_cron, every 15 minutes) lags a completed scrape by roughly an hour or more.

Chosen schedule (`infra/oracle/multi-source-pricing.crontab`, Phoenix time, `flock -n /tmp/multi-source-pricing.lock`, log `backend/logs/multi_source_pricing.log`, explicit `EVR_PRICING_STATE_DIR`, repository venv, `--resume`): a primary run at **04:10**, and an hourly retry at :40 in hours 04, 05 and 07–20 (none in hour 06). The pipeline exits 75 (no work, no eBay calls) until the day's scrape batch is COMPLETE, so late batches are still picked up the same market date, and a COMPLETE date is a cheap no-op. A daily 09:20 health report is included. The time was derived from the documented schedule and the scrape history, not from the example times in the brief. It is scheduling via the VM's cron, not pg_cron, and the unit tests assert both.

**What blocked installation:** the connection to `ubuntu@129.146.189.32` failed strict host-key checking ("REMOTE HOST IDENTIFICATION HAS CHANGED"). I did not bypass that check, so the live VM crontab could not be audited and nothing was installed. Separately, the P6 code exists only in this checkout; the VM cannot run it until it is pushed and pulled, and a push was not authorized. The verify-first installer `infra/oracle/install_multi_source_pricing_cron.sh` (checks code present, timezone, dry run, lock; `--apply` installs idempotently between markers) is ready. The operator needs to confirm the new host key, deploy, then run it. Not verified because they need the VM: scheduler entry present, next run resolvable, runtime-user environment access, log writability. The in-process lock is tested; a real cron `flock` was not exercised.

## 10. First production run (P6O)

Run `93968519-7020-41d6-aaf2-6c8abeb3eb5a`, market date 2026-09-20, receipt `p6_first_production_run_receipt_2026-09-20.json` (fingerprint `20d4be2a…`). Exit 0, every stage in order, 130 seconds, 0 failures, 0 retries.

- **Budget:** 836 of today's 1,000 requests had already been spent in P5B, so 164 remained; the selector planned 21 targets (7 missing-price gaps, 6 economically important, 2 stale high-impact, 6 rotation) and the run used **150 requests**, ledger 836 → 986, 14 left. This is far below the ~130-target scale of a normal day; scale behaviour in production is untested.
- **Collection and evidence:** 1,538 raw listings; 127 identity-qualified; 59 ENGLISH_PRICE_ELIGIBLE, 54 CONDITION_EXCLUDED, 14 LANGUAGE_UNRESOLVED hydrated decisions; 59 listing rows and 21 per-card summaries persisted.
- **Estimates:** SUFFICIENT 9, THIN 1, INSUFFICIENT 11; 9 estimate rows, each with ≥ 5 contributing evidence rows that exist in the evidence table; estimates replay from persisted evidence to the same fingerprint.
- **Multi-source rows (21):** TCGPLAYER_PRIMARY 6, EBAY_CORROBORATED 2, MODERATE_DISAGREEMENT 1, SOURCE_DISAGREEMENT 3, STALE_RETAINED 2, **EBAY_ACTIVE_ASK_FALLBACK 3**, UNPRICED 4, AGING 0. Fallbacks: $2.99, $3.49, $15.00, each 5 sellers. The three SEVERE cases are all sub-$8 cards. Stale TCG cards with eBay evidence were not replaced. No blend: every selected price equals the TCG or eBay value.

## 11. Replay / idempotency (P6P)

Re-running the completed date returned the stored receipt (`idempotent_replay: true`), identical receipt fingerprint and decisions, made no eBay call (ledger stayed 986), and added no evidence, estimate, shadow or run row. Crash and resume were exercised in tests only (not in production): a simulated crash after 40 requests leaves the counter at 40, the resumed run re-fetches no completed target and finishes with identical fingerprints, and rewinding the state machine to each of four later stages re-runs without new network calls or duplicate rows.

## 12. Canonical and public safety proof

Baseline and after counters (`pg_stat_user_tables`) for the provider, canonical, Set Value and simulation tables show no change from this run: `card_variant_price_observations` (ins 30), `card_variant_price_events_v2` (ins 139), `card_variant_price_current_v2` (upd 1002), the card, variant and canonical-card tables, all `simulation_*` tables and the Set Value history and snapshot tables are identical before and after. There are no non-TCGPlayer rows in observations or events (from 2026-09-19), in current, or in canonical latest. The only new writes are the P3 evidence tables, the estimate table, the run table and the shadow table.

**One counter moved and is attributed, not hidden:** `pokemon_canonical_card_market_prices_latest` insert/delete counters rose 2,387 → 3,328 during the run. The only writer of that table in the database is the existing per-set refresh function `refresh_pokemon_canonical_card_market_prices_latest_for_set`, fed by the TCGplayer projector; rows dated 2026-09-20 rose 3,767 → 10,710 in the same window, the total stayed 19,813, and all rows are TCGPlayer. The pipeline only reads that table (a test asserts it has no write path to provider or canonical tables). I did not prove a negative about the concurrent refresh beyond that.

## 13. Tests

`backend/tests/unit/pricing_pipeline/test_daily_multi_source_pipeline.py` (38 tests, one of which needs PGLITE_PACKAGE) plus `backend/tests/integration/p6_disposable_postgres.mjs`, run from pytest when `PGLITE_PACKAGE` is set. Combined with the frozen-policy, P4C, P4A and P5A suites: **79 passed** in one run with PGlite (this run also included the P4B evaluation tests). Coverage: migrations and mirroring; P4C grants (before and after, in Postgres); RLS and anon denial; the budget RPC (atomic, exhaustion, limit above 1000 rejected, direct mutation denied); sqlite budget persistence across restarts; the Phoenix day boundary; selector determinism, tiers and identity-gap exclusion; state machine and stage resumes; crash/resume budget preservation; evidence, estimate and shadow idempotency and conflict; TCG primary, stale retained, eBay fallback, THIN never filling, no blend, no carry-forward across days; fail-closed gates; provider/canonical write isolation; single-instance lock; cron file rules; degraded-eBay health semantics. Limits: the pipeline's unit tests use an in-memory store, so the Supabase store paths were exercised by the live run only (create, resume-free happy path, replay).

## 14. Final handoff document

`MULTI_SOURCE_PRICING_V1_FAIR_VALUE_HANDOFF.md`.

MULTI_SOURCE_PRICING_NOT_READY_VM_SCHEDULE_NOT_INSTALLED
