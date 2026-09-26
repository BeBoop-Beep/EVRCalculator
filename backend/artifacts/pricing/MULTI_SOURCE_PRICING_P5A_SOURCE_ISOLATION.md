# P5A multi-source pricing source isolation

## Scope and inventory

The [machine-readable inventory](multi_source_price_consumer_inventory.json) classifies 116 consumers: 38 direct SQL functions, 15 views, 8 wrapper RPCs, and 55 backend files. Each has exactly one A–E classification. Historical TCGplayer-authority paths are source-locked. Explicit source-selection and source-dimensional storage remain multi-source; research and obsolete paths are marked separately. The inventory records original behavior, expected contract, repair, and proof for each source-blind defect.

The audit found source-blind reads beyond the initial canonical resolver and latest-by-condition view: root-set latest prices, Set Value as-of and daily history, card constituents and fallback, simulation current NM, market latest, top hits, variant metrics, nightly freshness, and backend raw-observation readers. Seven mirrored migrations, beginning with [canonical and latest](../../db/migrations/20260920140000_p5a_source_lock_canonical_and_latest.sql), add TCGPlayer predicates at these historical authority reads without changing variant choice, NM/USD requirements, return columns, or Price Storage V2's `(card_variant_id, condition_id, source, currency)` key. Backend readers were similarly filtered. The P4C estimator, isolated eBay table, labels, and generic Price Storage writes were not changed.

## Disposable PostgreSQL evidence

The [integration test](../../tests/integration/p5a_disposable_postgres.mjs) runs the real migration against disposable PGlite PostgreSQL with a schema fixture derived from production. It seeds TCGPlayer NM USD 100 on September 18 and newer eBayActiveAsk NM USD 140 on September 19 for the same variant. Both source rows coexist. Explicit source history reads return their own values. Canonical, latest-by-condition, market latest, simulation NM, root-set latest, Set Value as-of, daily constituents and fallback, top hits, variant metrics, daily Set Value history, and nightly freshness retain TCGPlayer authority. Removing the predicates makes the same fixture return eBay 140, proving that the test detects the prior defect.

Mutation cases cover newer, cheaper, more expensive, same-date/newer metadata, TCGPlayer absent, and eBay absent. No TCGPlayer-authority reader substitutes eBay when TCGPlayer is absent. The 33-card canonical fixture (15 eras plus high-value promos) and 20 latest-view rows match before and after exactly:

| Projection | Before SHA-256 | After SHA-256 |
| --- | --- | --- |
| Canonical, 33 cards | `3eed6d1c2f2d62b3769aa2f763df4edc20f8563e65bad7d72c3e963a56cc5c98` | same |
| Latest-by-condition, 20 rows | `21a320db3445c773b25dae1b80d29f354a402f5c412db1e744807758b06a7c2f` | same |

Production pre-migration [canonical](p5a_pre_migration_canonical_baseline.json) and [latest-view](p5a_pre_migration_latest_view_baseline.json) snapshots retain IDs, prices, source, dates, and selection reason. The original single migration included an in-transaction `EXCEPT ALL` check. Splitting removed that check because it could not span independent migration transactions. The production cohort was instead compared after all seven units; its result is recorded below.

## Performance, security, and tests

Production EXPLAIN showed the latest-by-condition lookup using the current-price primary key and local incremental sort. The source-filtered lookup uses the same key, including `source='TCGPlayer'`, with one estimated current row. The view retains its LATERAL lookup and `security_invoker=true`; no full observation-history window sort is introduced. The canonical path reads the current V2 table. Existing performance projections: 12 passed. Focused set-market/card-detail/P4C tests: 49 passed. Onboarding, refresh, scrape, and rip tests: 228 passed. P5A contract tests: 3 passed. Disposable PostgreSQL integration: passed.

All seven migration units are mirrored byte-for-byte and set `lock_timeout='5s'`. Existing view grants and `security_invoker` were preserved. No table RLS, source-dimensional key, public access, function return type, or mutation right was broadened. A wider legacy test selection had 159 failures due to an existing removed `public_read_client` fixture alias; the alias is absent at HEAD. The older real-source SQL unittest suite also fails under pytest because its `run()` override does not accept pytest's `result` argument. Those suites did not supply a P5A regression signal.

## Production application and remaining gate

