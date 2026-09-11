# Market Explorer Remap Phase 5 — DB Prepared Directory

Status: `MARKET_EXPLORER_REMAP_PHASE5_DB_COMPLETE`

- Accepted generation: `80aad6a2-d5dd-47fc-9feb-3a15ba12b2c8`
- Canonical comparison watermark: `2026-09-08`
- Inventory: 106 Sets, 17 Eras, 6 curated Quick Markets, 9 rarity markets, 5 sealed-format markets (143 total)
- Comparable histories: 133 markets / 19,835 normalized points

## Serving contract

- `get_pokemon_market_explorer_prepared_directory_v1()` — public Browse directory. Set rows carry `parent_era_id`.
- `get_pokemon_market_explorer_prepared_comparison_v1(market_keys[])` — coherent DB-calculated comparison fields, maximum 25 keys.
- `get_pokemon_market_explorer_prepared_history_v1(market_keys[], start_date)` — normalized history clipped to the watermark, maximum 25 keys.
- `get_pokemon_market_explorer_prepared_screen_v1(screen_key, asset, limit)` — deterministic prepared Screens, limit 1..25.
- `get_pokemon_market_explorer_set_context_ranking_v1(set_id, ranking, timeframe, limit, as_of)` — read-only contextual value/risers/fallers ranking.

`source_as_of/current_value` belong to fresh single-market Browse display. `comparison_as_of/comparison_value/comparison_index_value`, returns, drawdowns, relative fields, and history belong to coherent comparison. They must not be conflated.

The six curated keys are `curated:obtainable`, `curated:intermediate`, `curated:premium`, `curated:new-releases`, `curated:established`, and `curated:global-top10`. Obtainable currently reports a failed latest source while preserving a valid previous-good series through the watermark.

Ten Sets are browse-only at this generation: Astral Radiance, Brilliant Stars, Celebrations, Crown Zenith, Fusion Strike, Kalos Starter Set, Lost Origin, Pokémon GO, Shining Fates, and Silver Tempest. No index may be synthesized. True 1Y return is unavailable for every prepared market.

Live migrations `20260911200732`, `20260911200916`, `20260911201029`, and `20260911201307` were read from `supabase_migrations.schema_migrations` and mirrored verbatim into both canonical source trees. No migration was reapplied.

Live verification on 2026-09-11 returned exactly 106 `set`, 17 `era`, 6 `curated`, 9 `prepared_rarity`, and 5 `prepared_format` rows.
