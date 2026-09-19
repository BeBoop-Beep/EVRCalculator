# P5A multi-source pricing source isolation

## Scope and inventory

The [machine-readable inventory](multi_source_price_consumer_inventory.json) classifies 116 consumers: 38 direct SQL functions, 15 views, 8 wrapper RPCs, and 55 backend files. Each has exactly one A–E classification. Historical TCGplayer-authority paths are source-locked. Explicit source-selection and source-dimensional storage remain multi-source; research and obsolete paths are marked separately. The inventory records original behavior, expected contract, repair, and proof for each source-blind defect.

The audit found source-blind reads beyond the initial canonical resolver and latest-by-condition view: root-set latest prices, Set Value as-of and daily history, card constituents and fallback, simulation current NM, market latest, top hits, variant metrics, nightly freshness, and backend raw-observation readers. The mirrored [migration](../../db/migrations/20260919231000_lock_tcgplayer_price_reads.sql) adds TCGPlayer predicates at these historical authority reads without changing variant choice, NM/USD requirements, return columns, or Price Storage V2's `(card_variant_id, condition_id, source, currency)` key. Backend readers were similarly filtered. The P4C estimator, isolated eBay table, labels, and generic Price Storage writes were not changed.

## Disposable PostgreSQL evidence

The [integration test](../../tests/integration/p5a_disposable_postgres.mjs) runs the real migration against disposable PGlite PostgreSQL with a schema fixture derived from production. It seeds TCGPlayer NM USD 100 on September 18 and newer eBayActiveAsk NM USD 140 on September 19 for the same variant. Both source rows coexist. Explicit source history reads return their own values. Canonical, latest-by-condition, market latest, simulation NM, root-set latest, Set Value as-of, daily constituents and fallback, top hits, variant metrics, daily Set Value history, and nightly freshness retain TCGPlayer authority. Removing the predicates makes the same fixture return eBay 140, proving that the test detects the prior defect.

Seven mutation cases cover newer, cheaper, more expensive, same-date/newer metadata, TCGPlayer absent, eBay absent, and the migration's in-transaction rejection of a deliberately changed cohort price. No TCGPlayer-authority reader substitutes eBay when TCGPlayer is absent. The 33-card canonical fixture (15 eras plus high-value promos) and 20 latest-view rows match before and after exactly:

| Projection | Before SHA-256 | After SHA-256 |
| --- | --- | --- |
| Canonical, 33 cards | `3eed6d1c2f2d62b3769aa2f763df4edc20f8563e65bad7d72c3e963a56cc5c98` | same |
| Latest-by-condition, 20 rows | `21a320db3445c773b25dae1b80d29f354a402f5c412db1e744807758b06a7c2f` | same |

Production pre-migration [canonical](p5a_pre_migration_canonical_baseline.json) and [latest-view](p5a_pre_migration_latest_view_baseline.json) snapshots retain IDs, prices, source, dates, and selection reason. Ordinary TCGPlayer captures continue to advance between reads; the migration therefore contains an in-transaction `EXCEPT ALL` zero-diff check over the cohort so that capture drift cannot be mistaken for a migration effect.

## Performance, security, and tests

Production EXPLAIN showed the latest-by-condition lookup using the current-price primary key and local incremental sort. The source-filtered lookup uses the same key, including `source='TCGPlayer'`, with one estimated current row. The view retains its LATERAL lookup and `security_invoker=true`; no full observation-history window sort is introduced. The canonical path reads the current V2 table. Existing performance projections: 12 passed. Focused set-market/card-detail/P4C tests: 49 passed. Onboarding, refresh, scrape, and rip tests: 228 passed. P5A contract tests: 3 passed. Disposable PostgreSQL integration: passed.

The mirrored migration files are byte-identical (115,956 bytes). Existing view grants and `security_invoker` were preserved. No table RLS, source-dimensional key, public access, function return type, or mutation right was broadened. A wider legacy test selection had 159 failures due to an existing removed `public_read_client` fixture alias; the alias is absent at HEAD. The older real-source SQL unittest suite also fails under pytest because its `run()` override does not accept pytest's `result` argument. Those suites did not supply a P5A regression signal.

## Production application and remaining gate

The authorized `lock_tcgplayer_price_reads` production migration call returned HTTP 504. Immediate verification showed **no migration history entry** and the production canonical resolver still lacked the TCGPlayer source predicate. Production therefore remains unmodified by P5A. Post-production zero-diff, production source-distribution checks, and public Set Value/simulation checks remain open. The local passing tests are not production completion.

The [P5B handoff dataset](p5b_source_comparison_handoff.json) contains the six frozen paired source estimates with canonical/variant identity, market dates, TCGplayer observation age and price, eBay estimator version, seller/listing depth, price ratio and differences, set/era/rarity, and price band. It does not select or fit a merge rule. P5B remains gated on successful production P5A application and validation.

MULTI_SOURCE_PRICING_NOT_READY_PRODUCTION_MIGRATION_HTTP_504
