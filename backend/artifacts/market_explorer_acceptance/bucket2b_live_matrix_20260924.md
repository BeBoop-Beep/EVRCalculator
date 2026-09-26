# Bucket 2B live acceptance matrix (read-only, 2026-09-23/24)

Source: Supabase project `TheIndex` (status ACTIVE_HEALTHY) via read-only SQL through the MCP. No writes, no DDL.
Serving generation for every row: `39f27e3b-8ff6-472e-a986-77a2c7bcba43`; directory published 2026-09-20 23:04Z; `source_as_of` = `comparison_as_of` = 2026-09-19.
Upstream (set-value snapshot, query caches) has advanced to 2026-09-22 -> the published generation is 3 days stale (see constituent findings).

## Directory matrix
market_key | label | type | asset | source_kind | hist | start | end | pts | current | comparison_value | index
--- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---
set:0010d2ec-894e-4c17-855d-5de6ff6fd204 | Base | set | cards | public_set_snapshot | yes | 2026-04-11 | 2026-09-19 | 162 | 2229.47 | NULL | 137.27
set:37e1b616-c5f4-4279-83c4-ea8dcdd83c69 | Jungle | set | cards | public_set_snapshot | yes | 2026-04-11 | 2026-09-19 | 162 | 2209.94 | NULL | 87.17
set:c86889c9-ea25-4caa-b63c-7aa0b9796da8 | Fossil | set | cards | public_set_snapshot | yes | 2026-04-11 | 2026-09-19 | 162 | 2453.06 | NULL | 95.16
set:4f84d317-e15d-4598-bc8d-52baa04b3485 | Team Rocket | set | cards | public_set_snapshot | yes | 2026-04-11 | 2026-09-19 | 162 | 2994.02 | NULL | 89.06
set:f59f25a2-d3da-4100-a918-901271a99925 | Surging Sparks | set | cards | public_set_snapshot | yes | 2026-04-11 | 2026-09-19 | 162 | 1236.44 | 1236.44 | 107.28
set:202518a0-5e86-4949-b1cd-c1c8ad95b616 | Paldea Evolved | set | cards | public_set_snapshot | yes | 2026-04-11 | 2026-09-19 | 162 | 1946.07 | 1946.07 | 119.18
era:a5571ca6-0dae-4366-8d16-d043a9b1659d | EX | era | cards | maintained_query_cache | yes | 2026-04-11 | 2026-09-19 | 155 | 161097.13 | 161097.13 | 135.54
era:85f7d2c4-1193-4da4-b86c-1f2f50625205 | Base/WOTC | era | cards | maintained_query_cache | yes | 2026-04-11 | 2026-09-19 | 155 | 18334.19 | 18334.19 | 122.85
era:dfb0dfa1-6a8e-4335-850f-e003867e19ee | Scarlet and Violet | era | cards | maintained_query_cache | yes | 2026-04-07 | 2026-09-19 | 159 | 30719.26 | 30719.26 | 116.03
rarity:rareUltra | Rare Ultra | prepared_rarity | cards | maintained_query_cache | yes | 2026-04-11 | 2026-09-19 | 155 | 54737.94 | 54737.94 | 118.92
rarity:rareHolo | Rare Holo | prepared_rarity | cards | maintained_query_cache | yes | 2026-04-11 | 2026-09-19 | 155 | 153302.10 | 153302.10 | 126.93
curated:obtainable | Obtainable (Quick) | curated | cards | maintained_query_cache | yes | 2026-04-07 | 2026-09-19 | 159 | 40001.20 | 40001.20 | 132.52
curated:premium | Premium (Quick) | curated | cards | maintained_query_cache | yes | 2026-04-07 | 2026-09-19 | 159 | 409764.02 | 409764.02 | 120.92
sealed-format:boosterBox | Booster Boxes | prepared_format | sealed | prepared_sealed_snapshots | yes | 2026-04-11 | 2026-09-19 | 162 | 145563.47 | 145563.47 | 102.60
sealed-format:packs | Packs | prepared_format | sealed | prepared_sealed_snapshots | yes | 2026-04-07 | 2026-09-19 | 166 | 64301.50 | 64301.50 | 129.92
sealed-format:eliteTrainerBox | Elite Trainer Boxes | prepared_format | sealed | prepared_sealed_snapshots | yes | 2026-04-07 | 2026-09-19 | 166 | 46187.33 | 46187.33 | 114.59

Directory totals: 155 sets, 17 eras, 9 prepared rarities, 6 curated quick markets, 5 sealed formats; all 192 have history.
Finding (not fixed, recorded): every pre-2000s WOTC/Neo set (Base, Jungle, Fossil, Team Rocket, Gym x2, Neo x4) has `comparison_value` (tracked value) NULL and `tracked_value` NULL on all 162 history rows; index_value is present. The frontend chart consumes index_value only, so this affects the Tracked Value column, not the line. No Base *Set* label collision: "Base" (WOTC) and "Base Set 2" both exist.

## Read path per market (comparison + history RPC, read-only)
All six sampled (Base, Jungle, Obtainable, Packs, Rare Ultra, EX) return 1 comparison row and full history via `get_pokemon_market_explorer_prepared_comparison_v1` / `_history_v1`
(162/162/159/166/155/155 rows). Both are direct reads of the serving views, statement_timeout=5s, no payload_json access.

## Constituent RPC (v2, live, before this change) generation 39f27e3b..., limit 100
market | availability | total | first page rows | payload bytes | exec ms
--- | --- | --- | --- | --- | ---
set Team Rocket | available | 83 | 83 | 37,681 | 1,042 (roster recomputed)
sealed Packs | unavailable ("Complete sealed roster is unavailable for this generation") | 0 | 0 | 465 | 23
sealed Booster Boxes | unavailable (same) | 0 | 0 | 470 | -
era EX | unavailable ("Maintained roster does not match the published definition and date") | 0 | 0 | 529 | 18
rarity Rare Ultra | unavailable (same) | 0 | 0 | 505 | -
quick Obtainable | unavailable (same) | 0 | 0 | 507 | -
wrong generation id | GENERATION_MISMATCH | - | - | 244 | -
Root cause of the unavailability: guard compares mutable upstream to the published generation (snapshot market_date 2026-09-22 vs source_as_of 2026-09-19; query caches computed_through 2026-09-22 vs 2026-09-19). Sealed source payload: 1,544,609 chars json / 503,521 bytes stored, 513 KB in the sealedSegments subtree, re-extracted per page.
Set: 30 sets via get_pokemon_cards_daily_constituents = 11.3 s (0.38 s/set); a full-roster stage for 155 sets is ~60 s.
