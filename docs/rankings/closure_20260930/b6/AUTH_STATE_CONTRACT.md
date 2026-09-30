# Cards and Product auth-state contract

| State | Required rendering and requests |
|---|---|
| Resolving | Show a neutral access check; do not show lock, empty, or error and do not issue a paid request. |
| Signed out | Public Product catalogue remains; paid Product/Card rows are absent; Card plan lock may render. |
| Signed in, not entitled | Same protected-data behavior as signed out, with the applicable plan boundary. |
| Entitled | Issue the protected request under the current user/access/publication cache identity. |
| Loading | Show immediate feedback for the active query. Never show prior-filter rows as if they matched. |
| Refreshing | Same-query last-good rows may remain while a forced request runs. |
| Error | Show a local Retry for the active query. |
| Refresh failed with last-good | Keep only same-query authorized rows, state that refresh failed, and offer Retry. |
| Empty | Render only after a successful authorized response with zero rows. |
| Logout/downgrade | Invalidate the generation, clear paid rows/facets, remount on the new identity, and render the public/locked state immediately. |

## Stale-response and cache rules

The mounted consumer accepts a result only when both its cleanup flag and request generation are current. Access identity changes remount Product/Cards via `sessionCache.identity`. Cache scope is `user/session identity + access mode + publication`, while Card entry keys contain lens, filters, page, sorting, and direction. A forced successor owns the cache write; a late predecessor may resolve to its original caller but cannot replace the cached successor. Public catalogue caching remains independent.

No component aborts a shared cache request globally on unmount.
