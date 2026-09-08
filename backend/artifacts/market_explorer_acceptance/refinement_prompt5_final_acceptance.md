# Market Explorer Refinement — Prompt 5 Final Acceptance

## A. Branch / starting HEAD

- Branch: `fix/backend-memory-restart-p0-20260904`
- Expected ancestor: `4ace6b517700f03aa13bc15c8882ecf98de31029` (verified earlier in this refinement run).
- Actual Prompt-5 starting HEAD: `0e2659d0fb3b3e83fb80c59b0c69107e962e5749`; the difference was legitimate concurrent shared-branch work.
- Implementation/evidence commit: `85923a43`.

## B. Personal authority audit

- Canonical holdings authorities: `user_card_holdings`, `user_sealed_product_holdings`, and `user_graded_card_holdings`.
- Canonical historical authority: `user_portfolio_value_history` with snapshot date, total/partition values, and partition counts, per the accepted production contract. Repository migration `008_refactor_refresh_user_portfolio_summary_and_deltas_no_live_recompute.sql` confirms the total snapshot path; the repository migration set does not fully reproduce every live partition column.
- Existing holdings repository writes scope by both row ID and `user_id`.
- No canonical persistent Wishlist membership/history authority was found. Current Wishlist surfaces contain mock/generated data and were not used.

## C. Portfolio foundation

- Added one canonical personal source descriptor and an owner-scoped portfolio history adapter.
- Partitions map exactly: Total → `portfolio_value`, Raw → `cards_value`, Sealed → `sealed_value`, Graded → `graded_value`.
- Counts remain point metadata.
- Output is explicitly `seriesKind=value`, USD, and not a market index or return. Holdings flows are explicitly not neutralized.
- The live reader accepts authenticated server identity, independently rejects a mismatched requested owner, and filters the Supabase read by that owner.

## D. Wishlist foundation

- Added the `wishlist` source interface with `available=false` and no points/payload.
- Reason: “Wishlist market history becomes available once saved Wishlist membership is published.”
- No mock Wishlist source is imported or adapted.

## E. Personal-market security

- Identity is SHA-256 derived from owner identity + source type + asset partition + methodology version and uses a `private:personal:` namespace. Raw user IDs never appear in keys or labels.
- Signed-out access and cross-owner access fail closed.
- Personal payloads declare request-private caching and `publicCacheEligible=false`.
- A cache-boundary guard rejects both personal source types and every `private:` identity.
- No production schema or RLS policy was changed. Existing RLS remains defense in depth; application ownership is enforced even for service-role reads.

## F. Final desktop QA

- Real Chromium, 1440×1000, anonymous/basic session: PASS for visible layout.
- One header identity, rail begins at top, Raw is initial draft, three signals span the canvas, one Active Markets strip, chart remains dominant, ambient artwork is visible, and no nested “window inside window” appeared.
- Multi-market Raw + Sealed lines, show/hide controls, constituents, comparison, and methodology rendered coherently.
- Paid Builder interactions are not accepted because no approved authenticated QA session was available.

## G. Wide desktop QA

- Real Chromium, 1728×1050: PASS for visible layout.
- The canvas uses the additional width; rail remains bounded; no excessive margins or horizontal overflow (`scrollWidth=clientWidth=1728`).

## H. Tablet QA

- Real Chromium, 768×1024: PASS for visible layout.
- Intentional stacked composition, full-width chart, collapsible Builder, usable signals/active strip, and no page-level horizontal overflow (`768=768`).

## I. Mobile QA

- Real Chromium, 390×844: PASS for visible basic layout.
- Compact header, horizontal signal/active controls, meaningful chart height, Builder placed after the chart with a Build toggle, readable responsive constituent/comparison cards, and no horizontal page overflow (`390=390`).
- Authenticated Exact Items and edit controls could not be exercised.

## J. Chart-scale visual evidence

