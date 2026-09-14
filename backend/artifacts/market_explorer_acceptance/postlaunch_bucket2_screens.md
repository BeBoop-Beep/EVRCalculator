# Market Explorer correction bucket 2 — Screens

## A. Starting branch/HEAD

- Required/current branch: `develop`
- Expected HEAD: `d2dcf594`
- Actual clean starting HEAD: `184b702a` (the shared branch had advanced)
- No branch or worktree created.

## B. Screen product contract

PASS. Screens are client-side selection over already-published prepared series. Selecting one highlights it and immediately renders its ranked results without changing Builder state or adding results to the graph.

## C. Registry result

PASS. `MARKET_EXPLORER_SCREENS` contains only `rankedPrepared` and `rankedDrawdown` entries. Builder templates remain exclusively in `MARKET_EXPLORER_QUICK_PRESETS`. The draft helper was renamed and narrowed to Quick Presets so Screens have no draft-conversion API.

## D. Selected-state visual language

PASS. Screens and Reference Market now share `ExplorerSelectableRow` primitives for the teal border/tint, focus ring, and non-color check indicator. Screen rows do not receive a fake series marker.

## E. Immediate prepared results

PASS. Selection synchronously runs the existing `resolveScreenResults` over in-memory `preparedSeries`. Rows expose stable rank, market label, and the Screen metric. Empty scans retain selection and show the explicit prepared-market empty message.

## F. Add/Active behavior

PASS. Inactive rows invoke `onAddPrepared` exactly once and never invoke `onAddQuery`. Active rows remain readable buttons with an explicit Active label/current state and do not silently remove the market.

## G. Builder-draft neutrality

PASS. The legacy dead Screens handoff—which contained `builder.replace`—was removed. The live Screens block has no Builder replace, Build Market, or query-add path. Component tests verify the Builder preview is unchanged across Screen selections.

## H. Asset context

PASS. Cards shows card-compatible Screens/results; Sealed shows sealed-compatible Screens/results. Generic momentum/drawdown scans are filtered to the current asset. Asset-specific selection clears when it becomes incompatible.

## I. Quick Preset isolation

PASS. Obtainable, Intermediate, Premium, New Release, Established, and Top 10 in Selected Set remain Quick Presets and do not render inside Screens.

## J. Network behavior

PASS. The Screens source block contains no fetch, routing, custom-query, build, or scroll path. Selection/results use local state and prepared data; Add uses only `onAddPrepared`.

## K. Accessibility

PASS. Screen buttons expose `aria-pressed`, keyboard-native activation, focus-visible rings, and an `aria-hidden` check. Result buttons have Add/Active accessible names. Plan gating remains unchanged; paid Screen content remains Plus-access controlled by the existing access panel and entitlement helper.

## L. Tests/build

- Focused Screen registry/model, QueryBuilder component/source, and Explorer layout regression suite: 41 passed, 0 failed.
- Production frontend build: passed.
- `git diff --check`: passed with line-ending warnings only.
- The broader `MarketExplorerClient.contract.test.jsx` emitted no assertion failure but retained a pre-existing open handle and was terminated; it is not counted as completed.
- Existing webpack cache, lint, and test-renderer warnings remained non-fatal.

## M. Files changed

- `frontend/lib/explore/marketExplorerScreens.mjs`
- `frontend/components/explore/MarketExplorerQueryBuilder.jsx`
- `frontend/components/explore/ExplorerMarketOption.jsx`
- `frontend/components/explore/ExplorerSelectableRow.jsx`
- Focused Screen registry, source-contract, and QueryBuilder component tests.

## N. Genuine blockers

None for Bucket 2.

## O. Commit SHA

Implementation: `dffa8542`

## P. Bucket-3 readiness

Bucket 2 is source-complete and verified. Bucket 3 was not started.
