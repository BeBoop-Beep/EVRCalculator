# Market Explorer Remap Phase 6 — Exact Basket V2

Status: `MARKET_EXPLORER_REMAP_PHASE6_SOURCE_COMPLETE`

## A. Starting SHA

Source integration resumed from `f53457c1` on `develop`. Existing Phase 5 and unrelated intervening work were preserved.

## B. V1 architecture and audit

V1 explicit definitions remain normalized under `pokemon-market-explorer-query-v1-explicit-instrument`, retain their `asset + instrumentIds[]` fingerprint payload, and remain readable through the shared cache. V1 detection uses `normalized_spec.contractVersion` semantics. Editing translates the explicit definition in memory; no persisted V1 row or fingerprint is rewritten.

## C. V2 identity contract

All new Exact Baskets use `pokemon-market-explorer-query-v2-qualified-explicit-instrument` and `instruments: [{asset, instrumentId}]`. Canonicalization trims and validates values, deduplicates by the qualified pair, sorts by asset then ID, enforces 1–25 leaves, makes fingerprints selection-order independent, and keeps identical raw IDs in different assets distinct. Cards-only, Sealed-only, and mixed definitions resolve cache asset to `cards`, `sealed`, and `mixed` respectively.

## D. Premium entitlement

Exact execution uses the centralized explicit-instrument capability. Basic and Index+ see a closed Premium entry gate; Premium can create, update, save-as-new, and compare an Exact Basket with prepared Phase 5 markets.

## E. Standalone workspace

Exact Basket is a top-level Explorer creation surface outside asset-specific Custom Builder filters. The Builder no longer mounts the Exact picker, and historical narrowing UI/concepts were removed from Exact.

## F. Mixed search

Search defaults to `asset=all` and offers All, Cards, and Sealed discovery scopes. Scope changes affect results only. Selected qualified Cards and Sealed Products coexist and remain selected across scope changes. At 25 leaves search remains available while only additional Add actions are disabled.

## G. Independent draft

Exact owns independent component state and never reads or mutates Builder Era, Set, rarity, Pokémon, price, age, ranking, mode, or Top-N fields. Close/reopen retains the session draft; edit, cancel, save-as-new, and update flows remain separate from Builder state.

## H. DB RPC integration

The backend adapter calls only `get_pokemon_market_explorer_explicit_basket_series_v2`. Aggregate identities are not accepted. Canonical search remains `search_pokemon_market_explorer_instruments_v2`; application source does not call the retained `_unfiltered_phase2` function.

## I. One-unit methodology

The UI and result metadata state one physical unit per qualified leaf. There are no quantities, sliders, equal-weighting, custom weighting, or alternate composition semantics.

## J. Coherent as-of handling

`basket_as_of` drives current basket value, constituent prices, shares, and displayed as-of state. `ready`, `stale`, and `unavailable` stay distinct. Unavailable baskets fail with an explicit unavailable response; null prices are never presented as zero.

## K. Chain-link/index integration

DB `common_instrument_count`, `common_current_value`, and `common_previous_value` feed `build_chain_linked_history_from_cohorts`, the existing canonical common-cohort chain-link path. `basket_value` is retained only as tracked value and is never used to calculate raw returns. A focused test pins a $10 → $1,010 tracked-value jump to a -10% common-cohort return/index move rather than +10,000%.

## L. Value-share display

The bounded Exact summary retains DB-provided current constituents (maximum 25). Selected rows use each item’s asset-specific identity/artwork/metadata and show DB `marketPrice` and `valueSharePercent` when current build state is available.

## M. V1 edit compatibility

V1 editing restores membership from `instrumentIds` and the V1 asset, not priced constituents, then creates an in-memory qualified V2 draft. Any update or save-as-new is submitted as V2 while the old V1 cache identity remains untouched.

## N. Cache lifecycle

Exact V2 reuses the existing query cache, claim/renew heartbeat, detail preparation and bounded upsert, stage-from-detail, finalize, fail, typed states, and comparison-series integration. Lineage is `pokemon-market-explorer-exact-basket-v2` / `pokemon-qualified-leaf-one-unit-v1`.

## O. Mixed invalidation

No alternate invalidation path was introduced. Mixed qualified definitions use the live scoped invalidation extension and existing detail publication lifecycle.

## P. Migration mirroring

The four live Phase 6 migrations are mirrored verbatim in both canonical trees without reapplication. Ledger MD5 values pass: `49f8184f49c9edface89cb12983686c8`, `ad8084a3f9ee4fd26d16ce32dcd0a537`, `35a28f3e34fbe111103018fede255388`, and `fa2cb59a708700fcfe37b379bc56eda3`.

## Q. Tests

- Focused backend query, exact, planner/cache, search, API/access, and migration coverage: 203 passed.
- Focused frontend V2 identity, standalone workspace, access, Builder-state, and Phase 5 regression coverage: 120 passed.
- Live read-only smoke query: mixed Card+Sealed returned `ready`, two selected/two priced/current constituents, coherent `basket_as_of=2026-09-10`, and basket value $570.72.
- `git diff --check`: passed after final cleanup.

## R. Frontend build

`npm.cmd run build` passed under Next.js 15.5.15. Existing repository lint and webpack-cache warnings remain non-fatal.

## S. Files changed

Changes cover canonical frontend/backend V2 normalization, Exact RPC/result adaptation, shared cache version metadata, bounded current-constituent summaries, standalone Exact UI and query integration, migration mirrors, focused tests, and both acceptance artifacts. Main `/Market` and Phase 5 prepared Browse/Compare/Screens behavior were not changed.

## T. Caveats

The repository’s older Prompt-1 migration byte-hash test remains platform-sensitive to CRLF checkout normalization; the independent Phase 6 mirror test passes normalized authoritative hashes. No Phase 7 work was started.

## U. Final commit SHA

Phase 6 source integration commit: `a9ef1772`. This report and final whitespace cleanup are carried by the immediately following acceptance commit.