The original 115,956-byte migration call returned HTTP 504. Before retry, production showed no migration ledger entry, no active P5A backend, no waiting lock, `statement_timeout=2min`, and `lock_timeout=0`. All 16 targeted functions/views were fingerprinted and lacked the proposed source locks; the V2 constituent function had its known pre-P5A MD5 `cab2e26e26e61a0fdddc1c2cafe17028`. This excluded an apparent partial source-lock application, though the preflight did not compare full definitions byte-for-byte with an archived pre-attempt dump. Gateway/statement timeout remains the likely 504 class; no live lock wait or dependency error was observed.

The unapplied full migration was replaced by seven ordered units `20260920140000` through `20260920140006`. Each applied successfully through the authorized Supabase migration API, with a ledger entry checked immediately after each. The units cover canonical/latest, root/as-of, V4/Set Value rows, market views/constituents, guard/top hits, metrics/history, and nightly freshness. Live post-apply function/view fingerprints changed for every target; V2 constituent MD5 is now the expected `756f4d28ea3710f59bb23f254ecd3580`. The direct authority views and resolvers contain the TCGPlayer lock; delegated functions retain their expected downstream calls. No active P5A migration session remained.

Production source distribution after application: observations 18,104,639 TCGPlayer; events 3,172,769 TCGPlayer; current 164,372 TCGPlayer; canonical latest 19,813 TCGPlayer. The six eBayActiveAsk estimates remain in their isolated table. The production latest-by-condition EXPLAIN uses `card_variant_price_current_v2_pkey` with `source='TCGPlayer'` and `currency='USD'`, followed by a local incremental sort over an estimated four rows. It does not scan or sort full observation history.

**Production exact zero-diff is not proven.** Against the saved pre-migration 33-card baseline, 31 cards matched exactly and two retained the same variant, condition, price, source, and selection reason but advanced `captured_at` from September 18 to 19. Against the saved 71-row latest-view baseline, 70 rows matched and one of those same variants advanced its captured/created timestamps. Current TCGPlayer observations for both variants have September 19 creation timestamps. The saved baseline itself was captured later that day, so those timestamps alone do not establish when the current projection advanced. Without an in-transaction baseline across the split units, the observed date changes cannot be attributed conclusively. Set Value/simulation/public end-to-end comparisons also remain incomplete. P5A therefore cannot claim the required exact production equivalence or P5B readiness.

The [P5B handoff dataset](p5b_source_comparison_handoff.json) contains the six frozen paired source estimates with canonical/variant identity, market dates, TCGplayer observation age and price, eBay estimator version, seller/listing depth, price ratio and differences, set/era/rarity, and price band. It does not select or fit a merge rule. P5B remains gated on successful production P5A application and validation.

Superseded by the forensic closure below (verdict at that point: `MULTI_SOURCE_PRICING_NOT_READY_PRODUCTION_ZERO_DIFF_UNPROVEN`).

## PRODUCTION ZERO-DIFF FORENSIC CLOSURE

Evidence gathered read-only against production (project TheIndex) on 2026-09-20. Same-instant diagnostics used non-persistent `pg_temp` objects inside a `DO` block that always rolled back.

### 1. The three mismatch rows

All three are Near Mint (`condition_id 4f8d1181-670e-4aea-937c-4d98d2e531a6`), TCGPlayer, USD. Price, source, variant, condition and selection reason are unchanged. Only the date fields moved.

| Surface | canonical_card_id | card_variant_id | Price | Baseline captured | Current captured |
|---|---|---|---|---|---|
| Canonical (baseline 2026-09-19 23:12:42 UTC) | e4b73b72-2882-436f-9d27-90b229185520 | 33aae8ca-8e63-406e-a672-c067a8dd27ca | 3.63 | 2026-09-18 | 2026-09-19 |
| Canonical | 58a01e34-87f7-4693-a763-c40f8c8cabc1 | 94fe980a-7a97-499e-9b76-07363f1c8b8b | 900.0 | 2026-09-18 | 2026-09-19 |
| Latest view (baseline 2026-09-19 23:16:35 UTC) | n/a | 33aae8ca-8e63-406e-a672-c067a8dd27ca | 3.63 | 2026-09-18 (created 2026-09-18 16:49:59.71581+00) | 2026-09-19 (created 2026-09-19 22:22:42.962716+00) |

