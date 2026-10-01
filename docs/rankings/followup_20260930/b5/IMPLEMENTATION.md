# Bucket 5 implementation

B5 removes avoidable Cards cold-path work without changing Card models, global
rank semantics, eligibility, or entitlements.

- `CardRankingsHub` remains the single top-level dynamic Cards boundary, while
  Collector and Chase are static children of that async chunk and only the
  active child mounts.
- the existing Cards intent signal preloads that complete chunk;
- entitled Plus/Premium viewers idle-prewarm Collector facets and default
  Overall page 1 through the mounted component's exact session-cache keys;
- Premium Chase facets/page 1 prewarm only on Chase toggle intent;
- anonymous/Base and save-data viewers perform no optional paid prewarm;
- Collector Overall/Pokémon/Trainer/Playability skip score-detail reads; Artist
  alone loads artist details; all lenses skip the unused Era batch;
- Chase page reads use an explicit public-field projection instead of `*`;
- cold footers say `Loading card rankings…` and do not invent zero/page 1-of-1.

Session-cache identity continues to include access/publication identity. A
logout, downgrade, or publication change creates a new cache and remount key;
request-generation guards prevent late responses repainting the old view.
