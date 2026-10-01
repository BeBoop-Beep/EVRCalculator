# B6 fixture performance summary

All numbers below are **FIXTURE / LOCAL ACCEPTANCE TIMINGS**. They are not
production p50/p95 measurements.

## Current B6 production-browser measurements

| Flow | B6 result | Prior reference | Assessment |
| --- | ---: | ---: | --- |
| Product Scores, normal first click | 935.7 ms | B4 1,226.7 ms | no regression |
| Product Scores, 250 ms delayed | 1,189.0 ms | B4 1,000.2 ms | within 2x; no new waterfall |
| Product Economics, normal | 142.0 ms | B4 72.3 ms | under 2x; request shape unchanged |
| Product Economics, 250 ms delayed | 372.3 ms | B4 345.2 ms | no regression |
| Product page 1 -> 2, normal/delayed | 151.9 / 341.0 ms | B4 134.4 / 340.7 ms | no regression |
| Product Economics -> Scores warm | 46.2 / 56.3 ms | B4 45.8 / 53.7 ms | stable |
| Cards Collector click -> shell | 356.0 ms normal; 358.4 ms delayed | B5 361.5 / 362.0 ms | stable |
| Cards Collector click -> rows | 364.5 ms normal; 828.9 ms delayed | B5 371.1 / 787.3 ms | stable |
| Cards warm return | 145.9 / 131.4 ms; **0 row requests** | B5 63.2 / 41.2 ms | slower render, no network regression and below 2x only narrowly exceeded for normal; no duplicate/waterfall |
| Premium Chase first click | 438.6 ms | B5 401.5 ms | stable |
| Chase -> Collector warm | 75.8 ms; **0 row requests** | B5 72.5 ms | stable |

Product payloads remained bounded: public page 5,099 bytes, paid Scores page
9,184 bytes, and paid Economics page 14,013 bytes. Card payloads remained
bounded: Collector page 12,264 bytes, Collector facets 184 bytes, Chase page
23,936 bytes, and Chase facets 184 bytes.

The Overview graph's established B3 controlled result remains applicable to
this unchanged source chain: one deduped default request, zero requests for
focus/hover/tooltip/Clear All, zero requests for cached Set subsets and warm
range returns, and one anchored request when changing range in Overall-only
mode. Under the B3 throttled fixture the optimized prewarm made the graph usable
in 3,195-3,274 ms versus 3,444-3,468 ms before B3. Era and Set first-click
request cardinality remains one public headline plus at most one paid wide
scorecard read; the B6 focused contracts verify this architecture.

No unexplained greater-than-2x network degradation, duplicate request, serial
N+1, or bundle increase was found. `/Rankings` First Load JS remains **119 kB**.

`LIVE_DB_ACCEPTANCE_BLOCKED`: no legitimate live credentials were available,
so these results intentionally make no production latency claim.
