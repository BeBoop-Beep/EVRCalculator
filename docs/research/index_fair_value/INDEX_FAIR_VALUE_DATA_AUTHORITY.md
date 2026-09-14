# inDex Fair Value — data authority

Live read-only audit date: 2026-09-11 America/Phoenix. Dataset fingerprint: `0e7b04f1119ce525fbe387b50b523ac580aa7a14c758e5d16487a334969825d9`.

## Target path

`card_variant_price_observations` → canonical legacy/API identity → `card_variants` physical printing → Near Mint condition → Price Storage V2-backed canonical resolver → `pokemon_canonical_card_market_prices_latest`.

The canonical table holds one selected positive Near Mint USD physical variant per canonical checklist card, with `card_variant_id`, `condition_id`, `captured_at`, source, and selection reason. Current live coverage is 19,856 of 20,651 canonical cards. Every selected row reports source `TCGPlayer`. Selected observation dates span 2026-04-11 through 2026-09-11; old dates are retained when no fresher valid observation exists, so freshness must be a reported diagnostic and stale rows must not be silently treated as same-day prices.

The value is TCGPlayer `market_price`. The ingestion/parser and historical schema retain market/low/high price fields, but no normalized completed-sale event table exists. Therefore the target is accurately described as a listing-derived TCGPlayer market statistic, never completed-sales data.

Daily history is stored in `card_variant_price_observations`, uniquely constrained by variant, condition, source, and captured date with latest scrape winning within a day. It supports as-of reconstruction. Exact total count timed out during the F1 count query and is not required for current-value fitting; the schema is live and its selected history reaches at least April 2026. Duplicate handling is database-enforced per daily key. Currency is normalized/filtered to USD. Reverse-holo, special, promo, and edition identities remain distinct physical variants; the canonical target chooses one according to explicit base-print/fallback reasons rather than averaging incompatible variants.

## Live input authority

- Collector Appeal: frozen `pokemon_collector_appeal_v7_expanded_price_blind_v1`, exact run `e282f26e-2136-4105-b0a3-f0974c4d9d70`; 18,293 card rows. Price and Treatment were excluded during construction.
- Pull Scarcity: `simulation_card_variant_pull_rates.modeled_probability`, restricted to 34 calculation runs selected by `explore_rip_statistics_latest`; 7,624 variant/run rows.
- Treatment: deterministic `pokemon_card_treatment_taxonomy_v3`, fingerprint `85fdb2344d9ae7842a91bf0b3b0a434e02e99298be4cb025c8b3826066f67ddc`; 18,040/18,293 Collector cards mapped and 253 explicitly unresolved in its authority audit.
- Lifecycle/structure: `sets`, `eras`, `pokemon_canonical_cards`, `cards`, and `card_variants`.

No authoritative live tables were found for completed sales, listings/order-book depth, PSA or other grading populations, gem rate, grading velocity, card-level reprint state, or surviving NM supply. These are absent—not assumed zero. The live feature matrix records exact roles and limitations.

## Strict intersection

The reproducible strict contract currently yields 4,349 rows across 22 sets/root sets and 2 modern eras. It requires target price, canonical identity, scored frozen Collector V7, accepted exact variant pull probability, resolved Treatment V3, and release date. Counts over the full canonical universe are non-exclusive: 795 lack price, 678 lack adequate bridge identity, 2,358 lack scored Collector authority, 16,246 lack exact pull scarcity, and 1,922 have unresolved treatment.

The overwhelming scarcity gap and modern-only intersection mean the available cohort is scientifically adequate to begin grouped modern F2 fitting, but not to claim universal or vintage coverage.
