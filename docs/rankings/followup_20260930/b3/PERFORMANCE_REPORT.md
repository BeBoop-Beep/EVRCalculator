# Rankings Follow-up B3 - Performance Report

Three kinds of evidence, kept separate. **Fixture/browser timings are not production p50/p95.**

## 1. Live database evidence (read-only Supabase inspection, supplied for B3 planning)
| Fact | Value |
|---|---|
| Financial-history authority | 336 rows, 24 entities, history 2026-08-22 .. 2026-09-30 |
| 22-Set 30D request | 110 rows, ~58 KB JSON, ~10.5 ms warm DB execution |
| 3-Set 30D request | ~44 ms on a colder DB read |
| Lookup index | exists on `(entity_type, entity_id, market_date, publication_id)` |

Conclusion: **no migration or index was added.** The multi-second graph delay is not database volume; B3 therefore works on request start time, duplicate/serialised requests, caching and render.

## 2. Source inference (before B3)
- The chart owned its request locally and called `readFinancialRipHistory` directly, bypassing the Rankings session cache: no deduplication, no reuse across Set add/remove, range revisits or Era presets.
- The request could only start after: auth resolved -> lazy `OpeningEconomicsOverall` chunk -> chart mount -> seed effect -> render -> fetch effect. Nothing started it earlier.
- An Era preset (selection change) could fire the same bounded request twice (observed below).

## 3. Fixture / browser measurements
Setup: production build, Playwright/Chromium, 22 Sets + 2 Eras fixture (14 publication dates), history route mocked with **250 ms** latency, auth route **150 ms**, local mock for the page's SSR data. "Before" = B2 `9de00997` built from the same tree; "after" = B3. Numbers are fixture-relative.

### Default cold graph (no throttling, 3-4 runs each)
| | auth->request start | usable (ms from navigation) |
|---|---|---|
| Before | 6-8 ms | 563, 569, 582, 629, 630, 633, 654 |
| After | 7-15 ms | 560, 568, 571, 595, 639, 644, 647, 650 |

No measurable difference on an unthrottled local machine: the request already starts within ~7 ms of auth because the lazy chunk is instant. (One earlier unwarmed baseline run showed a 1.07 s gap from auth to request start and 1.71 s to usable - cold-server noise, not used.)

### Default cold graph under CPU x4 + 1.6 Mbps / 150 ms latency throttling (3 runs each)
| | auth resolved | request start | auth -> request | usable |
|---|---|---|---|---|
| Before | 2263-2308 ms | 3060-3080 ms | 761, 797, 816 ms | 3453, 3444, 3468 ms |
| After | 2246-2272 ms | 2348-2359 ms | 76, 80, 113 ms | 3212, 3274, 3195 ms |

The parent prewarm removes ~0.7 s of idle time between "entitled" and "request sent" and makes the chart usable ~0.2-0.27 s sooner on a slow device. The remaining time after the response is chart-chunk/render cost on the throttled CPU (request start -> usable ~0.85 s in both builds). Honest limit: B3 does not reduce render cost.

### Requests and latency by action (3 runs each, unthrottled)
| Action | Before | After |
|---|---|---|
| Default view | 1 request | **1 request** (prewarm + chart mount dedupe; asserted) then 1 idle 22-Set 30D prefetch |
| Add a 4th Set | 1 request, 353-370 ms | **0 requests**, 92-104 ms |
| Era preset (16 Sets) | **2 requests** (duplicate), 368-381 ms | **0 requests**, 106-116 ms |
| Clear All | 0 | 0 |
| Focus / hover focus / remove | n/a | 0 requests |
| Tooltip hover / wheel / pin | 0 | 0 requests |
| Overall-only 30D -> 3M | n/a | 1 request (1-entity anchor, range 2026-07-03..2026-09-30) |
| Overall-only 3M -> 6M | n/a | 1 request (range 2026-04-04..2026-09-30) |
| Warm return to a loaded range | n/a | 0 requests |
| Switch to Eras mode | n/a | 1 request (`era` x 2, authoritative Era history) |
| Back to Sets | n/a | 0 requests |

Warm same-session render is a synchronous cache apply inside the fetch effect; it was verified as "no request, no spinner" but not separately timed.

### Bundle
`/Rankings` First Load JS 115 kB -> 119 kB (legend, tooltip, cache modules).

## Architecture notes
- Cache: `lib/rankings/financialHistoryCache.mjs` wraps the existing session cache (`request`/`peek`); a per-cache `WeakMap` index records completed responses so a wider response for the same `(type|start|end)` serves a narrower selection by pure row filtering. No second cache system, no global/shared store, nothing persisted.
- Prewarm: `RankingsLazyClient` starts the chart's own key once auth is resolved, the viewer is entitled, the cohort has identities and the publication date is known. Prefetch: after the default response, one idle request for the full <=22 cohort of the same range; skipped under save-data, for non-entitled viewers, and when the cohort would exceed the API ceiling. Not preloaded: other ranges, 1Y/ALL, Era mode.
