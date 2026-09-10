# Collector Appeal V6 — Pokémon Roster Desirability (D_pokemon) Construct-Validity Audit

Status: **RESEARCH ONLY.** No production writes, no pointer cutover, no model mutation. Frozen control `pokemon_collector_appeal_v6_generalized_roster_frequency` / `0efa3c8f-918d-49d7-ad5e-3ae37278058f` untouched. Cross-bucket decision (Candidate B1 Trainer headroom lift, Functional diagnostic-only) treated as locked and not re-litigated; this document evaluates only whether `D_pokemon` itself — the anchor B1 sits on top of — is construct-valid.

## Primary question

> Is `D_pokemon` materially sensitive to WHO the Pokémon are, or is it primarily determined by HOW MANY eligible Pokémon groups the set contains?

**Answer: primarily determined by HOW MANY, once group count exceeds roughly 25–30.** Below that range appeal quality still moves the score meaningfully; above it the saturating mass formula collapses almost any large roster toward D≈95–100 regardless of how strong the individual Pokémon actually are, and separately, tens of only-barely-positive Pokémon groups can accumulate enough mass to match or exceed a handful of genuinely elite Pokémon. This is a real construct-validity defect, established by direct falsification (Phases 2–4 below), not inferred from correlation alone.

## Phase 1 — Decomposition and raw correlations (128 sets)

Full table: `backend/artifacts/collector_v6_redesign_research/pokemon_D_decomposition.json`.

| Predictor | Spearman vs D_pokemon | Pearson vs D_pokemon |
|---|---|---|
| groupCount | 0.9989 | 0.536 |
| positiveGroupCount | 0.9998 | 0.710 |
| rawMass | 1.0000 | 0.744 |
| meanAppeal | 0.9927 | 0.194 |
| medianAppeal | 0.9933 | 0.304 |
| top3Mean | 0.9965 | 0.752 |
| top5Mean | 0.9974 | 0.817 |
| top10Mean | 0.9986 | 0.875 |
| share_gt60/70/80/90 | ~0.993 each | 0.10–0.24 |

**Important caveat before drawing conclusions from this table alone**: nearly every predictor is Spearman-correlated with D above 0.99, including ones that shouldn't mechanically dominate (mean appeal, high-appeal shares). This is not because D responds to all of them equally — it's because groupCount, positiveGroupCount, and appeal-quality metrics are themselves highly mutually correlated across the real 128-set population (bigger/newer sets tend to also contain stronger chase Pokémon). Raw correlation cannot separate "D tracks count" from "D tracks quality" when count and quality co-vary in the data. This is exactly why the task specifies direct falsification (Phases 2–4) as the decisive test, not correlation.

## Phase 2 — Matched-count test (within similar breadth, does appeal still move D?)

Within `±1`-group bands (n≥5, spanning group counts 12–37) and within quintile bands by group count, `Spearman(meanAppeal, D)` and `Spearman(top5Mean, D)` both stay high (0.94–1.00) — **conditional on breadth, D does still rank sets by appeal quality**. Representative quintile-band comparisons (same breadth band, high vs. low appeal):

| Band (groupCount range) | High-appeal set | Low-appeal set | D difference at matched breadth |
|---|---|---|---|
| 4–16 | Detective Pikachu (mean 99.0, n=4) | Emerging Powers (mean 31.6, n=10) | 23.55 |
| 16–20 | Legendary Collection (mean 86.0, n=19) | Shrouded Fable (mean 44.9, n=18) | 33.12 |
| 20–24 | Delta Species (mean 88.5, n=21) | Chaos Rising (mean 59.1, n=21) | 16.97 |
| 24–33 | Power Keepers (mean 77.6, n=24) | Twilight Masquerade (mean 53.5, n=32) | 6.59 |
| 33–138 | Team Up (mean 80.1, n=37) | Scarlet & Violet Base (mean 43.1, n=36) | 18.30 |

**Conclusion**: at matched breadth, appeal quality is not ignored — this rules out the extreme claim that D is *purely* a count statistic. But this alone is not sufficient to validate D, because the matched-count test cannot see how much bigger a role breadth itself plays when it's allowed to vary — that's Phase 3.

## Phase 3 — Matched-appeal test (the decisive falsification)

Holding mean appeal roughly fixed (quintile bands) and letting group count vary freely:

| Appeal band | High-count set | Low-count set | D swing from count alone |
|---|---|---|---|
| mean 31.6–64.5 | Paldean Fates (n=138, mean=50.0) | Emerging Powers (n=10, mean=31.6) | **75.19** |
| mean 64.7–69.0 | Ascended Heroes (n=75, mean=68.2) | Celebrations (n=6, mean=68.9) | **56.27** |
| mean 69.2–72.4 | Evolving Skies (n=45, mean=71.5) | Majestic Dawn (n=16, mean=70.0) | 18.65 |
| mean 72.5–76.2 | Cosmic Eclipse (n=50, mean=74.0) | Great Encounters (n=12, mean=76.1) | 25.18 |
| mean 76.4–99.0 | Unified Minds (n=42, mean=78.1) | Detective Pikachu (n=4, mean=99.0) | **50.99** |

