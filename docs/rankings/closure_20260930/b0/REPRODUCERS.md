# Rankings Bucket 0 reproducers

All browser reproducers must use a production build (`npm.cmd run build` plus `next start` with its isolated `PERF_AUDIT_DIST_DIR`), never `next dev`.

## Anonymous Era/Set gate

1. Open `/Rankings` in a clean anonymous browser context.
2. Select `Eras`, then `Era RIP Score`.
3. Observe the current “available with Index Plus or Premium” lock and confirm no scorecard request is made.
4. Select `Sets` and observe the same lock.
5. Expected after Bucket 1: narrow headline rows load publicly; Financial/Chase/Collector/history remain absent from response bytes.
6. Direct checks: anonymous `/api/tcgs/pokemon/rankings/scorecards?entity_type=set|era` currently returns 401. Do not fix by unguarding that wide endpoint.

## Product scale mismatch

1. With legitimate Plus access, open Rankings -> Products -> Scores.
2. Capture `/api/explore/product-rankings/scores`.
3. Compare `ripScore.score` and `benchmarkReferenceScore` to the underlying live `overall_rip_v12_score`.
4. Current source reproducer: `project_product_contract` passes `row.overallRipScore` (absolute 0–100) into `benchmark_presentation` (5.0-centered 0–10 presentation).
5. Live bounded examples include 53.073 and 51.2042, while the rendered reference label says 5.0.
6. Query the Product Benchmark publication key. Current expected result is zero published headers. Never divide/clamp as a workaround.

## Product Scores -> Economics

1. Start a fresh legitimate Plus session and record network/performance entries.
2. Open Products; wait for Scores render-ready.
3. Select Economics once; record module-ready, request start/response, payload bytes and render-ready separately.
4. Return to Scores, then Economics; record the warm session-cache transition.
5. Verify economics came from its separate key and exact Best-Open source date is shown.
6. Repeat after cache age exceeds 60 seconds.

## Cards login -> Overall empty/fails -> refresh recovers

1. Start logged out in a clean context and open `/Rankings`; keep network and console recording active.
2. Log in through the normal application flow using an authorized Plus test account.
3. Navigate to Cards -> Collector Appeal -> Overall without reloading.
4. Record auth revision, request-key identity, Cookie/Authorization presence at the Next proxy, response status/body, cache key, UI state and timing.
5. If empty/error occurs, save evidence before refresh. Refresh once and repeat the identical request.
6. Compare request credentials and response, not only UI text.
7. Confirm a real empty response renders an explicit empty state; transport/401/403/5xx renders error plus retry; neither may render “0 ranked cards” as if successful.

Confirmed source facts: cache identity changes with user/access mode; the Card hub remounts on that identity; same-origin fetch uses the browser's cookie policy. Hypotheses requiring this reproducer: auth cookie becomes available after the initial client transition, an initial 401 is retained in component error state, or a proxy/backend request races auth resolution. No DB cause is confirmed.

## Rapid Card component changes

1. With legitimate Plus access, load Collector Overall.
2. Rapidly select Pokémon -> Trainer -> Artist -> Playability -> Overall.
3. Record every request query (`lens` must match), completion order, cache key and final visible lens.
4. Assert late responses only update their own `results[lens]` entry and never overwrite the selected lens.
5. Apply Era/Set/rarity/search filters and confirm returned `rank` remains the precomputed global component rank.

## Logout/access loss

1. Load paid Product/Card data, then log out without refreshing.
2. Confirm the request key changes to anonymous mode, the keyed subtree remounts and stale paid bytes disappear synchronously.
3. Confirm no superseded in-flight response can repopulate the cleared identity cache.
4. Verify subsequent paid proxy calls return 401/403 and public headline/catalogue surfaces remain usable.
