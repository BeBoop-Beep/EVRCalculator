# Market Explorer Remap Phase 3 — Filter Taxonomy + Instant Options

## A–D. Starting state and taxonomy boundary

Started from clean synchronized local/remote `develop` at `1cde8c9295218002680d514fbb30392514af58bc`; Phase 2 commits remain in history. Source now mirrors all 39 audited exact rarity IDs under versioned `FILTER_RARITY_DEFINITIONS`. `segmentIds` accepts that full Cards vocabulary. `RAW_CARD_SEGMENT_DEFINITIONS`, its nine entries, and both quality thresholds remain unchanged. Filter-only `legend`, `radiantRare`, and `aceSpecRare` are valid custom filters but not prepared equivalents.

## E–F. Compatibility and migrations

Offline construction reads card rarity compatibility from `pokemon_market_explorer_card_current_metadata`, the same eligible authority as custom queries. The canonical payload exposes `cardRarities`, separate prepared `cardSegments`, and `compatibility.cardRaritySetIds`; OR union occurs within selected rarities and intersection remains across rarity/Pokémon axes. Four exact applied migrations are mirrored into both canonical trees and pinned to live-ledger MD5s.

## G–J. Publication and request paths

`publish_market_explorer_filter_options.py` is a separate bounded command. It builds and validates the complete payload before any publish call, fingerprints canonical JSON, skips an unchanged current payload, and delegates atomic current-row replacement to the DB RPC. A failed build cannot call the publisher; a failed atomic publication leaves the prior current row intact.

The protected API retains its Index+ gate and process L1, but a cold L1 miss now performs only `get_pokemon_market_explorer_options_snapshot_v1`. Missing snapshots return typed `MARKET_EXPLORER_OPTIONS_REFRESHING` HTTP 503 with `Retry-After: 15`; the web request has no heavy-builder fallback.

The finalized real production publication completed at `2026-09-11T19:04:59.904441+00:00`: snapshot `7`, source-as-of `2026-09-11`, schema `market-explorer-filter-options-v1`, 1,234,418 bytes, fingerprint `4768d2a59b79309293471874590063a6cdef36c7087994ba9f0e56697c47ebfb`. Verification found exactly one current row, 39 filter rarities, nine prepared segments, and the expected filter-taxonomy source metadata. A consecutive publisher run returned `published: false` / `reason: unchanged` for snapshot `7`.

## K–M. UX, maintained safety, entitlement

Cards Rarity now uses `cardRarities` and the existing client-only case-insensitive searchable multi-select. Selected chips remain visible/removable outside filtered results. Sealed retains product-family behavior. Maintained-axis provisioning still reads only `cardSegments`, with a regression proving `legend` is ignored. Existing Index+ options and Premium compound-query enforcement are unchanged.

## N–P. Performance and validation

Final production offline build: 11,658.1 ms; publish RPC round trip: 609.8 ms. Service-role snapshot reads measured 382.7 ms cold-process and 125.5 ms warm connection for the 1.23 MB payload; DB-internal read remains ~0.44 ms. Warm L1 avoids the DB call entirely. Explicit ordering on paged compatibility-authority reads makes the payload fingerprint stable across processes.

Focused backend taxonomy/query/options/provisioning/API tests passed. Focused Builder tests and the production frontend build passed. Migration mirrors match the live ledger. `git diff --check` passed for the committed scope.

## Q–S. Files, caveats, final commit

Changed the rarity taxonomy/query validation, options builder, snapshot adapter/API, standalone publisher, Builder hook/control, exact migration mirrors, tests, and acceptance artifacts. Historical quick-segment tests on the current base have 13 unrelated failures in the separate prepared chart-toggle panel; Phase 3 does not change that panel. The options payload is intentionally large (1.23 MB) because compatibility is preserved; persistent reads remain below one second.

Final source commit: `77b94bbd9115e5caf741aa80a76f32c70a1fd5d6`.