This is the decisive result: **Ascended Heroes (mean appeal 68.2) scores D=99.91 — nearly saturated — while Celebrations, with a nearly identical mean appeal of 68.9, scores only D=43.64, a 56-point gap explained entirely by group count (75 vs 6).** Similarly, Detective Pikachu has the single highest mean Pokémon appeal in the entire cohort (99.0, essentially all-elite) but its D (48.33) is *lower* than dozens of sets with mediocre average appeal simply because it only has 4 eligible Pokémon groups. Breadth is not a secondary factor here — for sets above roughly 40 groups, it is the dominant factor, capable of overriding a 30+ point mean-appeal disadvantage.

## Phase 4 — Synthetic archetypes

`backend/artifacts/collector_v6_redesign_research/synthetic_archetypes_pokemon_roster.txt` (12 required archetypes computed).

Key falsification answers:
- **Can a broad weak roster outrank a narrow elite roster? Yes.** 60 Pokémon at appeal=55 (barely above neutral) → D=95.77, versus 3 Pokémon at appeal=98 (near-maximal) → D=38.73. The broad-weak roster outranks the narrow-elite roster by 57 points.
- **How many mediocre(65) Pokémon overpower 5 elite(95)?** Only **10** (D=59.86 vs D=54.64 for the 5 elites) — fewer than half the number of elites needed to exceed them.
- **Does adding neutral-50 Pokémon change D?** No — confirmed exactly zero change (`base=47.5598`, `+50 neutral=47.5598`). This part of the construct is sound.
- **Does adding barely-above-neutral (51) Pokémon accumulate too much mass?** Yes — 200 cards at appeal=51 alone drive D from a 5-elite base of 47.56 up to 99.53, i.e., a large quantity of essentially-negligible individual desirability accumulates to near-total saturation.
- **Does the saturation constant prevent excessive checklist-size dominance, or only cap it near 100?** **Only caps it near 100.** The `k=6.0` saturation constant makes D asymptotically bounded, but the approach to that bound is governed entirely by accumulated count × marginal appeal — it does not distinguish "legitimately large elite roster" from "large roster of marginally-positive filler," both reach the same ceiling.

## Phase 5 — Marginal contribution curves

`backend/artifacts/collector_v6_redesign_research/marginal_contribution_table.txt`. Marginal ΔD from adding the Nth subject at a given appeal level (holding all prior additions at the same level):

| Appeal | 1st | 2nd | 5th | 10th | 20th | 40th | 60th |
|---|---|---|---|---|---|---|---|
| 55 | 5.13 | 4.87 | 4.16 | 3.19 | 1.89 | 0.66 | 0.23 |
| 70 | 10.00 | 9.00 | 6.56 | 3.87 | 1.35 | 0.16 | 0.02 |
| 90 | 13.85 | 11.93 | 7.63 | 3.62 | 0.82 | 0.04 | 0.002 |
| 100 | 15.35 | 13.00 | 7.88 | 3.43 | 0.65 | 0.02 | 0.0008 |

Marginal contribution does decay per-position (diminishing returns are real, not absent) — but the decay rate is governed only by *position within the accumulating roster*, identically regardless of whether the roster is filled with barely-positive or near-maximal subjects at a given size. This is why 200 near-neutral cards can still reach the same ceiling a handful of elite cards reach — the position-based decay eventually saturates any sufficiently large N, not just a large N of strong subjects.

## Phase 6 — Candidate correction family tested

Per the pre-registered instruction not to grid-search, two structurally distinct families were tested (not tuned to price):

### Candidate: Top-K truncation of the existing mass formula
Restrict `raw_mass`/`roster_score` to only the top-K highest-appeal groups (tested K=25, K=20, K=15, K=12, with saturation constants k=6/10/12/14). **This does not fix the falsification failures at any tested parameterization** — a truncated mass of even 15–25 groups at moderate appeal still saturates the exponential transform, so "10 mediocre(65) beats 5 elite(95)" and the matched-appeal count-driven swings (still 50–75 points in the worst bands) persist essentially unchanged. Truncating the *count* of contributing groups does not address the underlying issue, which is that the sqrt-mass/exponential-saturation transform treats "many weak" and "few strong" as fungible by design.