- Explorer 7D visually shows the real narrow movements without forcing the domain to include 100.
- `/Market` 7D and 30D were rendered and captured.
- Prompt-4 domain unit contracts cover 12% padding and the 0.75% minimum-span guard, but this run could not record a complete authenticated three-market numeric min/max/domain comparison. That gate remains unaccepted.

## K. /Market parity

- `/Market` returned 200 and rendered under real Chromium at 7D and 30D without layout regression or horizontal overflow.

## L. Exact-item browser QA

- BLOCKED: basic/anonymous access correctly presented the Index Plus boundary before paid Builder controls. No approved QA token/session was present, and no account/plan was mutated.

## M. Edit/update/save-as-new QA

- BLOCKED with the same authenticated-session constraint. Accepted Prompt-3 source/unit behavior was not reopened.

## N. Screens/reference QA

- Source/backend suites cover the accepted Screen, Composition, reference, and set-cardinality behavior.
- Live paid Screen/reference interaction is BLOCKED by the missing approved authenticated session.

## O. Constituent movement QA

- Anonymous maintained-market constituents rendered real rows and movement controls.
- Source/backend contracts cover client-side movement switching and paged requests.
- Full authenticated interaction/network proof is BLOCKED.

## P. Network QA

- Each fresh anonymous Explorer page issued one canonical `/api/market/explorer/query` request; the expected 401 was the paid filter-options boundary, not a page failure.
- No page errors occurred. Development hot-update traffic was excluded as non-product traffic.
- Paid build/search/edit/paging request-count acceptance is BLOCKED by authentication.

## Q. Performance observations

- Browser navigation-to-network-idle observations: first cold Explorer 14.7s; warm Explorer 1.1–1.7s; `/Market` cold 5.2s and warm 1.4s.
- These are local Next development observations, not SLOs. Cold compilation dominates the first measurement.
- Paid query/search/build timings were not observable.

## R. Accessibility

- Semantic disclosure buttons, radio roles, status regions, disabled/locked text, explicit selected/hidden labels, and non-color positive/negative marks remain present.
- Responsive screenshots showed readable contrast and controls.
- Full keyboard traversal of paid interactions is BLOCKED by authentication.

## S. Screenshot paths

All evidence is under `backend/artifacts/market_explorer_acceptance/refinement_final_browser_20260908/`:

- `01-explorer-default-1440.png`
- `02-explorer-interaction-base-1440.png`
- `03-explorer-wide-1728.png`
- `07-screens.png` (basic boundary; paid Screen content unavailable)
- `11-explorer-tablet-768.png`
- `12-explorer-mobile-390.png`
- `13-market-7d.png`, `13-market-30d.png`
- `14-basic-plus-lock-state.png`
- `15-my-markets-foundation.png`
- `browser-evidence.json`

Required paid-only screenshots (Exact search/selection/edit and paid Screens) could not be truthfully produced.

## T. Screenshot-driven fixes

- Added the requested compact My Markets placement.
- No additional Prompt-4 styling change was justified: inspected desktop/mobile captures showed no overflow, crushed chart, excessive rail, clipped foundation copy, or misleading visual amplification.

## U. Full regression

- Personal source/security: 13 passed.
- Broad backend selection: 440 passed, 7,997 deselected; only two upstream Supabase client deprecation warnings.
- Prompt-4 + Prompt-5 source contracts: 10 passed. Two older `MarketExplorerQueryBuilder.contract.test.mjs` assertions fail because they still require the pre-refinement “Market Builder” heading and obsolete `onAddQuery?.(spec)` signature; accepted current behavior is “Market Explorer” and passes Exact Items separately.
- Full frontend runner is currently noisy with 293 pre-existing contract/harness failures, including accepted route/header drift and legacy proxy assertions; it is not a clean repository-wide gate.
- Next production build: PASS (existing lint warnings only).
- Prompt-5 path `git diff --check`: PASS. Concurrent machine log whitespace was excluded.

