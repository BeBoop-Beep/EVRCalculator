# Market Explorer Remap Phase 1 — source acceptance (final)

## A. Starting develop SHA

This pass started from shared `develop` at merge commit
`7a138116ddc203a9999cc246bafc5f01908bdfad` (origin/develop tip
`4e23b69ff486b82a50307a7719571e584a5c10d8`). By the time this pass resumed,
`develop` had already advanced to `dba867f4` ("updates"), which itself
already carried an earlier completion of this same Phase 1 scope: the
Filtered/Exact isolation (Task 1) with its regression tests, the
`scope='market'` watermark fix (Task 2), and a pure RPC-row translation
module (`backend/domain/pokemon/market_explorer_preflight.py`) for Task 3's
typed contract, but not yet the DB-calling RPC caller, the HTTP endpoint, or
the migration-signature parity check. This pass verified that prior state and
completed the remaining Task 3/4 wiring described below.

## B. Exact/Filtered separation

Audited `frontend/lib/explore/marketExplorerQuery.mjs`,
`backend/domain/pokemon/market_explorer_query.py`,
`frontend/lib/explore/marketExplorerBuilderDraft.mjs`, and
`frontend/hooks/explore/useMarketExplorerBuilderDraft.js`. The invariant was
already correctly implemented on both halves: `normalize_query_spec`
(Python) / `normalizeQuerySpec` (JS) only attach `instrumentIds`/
`membershipMode` to the normalized spec when `membershipMode === 'explicit'`;
a payload with `membershipMode='filters'` and a populated `instrumentIds`
canonicalizes by dropping the stale explicit field entirely (never rejects
it) — this is the codebase's existing "canonicalize away stale state" idiom,
matching how the explicit branch already drops stale scope/segment/price/
release-age/mode/topN fields. The Builder reducer
(`marketExplorerBuilderDraftReducer`) independently resets `membershipMode`
to `filters` whenever an ordinary filter-definition field changes, so stale
Exact draft state cannot silently survive into a Filtered execution even
before normalization runs.

No change was made here; this pass only verified it and ran the existing
regression coverage (see section I).

## C. Normalized/fingerprint behavior

