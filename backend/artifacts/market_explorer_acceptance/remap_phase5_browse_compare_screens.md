# Market Explorer Remap Phase 5: Browse, Compare, and Screens

Status: `MARKET_EXPLORER_REMAP_PHASE5_SOURCE_COMPLETE`

## A. Starting SHA

- Phase 5 foundation started from `f9f2c62d`.
- DB source integration resumed from `efdced66`; intervening commits were the separate Collector Appeal workstream and were preserved.

## B. Entitlement model

Capabilities are centralized in the frontend and backend access modules. Basic can browse prepared markets; Index+ adds prepared comparison, analytical screens, and advanced rankings; Premium inherits those capabilities and exclusively adds Custom Builder execution.

## C. Prepared-directory integration

The public directory is loaded through `get_pokemon_market_explorer_prepared_directory_v1()`. The server fetch supplies the initial Explorer render and the prepared API proxy supplies comparison, history, screen, and contextual-ranking reads. Array limits remain bounded to 25.

The accepted inventory is 143 markets: 106 Sets, 17 Eras, 6 curated Quick Markets, 9 prepared rarity markets, and 5 prepared sealed-format markets. Sets use the directory's `parent_era_id`; no secondary Era grouping lookup is performed.

## D. Basic Set/Era/Quick browsing

Browse exposes searchable Sets, Eras, and Quick tabs. All Sets and Eras are available, Sets are grouped by Era, and Quick contains the six maintained prepared identities. Directory `current_value` and `source_as_of` are shown as browse facts.

## E. Basic replacement semantics

Basic has one prepared market slot. A new primary selection replaces the previous prepared selection. Compare remains visible as an Index+ upgrade action and cannot accumulate Basic series.

## F. Index+ comparison

Index+ and Premium can add up to 25 prepared markets. Set/Set, Set/Era, and Era/Quick combinations share the existing chart, timeframe, synchronized tooltip, and Performance/Index modes. Prepared interactions call only the prepared read endpoints.

## G. Comparison metrics

The UI consumes DB-returned comparison value, canonical index value, 7D/30D/90D returns, current/max drawdown, and Set-relative-to-Era metrics. It does not recompute those analytics or introduce volatility. Screens retain the DB's deterministic ordering.

## H. Watermark handling

All analytical values and histories use `comparison_as_of`, pinned by the accepted generation to 2026-09-08. Browse `current_value`/`source_as_of` remain separately labeled and are never substituted into comparison metrics.

## I. Unavailable history handling

The ten browse-only Sets remain selectable and show their current prepared browse value. Their missing normalized history and analytics render as unavailable; no raw-history reconstruction or custom-build fallback occurs. The 1Y metric is also unavailable rather than zero or partial-period.

## J. Screens

Rarity Leaders, Sealed Format Leaders, Momentum Leaders, and Largest Drawdowns live outside Builder and call `get_pokemon_market_explorer_prepared_screen_v1()`. Momentum uses the DB 30D definition; frontend code does not re-rank returned rows.

## K. Contextual rankings

Prepared Set detail exposes Top 10 by Value, Biggest Risers, and Biggest Fallers through `get_pokemon_market_explorer_set_context_ranking_v1()`. Mover requests use only supported 7D/30D/90D Explorer timeframes and do not mutate membership or Builder state.

## L. Main /Market preservation

The existing public `/Market` page was not changed or paywalled. Phase 5 applies to interactive comparison in `/Market/Explorer`.

## M. Quick Market identity

The exact identities are `curated:obtainable`, `curated:intermediate`, `curated:premium`, `curated:new-releases`, `curated:established`, and `curated:global-top10`. “Top 10 in Selected Set” is contextual analysis, not a Quick Market.

## N. Obtainable caveat

Obtainable remains browsable from its preserved previous-good history through Sep 8. Its failed current source status is surfaced and does not initiate a replacement build.

## O. Migration mirroring

The four live Phase 5 migrations (`20260911200732`, `20260911200916`, `20260911201029`, and `20260911201307`) are mirrored in both canonical trees. Normalized statement MD5 values match the authoritative ledger: `6338d0a85b16eeec33f628621540d033`, `f0e0071263c2424f1981516c4bc3fb10`, `66f9a79a0dcdc5e23fb1707be86b9c88`, and `545fbfc912f1bcaa36743c041c9e4ec8`. No live migration was reapplied or historical migration edited.

## P. Custom-build isolation

Directory, prepared comparison/history, Screens, and contextual rankings use dedicated read-only adapters. They do not call custom query evaluation, preflight, query-cache creation, build leasing, or directory refresh. Custom creation remains Premium-only and Phase 4 Builder behavior is retained.

## Q. Performance

The implementation uses the precomputed serving contract instead of per-interaction custom construction. DB acceptance timings remain approximately 2.0 ms for the full directory, 1.8 ms for a three-market comparison, 0.45 ms for Momentum, 2.2 ms for three histories, and 13.9 ms for a contextual ranking.

## R. Tests

- Focused frontend Phase 5/chart/prepared/access suite: 159 passed.
- Focused backend prepared-directory/API/access/query/preflight suite: 114 passed.
- Additional focused screen/prepared backend coverage completed earlier: 10 passed.
- `git diff --check`: passed.
- The new Phase 5 migration mirror test passes. Running the entire historical mirror module also exposes one pre-existing Prompt-1 byte-hash failure caused by checkout CRLF normalization; it is unrelated to the four Phase 5 mirrors and remains a repository follow-up.

## S. Build

`npm.cmd run build` completed successfully with Next.js 15.5.15. Existing lint/cache warnings remain non-fatal. `/Market/Explorer` and the prepared proxy route were emitted successfully.

## T. Files changed

The source commit updates centralized access policy, backend prepared read adapters/routes, Explorer state and page integration, Browse/Screen/context UI, prepared-series mapping, focused tests, the DB handoff, and both canonical migration trees. No Collector Appeal file was included.

## U. Caveats and follow-ups

- Saved comparison persistence was not introduced because no safe existing persistence primitive was available.
- No existing Explorer telemetry pipeline was available. Recommended future events are Explore visit, selected, replaced, compare attempted, paywall shown, upgrade clicked, and comparison created.
- Repair the older Prompt-1 migration test's platform-dependent line-ending assumption separately; do not rewrite its historical migrations.

## V. Final commit SHA

Phase 5 source integration commit: `f8ba78ca`.

