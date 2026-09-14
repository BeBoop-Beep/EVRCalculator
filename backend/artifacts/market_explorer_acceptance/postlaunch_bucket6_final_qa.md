# Market Explorer Bucket 6 final QA

## A. Source baseline

- Branch: `develop`.
- Current local HEAD: `73518ae7ca3747020c3c6c7f5df9c17d10abf388`.
- `origin/develop`: `73518ae7ca3747020c3c6c7f5df9c17d10abf388` after fetch.
- There were no intervening commits after the accepted Bucket 5 source, so no commit classification was required.
- Existing unrelated untracked research, rankings, and export-script work was preserved.

## B. Deployment identity

- Preview URL: `https://index-j6wwc2h14-shiny-finds.vercel.app`.
- Develop alias: `https://index-git-develop-shiny-finds.vercel.app`.
- Vercel deployment ID: `dpl_13bCCZdds4TPPSnZfHFkkziWSNTZ`.
- Project/repository: `index` / `EVRCalculator`.
- Git branch: `develop`.
- Git commit: `73518ae7ca3747020c3c6c7f5df9c17d10abf388`.
- Commit message: `Document Market Explorer Bucket 5 acceptance`.
- Created: `2026-09-09T10:27:45.503-07:00`.
- Status: `READY`.
- Environment: `Preview`, not Production.

## C. Deployment parity evidence

Vercel CLI inspection identified the deployment as a Preview and the authenticated Vercel deployment API returned its Git metadata. The served deployment SHA exactly equals both local `develop` and `origin/develop`:

```text
local develop       73518ae7ca3747020c3c6c7f5df9c17d10abf388
origin/develop      73518ae7ca3747020c3c6c7f5df9c17d10abf388
Preview deployment  73518ae7ca3747020c3c6c7f5df9c17d10abf388
```

Deployment parity is proven. No deployment was created or triggered during this gate.

## D. Stale-build fingerprints

`SOURCE-VERIFIED / MANUAL NOT EXERCISED` — the proven-current preview is protected by Vercel Authentication. An unauthenticated request to `/Market` was redirected to the Vercel login flow before application HTML loaded. The four UI fingerprints therefore could not be honestly inspected from this environment.

## E. `/Market` chart QA

`SOURCE-VERIFIED / MANUAL NOT EXERCISED` — Performance/Index, timeframe rebasing, tooltip readings, and keyboard interaction await user-owned manual browser verification.

## F. Explorer layout QA

`SOURCE-VERIFIED / MANUAL NOT EXERCISED` — current source/build regression evidence remains accepted; protected-preview visual verification is pending.

## G. Screens QA

`SOURCE-VERIFIED / MANUAL NOT EXERCISED` — Cards/Sealed discovery, selection, add/active state, and scroll stability await user-owned manual verification.

## H. Quick Presets QA

`SOURCE-VERIFIED / MANUAL NOT EXERCISED` — separation from Screens and Builder-draft mutation await user-owned manual verification.

## I. Reference Market QA

`SOURCE-VERIFIED / MANUAL NOT EXERCISED` — page/rail scroll stability and keyboard toggling await user-owned manual verification.

## J. Exact workspace QA

`SOURCE-VERIFIED / MANUAL NOT EXERCISED` — desktop/mobile workspace, physical-instrument search, draft persistence, Premium build/edit/update, duplicate, and unchanged paths were not exercised. Plus-tier browsing was also not exercised. No QA token was created.

## K. Auth/options QA

`SOURCE-VERIFIED / MANUAL NOT EXERCISED` — same-page login and safely induced transient recovery were not exercised. No application credential was minted or reused.

## L. Builder custom-market QA

`SOURCE-VERIFIED / MANUAL NOT EXERCISED` — paid single-axis, compound, Pokemon-filtered, and ranked compositions await user-owned manual verification. No custom cache entries were created.

## M. Active Markets QA

`SOURCE-VERIFIED / MANUAL NOT EXERCISED` — inspect, visibility, show/hide, removal, Clear Graph, and one-row geometry await user-owned manual verification.

## N. Constituents QA

`SOURCE-VERIFIED / MANUAL NOT EXERCISED` — prepared/query/exact tables, movement windows, pagination, edit actions, and mobile containment await user-owned manual verification.

## O. Comparison QA

`SOURCE-VERIFIED / MANUAL NOT EXERCISED` — multi-series comparison analysis and timeframe changes await user-owned manual verification.

## P. Tooltip QA

`SOURCE-VERIFIED / MANUAL NOT EXERCISED` — pointer, keyboard, dense-series, edge placement, internal scroll, and graph containment await user-owned manual verification.

## Q. Desktop responsive QA

`SOURCE-VERIFIED / MANUAL NOT EXERCISED` at 1280, 1440, and 1728 widths.

## R. Tablet responsive QA

`SOURCE-VERIFIED / MANUAL NOT EXERCISED` at 768 and 1024 widths.

## S. Mobile/touch QA

`SOURCE-VERIFIED / MANUAL NOT EXERCISED` at 390px and on a real touch device.

## T. Network observations

- The only route observation was the Vercel Authentication redirect for `/Market`; application requests did not begin.
- No Market Explorer build, search, constituent, mutation, or cache-publication request was issued.
- No deployment was triggered.

## U. Console observations

No application console observation was possible because Vercel Authentication intercepted navigation before the application loaded.

## V. Defects found

No current-preview product defect was established. Inability to enter a protected preview without an interactive Vercel session is an environment/access limitation, not evidence of a Market Explorer defect.

## W. Fixes made, if any

None. Bucket 6 did not reopen or modify Market Explorer source.

## X. Tests/build after any fixes

No source changed, so no post-fix run was required. The accepted Bucket 5 baseline remains 144/144 focused regressions passed and production frontend build passed. This report does not represent a new test or build execution.

## Y. Remaining limitations / unexercised cases

- All required current-preview UI interactions remain user-owned manual QA.
- Premium and Plus application sessions were unavailable under the standing no-new-token direction.
- The Vercel-protected Preview requires an interactive authorized Vercel browser session.
- Transient 5xx recovery was not induced.
- Browser/device-specific cases were not exercised.

Authenticated desktop/mobile browser QA was intentionally deferred at the user's direction. The user will perform manual verification. No additional QA token was created.

## Z. Final deployment SHA

`73518ae7ca3747020c3c6c7f5df9c17d10abf388`

## AA. Final decision

Deployment parity is proven and accepted source is ready, but the mandatory current-preview interaction matrix was not executed. Therefore `MARKET_EXPLORER_POSTLAUNCH_ACCEPTANCE_COMPLETE` is not claimed, and no defect-based failure is claimed.

Final status: `MARKET_EXPLORER_POSTLAUNCH_INTERACTIONS_SOURCE_READY_USER_QA_PENDING`
