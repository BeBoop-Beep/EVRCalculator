# Market Explorer post-launch Bucket 3 acceptance

## A. Starting branch/HEAD

- Branch: `develop`.
- Requested baseline: `ab3e4cac`.
- Observed clean starting HEAD: `4aa40340`; the permanent shared branch had advanced by one unrelated commit. Work continued in place without a branch or worktree.

## B. Existing modal audit

The existing `MarketExplorerExactItemPicker` architecture was preserved and hardened. It remains the single dedicated exact-item browser, with an accessible fixed overlay, local selected basket, direct build actions, debounced search, and explicit error/status presentation.

## C. Rail behavior

The narrow Builder rail retains only the Filters / Exact Items mode controls and compact exact-item count/open-workspace summary. Search results, artwork, selected rows, and the full browser remain exclusively in the dedicated workspace.

## D. Desktop workspace

Desktop uses a centered, bounded research dialog (`max-w-5xl`, `max-h-[86vh]`) with the results pane receiving the majority of horizontal space and a separate selected-basket pane. Header, search, content, and action footer have deliberate layout ownership.

## E. Mobile workspace

Narrow layouts use the full usable viewport (`100dvh`) with an intentional results/selected grid. Results retain flexible scroll space, the selected basket is bounded to 30vh, and the footer includes bottom safe-area padding.

## F. Artwork

Card results retain useful 80x112 artwork; sealed products use a contained 96x96 square. Failed artwork is replaced by a stable same-size placeholder. Selected rows reuse compact thumbnails and retain their full physical identity labels.

## G. Search/selection

Search remains asset-bounded, 300ms debounced, capped at 20 results, abortable, and protected against stale responses. Duplicate selection is prevented, selections are bounded to 1-25 for execution, selected results read `Added` explicitly, the 25-item ceiling is explained, and removal immediately restores addability.

## H. Close/cancel lifecycle

Close and X now close only the workspace, preserve the exact draft, make no request, and retain the outer edit session. Editing exposes a separate `Cancel edits` action that closes the workspace and delegates restoration/exit to the established edit lifecycle.

## I. Build/update/save lifecycle

Build Market, Update Market, and Save as new remain inside the workspace. Genuine success closes it; update preserves the existing instance lifecycle. Duplicate and unchanged outcomes remain open with actionable messages. Failure remains open and preserves selected items and the existing active line.

## J. Plus/Premium behavior

Execution lock is separated from picker interaction. Plus users can open, search, inspect, add, remove, and retain up to 25 selections. The primary action communicates `Requires Index Premium` and routes interaction through the existing upgrade presentation. Premium execution policy is unchanged.

## K. Narrowing filters

Active semantic narrowing is shown using option labels already in memory for era, set, rarity/product family, Pokemon, price, and release age. Chase composition is shown as `Composition: Top N`. Clear narrowing removes those filters only, preserving asset, explicit membership mode, exact items, and active graph markets.

## L. Edit Items

The Constituents `Edit Items` path continues to set the editing series, restore the explicit definition from `editingSeries.spec + editingSeries.exactItems`, and open this same workspace. It does not reconstruct authority from currently priced constituents.

## M. Scroll/focus accessibility

The workspace retains `role=dialog`, `aria-modal=true`, a labelled title, search autofocus, Escape close, and focus return to the Exact Items trigger. The trap now uses a generic focusable-element selector. Opening saves and locks body overflow; cleanup restores the prior value.

## N. Network behavior

Open, close, local add, and local remove issue no requests. Search alone uses the bounded debounced lookup. Build, update, and save-as-new each retain the single semantic-market request path; no per-instrument market construction was introduced.

## O. Tests/build

- Exact workspace, Builder lifecycle, and post-launch interaction contracts: 40 passed.
- Bucket 1 chart, Bucket 2 Screens, query/auth, draft, and fingerprint regressions: 39 passed.
- Backend explicit-query contract: 8 passed.
- Frontend production build: passed. Existing non-fatal lint, webpack cache restoration, and unauthenticated static-generation diagnostics were emitted.
- `git diff --check`: passed (Git reported only LF-to-CRLF working-tree notices).
- Authenticated browser QA: intentionally not run; no QA token was created, per user direction.

## P. Files changed

- `frontend/components/explore/MarketExplorerExactItemPicker.jsx`
- `frontend/components/explore/MarketExplorerExactItemPicker.test.jsx`
- `frontend/components/explore/MarketExplorerExactWorkspace.contract.test.mjs`
- `frontend/components/explore/MarketExplorerQueryBuilder.jsx`
- `frontend/components/explore/MarketExplorerQueryBuilder.controls.test.jsx`
- `backend/artifacts/market_explorer_acceptance/postlaunch_bucket3_exact_workspace.md`

## Q. Genuine blockers

None. Authenticated desktop/mobile browser QA remains user-owned manual testing and is not a blocker for this source pass.

## R. Commit SHA

Implementation commit: `212cbef3c176477e72392560454af1501291d634`.

## S. Bucket-4 readiness

Bucket 3 is source-ready and independently verified. Bucket 4 was not started.

Final decision: `MARKET_EXPLORER_BUCKET3_EXACT_WORKSPACE_COMPLETE`