## V. Runtime health

- Local backend and frontend started successfully; Explorer and `/Market` returned 200.
- This foundation was not deployed. Production maintained-cache health was therefore not mutated or re-audited.

## W. Deferred personal-market items

- Publish Portfolio lines only after product acceptance of value-series presentation and an authenticated API surface.
- Research current-holdings, quantity-aware, holdings-flow-neutralized market performance.
- Publish a real Wishlist membership/history authority and explicitly choose current-membership-repriced vs point-in-time membership semantics.
- Future one-of-each Wishlist value partitions: Total, Raw, Sealed, Graded.
- Future Top Performers: rank by percentage price change over the selected timeframe, never highest price/value and never Chase Top N.

## X. Genuine blockers

- No approved existing authenticated QA token/session was available in the local environment. Creating credentials, extracting browser secrets, or mutating a production plan would violate the prompt.
- Consequently Exact search/select/build, edit/update/save-as-new, paid Screens/reference, paid constituent paging, their bounded network behavior, and full keyboard coverage were not exercised in a real authenticated browser.

## Y. Final decision

`MARKET_EXPLORER_REFINEMENT_AUTH_QA_BLOCKED`

The personal-market foundation is source-ready and secure, responsive review passed, and authenticated Plus Screens/Exact-lock review now passes. A reproducible cache build/publish failure prevents the required custom-market lifecycle and query-constituent browser acceptance.

## Z. Commit SHA

- Implementation and browser evidence: `85923a43`
- Final report commit: populated by the enclosing git commit; use repository HEAD containing this file.

## AA. Auth mechanism and safety

- The user explicitly approved one local QA token for their own existing account.
- The account resolved uniquely from the canonical `users` profile as real plan `plus`; no profile, subscription, or plan field was changed.
- The token was minted with `backend.db.services.frontend_proxy_service.issue_token`, written only to a uniquely named OS-temp file, and used only against `127.0.0.1` local backend/frontend services.
- Normal cookie authentication and all application/API authorization remained active. Local `/api/auth/me` returned 200 and Market Explorer rendered `Index Plus`.
- The token value was never printed, serialized into evidence, included in screenshots, written to this report, or staged in git.

## AB. Plus Screens browser QA

- PASS in real Chromium with the authenticated Plus session.
- Cards: Rarity Leaders, Momentum Leaders, Largest Drawdowns, Obtainable, Intermediate, Premium, New Release, and Established all acted immediately. Ranked Screens exposed results; template Screens visibly applied their definition.
- “Top 10 in Selected Set” remained Premium-locked. No obsolete “Use in Market Builder” handoff appeared.
- Sealed exposed only Sealed Format Leaders, Momentum Leaders, and Largest Drawdowns. Card-only Screens did not leak into the Sealed Builder.
- Evidence: `16-auth-plus-cards-screens.png` and `17-auth-plus-sealed-screens.png`.

## AC. Exact Items Plus-lock browser QA

- Initial live QA exposed and fixed two narrow entitlement defects: the backend search endpoint incorrectly required Premium for discovery, while the frontend access mirror failed to classify explicit execution as Premium.
- After the fix, authenticated `Charizard` discovery returned 20 canonical instruments with one debounced request and no catalog preload. The first five labels represented five distinguishable physical identities.
- Keyboard Enter selected and removed items; the counter reached 5 of 25; duplicate selection was disabled; removal and reselection worked.
- The Plus Build control remained disabled with a clear Index Premium message. The five selected items stayed visible and the attempted keyboard activation issued zero market query requests, so no accidental Global market was created.
- Evidence: `18-auth-plus-exact-populated-lock.png` and `authenticated-closure-evidence.json`.

## AD. Generic edit/update/save-as-new browser QA

