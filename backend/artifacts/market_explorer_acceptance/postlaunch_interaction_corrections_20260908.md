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

Final status: `MARKET_EXPLORER_POSTLAUNCH_INTERACTIONS_SOURCE_READY_USER_QA_PENDING`.
