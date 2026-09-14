# Market Explorer Remap Phase 2 — DB Search Handoff

## Contract

- RPC: `search_pokemon_market_explorer_instruments_v2(p_query text, p_asset text, p_limit integer)`
- Assets: `cards`, `sealed`, `all`
- Default/hard limit: 20/50
- Addable identity: `instrument_id`; discriminator: `asset`
- Access: execution revoked from `public`, `anon`, and `authenticated`; granted only to `service_role`

The RPC owns normalization, candidate selection, relevance ranking, typo tolerance, cross-asset ordering, and result capping. Application code must preserve returned order and must not expose `match_kind`, `relevance_score`, or `name_similarity`.

## Normalization and ranking

Normalization lowercases, maps Pokémon to Pokemon, converts punctuation/hyphens/apostrophes to token boundaries, collapses whitespace, and expands the intentional `ETB` synonym to `Elite Trainer Box`.

Ranking bands are exact normalized primary name, all primary-name tokens, primary-name prefixes/tokens, primary name plus Set context, exact collector number, controlled single-token fuzzy primary-name matching, then weaker metadata. Short tokens do not enable broad fuzzy scans.

## Applied migrations

The following live ledger statements were retrieved read-only from `supabase_migrations.schema_migrations` and mirrored without reconstruction into both repository migration trees:

- `20260911153742_market_explorer_phase2_enable_pg_trgm` — statement MD5 `a9f2a818cb67519ee57158cd560ed77a`
- `20260911154138_market_explorer_phase2_card_search_fts` — statement MD5 `6ed68aa308da90df7f30d78f2881dbe2`
- `20260911154222_market_explorer_phase2_card_name_trgm` — statement MD5 `2c5a1a60fb8c06dd32e777627eda201f`
- `20260911154613_market_explorer_phase2_canonical_instrument_search_v2` — statement MD5 `0cb94dddaf76bf6714116db590b822b1`

Repository files contain the exact ledger statement plus one terminal newline. Automated tests strip only that terminal newline before verifying the live-ledger MD5.

## Accepted DB behavior and latency

DB acceptance covered `mega dragonite`, reversed token order, `dragnoite`, `dragnite`, Temporal Forces + Gastly in both orders, collector number `290`, `DRAGONITE-GX`, Pokemon/Pokémon equivalence, ETB/Elite Trainer Box, Pokemon Center ETB, Booster Bundle, reversed sealed terms, and every asset mode.

Warm measurements supplied by the DB workstream:

| Query / asset | DB time |
|---|---:|
| mega dragonite / cards | ~63 ms |
| dragnoite / cards | ~59 ms |
| temporal forces gastly / cards | ~82 ms |
| elite trainer box / sealed | ~60 ms |
| etb / sealed | ~60 ms |
| temporal forces / all | ~143 ms |
| ex / broad two-character query | ~256 ms |

The broad two-character case is an accepted non-blocking caveat, controlled application-side by debounce and rate limiting.
