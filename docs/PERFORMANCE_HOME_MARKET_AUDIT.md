# Performance Audit — Homepage + Market Critical Path

Branch `feature/perf_updates_two`, starting SHA `7d8478f96a4c31d1c4eabc4af9dc37ef6fc2269f`, working tree clean.
Measurement date 2026-08-13. Backend run locally (`uvicorn backend.api.main:app`, port 8000, no `--reload`)
against the **live** Supabase public snapshots, so all payload sizes and DB timings below are production data.

**No production code was changed in this pass.** See [Changes](#changes).

---

## Baselines

### Backend endpoints (warm, 8 sequential runs each)

| Endpoint | TTFB p50 | total p50 | bytes |
|---|---|---|---|
| `GET /explore/rip-statistics/targets?limit=200` | 1.749 s | 1.750 s | 2,625,401 |
| `GET /explore/card-market-movers` | 0.058 s | 0.058 s | 79,029 |
| `GET /tcgs/pokemon/sets/{#1}/insights/secondary` | 0.238 s | 0.239 s | 42,411 |

Cohort size: 34 targets. Top-ranked set at measurement time: `Perfect Order`
(`5e99f658-39f0-4845-9228-db8db3965f32`).

### Not yet measured

Next.js production-build TTFB, FCP/LCP/TBT, transfer sizes, and the browser waterfall for `/` and
`/Market` (brief sections 3, 16, 17, 18, 21) are **deliberately not recorded here**. See
[Root causes](#root-causes) — the currently published Rankings artifact is not the one this branch
produces, so any page-level baseline taken now would describe a state the branch already supersedes
and would make every before/after comparison misleading. These are unblocked as soon as the
publication path question is resolved.

---

## Root causes

Ranked by user-facing impact.

### P0 — the Rankings payload projection and set-value guarantee are not reaching production

The live published `_latest` row still carries every block the publisher is supposed to strip:

- `publicRipContractV4`, `publicRipContractV5`, `publicRipContractV6` present on **34/34** targets
- raw `financial_rip_v3_payload` present

`meta.snapshot.builtAt = 2026-08-13T14:08:34Z` — this is **today's** publication, not a stale row.

There is no read-time re-add; `pokemon_public_snapshot_service.py:1929-1995` does not restore these
blocks. Verified by git rather than inferred:

```
git show main:backend/scripts/pokemon_explore_rankings_publisher.py | grep -c project_latest_rankings_payload   -> 0
git show main:backend/scripts/pokemon_explore_rankings_publisher.py | grep -c PUBLIC_SET_VALUE_CONTRACT_VERSION -> 0
git rev-list --count main..HEAD                                                                                 -> 13
```

Both optimizations exist **only on this branch**. The daily publication runs `main`, so each nightly
publish rewrites `_latest` as an unslimmed document lacking the `setValueContract` marker.

Consequence — the endpoint decomposed by calling the service functions directly (5 runs):

| Stage | p50 |
|---|---|
| `_load_pokemon_explore_rankings_snapshot_row` (2.79 MB across the DB boundary) | ~690 ms |
| `_enrich_rankings_payload_with_checklist_set_values` | **~870 ms** |
| JSON serialize | 16 ms |

`payload_guarantees_canonical_set_value(payload)` returns `False`, so the compatibility fill runs on
**every request**. `meta.sources.checklist_set_value_enrichment` reads
`"legacy_missing_value_fill_only"`, confirming it executed. The in-code comment prices this fallback
at ~403 ms; measured live it is closer to 870 ms — roughly **half the endpoint**.

So ~50% of the gating cost on both pages is a fallback this branch already eliminates, and much of
the remaining half is bytes this branch already drops.

### P1 — both pages read the full Rankings document for a ~1.7% field subset

See [Shared projection opportunity](#shared-projection-opportunity).

### P2 — homepage serial waterfall

Real, but small relative to the above: ~240 ms behind a ~1,750 ms dependency. Not the homepage's
problem.

---

## Market critical path

`frontend/app/Market/page.js` awaits `Promise.allSettled([getRipStatisticsTargets({limit:60}), getExploreMarketMovers()])`.

| Source | p50 | share of the gate |
|---|---|---|
| targets | 1.750 s | **96.8%** |
| movers | 0.058 s | 3.2% |

**Targets gates Market, unambiguously.** Movers is 1/30th of the cost. There is no movers problem to
solve, and `Promise.allSettled` is correct as written.

### Streaming (brief section 7)

Movers renders *before* `ExploreTopRankings` in the DOM, so Suspense-splitting the two would let the
header + Movers paint at ~60 ms instead of ~1.75 s. This is a genuine first-usable-content win, but
it is **worth far less after the P0 and P1 fixes** (a ~60 ms vs ~700 ms split, or ~60 ms vs ~100 ms
once projected). Recommendation: do not implement streaming now — re-evaluate once targets is
corrected, so the decision is made against the real remaining gap rather than against an inflated one.

---

## Movers source/read path

Not pursued beyond timing. At 58 ms / 79 KB for 30 returned movers it is immaterial to the Market
critical path, and brief section 5 gates the deeper trace on the request being material. Recorded as
measured-and-cleared rather than unexamined.

---

## Market targets field consumption

Consumers: `components/explore/ExploreTopRankings.jsx` and `components/explore/rankingMovement.mjs`.

| Field | Consumer | Required |
|---|---|---|
| `target_type`, `target_id`, `set_id` | routing, stable row id | yes |
| `name` | row label | yes |
| `logo_image_url`, `symbol_image_url` | row visual | yes |
| `checklistSetValue` | set value column | yes |
| `checklistSetValueAsOf` | as-of label | yes |
| `checklistSetValuePricedCardCount`, `checklistSetValueTotalCardCount` | coverage label | yes |
| `previousChecklistSetValue7d` | 7D movement | yes |
| `setValueComparisonStatus7d` | movement availability gate | yes |

(snake_case aliases of the same values are read as fallbacks and are not counted separately)

**Nothing** from `publicRipContractV4/V5/V6/V7`, `financialRipV3`, `financial_rip_v3_payload`,
`openingExperience`, `universalSetDesirability`, `rip`, or `ripCore` is read on `/Market`.

> full targets array **2,591,932 B** → Market-consumed projection **16,877 B** = **0.65%**

---

## Homepage critical path

`getLandingPageData()` (`frontend/lib/landing/landingHeroServer.js:43-62`) is a proven serial chain:

```
getRipStatisticsTargets({limit:60})      ~1.750 s
  -> selectLandingHeroEntries -> entries[0]     (in-process, negligible)
    -> getLandingDistribution(#1 set id)   ~0.240 s
      -> selectors / pack asset resolution      (in-process, negligible)
```

Serial secondary request = **~12%** of the chain. The targets leg is ~88%.

`T0-T7` instrumentation (brief section 9) was not added: the two awaited legs were measured directly
at their own boundaries, which answers the same question without modifying production code, and the
in-process selector work between them is pure array mapping over 34 rows.

---

## Homepage targets field consumption

Consumers: `landingHeroSpotlight.mjs` (`toEntry`), `landingPreviews.mjs`
(`selectExploreRankingRows`, `selectHeroRankingVisuals`, `selectMarketContext`), and the renderer
`components/landing/RankingTheaterHomepage.jsx`.

Beyond the Market set above, the homepage additionally requires:

| Field / path | Consumer |
|---|---|
| `canonical_key` | booster pack asset resolution |
| `era` | entry model |
| `currentChecklistSetValueDate` | set value as-of |
| `pack_cost`, `mean_value`, `median_value` | opening economics, rendered |
| `prob_profit`, `expected_loss_per_pack` | entry model |
| `max_value`, `financial_rip_v3_simulation_count` | distribution markers / simulation count |
| `publicRipContractV7.overallRip.{relativeScore,absoluteScore,rank,tier,rankedSetCount,status,statusReason}` | canonical RIP score/rank/tier |
| `publicRipContractV7.financialRip.{same 7}` | Financial RIP score |
| `publicRipContractV7.financialRip.distributionDisclosures.p05Value` | P05 marker fallback |
| `publicRipContractV7.financialRip.components.realisticUpside.raw.p95ThresholdValue` | P95 marker fallback |
| `publicRipContractV7.financialRip.components.jackpotUpside.raw.p99ThresholdValue` | P99 marker fallback |
| `publicRipContractV7.financialRip.sourceRun.simulationCount` | simulation count |

Computed but **not rendered**: `universalSetDesirability.score/.rank`, `collector_appeal_score`,
`desirability_is_fallback` — `toEntry` builds them, but no homepage component reads them. Excluded
from the required set; flagged rather than removed, since removing them is a semantics question, not
a performance one.

`publicRipContractV7.audit` is attached by `resolveCanonicalRipV7` but never read by any landing
consumer. **Not pursued in this pass** per the brief.

> full targets array **2,591,932 B** → Homepage-consumed projection **43,312 B** = **1.67%**

---

## Secondary insights waterfall

`GET /tcgs/pokemon/sets/{id}/insights/secondary` — 42,411 B, ~240 ms warm.

| Family | bytes | homepage consumes |
|---|---|---|
| `historyTrend` | 22,492 | **no** |
| `outcomeDistribution` | 12,294 | **yes, entirely** |
| `simulationDrivers` | 4,136 | no |
| `desirability` | 1,529 | no |
| `rarityContribution` | 1,155 | no |
| `ripStatistics` | 260 | no |
| `meta` / `set` | 258 | no |

`selectLandingDistribution` reads only `outcomeDistribution.{percentiles, distributionBins,
thresholdBins}` = **12,294 B of 42,411 B (29%)**. `historyTrend` alone is 53% of the response and is
fetched purely as waste.

---

## Distribution provenance

Brief section 11 — can the homepage distribution come from already-fetched data?

**No.** `distributionBins` (8,554 B) and `thresholdBins` (3,456 B) do not exist anywhere in the
Rankings target document, under any casing, in `publicRipContractV7`, `financialRipV3`,
`financial_rip_v3_payload`, or `openingExperience`. Only the scalar percentile *markers*
(`p05Value`, `p95ThresholdValue`, `p99ThresholdValue`, `max_value`) are present, and those are
already used solely as fallbacks when the secondary payload is missing.

The real simulation histogram is only available from the secondary endpoint. Per the standing
requirement that the homepage show the **real** distribution and never a reconstruction, the
secondary call cannot be removed. The addressable waste is the 71% of that response the homepage
does not consume, not the request itself.

---

## Shared projection opportunity

Brief section 14.

| | fields | bytes | share of full targets array |
|---|---|---|---|
| Full targets array | — | 2,591,932 | 100% |
| Market required | 12 | 16,877 | 0.65% |
| Homepage required | 40 | 43,312 | 1.67% |
| **Union** | **40** | **43,312** | **1.67%** |

**The Market field set is a strict subset of the homepage field set.** The union is exactly the
homepage set — there is no Market-only field. A single shared "public set market summary" projection
would serve both pages at **43 KB instead of 2,592 KB**, removing **~2.43 MB** from each cold read
and eliminating the full-document DB transfer (~690 ms) from both critical paths.

Every union field is already present in the same persisted `_latest` document, post-enrichment, so a
canonical persisted source **can** produce it without any new computation, new scoring, or any change
to Rankings semantics.

### Recommendation: do not implement it yet

Not because the numbers are unconvincing — they are the strongest result in this audit — but because
of a delivery-path dependency:

1. A new projection artifact would be written by the **same publisher** whose existing projection and
   set-value marker are not reaching production (P0). Adding a second publisher-dependent artifact to
   a publication path that demonstrably does not deliver its current changes would reproduce the exact
   same failure mode, silently.
2. Persisting an additional row inside the publish RPC touches **publication atomicity**, which the
   brief places in hard scope.
3. It introduces a second cache identity next to the canonical targets cache, which the brief requires
   proving end-to-end before adopting.

All three objections dissolve once the publication path is fixed and verified. The correct order is
P0 first, then re-measure, then decide on the projection against the corrected baseline.

---

## Changes

**NONE.** No production code was modified in this pass. The audit's headline finding is that
optimizations already written on this branch are not reaching the published artifact; writing further
optimizations onto the same undelivered path would compound the problem rather than fix it.

---

## Semantic parity

Not applicable — no changes were made, so displayed content on both pages is byte-identical to the
starting SHA.

---

## Before/after

Not applicable — no changes were made. No Rankings regression check was required for the same reason;
`getRipStatisticsTargets` canonical cache identity, the Rankings payload projection code, Phase 2A
request gating and the sealed shared resolver are all present and untouched at `7d8478f`.

---

## Remaining opportunities

Ranked by proven impact, all currently blocked on the P0 delivery question:

1. **P0 — get the branch publisher onto the path that runs the daily publication**, republish
   `_latest`, re-measure. Expected: `/targets` ~1.75 s → well under 1 s (removes ~870 ms fill and a
   large share of the ~690 ms transfer), improving `/Market` and `/` together with zero new
   architecture.
2. **P1 — shared 43 KB Home+Market projection.** Proven at 1.67% of current bytes; deferred per the
   reasoning above.
3. **P2 — narrow `/insights/secondary` for the landing consumer**, or fetch only
   `outcomeDistribution`. 71% of that response is unused by the homepage. Worth ~120-170 ms of
   transfer at best; do after 1 and 2.
4. **P3 — Market streaming (Suspense).** Defer; its value shrinks substantially once 1 and 2 land.

---

## Carry-forward reliability

Unchanged and not reproduced in this pass:

- **Top Chase backend 503** — UNRESOLVED LOAD RELIABILITY.
- **Pull Rates request lifecycle** — FOLLOW-UP.
- `financialRipV3.audit` removal — deliberately not pursued.