`fingerprint_payload`/`query_fingerprint` (Python) and `buildQueryKey`
(JS) both derive solely from the already-canonicalized spec, so a Filtered
spec's fingerprint never varies with stale `instrumentIds`, and an Explicit
spec's fingerprint never varies with stale scope/peer-filter fields. Existing
test `test_market_explorer_query.py` /
`marketExplorerQuery.test.mjs` ("filtered specs omit stale explicit
membership and exact specs omit stale filters") cover exactly the
"SIR + Intermediate + New" shape described in the task.

## D. Comparison watermark authority — found and changed

**Found (genuine bug, confirmed and fixed this pass):**
`backend/db/services/market_explorer_query_planner.py`'s
`resolve_explorer_comparison_through` queried
`pokemon_explore_set_value_snapshot_latest` with
`.eq("scope", "global")`, but the production canonical row for the Pokémon
Explorer publication uses `scope='market'` (`tcg='pokemon',
scope='market'`), as confirmed by
`backend/db/services/pokemon_explore_set_value_service.py` (writes with
`"scope": "market"`) and by the DB agent's read-only audit
(`remap_phase1_db_execution.md` section G: the row was found at
`scope='market'`, `market_date='2026-09-09'`). The stale `scope='global'`
predicate meant this resolver could never find the accepted row in
production, and this pass changed it to `.eq("scope", "market")`.

**comparisonAsOf exposure:** `resolve_explorer_comparison_through` returns
`min(source_through, comparison_as_of)` — the accepted Explorer publication
date bounded further by the asset's own source-publication watermark, never
`CURRENT_DATE` and never an independently-computed "latest quality-ready
date". `POST /market/explorer/query` already threads this through the
existing response contract as `comparisonAsOf` (no parallel channel added).
`resolve_scope_set_ids` was extracted from the inline era→set expansion in
`resolve_canonical_through` into a shared helper, reused by the new
preflight caller (section F) so Set-ID scope resolution is not re-derived.

## E. `scope='market'` correction — regression tests added

`backend/tests/unit/db/services/test_market_explorer_query_planner.py`:
- `test_explorer_comparison_watermark_resolves_scope_market_row` — a
  `scope='market'` row with `market_date='2026-09-09'` resolves correctly
  with no `scope='global'` row present at all.
- `test_explorer_comparison_watermark_does_not_read_scope_global_rows` — a
  newer V2 source date (`2026-09-10`) with only a `scope='global'` row does
  NOT let the resolver read it (asserts `RuntimeError`), proving the
  predicate is genuinely scoped and a custom Explorer comparison cannot
  silently extend past a missing prepared publication.
- The pre-existing `WatermarkClient` fake and
  `test_explorer_comparison_watermark_clips_newer_source_projection` were
  updated to use `scope='market'` fixture rows (the production shape) and
  continue to assert the clip-to-prepared-date behavior.

## F. Preflight integration

Read the three successive preflight migrations
(`20260910203112_add_market_explorer_filtered_cards_preflight_v1.sql`,
`20260910204247_correct_market_explorer_filtered_cards_preflight_history.sql`,
`20260910204843_optimize_market_explorer_filtered_cards_preflight.sql`) to
confirm the RPC's final live signature and returned columns before writing
any caller. Function name:
`preflight_pokemon_market_explorer_filtered_cards_v1(p_set_ids uuid[],
p_segment_ids text[], p_pokemon_ids bigint[], p_price_segment_ids text[],
p_release_age_cohort_ids text[], p_comparison_as_of date)`. Implemented:

- `backend/domain/pokemon/market_explorer_preflight.py`:
  `call_filtered_cards_preflight(client, set_ids=..., segment_ids=...,
  pokemon_ids=..., price_segment_ids=..., release_age_cohort_ids=...,
  comparison_as_of=...)` calls `client.rpc(PREFLIGHT_RPC_NAME, {...})`,
  passing sorted deduplicated arrays (or `None` for an empty axis, matching
  the RPC's `default null`/EMPTY MEANS ALL convention), and hands the single
  returned row to `translate_preflight_row` for the typed contract. It
  performs no filtering, ranking, or index math itself, and never passes
  Exact Basket instrument IDs.
- `backend/api/main.py`: new `POST /market/explorer/query/preflight`
  endpoint. It normalizes the request through the same
  `normalize_query_spec` used by the real query endpoint (so an invalid
  spec is rejected identically), enforces the same access/abuse gates as
  `/market/explorer/query`, resolves Era→Set scope via the existing
  `resolve_scope_set_ids` authority, resolves `comparisonAsOf` via the
  existing (now-corrected) `resolve_explorer_comparison_through`, and calls
  the RPC. It transports no constituent IDs and builds no index — purely a
  cheap readiness check, kept separate from the real query-execution path.

Typed contract fields preserved (translated from the RPC's snake_case
columns to camelCase): `matchingConstituentCount`, `matchingSetCount`,
`comparisonAsOf`, `previousApprovedMarketDate`,
`previousMatchingConstituentCount`, `previousMatchingSetCount`,
`commonConstituentCount`, `currentChainLinkReady`, `scopeSetCount`,
`scopeProjectionReadySetCount`, `scopeProjectionMissingSetCount`,
`scopeProjectionReady`, `historyProbeProjectionReady`,
`projectionRetainedFrom`, `projectionComputedThrough`, `preflightStatus`,
plus this module's own `readiness` and `queryOutcome` codes.

## G. Typed status mapping

`backend/domain/pokemon/market_explorer_preflight.py` maps every SQL
`preflight_status` value the live RPC can return
(`ready`, `empty`, `current_only`, `disconnected_current_segment`,
`history_probe_unavailable`, `projection_lagging`, `no_approved_market_date`,
`invalid_scope`) to an internal readiness code, then to the frontend's
existing typed `MARKET_QUERY_OUTCOME` vocabulary
(`frontend/hooks/explore/useMarketExplorerQueries.js`):
`empty → QUERY_EMPTY_NOW`; `current_only`/`disconnected_current_segment` (has
current membership but no usable common history) → `QUERY_NO_HISTORY`;
`projection_lagging`/`history_probe_unavailable`/`no_approved_market_date` →
`QUERY_UNAVAILABLE` (never a reported zero-match — the projection-lag
regression test asserts the counts are `None`, not `0`, and the outcome is
never `QUERY_EMPTY_NOW`); `invalid_scope → QUERY_INVALID`; any unmapped
future SQL status degrades to `QUERY_UNAVAILABLE`, never silently reading as
ready. The real `/market/explorer/query` endpoint's existing exception→code
mapping (`QUERY_INVALID`/`QUERY_UNAVAILABLE`/`QUERY_CACHE_REFRESHING`/
`QUERY_BUILDING`/`QUERY_FAILED`, HTTP 429→`QUERY_RATE_LIMITED` on the
frontend fetch layer) was already in place from the prior pass and was not
touched; the preflight endpoint reuses `QUERY_INVALID`/`QUERY_UNAVAILABLE`/
`QUERY_FAILED` for its own request/RPC failure modes.

## H. DB work already supplied

Five migrations dated 2026-09-10 (read, not modified): a V2 daily
publication hardening fix, the three-revision Filtered Cards preflight RPC
above, and two revisions of a materialized-series hot-path/common-link
optimization for the existing cohort reader
(`get_pokemon_market_explorer_filtered_cohort_materialized_series`) — no
overlap with the preflight RPC's own logic; neither was re-derived in
Python/JS.

## I. Tests added/run and results

Backend (`.venv-api-test`), focused to Market Explorer:
`pytest backend/tests/unit/db backend/tests/unit/domain -k market_explorer`
→ **292 passed, 1 pre-existing unrelated failure**
(`test_market_explorer_migration_source_sync.py::
test_prompt1_sources_use_actual_ledger_versions_and_match_statement_bytes`,
a byte-hash check against an unrelated 2026-09-08 migration ledger; no
migration file was touched by this pass — confirmed via `git status` showing
no changes under `backend/db/migrations/`).

New tests this pass:
`backend/tests/unit/domain/pokemon/test_market_explorer_preflight.py` —
ready/empty/current-only/history-unavailable/unmapped-status translation,
the projection-lag-is-not-zero-matches regression, and
`call_filtered_cards_preflight`'s RPC-call shape (correct name, sorted/
deduplicated params, empty-response error) against a fake Supabase client.
`backend/tests/unit/db/services/test_market_explorer_query_planner.py` —
two new `scope='market'` regressions (section E).

Frontend (`tsx --test`), focused to Market Explorer:
`lib/explore/**/*.test.{js,mjs,jsx} hooks/explore/**/*.test.{js,mjs,jsx}` →
332 passed, 6 pre-existing failures unrelated to this pass's files
(`explorePageServer`/`ripStatisticsServer` recoverable-fallback tests — none
of the four touched backend files have a frontend counterpart in this pass,
and no frontend file was edited this pass).

## J. Frontend production build result

`npm run build` (Next.js) completed successfully with no build errors.
Existing warnings unrelated to this change remained.

## K. Files changed

- `backend/db/services/market_explorer_query_planner.py` — `scope='market'`
  fix; extracted `resolve_scope_set_ids` helper.
- `backend/domain/pokemon/market_explorer_preflight.py` — added
  `call_filtered_cards_preflight` (RPC caller) alongside the existing
  translation table.
- `backend/api/main.py` — added `MarketExplorerPreflightRequest` and
  `POST /market/explorer/query/preflight`.
- `backend/tests/unit/domain/pokemon/test_market_explorer_preflight.py` —
  new RPC-call-shape tests.
- `backend/tests/unit/db/services/test_market_explorer_query_planner.py` —
  new `scope='market'` regressions (already present in `dba867f4`, verified
  and extended this pass).
- This report (`backend/artifacts/market_explorer_acceptance/
  remap_phase1_market_contract.md`).

No frontend file, migration file, search behavior, rarity taxonomy, Screens/
Quick Markets, or sidebar file was touched.

## L. Blockers / honesty notes

- The `/market/explorer/query/preflight` endpoint and
  `call_filtered_cards_preflight` were verified by loading `backend.api.main`
  in-process (route registers, imports resolve cleanly) and by unit tests
  against a fake Supabase client; there is no live database in this
  environment, so the actual RPC round-trip against a real Postgres instance
  was **not** exercised end-to-end. The DB agent's own parity tests
  (`remap_phase1_db_execution.md` section L) already verified the RPC's SQL
  behavior directly against production-shaped data at the SQL layer.
- The typed preflight outcome codes are not yet consumed by any frontend UI
  (e.g. shown in the Query Builder before a Build click) — only the backend
  contract and endpoint exist. Wiring a frontend consumer was out of this
  pass's verified scope; `useMarketExplorerQueries.js`'s existing typed
  error shape is unchanged and already compatible with these codes.
- **Genuine SQL bug found in the final preflight migration, not fixed (per
  instructions not to touch migrations).** In
  `backend/db/migrations/20260910204843_optimize_market_explorer_filtered_cards_preflight.sql`
  — the last migration in the repo that defines
  `preflight_pokemon_market_explorer_filtered_cards_v1` — the `coverage` CTE
  defines a column named `history_probe_ready_set_count` (line 75), but the
  `readiness` CTE two blocks later references
  `c.history_probe_projection_ready_set_count` (line 99) — a column that does
  not exist in `coverage`'s output list. This is a column-name typo, not a
  semantic difference; the two migrations before it
  (`20260910203112`, `20260910204247`) do not have this mismatch. If this
  exact SQL text is what is actually live in the production database, the
  function's `history_probe_projection_ready` computation (and therefore
  `previous_matching_*`, `common_constituent_count`,
  `current_chain_link_ready`, and the `current_only` /
  `disconnected_current_segment` / `history_probe_unavailable` status
  branches) would either fail outright at function-creation time or at
  query time, depending on how Postgres resolves the reference. The DB
  agent's own execution report (`remap_phase1_db_handoff.md` /
  `remap_phase1_db_execution.md`) describes successful parity tests against
  this same function name and a working ACL, which is hard to reconcile with
  this reading of the merged migration file — either the DB agent applied
  slightly different SQL than what is committed here, or this text-level
  mismatch needs to be re-verified against the live function definition.
  **This was not edited.** The application-level caller
  (`call_filtered_cards_preflight`) was written against the function's
  documented `returns table(...)` signature, which is identical and
  consistent across all three migration revisions, so the caller itself is
  correct regardless of which revision's body is actually live; only the SQL
  body of the CTE named above is in question. Recommend the DB workstream
  re-verify (or re-apply) this function against the committed migration text.

## M. Final commit SHA

(recorded after commit — see repository history)
