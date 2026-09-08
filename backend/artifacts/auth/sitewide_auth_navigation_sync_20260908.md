# Sitewide Auth Navigation Synchronization — 2026-09-08

## A. Branch / HEAD

- Branch: `fix/backend-memory-restart-p0-20260904`
- HEAD observed while preparing this report: `34afe63c`
- Auth implementation commit: `1f6f7bce`
- No branch, worktree, rebase, or reset was created or performed.

## B. Observed bug reproduction

The reported production/QA behavior is consistent with the inspected code: the persistent root `AuthProvider` was seeded once by the server layout, while client route transitions did not revalidate it. The Header read only that persistent context. A hard refresh remounted the layout and restored the canonical cookie-backed profile.

Authenticated browser reproduction was not possible in this workspace because no QA credentials or reusable authenticated browser session were available.

## C. Root cause

Next App Router keeps the root layout/provider alive across client navigation. Destination Server Components could resolve the current cookie independently while `AuthContext` retained older client state. The only existing client resolver was a strong `refreshUser()` implementation that cleared the user on every error and always called `router.refresh()`, making it unsafe as a route-change poller.

## D. Auth lifecycle before fix

- `initialUser` seeded client auth state.
- Login and billing flows called `refreshUser()`.
- Every `/api/auth/me` non-OK response or exception cleared the user.
- Every refresh result invoked `router.refresh()`.
- No pathname transition reconciliation existed.
- `authRevision` incremented on every refresh, even when canonical state was unchanged.

## E. New canonical resolver

`frontend/lib/auth/clientAuthLifecycle.mjs` now owns the side-effect-free `/api/auth/me` request and returns one of:

- `authenticated`: HTTP 200 with the complete canonical `user` object.
- `unauthenticated`: HTTP 401 or 403.
- `transient_failure`: other HTTP errors, network errors, aborts, malformed payloads, or JSON parse failures.

The request uses `credentials: "include"` and `cache: "no-store"`. It does not mutate React state or refresh the router.

## F. Soft navigation reconciliation

`AuthProvider` observes `usePathname()`. Each genuine pathname change starts at most one soft resolution. A server-provided `initialUser` suppresses a duplicate hydration fetch; a missing seed performs one mount-time reconciliation to support OAuth/client cookie transitions. Soft sync keeps the current user visible while resolving and never calls `router.refresh()`.

## G. Strong explicit refresh

The public `refreshUser()` remains compatible with login, OAuth completion, billing success, and membership/profile mutation callers. It runs the canonical resolver, commits meaningful client changes, and then calls `router.refresh()` so entitlement-aware Server Components resolve the cookie-backed session again.

## H. Failure semantics

- HTTP 200 replaces the client user with the full canonical profile.
- HTTP 401/403 clears the client user.
- HTTP 5xx, network errors, and parse failures preserve the existing user and set `authStatus` to `degraded`.
- Resolving never clears the current user.

## I. Concurrency protection

A request coordinator supplies monotonic generations and `AbortController`s. Newer requests invalidate older results. A strong request aborts an older soft request, while a soft request is ignored during a strong request. Logout cancels all in-flight resolution before clearing state.

## J. Header identity result

Header identity remains sourced exclusively from `AuthContext`. Its label fallback is now `display_name`, then `username`, then a readable email local part, then `Account`. This is defensive presentation; canonical synchronization remains the primary fix.

## K. Cross-page browser QA

Not executed: no authenticated browser session/credentials were available, and the configured local backend at `127.0.0.1:8001` was unavailable during build-time fetches. Therefore no claim is made for live navigation evidence through `/Market`, `/Rankings`, `/TCGs/Pokemon/Sets`, `/Articles`, `/Market/Explorer`, and `/account-settings`.

## L. Entitlement consistency

Server authorization was not changed. `frontend/lib/authServer.js` remains authoritative for Server Components and paid access. Client state remains presentation/reactivity only. Meaningful canonical profile or plan changes increment `authRevision`; unchanged navigation results do not.

Live Plus-session cross-surface verification was blocked by the missing authenticated browser session.

## M. Network request counts

The implemented lifecycle bounds normal navigation to one intended soft `/api/auth/me` request per genuine pathname change. Initial hydration with `initialUser` makes zero duplicate requests. Soft sync never invokes `router.refresh()`. Rapid transitions abort and invalidate older requests; navigation during a strong refresh starts no competing request.

Static and unit verification supports these counts; live browser network capture was not available.

## N. Tests/build

- Focused auth/header/billing suite: 29/29 passed.
- Expanded focused lifecycle/layout/header suite after concurrency extraction: 19/19 passed.
- Production `npm run build`: passed on clean retry (compile, lint/type validation, static generation, route output). Existing lint warnings remain outside this change.
- Repository-wide `npm run test:frontend`: 2,482 passed and 292 failed. The failures are pre-existing/shared Market Explorer contract drift and missing-module/export failures unrelated to the auth files (examples: `Explore/exploreShell.contract.test.js`, `MarketExplorerPage.contract.test.mjs`, `lib/landing/landingHeroServer.publicAuthInvariance.test.mjs`, and `pokemonSetCardsClient` export tests).
- `git diff --check` on the whole shared worktree is blocked by trailing whitespace in the unrelated modified `logs/task_scheduler_debug.log`.

## O. Genuine blockers

- No authenticated browser credentials/session, so the exact cross-page production QA matrix and request capture could not be executed.
- The local backend was not listening on `127.0.0.1:8001`.
- The shared branch's full frontend suite has 292 unrelated failures.
- The shared worktree has unrelated scheduler-log whitespace changes.

## P. Commit SHA

Auth implementation: `1f6f7bce` (`updates`). The commit was created concurrently on the required shared branch and also contains the active in-scope shared-branch Market Explorer work; history was not rewritten or split.

Final release verdict is withheld until authenticated cross-page QA passes and the required full test baseline is green.