The latest-view mismatch is the same physical variant (33aae8ca) as the first canonical mismatch. There are two distinct variants in total.

### 2. Raw TCGPlayer observation timelines

Table `card_variant_price_observations`, NM, source TCGPlayer. High and low prices are null throughout.

Variant 33aae8ca:

| id | market_price | captured_at | created_at (UTC) |
|---|---|---|---|
| e588c493-2e43-42f5-ad97-326821a458ce | 3.63 | 2026-09-17 | 2026-09-18 01:04:00.33 |
| 0bfd6ce5-3c82-49d9-a087-11ead6eb2c16 | 3.63 | 2026-09-18 | 2026-09-18 16:49:59.72 |
| **e0138455-7a40-4a11-8c2a-0115e4de6407** | **3.63** | **2026-09-19** | **2026-09-19 22:22:42.96** |

Variant 94fe980a: the price is 900.0 in every row from 2026-09-10 to 2026-09-19.

| id | captured_at | created_at (UTC) |
|---|---|---|
| 8bfa3bb7-b144-4124-9d30-ec45c9764953 | 2026-09-17 | 2026-09-18 01:06:44.89 |
| 4ca1a352-d37c-445c-b2ac-a4da03c7ea97 | 2026-09-18 | 2026-09-18 16:52:59.03 |
| **eb3e73db-8e75-4a3f-b6df-737d75878a47** | **2026-09-19** | **2026-09-19 22:25:19.27** |

For each variant, a legitimate newer TCGPlayer observation exists with the same price as its predecessor. Both are dated 2026-09-19. Both were created (22:22 and 22:25 UTC) before the baseline captures (23:12 and 23:16 UTC). They had not yet propagated to the projection when the baseline was taken (see section 3).

Earlier observations from 2026-09-10 onward were also reviewed and are omitted here. The 33aae8ca prices drift between 3.56 and 3.64 across the window.

### 3. Price Storage V2 provenance

`card_variant_price_current_v2` rows:

| Variant | event_id | effective_date | last_observed_date | last_observation_id | last_observation_created_at | updated_at |
|---|---|---|---|---|---|---|
| 33aae8ca | 3750454 | 2026-09-17 | 2026-09-19 | e0138455-... | 2026-09-19 22:22:42.96 | **2026-09-19 23:30:00.36** |
| 94fe980a | 1395160 | 2026-08-12 | 2026-09-19 | eb3e73db-... | 2026-09-19 22:25:19.27 | **2026-09-19 23:45:00.52** |

- Both current rows keep the same event and `source_observation_id`. For 33aae8ca the source is `e588c493` and the event was created 2026-09-18 02:15:00.
- No new price event was created, because the price was unchanged. The projection advanced only its `last_observation_*` and `last_observed_date` columns.
- Both the canonical resolver and the latest view read `last_observed_date` and `last_observation_created_at` from this table. That is the propagation path: raw observation, then the current-projection heartbeat, then `captured_at` and `created_at` in both readers.
- The refresh is `price-storage-v2-shadow-cycle` (pg_cron job 19, every 15 minutes). `updated_at` 23:30:00.36 and 23:45:00.52 match cron runs 8036 (23:30:00.358) and 8037 (23:45:00.522). Both succeeded.
- The cycle processed the backlog in chunks. Rows updated per 15-minute slot: 22:00 6000, 22:15 4475, 22:30 4389, 22:45 3322, 23:00 974, 23:15 4846, 23:30 5946, 23:45 3153, 00:00 794. Neither variant was reached before the baseline capture at 23:12.

### 4. Ingestion window and the migration timeline

- Raw TCGPlayer observations for both variants were created at 22:22 and 22:25 UTC on 2026-09-19. Earlier rows for the same variants were created at about 16:50 on 2026-09-18 and 01:05 on 2026-09-18, so this is the normal recurring ingestion.
- Ledger versions for the seven split units are `20260920000042`, `000054`, `000101`, `000112`, `000113`, `000115` and `000117`. These are Supabase API apply stamps, taken as UTC. The first migration therefore landed at 00:00:42 UTC on 2026-09-20, after both projection advances (23:30 and 23:45 on 2026-09-19).
- `card_variant_price_current_v2.updated_at` for both variants (23:30 and 23:45 on 2026-09-19) predates every ledger entry.
- The migrations perform no top-level DML. The `INSERT`, `DELETE` and `TRUNCATE` statements found in units 4 and 5 are inside function bodies and do not run at apply time. Only function and view definitions were replaced. No row in `card_variant_price_current_v2` or the observations table was written by any migration.
- The earlier 115,956-byte attempt (HTTP 504) left no ledger entry and applied no source locks (preflight in the previous section).
- Scrape batch and job correlation was not queried, because raw observation provenance is conclusive.