- BLOCKED before an active custom instance could be created.
- A Plus-allowed one-axis Premium-price Screen definition reached the real summary endpoint and failed HTTP 500 after cache read/build transport errors.
- A second, narrower one-axis definition (Raw Cards + Gym Challenge set) independently reached the real summary endpoint and failed HTTP 500 at `market_explorer_cache_publish_returned_false`.
- Because no active query instance was returned, Edit → Update, Save as new, and Cancel could not be truthfully browser-tested. Prompt-3 automated lifecycle evidence remains green, but it cannot substitute for this explicitly required browser gate.

## AE. Keyboard acceptance

- PASS: disclosure controls, Cards/Sealed asset switch, Filters/Exact Items switch, search field, Enter-to-select, and selected-item removal had working keyboard interaction and visible focus treatment.
- BLOCKED: active custom-market edit/remove/visibility keyboard traversal because the backend could not create the required one-axis market.

## AF. Authenticated network acceptance

- Final isolated run: one options GET, one debounced instrument-search GET, one summary query POST, zero constituent-page POSTs.
- Screens themselves caused no duplicate market requests. Exact locked Build caused zero query POSTs.
- The one summary POST failed in the existing cache publication path; therefore visibility/timeframe and edit lifecycle request invariants could not be exercised on a query-built instance.

## AG. Constituent movement acceptance

- Published maintained-market movement remains visible and covered by accepted source tests.
- Query-sourced 1D/7D/30D/3M client-only switching and one-request paging are BLOCKED because both legitimate Plus one-axis builds failed before returning an active query series.

## AH. Token cleanup proof

- The exact OS-temp token file was deleted immediately after the final QA attempt; `Test-Path` returned `False`.
- A wildcard check found no remaining `index-market-explorer-qa-*.token` file in the OS temp directory.
- `git status` contains only product/evidence/report changes plus the pre-existing concurrent scheduler log; no token file is present.
- Repository search/report inspection contains no token value. Screenshots show only normal account UI and never credentials.

## AI. Final acceptance rationale

- Auth mechanism: PASS.
- Plus Screens: PASS.
- Authenticated Exact discovery/selection/Premium lock: PASS after two minimal entitlement-alignment fixes.
- Generic Plus custom-market creation: FAIL due reproducible live cache build/publish errors on two distinct one-axis definitions.
- Consequently edit/update/save-as-new, active-query keyboard/network invariants, and query constituent movement/paging remain unaccepted.
- Focused regression: 66 backend tests and 26 frontend source/unit tests passed. Next production build passed with existing warnings.
- Final decision remains `MARKET_EXPLORER_REFINEMENT_AUTH_QA_BLOCKED`; the authenticated session itself worked, but a genuine backend product blocker prevents completion of the remaining authenticated scenarios. No broader cache-architecture work was attempted in this closure-only phase.

## AJ. Custom-cache failure root cause

- CONFIRMED publication defect: rank-first upsert retained old `instrument_id` values, so a reorder could violate `UNIQUE(query_fingerprint, instrument_id)` before the old rank was reconciled.
- CONFIRMED planner defect: summary execution claimed the row before a second full read. The claim changed `ready`/`failed` to `building`, destroyed the status evidence used for incremental-base selection, and transported the full constituent JSON.
- A separate unresolved failure remains for the original global Premium-price axis: its current-date interval-fallback statement failed at the Supabase REST origin with HTTP/Cloudflare 520 after the normal client timeout failures. This occurred before cache publication.

## AK. Planner build-base correction

- The bounded summary row is now captured once before claim and reused as the build base.
- Failed-base integrity uses compact detail count, non-null/unique instrument count, rank bounds, and version metadata from a service-only RPC. Summary mode no longer fetches `current_constituents` to decide reuse.
- Tests prove stale READY summary reuse, FAILED build-base-only behavior, stale/unknown-repair fail-closed behavior, and incompatible-version rejection.

## AL. Detail publication reconciliation correction

