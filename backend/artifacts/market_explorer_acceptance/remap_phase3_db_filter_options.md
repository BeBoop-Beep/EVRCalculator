# Market Explorer Remap Phase 3 — DB Filter/Options Handoff

The live Cards authority contains 34,228 eligible variants across 165 sets. It has 41 non-null raw rarity spellings, 39 normalized concepts/filter IDs, 299 null-rarity variants, and zero unmapped non-null values. `market_explorer_filter_rarity_key(text)` is the exact, immutable, parallel-safe, service-role-only normalization authority. Unknown and null values map to null; distinct rarity concepts are never substring- or fuzzy-folded.

Prepared rarity markets remain exactly nine: `specialIllustrationRare`, `illustrationRare`, `ultraRare`, `hyperRare`, `doubleRare`, `rareUltra`, `rareSecret`, `rareRainbow`, and `rareHolo`.

The live custom-query materialized, interval-shadow, shadow, and both preflight RPCs use the full rarity filter function. DB acceptance proved filter-only and prepared membership, OR within rarity, and AND across price/release-age axes.

Persistent contract: `pokemon_market_explorer_options_snapshots`, atomic publisher `publish_pokemon_market_explorer_options_snapshot_v1`, and service-role reader `get_pokemon_market_explorer_options_snapshot_v1`. The reader performs no catalog/card/link/sealed scans or refresh. DB read measured about 0.44 ms.

Exact live-ledger migration statements are mirrored in both repository trees:

- `20260911182748_market_explorer_phase3_filter_rarity_key` — MD5 `8eda8d5e71a6003a908c5a78df6f27e6`
- `20260911182822_market_explorer_phase3_use_full_rarity_filter_for_custom_queries` — MD5 `ed8fcf7e8a9e80e6ddebf63f8c111dbb`
- `20260911183142_market_explorer_phase3_options_snapshot_contract` — MD5 `b0ce4b2272f0328cb84050de233376f3`
- `20260911183523_market_explorer_phase3_options_snapshot_least_privilege` — MD5 `8c24634ed0c1db7ccadeb775b9b650cf`

Measured offline inputs: rarity/Set aggregation ~866 ms, Pokémon/Set ~51 ms, and sealed-family/Set ~18 ms.
