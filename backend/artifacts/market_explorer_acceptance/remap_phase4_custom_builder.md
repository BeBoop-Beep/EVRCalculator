# Market Explorer Remap Phase 4 — Custom Builder Correctness + Performance

## A. Starting SHA

Source work started from clean shared `develop` at `434d25df0e8483551c4ac95cebfefaa3713f7f67`, with Phase 3 source `77b94bbd9115e5caf741aa80a76f32c70a1fd5d6` intact. Local `develop` was intentionally ahead of stale `origin/develop`; no reset was performed.

## B. Prior membership defects

The backend already normalized every multi-select axis into sorted, de-duplicated IDs and sent all selected values to one canonical SQL call. Exact membership also already discarded stale Filtered fields. The remaining product defects were frontend-facing: generic Composition/Top-N appeared as a peer Builder filter, compatibility semantics were duplicated rather than named and pinned, the Phase 1 preflight endpoint had no browser integration, known-empty drafts could reach Build, and Build failures displayed arbitrary exception text instead of typed outcomes.

## C–E. Final membership and compatibility model

Ordinary Raw Cards membership is Scope (Era, Set) plus Filters (Rarity, Pokémon, Price, Release Age). Sealed membership is Scope (Era, Set) plus Filters (Product Family, Price, Release Age). Exact Items remains a separate explicit-instrument workflow.

Each selected ID list is one OR group. Different non-empty axes are ANDed by the canonical RPC. Set compatibility is now expressed by one `compatibleSetIds` function: union all selected values inside each axis, then intersect those per-axis unions. This only narrows displayed Set choices and reconciles selections; the backend query spec remains authoritative.

## F. Ranking/composition removal

The generic Composition control and its dormant duplicate were removed from the Builder. Ranking is no longer presented as ordinary membership. Existing prepared Quick Presets and backend legacy chase support remain intact for their established routes; Phase 5 replacement controls were not started.

## G–I. Preflight, one-match, empty, and broad markets

Filtered Cards drafts use the Phase 1 preflight through a dedicated same-origin proxy and client hook. Requests debounce for 350 ms, carry an AbortController signal, invalidate immediately on semantic draft change, and use a generation guard so stale responses cannot overwrite a newer result. Sealed and Exact Items never preflight. Ready copy reports matching cards and sets without database terminology.

`PREFLIGHT_READY` remains buildable at one matching card. A truthful `QUERY_EMPTY_NOW`/`PREFLIGHT_EMPTY` disables Build and the Build handler independently refuses execution. No-history and projection/unavailable states never claim zero matches. Broad markets remain valid and builds continue to request `responseMode: summary`; Constituents stays a separate paged post-build inspection surface.

## J. Identity and fingerprints

Frontend and backend canonicalization sort and de-duplicate every selected axis. Reordered values share a query key/fingerprint, materially different filters remain distinct, and Filtered specs omit stale Exact instrument IDs. Preflight uses the same canonical identity, so checkbox order does not create duplicate requests. Prepared-equivalent resolution remains unchanged; filter-only rarity definitions remain custom.

## K. Database performance handoff

The completed live-DB handoff in `remap_phase4_db_builder_performance.md` was consumed. It proves exact expected/actual membership across the eight semantic combinations, one-match execution, truthful empty versus NULL projection-lag counts, current-window V2 routing, bounded interval fallback, and sub-second representative preflight/materialized execution. No DDL or speculative index was required.

## L. Execution states

The Builder distinguishes `QUERY_EMPTY_NOW`, `QUERY_NO_HISTORY`, `QUERY_BUILDING`, `QUERY_CACHE_REFRESHING`, `QUERY_RATE_LIMITED`, `QUERY_INVALID`, `QUERY_UNAVAILABLE`, and `QUERY_FAILED` by code. Retry metadata is preserved through the preflight proxy and used in rate/build messaging. No message parsing is used.

## M–N. Tests and build

Focused backend query normalization, preflight, planner/cache, query service, API entitlement, and Phase 3 rarity regressions: 207 passed. Focused frontend Builder/query/preflight tests: 56 passed. The production Next.js build passed. A mistakenly broad frontend invocation exposed existing repository-wide failures unrelated to this scope; no Phase 4 failure remained in the focused suite.

## O–Q. Files, blockers, final commit

Changed the Builder component, draft compatibility helper/hook, typed preflight helper/hook, same-origin preflight proxy, focused tests, and this report. Unrelated concurrent Collector V7 files were preserved and excluded.

Blockers: none.

Final source commit: `9edfae4f9a67672ca35057b2e7472f1c88a98660`.