- Publication now renews the lease, calls a lease-guarded prepare RPC, then performs the existing bounded upsert/trim/stage/finalize sequence.
- Prepare nulls old generic/legacy identities while the row remains `building`; the uniqueness rule remains intact and no partially prepared row can be served.
- Internal diagnostics now identify lease, prepare, upsert batch offset/count, trim, stage, finalize, and exception stages without payloads or credentials.
- Rollback-only live SQL passed `A,B,C -> C,A,B`, `A,B,C -> B,D,A`, shrink, grow, partial-batch retry, finalization, mismatched token, and expired token.

## AM. Production migration

- Applied forward migration `20260908192748_reconcile_market_explorer_cache_publication` and recorded version `20260908192748` in `supabase_migrations.schema_migrations`.
- Both functions are `SECURITY INVOKER`, have empty `search_path`, deny `anon`/`authenticated`, and grant execute only to `service_role`.
- The production SQL is mirrored byte-for-byte under both migration trees. Existing migration history was not rewritten.

## AN. Original two-query reproduction after fix

- Gym Challenge fingerprint `702144a82725`: PASS. The failed 2026-09-06 artifact incrementally published through 2026-09-08 in 8174.7 ms; 264 detail rows, 264 non-null and unique instrument IDs, ranks 1..264, lease cleared. Immediate repeat used L1 in 178.7 ms.
- Premium-price fingerprint `7771a3cd5510`: FAIL before publication. Bounded one-day interval fallback still exceeded the REST transport/origin envelope; a diagnostic 120-second attempt ultimately received Cloudflare 520 from the Supabase host. The row correctly returned to `failed` with no orphan lease.

## AO. Maintained-cache regression

- FAIL due upstream daily advancement state, not the reconciliation migration: health audit reports 37 maintained caches, 36 ready through 2026-09-06, one Premium cache failed, and 0/37 current against the approved 2026-09-08 watermark.
- V1 and V2 coverage each contain all 165 authority sets but have minimum `computed_through=2026-09-07`; no cache-wide rebuild or invalidation was performed.

## AP. Exact-instrument regression

- The generic uniqueness index was retained and rollback-only live reorder/retry validation passed.
- Full 1/5/25/sealed live cache regression was not run after the Premium compute blocker and maintained-cache freshness gate failed.

## AQ. Authenticated edit/update/save-as-new closure

- BLOCKED. A fresh token was not minted because the required backend gate failed before browser QA; the prior approval was therefore not consumed in this pass.

## AR. Query constituent movement/paging closure

- BLOCKED because the required end-to-end custom lifecycle could not be completed after the Premium-price failure.

## AS. Network/keyboard closure

- BLOCKED for the same active-query prerequisite. Previously accepted Plus Screens and exact-item lock behavior were not reopened.

## AT. Token cleanup

- No token was created in this pass. No token temp file, report value, screenshot value, git change, or log value exists from this closure.

## AU. Final runtime health

- Migration/function/grant verification: PASS.
- Gym Challenge real planner publication/reuse: PASS.
- No orphan maintained build leases: PASS (`building=0`).
- Maintained currentness: FAIL (`ready_and_current=0`, approved watermark two days ahead of caches and one day ahead of V1/V2 coverage minimum).
- Premium-price current-date computation: FAIL (Supabase REST origin HTTP 520).
- Regression suites: 236 focused backend tests and 148 Market Explorer/access frontend tests passed.
- Next.js 15.5.15 production build passed; only pre-existing lint/cache and unavailable-local-backend prerender warnings were emitted.

## AV. Final decision

`MARKET_EXPLORER_REFINEMENT_BLOCKED`

Cache publication correctness and bounded build-base transport are repaired and deployed, but the original Premium-price build still does not return HTTP 200 and maintained caches are not current. Consequently the authenticated lifecycle, constituent paging/movement, and active-query keyboard/network gates cannot be truthfully accepted.