### 5. Same-instant old-vs-new canonical comparison

- The old logic was derived from the live production definition of `get_pokemon_canonical_card_market_prices_latest_for_set_v2_shadow(uuid)` (which Postgres names `..._v2_shad` after 63-byte identifier truncation). The transform removed only the line `AND current_row.source = 'TCGPlayer'`, and the transform asserted the exact length delta.
- A diff of migration `20260906180118` (last pre-P5A definition) against `20260920140000` also shows exactly that one added line.
- The comparison ran as one SQL statement over all 175 canonical sets, so old and new share one snapshot. It used `EXCEPT ALL` in both directions over the complete output row: canonical_card_id, set_id, pokemon_tcg_api_card_id, legacy_card_id, card_variant_id, condition_id, printing_type, market_price, captured_at, source and price_selection_reason.
- Result: old 19,856 rows, new 19,856 rows, **old minus new = 0, new minus old = 0**. All rows are TCGPlayer, and all 7 selection reasons are present. This does not depend on the 33-card fixture.
- The public wrapper only adds a catalog-role filter and delegates to this function.

### 6. Same-instant old-vs-new latest-view comparison

- The old logic was the live view definition with only `AND (current_row.source = 'TCGPlayer'::text)` removed. A diff of migration `20260906032734` against `20260920140000` shows the same single added predicate.
- The comparison ran as one statement, with `EXCEPT ALL` in both directions over every column: card_id, set_id, set_name, card_name, card_number, rarity, variant_id, printing_type, special_type, edition, condition_id, condition, market_price, high_price, low_price, currency, source, captured_at and created_at.
- Result: old 164,372 rows, new 164,372 rows, **old minus new = 0, new minus old = 0**. All rows are TCGPlayer.

### 7. Current source distributions

| Object | Source rows |
|---|---|
| `card_variant_price_current_v2` | 164,372 TCGPlayer USD |
| `pokemon_canonical_card_market_prices_latest` | 19,813 TCGPlayer |
| `card_market_usd_latest_by_condition` | 164,372 TCGPlayer USD |
| `card_variant_price_events_v2` | 3,172,769 TCGPlayer |

- No row in the current or events tables has an eBay source. The observation count (18,104,639 TCGPlayer) is carried over from the previous section and was not recounted.
- With one source present, adding `source = 'TCGPlayer'` selects the same row.
- The canonical latest view shows 19,813 rows while the resolver function returns 19,856. The difference is the market-instrument role filter in the wrapper plus view definition; it is not a source effect. This was not investigated further.

### 8. Final adjudication

- **A. Same-instant old-vs-new:** exactly zero semantic differences. This holds for the canonical resolver (19,856 rows) and the latest view (164,372 rows).
- **B. Historical timestamp differences:** each of the two variants had a legitimate newer TCGPlayer observation. Both were created before the baseline (22:22 and 22:25 UTC), but the projection heartbeat applied them only at 23:30:00 and 23:45:00 UTC (cron runs 8036 and 8037). Both times fall after the baseline capture and before the first migration (00:00:42 UTC on 2026-09-20). Prices, event ids and source observation ids were unchanged.
- No price, source, variant, condition or selection reason changed.
- The original 31/33 and 70/71 mismatch is therefore live-data drift, not a migration semantic difference. The source-lock contract was not weakened.

Caveats: the exact time of the earlier post-migration comparison was not recorded. The causal claim rests on the projection updating before any migration was applied, which makes that time immaterial. The ledger-time reading assumes Supabase stamps versions at apply time (UTC). Set Value, simulation and public end-to-end comparisons remain outside this closure.

MULTI_SOURCE_PRICING_SOURCE_ISOLATION_COMPLETE_READY_FOR_P5B
