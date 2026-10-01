# Rankings Follow-up B1 - Tier Contract

Two explicit contracts, two helpers (`backend/rankings/public_relative.py`). They are never interchangeable.

## 1. Benchmark contract - `benchmark_relative_tier(score, rank, cohort_size, reference=5.0)`
Applies to Set/Era benchmark-centered scores on the 0-10 scale (Pokemon Overall Average = 5.0). Used by `benchmark_presentation()`.

- **Neutral band:** `abs(score - 5.0) <= 0.25` (4.75-5.25 inclusive) is **C regardless of rank**. A rank-1 score of 5.10 is C.
- **Above band (score > 5.25):** S = rank <= `max(1, floor(N*0.01))`; A = rank <= `max(sCount, floor(N*0.10))`; B = the rest.
- **Below band (score < 4.75):** F when `N >= 4` and `rank > N - max(1, floor(N*0.25))`; otherwise D.
- **Tiny cohorts:** with N < 4 (e.g. the two Eras) a below-neutral score is D, never forced to F.
- All cut-offs use **floor**, never ceil.
- Any null/non-numeric score, rank or cohort, rank < 1, rank > N, or N < 1 returns `None`.

## 2. Absolute contract - `absolute_rank_percentile_tier(rank, cohort_size)`
For scores with no benchmark-neutral point (Product V12 0-100, Card rankings). Rank percentile only, no 5.0 band.

S top 1%, A through 10%, B through 25%, C through 50%, D through 75%, F bottom 25%. Floor boundaries, each at least the previous; `max(1, ...)` for S. Cohorts: Product Full Market 138, Collector Overall Cards 18,293. Product V12 scale unchanged.

Legacy `public_rank_tier` (S 5% / A 15% / B 30% / C 50% / D 75% / F, ceil) and its alias `public_product_rank_tier` have **no remaining production caller** and are kept, marked LEGACY, only for older tests/external imports. They were deliberately not redefined to mean either new helper.

### Production call-site audit (closure)
| Call site | Cohort | Helper now |
|---|---|---|
| `rankings_redesign_contract_service.benchmark_presentation` | Set/Era benchmark 0-10 | `benchmark_relative_tier` |
| `chase_efficiency_query_service._public_row` | Card Chase Efficiency overall rank | `absolute_rank_percentile_tier` |
| `explore_rip_statistics_service._calculate_score_ranks_and_tiers` | fixed-anchor absolute scores | `absolute_rank_percentile_tier` |
| `public_rank_tier` / `public_product_rank_tier` | none | legacy, unused |

## Palette (existing shared tone, `lib/explore/interpretationTone.js`)
S purple `rgba(192,132,252)`, A teal `rgba(45,212,191)`, B green `rgba(134,239,172)`, C sky/neutral blue, D orange `rgba(251,146,60)`, F red. No second palette was introduced.

## Live Sep-30 examples (covered by tests)
| Surface | Entity | Score | Rank | Tier |
|---|---|---|---|---|
| Set Overall | Temporal Forces | 7.358 | 1/22 | S |
| Set Overall | Paradox Rift | 6.426 | 2/22 | A |
| Set Overall | Scarlet & Violet 151 | 6.374 | 3/22 | B |
| Set Overall | Perfect Order | 5.237 | 10/22 | C |
| Set Overall | Mega Evolution | 4.564 | 16/22 | D |
| Set Overall | Obsidian Flames | 4.348 | 18/22 | F |
| Era Overall | Scarlet & Violet | 5.149 | 1/2 | C |
| Era Overall | Mega Evolution | 4.602 | 2/2 | D |
| Era Chase | Scarlet & Violet | 5.260 | 1/2 | S |
| Era Chase | Mega Evolution | 4.306 | 2/2 | D |
