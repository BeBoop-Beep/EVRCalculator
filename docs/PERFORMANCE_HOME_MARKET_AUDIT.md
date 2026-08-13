# Performance Audit — Homepage + Market Critical Path

Branch `feature/perf_updates_two`, starting SHA `7d8478f96a4c31d1c4eabc4af9dc37ef6fc2269f`.
Backend run locally (`uvicorn backend.api.main:app`, port 8000, no `--reload`) against the **live**
Supabase public snapshots. Frontend measured from an isolated production build
(`PERF_AUDIT_DIST_DIR=.next-perf-audit`, port 3100). All payload sizes and DB timings are production
data.

---

## PRE-CORRECTED-PUBLICATION (superseded — retained for history)

Measured 2026-08-13 against publication `builtAt 14:08:34Z`, which predated the Rankings payload
projection reaching the published row.

| Endpoint | TTFB p50 | total p50 | bytes |
|---|---|---|---|
| `/explore/rip-statistics/targets?limit=200` | 1.749 s | 1.750 s | 2,625,401 |
| `/explore/card-market-movers` | 0.058 s | 0.058 s | 79,029 |
| `/tcgs/pokemon/sets/{#1}/insights/secondary` | 0.238 s | 0.239 s | 42,411 |

Service decomposition at that publication: PostgREST row read ~690 ms, **set-value compatibility
fill ~870 ms** (`payload_guarantees_canonical_set_value → False`), serialize 16 ms.