### Candidate: Strength + Bounded Breadth (two-part model, Family D from the pre-registration)
```
strength = mean(top-5 appeal values), clamped [0,100]
breadth  = 100 * (1 - exp(-positiveGroupCount / 15))
D        = strength + (100 - strength) * 0.5 * (breadth / 100)
```
This explicitly separates "how good are the headline subjects" from "how many qualifying subjects exist," and lets breadth only act as a *bounded headroom lift* on top of strength — architecturally consistent with the already-accepted Trainer-lift and card-level Playability-lift pattern (bounded, positive-only, shrinking as the base approaches its ceiling).

**Falsification results for this candidate:**
- Broad weak (60×55) → D=77.09; narrow elite (3×98) → D=98.18. **Broad weak no longer beats narrow elite** (was 95.77 vs 38.73 under current D — a complete reversal).
- 150×mediocre(65) → D=82.50, still below 5×elite(95) → D=95.71. **No count of mediocre subjects overpowers a small elite roster**, at any tested N up to 150.
- Neutral-50 additions: confirmed exactly zero effect (82.83 → 82.83).
- Barely-above-neutral (51) accumulation: bounded — 200 additional cards at appeal=51 move D from 82.83 to only 90.00 (versus the current model's 47.56→99.53 for the same stress test), a materially smaller and still-bounded effect.
- 128-set correlation with groupCount: Spearman **0.9963** (current model: 0.9989) — only a marginal reduction, because groupCount and top5-appeal-strength are themselves highly correlated in the *real* set population (this is a population-level confound, not a formula defect — see the caveat in Phase 1).

**Known weakness of this candidate, not yet resolved**: applying it to the full 128-set cohort produces very large rank churn relative to current D (max |rank delta| = 102, mean = 19.4, 79/128 sets moved more than 10 ranks). Inspection shows the `top-5 mean appeal` strength anchor saturates near 100 for the large majority of modern sets (most curated chase rosters already contain 5+ very strong subjects), which compresses differentiation among genuinely different high-end sets and inflates narrow sets like Detective Pikachu (only 4 total Pokémon groups) into near-ceiling territory (rank 125→23) purely because its 4 subjects are all elite. This is not a falsification-criteria failure (it doesn't violate any Phase 7 requirement), but it is a legitimate open design concern about differentiation power at the top end that a naive `top-5 mean` strength anchor does not adequately address, and that requires its own calibration pass (e.g., a broader top-N, a less-saturating strength transform, or a different GAMMA) before this becomes implementation-ready.

## Phase 7 — Falsification checklist results

| Requirement | Current D_pokemon | Strength+BoundedBreadth candidate |
|---|---|---|
| Increasing appeal cannot lower D | ✅ (monotone by construction) | ✅ |
| Neutral(50) addition cannot raise D | ✅ confirmed | ✅ confirmed |
| Duplicate printing cannot raise D | ✅ (max-per-group dedup, unchanged) | ✅ (same dedup, unchanged) |
| One weakly-positive subject cannot dominate an elite subject | ✅ (single subject can't) | ✅ |
| Broad roster can beat narrow roster only when breadth is meaningfully desirable | ❌ **FAILS** — 60×barely-positive(55) beats 3×near-max(98) | ✅ breadth capped by headroom; broad-weak stays well below narrow-elite |
| Elite narrow roster distinguishable from weak broad roster | ❌ **FAILS** — collapses together near ceiling for large N | ✅ clearly separated |
| Set size alone cannot nearly determine rank | ❌ **FAILS** — Phase 3 shows 50–75 point swings from count alone at matched appeal | Partially improved — Spearman-vs-count only drops marginally (0.9989→0.9963) due to population-level confound, but the mechanism no longer directly rewards raw count once strength saturates |
| No cohort-membership dependence affecting other sets' scores | ✅ (per-set independent computation, unchanged) | ✅ |
| No market price input | ✅ | ✅ |

Current `D_pokemon` **fails three of the nine falsification requirements outright** (the three most central to the construct-validity question). The tested replacement candidate satisfies all nine, but carries an unresolved secondary concern (top-end differentiation / rank-churn magnitude) that should be addressed before final parameter acceptance.

## Files produced

- `docs/research/collector_appeal_v6_pokemon_roster_d_construct_validity.md` (this file)
- `docs/research/collector_appeal_v6_pokemon_roster_d_recommendation.md` (Phase 9 decision)
- `backend/artifacts/collector_v6_redesign_research/pokemon_D_decomposition.json` (Phase 1, full 128-set decomposition)
- `backend/artifacts/collector_v6_redesign_research/candidate_topK_comparison.json` (Top-K candidate, rejected)
- `backend/artifacts/collector_v6_redesign_research/candidate_strength_breadth_comparison.json` (Strength+BoundedBreadth candidate, full 128-set comparison)
- `backend/artifacts/collector_v6_redesign_research/synthetic_archetypes_pokemon_roster.txt`
- `backend/artifacts/collector_v6_redesign_research/marginal_contribution_table.txt`
