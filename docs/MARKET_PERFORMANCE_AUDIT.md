# Global Market performance audit

Scope: `/Market` only. Rankings and the set page are intentionally excluded.

## Request trace

Initial navigation is a Next server-component render. `frontend/app/Market/page.js` starts two independent requests concurrently:

| Resource key | Endpoint | Caller | Side | Blocks content | DB reads | JSONB | Cache |
|---|---|---|---|---|---:|---|---|
| `set-market:current` | `/explore/set-value-market` | `getExploreSetValueMarket` | server | Overview + Set Market | 1 | one prepared compact payload | 120s bounded single-key process cache |
| `market-movers:7D` | `/explore/card-market-movers?limit=30` | `getExploreMarketMovers` | server | movers only | 1 | one prepared 30-row payload | 120s bounded single-key process cache |

They are isolated with `Promise.allSettled`: either panel can render when the other fails. There is no hydration refetch for either resource. The page does not request Rankings or the full set-page snapshot.

On desktop, Set Market subsequently loads only the selected row's chart and movers. Value history uses `value-history:<set>:<days>:standard`; movers uses `movers:<set>:7D:10:all`. Identical in-flight calls join. Changing a period uses the already-published per-window row metrics and does not request the backend; the selected chart is clipped locally. Switching back reuses the per-page history cache. Selecting a set never reloads either global endpoint. Mobile loads neither selected-set detail resource.

Retries target only the failed selected history resource. Global panel failures remain explicit transport failures and do not become business `N/A`. A valid stale server snapshot is retained on refresh failure.

## Confirmed findings and changes

- The global route previously needed only two calls; no duplicate hydration burst was found.
- The movers reader selected the complete database row. It now projects `payload_json,market_date,updated_at,card_count`.
- The Set Value publication embeds deep card/sealed Explorer segments that `/Market` never reads. The endpoint now returns only the three visible parent families plus their contract/coverage fields; publication storage and methodology are unchanged.
- Market Explorer's authenticated query-result dictionary was unbounded. It is now capped at 128 entries with its existing 300-second TTL.
- Selected-set mover results were retained without a bound in the browser module. The cache is now capped at 48 sets.
- Market routes had generic exception logs but no duration, payload-size, request-ID, or RSS record. Middleware now emits one compact `market_request` JSON event and response headers `x-request-id` and `x-index-build`; service reads separately report DB duration and major read count.
- `/health` returns the deployed `RENDER_GIT_COMMIT`/`GIT_SHA`/`SOURCE_VERSION` identity without exposing secrets.

## Interaction audit

- Overview window switch: zero requests; active snapshot fields are selected locally.
- Set Market period switch: zero requests; published window contract and cached chart are reused.
- Set selection (desktop): at most two independently-failing slim requests; unchanged global data is not fetched.
- 7D global movers: part of the two-request initial render only.
- Navigate away: server initial requests have bounded fetch lifetimes; client selected-detail effects ignore obsolete results, while their shared helper aborts stalled fetches at 20 seconds.
- Retry: selected history only; no page-wide retry storm.

## Measurement

Run `python -m backend.scripts.benchmark_market_api --base-url <backend> --requests 20`. It reports endpoint, request count, p50, p95, max, mean bytes, and errors. RSS start/after/delta is emitted by the backend for every Market request when `psutil` is installed; repeated runs show whether RSS plateaus. Compare a baseline commit and this commit against the same database and worker configuration. Do not claim network latency improvements from unit-test timings.

Local running-backend baseline (20 sequential requests per endpoint, 2026-08-27):

| Endpoint | p50 | p95 | max | mean bytes | errors |
|---|---:|---:|---:|---:|---:|
| `/explore/set-value-market` | 248.22ms | 780.30ms | 2851.83ms | 373,679 | 0 |
| `/explore/card-market-movers?limit=30` | 130.14ms | 182.82ms | 273.00ms | 78,976 | 0 |

## 2026-08-27 Set Market integrity correction

The malformed live snapshot was built at `2026-08-27T15:55:41Z` from the scheduled checkout logged at HEAD `876718c92b6c31678d2547eaa0b8da4b50975d1e` in local mode with a modified worktree. That commit contains the corrected projection and elapsed-window code, but the output contained neither, proving that the effective runtime/worktree was stale. The old snapshot did not record source identity, so its exact effective source-byte SHA cannot be recovered after the fact.

The real PostgREST projection `cardsMarket:payload_json->cardsMarket` was verified directly against Ascended Heroes and returned Market Index 91.90172147751157 plus its 7D movement. Publication now records `publisherBuildSha` and blocks when any available dashboard Market Index disappears or is malformed. The corrected canonical publication records HEAD `c00de31e49b89151b98b266189da5b2f3a8e8b5c`, 22 eligible sets, 22 available dashboard indices, 22 published indices, and no missing IDs.

Ascended Heroes after publication: Set Value $5,789.11; Market Index 91.90172147751157; 7D Set Value movement -$81.88 (-1.394654%); 7D Market Index return -1.394654%; target/start/end 2026-08-20 / 2026-08-20 / 2026-08-27.

Actual compact read-path benchmark, two 20-request runs against the current server on port 8001:

| Run | Endpoint | p50 | p95 | max | mean bytes | errors |
|---|---|---:|---:|---:|---:|---:|
| 1 | Set Value Market | 519.51ms | 668.32ms | 967.72ms | 207,669 | 0 |
| 1 | Global Movers | 155.72ms | 242.03ms | 526.31ms | 78,976 | 0 |
| 2 | Set Value Market | 503.16ms | 613.23ms | 936.00ms | 207,669 | 0 |
| 2 | Global Movers | 144.38ms | 197.51ms | 339.25ms | 78,976 | 0 |

The stale port-8000 process returned 640,897 Set Value bytes after republishing. The current read path returns 207,669 bytes, a 67.6% reduction. The persisted canonical publication is 641,211 bytes; persistence size and transferred response size are intentionally reported separately.

