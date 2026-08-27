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

The deterministic response projection against that same live snapshot is 119,426 bytes for Set Value, reducing immediately visible critical JSON from 452,655 to 198,402 bytes (56.2%). The already-running backend process did not contain this working-tree code, so an after-change latency/RSS claim would be misleading; rerun the command after restart/deploy and compare its structured `market_request` RSS records.

