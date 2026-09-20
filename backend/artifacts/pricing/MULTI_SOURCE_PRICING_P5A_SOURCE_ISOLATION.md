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

MULTI_SOURCE_PRICING_NOT_READY_PRODUCTION_ZERO_DIFF_UNPROVEN
