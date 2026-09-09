# Market Explorer post-launch interaction corrections — 2026-09-08

## A. Branch/develop synchronization

The permanent branch `fix/backend-memory-restart-p0-20260904` was already synchronized to the requested observed `origin/develop` revision `f5469962ebfb24976ca6993a3fd9fa57b64922e7` before implementation. No branch, worktree, rebase, reset, or force push was used. Concurrent staged work was preserved.

## B. Exact Items workspace

Exact Cards and Exact Sealed now open a dedicated `role=dialog`, `aria-modal=true` workspace. It is full-screen on mobile/tablet and a centered, viewport-bounded two-column workspace on desktop. Search receives focus, Tab is trapped, Escape closes, and focus returns to the Exact Items trigger. Results use materially larger artwork and retain exact physical-instrument metadata, debounce, abort/stale suppression, duplicate prevention, and the 25-item ceiling. The selected basket and sticky action footer remain visible. Build/Update/Save-as-new execute inside the workspace; failures leave it open with selections preserved.

## C. Screens product-model correction

`MARKET_EXPLORER_SCREENS` now contains discovery screens only. Selection is an actual `aria-pressed` button with teal selected treatment and a check marker. Results appear immediately, add prepared markets without mutating the draft or issuing a custom build, show `Active` when already selected, and expose an explicit empty state.

## D. Quick Presets

The six former builder templates now live in `MARKET_EXPLORER_QUICK_PRESETS` and a separate Quick Presets disclosure. Applying one modifies the draft and requires Build. Match state is derived from the normalized relevant draft axes and clears after a conflicting manual change. Selected-set Top 10 rejects zero sets and multiple sets with distinct messages.

## E. Relative-performance research

The accepted comparison model is first-visible-value normalization: `(raw / firstVisibleRaw - 1) * 100`. This matches the supplied TradingView Compare/indexed-to-100 research basis and is appropriate for comparing independently based lifetime Market Index series.

## F. Chart implementation

The shared chart transforms each selected published window independently, anchors its first non-null observation at 0%, preserves nulls, and retains raw values alongside display percentages. The y-domain operates on relative percentage values, always includes zero, adds truthful padding, and uses a restrained 0.75 percentage-point minimum span. Axis labels are percentages and the tooltip plus screen-reader description expose both period performance and canonical Market Index.

## G. /Market parity

Both `/Market` and `/Market/Explorer` use `MarketPerformanceChart`; the presentation-only normalization is implemented in that shared primitive. Backend trends, stored index values, fingerprints, family changes, and cache/query math are untouched.

## H. Live auth correction

`MarketExplorerClient` now consumes `useAuth()` and treats the provider's live user as client-shell authority, while retaining the server prop fallback for first paint and isolated tests. Backend/API entitlement remains authoritative.

## I. Filter-options auth retry

The option hook keys retry behavior to live `authRevision`/authentication state, caches only successful canonical payloads, and does not loop on signed-out/failure state. The client is the production request owner; the Builder fallback is enabled only when the options prop is omitted by a standalone consumer.

## J. Build/error feedback

Build state distinguishes idle, building, success, error, and locked outcomes. Errors render beside the sticky CTA with `role=alert`; modal errors render in its sticky footer. Draft, exact selections, and existing active lines remain intact on failure.

## K. Desktop QA

Production compilation passed. Authenticated desktop browser QA was intentionally deferred at the user's direction. The user will perform manual verification. No additional QA token was created.

## L. Mobile QA

Static responsive contract and production compilation pass: the exact workspace is full viewport below desktop, has independently scrolling results/basket regions and a sticky footer. The user will manually verify the authenticated 390×844 experience.

## M. Network QA

Implementation preserves debounced bounded exact search; Screen and preset selection are client-only; timeframe transformation is client-only. Successful option payloads remain cached, signed-out state retries once on auth transition, and Builder fallback shares no production ownership.

## N. Tests/build

- Relative performance/domain/Screen registry: 15/15 passed.
- Exact picker behavior: 3/3 passed.
- Post-launch source contracts plus Screen/chart/domain coverage: 18/18 passed.
- Next.js 15.5.15 production build: passed with pre-existing lint/cache warnings.

## O. Genuine blockers

None for source readiness. Authenticated desktop/mobile browser QA was intentionally deferred at the user's direction and is user-owned manual testing, not an implementation blocker. The earlier one-time token remains deleted, and no additional credential was created. No database change was required or made.

## P. Commit SHA

Implementation commit: `d78f7719`.

## Q. Pre-manual-test completeness audit

- **Exact Items — FIXED IN THIS PASS.** The picker remains outside the rail as a full-screen mobile/centered desktop dialog with large card/sealed artwork, bounded debounced search, stale cancellation, keyboard selection, duplicate/25-item guards, removable basket, narrowing disclosure/clear, and sticky Build/Update/Save-as-new/Cancel actions. The audit corrected edit-session closure and focus restoration after successful modal actions; failure and Premium-lock paths retain the workspace and draft.
- **Screens — PASS.** The registry contains only prepared discovery types. Screen selection is draft- and query-neutral, synchronizes disclosure/visual selected state, uses `aria-pressed`, teal treatment and a check, and immediately exposes ranked Add/Active results or the explicit empty state.
- **Quick Presets — PASS.** All six templates live separately under Quick Presets, modify draft state without executing, derive selection from the relevant normalized draft axes, clear on conflict, and enforce exactly one set for Top 10 with distinct zero/multiple-set messages.
- **Chart — FIXED IN THIS PASS.** Every selected window and series independently anchors its first non-null raw index at 0%; nulls remain null. The shared `/Market` and Explorer primitive retains raw values, computes only display percentages, uses a zero-inclusive relative domain with a restrained 0.75-point floor, formats signed percentage ticks, and now explicitly labels the tooltip value as the selected timeframe's performance beside canonical Market Index. Formula tests pin 7D/30D endpoint agreement.
- **Auth — FIXED IN THIS PASS.** Explorer uses the live AuthContext user with server-prop fallback. The audit restored explicit signed-out `Not authenticated`/Sign in presentation, while live plan changes immediately re-gate controls. The single production options owner retries once after signed-out-to-authenticated revision change, caches success, and does not loop or double-fetch.
- **Errors — PASS.** Idle/building/success/error/locked states are explicit. Builder and modal failures render adjacent to their CTAs with alert semantics, preserve useful backend text and all draft/selection/active-line state, and remain distinct from a Screen empty result.
- **Responsive — PASS.** Source contracts keep the dialog viewport-fixed and rail-independent, desktop-bounded, mobile full-screen, with internally scrollable result/basket surfaces, useful artwork, sticky search/action regions, and reachable Screen/Preset buttons. Manual visual validation remains intentionally pending.
- **Regression — PASS.** The non-toggle signal row, one Active Markets strip, shared large transparent chart, Pokémon environment, left Builder rail, single comparison hierarchy, and Constituents → Comparison Analysis → Methodology order remain intact. Backend trend/storage, query fingerprints, family changes, chain-linking, query/cache engines, constituent paging, and the 37-cache architecture were not changed.

Focused audit suite: 38/38 passed. Next.js 15.5.15 production build passed with the repository's pre-existing lint and webpack-cache warnings. `git diff --check` passed for scoped files.

No browser verification is claimed. Authenticated desktop/mobile manual validation is pending by explicit user direction, and no QA credential was created.

## R. Remaining implementation gaps

None.

Manual validation pending; source implementation complete.

Final status: `MARKET_EXPLORER_POSTLAUNCH_INTERACTIONS_SOURCE_READY_USER_QA_PENDING`.
