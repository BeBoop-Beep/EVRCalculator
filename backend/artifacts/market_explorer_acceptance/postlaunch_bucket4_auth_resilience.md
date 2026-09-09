# Market Explorer post-launch Bucket 4 acceptance

## A. Starting branch/HEAD

- Branch: `develop`.
- Starting HEAD: `693b8aca8dd0b17ca317db53c67c526133c68078`, matching the requested baseline.
- Existing unrelated scheduler/log and backend-script work was left untouched. No branch or worktree was created.

## B. Canonical options ownership

`MarketExplorerClient` remains the production owner of `useMarketExplorerFilterOptions`. It passes an explicit `optionsProvided` ownership sentinel plus options, status, message, retry, and retry-progress state to `MarketExplorerQueryBuilder`. The Builder's local loader is disabled whenever the parent owns state.

## C. Parent-null/error-state correction

Ownership is no longer inferred from payload truthiness. A parent-owned `options=null` with unavailable or offline status renders that exact state and cannot fall through to a second hook's loading state. Standalone tests opt into their fixture ownership explicitly.

## D. Automatic retry policy

Transient cold-load failures receive two bounded retries after 350ms and 850ms. The hook owns timing, cleanup, deduplication, and state transitions. Retry timers are cleared and resolved during cleanup so no pending operation can later mutate an unmounted owner.

## E. Retry classification

One helper classifies transport failures and HTTP 5xx as retryable. HTTP 401, 403, and deterministic 4xx responses do not retry automatically. HTTP status remains attached to internal results for truthful classification.

## F. Manual Retry Filters behavior

After unavailable or offline exhaustion, the Builder shows `Retry filters`. It delegates to the canonical owner, joins any current operation, runs the same bounded policy, and never invokes custom-query POST behavior. While retrying, the action reports progress and is disabled against duplicate clicks.

## G. Same-page login recovery

The Explorer derives identity from the live sitewide `AuthContext` user and supplies `authRevision` to the options owner. A revision after login invalidates the older generation, waits for an older in-flight request without duplicating it, and then makes one fresh authenticated options request. A late 401 cannot overwrite its success.

## H. Same-page plan/entitlement recovery

Plan access is recomputed from the live AuthContext user. Canonical-user equality already treats `index_plan` changes as meaningful and increments `authRevision`. If taxonomy is missing, that revision triggers recovery; if a successful taxonomy is already cached, it stays rendered without loading flicker while access updates from the new plan.

## I. 401/403 presentation

401 maps to signed-out/session presentation and never enters a retry loop. 403 maps separately to entitlement/plan-lock presentation, is not described as signed out or as a service outage, and offers no meaningless filter retry.

## J. Successful cache preservation

Only successful canonical payloads enter the module cache. Failures never poison it. A failed manual/background revalidation retains the last known-good payload in ready state, preserving usable controls and avoiding a loading/error flash. A later successful response atomically replaces the cached canonical payload and clears old error text.

## K. Race/stale-response protection

Hook generations prevent old completions from committing after auth changes or unmount. In-flight requests are coalesced. Cache versions let simultaneous retry consumers accept the same newly successful resolution without either merging arrays or starting a redundant follow-up request.

## L. Network behavior

Options recovery calls only `GET /api/market/explorer/query`. The existing proxy still forwards the ordinary cookie/session, uses `cache: no-store`, and returns `Cache-Control: private, no-store`. No bearer injection, second route, custom-query POST, exact search, constituents request, chart fetch, or mutation was introduced.

## M. Builder draft preservation

Retry state is external to `useMarketExplorerBuilderDraft`; no draft action is dispatched by loading, retry, failure, or recovery. Known-good options remain mounted after transient revalidation failure, so asset, filter IDs, composition, membership mode, and exact selections remain intact.

## N. Existing AuthContext integration

No authentication mechanism was added. `AuthContext`, its strong refresh, canonical-user comparison, `authRevision`, and `indexPlanAccess.mjs` remain the identity and entitlement authorities. There is no polling, localStorage auth, duplicated `/api/auth/me`, or Explorer-specific subscription listener.

## O. Tests/build

- Focused Bucket 4 plus Bucket 1-3/Builder/auth/proxy/query regressions: 113 passed.
- Focused final options/Builder verification after cleanup refinements: 49 passed.
- Backend options-entitlement and explicit-query regressions: 9 passed using `.venv-api-test`.
- Frontend production build: passed. Existing non-fatal webpack cache, lint, unauthenticated static-generation, and dynamic-route diagnostics were emitted.
- Scoped `git diff --check`: passed; only Git LF-to-CRLF working-tree notices appeared.
- Authenticated browser QA was not run and no QA token was created, as directed.

## P. Files changed

- `frontend/hooks/explore/useMarketExplorerFilterOptions.js`
- `frontend/hooks/explore/useMarketExplorerFilterOptions.resilience.test.jsx`
- `frontend/components/explore/MarketExplorerClient.jsx`
- `frontend/components/explore/MarketExplorerQueryBuilder.jsx`
- `frontend/components/explore/MarketExplorerQueryAuth.contract.test.jsx`
- `frontend/components/explore/MarketExplorerQueryBuilder.controls.test.jsx`
- `frontend/components/explore/MarketExplorerPostlaunchCorrections.contract.test.mjs`
- `backend/artifacts/market_explorer_acceptance/postlaunch_bucket4_auth_resilience.md`

## Q. Genuine blockers

None. The default system Python lacked the backend API test dependencies; the repository's `.venv-api-test` environment was available and passed the requested backend regressions. Unrelated worktree changes remain outside this bucket and were not altered.

## R. Commit SHA

Implementation commit: `44e4fb8ca658ebaa3376279b7eb28d139efabb3e`.

## S. Bucket-5 readiness

Bucket 4 is source/test ready. Same-page visual browser behavior remains intentionally deferred to user-owned manual QA. Bucket 5 was not started.

Final decision: `MARKET_EXPLORER_BUCKET4_AUTH_RESILIENCE_COMPLETE`