> **These numbers must not be used as an optimization baseline.** The earlier diagnosis that the
> publisher changes were missing from `main` was itself wrong: it read a **stale local `main`**.
> `origin/main` contains `project_latest_rankings_payload`, the V4/V5/V6 and
> `financial_rip_v3_payload` latest-row slimming, `PUBLIC_SET_VALUE_CONTRACT_VERSION` and the
> Set Value marker (merged as PR #112).

---

## Live publication verification

Publication republished at `builtAt 16:22:18Z` / `updated_at 16:23:50Z`. **All gate checks pass.**

| Check | Result |
|---|---|
| publicationId | `8fd439ac-dee3-41a5-bbc3-cbdd5102c0d5` |
| marketDate | `2026-08-13` |
| payload bytes | **1,512,908** (was 2,794,574) |
| targets | 34 |
| `publicRipContractV4` | absent — 0/34 |
| `publicRipContractV5` | absent — 0/34 |
| `publicRipContractV6` | absent — 0/34 |
| `financial_rip_v3_payload` | absent — 0/34 |
| `meta.snapshot.setValueContract` | present — `v1`, coverage `complete`, 34/34 |
| `payload_guarantees_canonical_set_value(payload)` | **True** |
| Set Value compatibility enrichment | **skipped** |

---

## CORRECTED-PUBLICATION BASELINE

### Targets endpoint — 25 reads

| Layer | p50 | p95 |
|---|---|---|
| PostgREST row read | **408.2 ms** | 540.7 ms |
| Set Value compatibility enrichment | **0.01 ms (skipped)** | 0.01 ms |
| JSON serialize | 8.3 ms | 12.3 ms |
| HTTP TTFB | **0.643 s** | 0.719 s |
| HTTP total | 0.653 s | 1.55 s (2 outliers) |

Response bytes **1,425,561** (was 2,625,401 — **−45.7%**). The ~870 ms fill is fully eliminated;
targets is ~2.7× faster end-to-end than the pre-corrected measurement.

### Page servers — before this pass's changes

| | cold p50 (fresh process) | warm p50 | bytes | gzip |
|---|---|---|---|---|
| `/Market` | 0.657 s | 0.051 s | 1,415,318 | 194,229 |
| `/` | 0.945 s | 0.277 s | 107,537 | 23,355 |
| `/Rankings` | — | 0.051 s | 1,343,751 | 186,013 |

Cold-process methodology note: an earlier harness used `kill $!`, which on Git Bash/Windows kills the
`npx` wrapper and leaves the node child listening — every "cold" sample it produced was silently warm,
and interleaved `/Rankings` probes re-warmed the shared canonical cache. The recorded figures come
from a corrected harness that kills by LISTENING PID and refuses to sample unless port 3100 is
confirmed free.

---

## Current over-fetch (against the slim publication)

| | fields | bytes | share of targets array |
|---|---|---|---|
| Full targets array | — | 1,407,091 | 100% |
| Market required | 12 | 16,877 | **1.20%** |
| Homepage required | 40 | 43,312 | **3.08%** |
| **Union** | **40** | **43,312** | **3.08%** |

Market's field set remains a **strict subset** of the homepage's; the union is exactly the homepage
set. Homepage over-fetch is **1,363,779 B (96.92%)**.

Heaviest remaining blocks, none read by either page: `publicRipContractV7` 547,737 (Home reads ~20
leaves of it), `financialRipV3` 272,107, `openingExperience` 157,273, `universalSetDesirability`
70,183, `rip` 38,431, `overallRipV6` 21,784, `ripCore` 21,584, `overallRipV5` 16,711.

---

## Existing-storage feasibility

`pokemon_public_rip_leaderboard_rows` is a small per-set relation and was the strongest candidate.
It **cannot** serve Home/Market:

| Needed | In the relation? |
|---|---|
| set_id, canonical key | yes |
| overall/financial rank, cohort counts, pack price | yes |
| **tier** (overall + financial) | **no** |
| **all Set Value fields** (value, as-of, coverage counts, previous 7d, comparison status) | **no** |
| mean/median value, prob profit, expected loss, max value, simulation count | **no** |
| name, logo, symbol, era, target_type/target_id | **no** |
| distribution marker values (p05/p95/p99) | **no** |

Decisive disqualifier beyond the gaps: `overall_rip_score` stores `overallRipV7.score` — the
**absolute fixed-anchor model score**, not the cohort-relative public score the pages render
(`publicRipContractV7.overallRip.relativeScore`). Serving it under a public label is precisely the
defect `canonicalRipV7.mjs` exists to prevent. Filling the gaps would also require request-time joins
across `sets`, set-value history and simulation runs for 34 sets — reintroducing the ~870 ms of
enrichment the corrected publication just removed — and would couple live pages to
**historical leaderboard** rows, which section 8 protects.

**Conclusion: no existing artifact can serve the shared summary. A new projection would be required.**

---

## Shared summary analysis

A 43 KB shared Home/Market summary published from the same validated payload would remove the
~408 ms PostgREST read and ~1.36 MB of DB→backend transfer from both pages.

**Not implemented in this pass**, deliberately. It requires a new persisted artifact written inside
the publish RPC, which touches **publication atomicity** — explicitly protected scope — and adds a
second cache identity beside the canonical targets cache. With the corrected publication the targets
leg is now 0.65 s rather than 1.75 s, so the remaining prize is smaller than it was, while the risk is
unchanged. It should be a scoped change of its own, not a rider on a frontend pass.

The two changes below were taken instead because they are frontend-only, carry zero publication risk,
and — as measured — capture more user-facing improvement than the summary projection would have.

---

## Changes

### 1. `/Market` — project targets at the server/client boundary

`ExploreTopRankings` is `"use client"`. It was handed whole Rankings targets, so **every** property of
every target was serialized into the RSC flight payload and shipped to the browser:
`publicRipContractV7`, `financialRipV3`, `openingExperience`, `universalSetDesirability`,
`overallRipV6`, `ripCore`, `rip` — all confirmed present in the delivered HTML, none read by the
ladder.

New `lib/explore/marketRankingsProjection.mjs` projects each eligible target to the 19 keys (12 logical
fields across both casings) the ladder actually reads. Eligibility is still decided on the **complete**
target, because the coverage predicate reads fields the ladder does not.

This is **not** offered as the DB→backend fix, and does not pretend to be: `getRipStatisticsTargets`
still fetches the full canonical cohort, deliberately, to preserve the shared cache identity Rankings
and set detail depend on. What it removes is the server→browser copy, which is waste at any payload
size.

### 2. Homepage — cache the spotlight distribution

`getLandingDistribution` was the only landing data source with **no cross-request cache** — targets and
the global movers each hold a 120 s process cache, while this ~240 ms request ran on every homepage
render. With the corrected publication that made it ~86% of warm homepage server time.

Added a 120 s process cache keyed by set id, matching `ripStatisticsServer` and
`exploreMarketMoversServer` exactly. Only successful payloads are cached — a failure retries on the
next render rather than pinning the homepage to a null distribution for 120 s. The request itself is
**not** removed and the real simulation distribution is **not** reconstructed; freshness semantics are
unchanged.

---

## Before / after — same build, same publication, same window

### Homepage

| | before | after |
|---|---|---|
| warm TTFB p50 | 0.0058 s | 0.0089 s |
| **warm server total p50** | **0.277 s** | **0.010 s** (−96%) |
| cold server total p50 | 0.945 s | 0.905 s |
| transfer | 107,537 B / 23,355 gzip | 106,667 B / 21,840 gzip |

### Market

| | before | after |
|---|---|---|
| warm TTFB p50 | 0.0428 s | 0.0099 s |
| **warm server total p50** | **0.051 s** | **0.011 s** (−78%) |
| cold server total p50 | 0.657 s | 0.554 s |
| **transfer** | **1,415,318 B / 194,229 gzip** | **219,561 B / 24,254 gzip** (−84.5% / −87.5%) |

### Rankings regression check

| | before | after |
|---|---|---|
| warm total p50 | 0.0512 s | 0.0510 s |
| bytes | 1,343,751 | 1,343,751 |
| gzip | 186,013 | 186,012 |
| Rankings → Set (warm p50) | — | 0.0594 s, cache reuse intact |

**No regression.** Rankings is byte-identical and unchanged in latency; the canonical targets cache
identity, publication identity, Set Value capability and fallback behavior are untouched.

---

## Semantic parity

`/Market` rendered visible text (all markup and the RSC flight payload stripped) is **byte-identical**
before and after — set ordering, Set Values, coverage labels, movement and links all unchanged.

Homepage: distribution markers `Bad Floor`, `Typical Opening`, `Strong Upside`, `Jackpot Upside`,
`Best Pull` and the `Perfect Order` spotlight all render post-change. The homepage change is
memoization only — no data shape, selector or component was modified.

---

## Browser / LCP findings

**Not collected.** No browser automation runs (FCP, LCP, LCP element, TBT, main-thread, hydration)
were performed in this pass. Transfer size is measured and reported above and is the one browser-side
quantity that is known; everything else in brief sections 4/14 relating to render metrics remains
outstanding. Recorded as a gap rather than estimated.

The 171 KB gzip removed from `/Market` is a genuine browser-side saving in bytes and in RSC parse/
hydration work, but its effect on LCP specifically is **unmeasured**.

---

## Remaining opportunities

1. **`/Rankings` has the same client-boundary issue** — 1,343,751 B / 186,012 gzip, the largest single
   transfer on the site. Out of scope this pass (Rankings is protected and performing well), but it is
   now the biggest remaining transfer win and the same projection technique applies.
2. **Shared 43 KB Home/Market summary projection** — designed and justified above; needs its own
   scoped change because it touches publication atomicity.
3. **Narrower `/insights/secondary`** — the homepage reads 12,294 of 42,411 B; `historyTrend` (53%) is
   unused. Much less urgent now that the response is cached.
4. **Browser/LCP measurement**, then any JS/main-thread work indicated by it.

---

## Carry-forward reliability

Unchanged and not reproduced: Top Chase backend 503 (UNRESOLVED LOAD RELIABILITY), Pull Rates request
lifecycle (FOLLOW-UP). `financialRipV3.audit` deliberately not pursued.
