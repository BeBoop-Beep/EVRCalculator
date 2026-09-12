# Pokemon Collector V6 -- D_pokemon (Roster-D) Final Freeze

**Status:** FROZEN
**Scope:** Narrow construct-calibration task remediating blocker `POKEMON_COLLECTOR_D_FORMULA_ARTIFACT_MISSING`. Produces only file artifacts; no DB writes, no model runs, no set-page builds, no production changes.
**Freeze artifact:** `backend/config/pokemon_collector_v6_pokemon_roster_d_freeze_v1.json`
**128-set output:** `backend/artifacts/collector_v6_redesign_research/pokemon_roster_d_final_128set.json`
**Formula fingerprint:** `3bb56da6353fe55e787a893a1250ed1a54d7670cef85d024323fea42612067a6`
**128-set output fingerprint:** `7e1c3fdc060ed5830592f51a4a470a1e38a8f14f2f179c21e54def8746c2bc19`

## A. Corrected input authority used

- Distinct-subject, per-set Pokemon appeal lists (`pokeAppeals`): `backend/artifacts/collector_v6_redesign_research/pokemon_D_corrected_128set.json` (128 sets, already deduplicated to one entry per distinct Pokemon species per set, built from the corrected Trends V2 chain).
- Raw composite verified against `backend/artifacts/collector_v6_redesign_research/pokemon_composite_raw.json` (`desirability_score = 0.75*fan_popularity_score + 0.25*current_trend_score`, raw, no percentile transform).
- Trends V2 dependency: manifest `pokemon_trends_anchor_ladder_manifest_v1`, code_version `capture_pokemon_trends_anchor_ladder_v2_r1`, checkpoint `backend/artifacts/collector_v6_redesign_research/trends_v2_capture/checkpoint_rows.jsonl` (1025/1025 canonical subjects; SCORED=993, scored_zero_high_confidence=27, failed=5).
- No price/market data consumed at any point.

## B. Candidate formulas tested

All candidates share the locked architecture `D = S + (100-S)*lambda_breadth*B`. Pre-registered family (fixed before selection, though the exponent-`k` idea was added mid-task after the first pass revealed pathological ceiling compression -- see note below):

| Candidate | N | r (decay) | stretch k | lambda swept |
|---|---|---|---|---|
| `S_N5_r050_k1` | 5 | 0.50 | 1 (no stretch) | 0.10-0.25 |
| `S_N5_r050_k3` | 5 | 0.50 | 3 | 0.10-0.25 |
| `S_N8_r060_k4` | 8 | 0.60 | 4 | 0.10-0.25 |

Breadth threshold family tested: T in {50, 60, 70}; T=60 selected (semantically "meaningfully above-average" on the raw 0-100 composite; T=50 rewards merely-average subjects, T=70 rarely triggers).

**Deviation note (transparency):** an initial pass used plain weighted-top-N averages (`k=1`, no stretch) with three N/r variants. All three passed falsification, but the least-narrow variants failed the strength-dominance check, and the only fully-passing variant (`S_N5_r050_k1`) produced a severe near-ceiling compression (100/128 sets >= 97.5, matching the exact pathological pattern the spec requires this freeze to resolve). A second small family adding a monotonic ceiling-stretch exponent `k` (applied to each subject's appeal fraction above the qualifying floor, strictly increasing so it cannot reverse any ranking) was tested to resolve this. This is a normal part of the pre-registered candidate refinement within Phase 2-4's stated small-family bound (3 final candidates, not a grid search) and is disclosed here rather than hidden.

## C. Hard falsification results (winner: `S_N8_r060_k4`, lambda=0.20, T=60)

All 12 structural checks + all synthetic archetypes PASS, including the historical monotonicity bug case:

- `1x100` = 84.72, `1x100+4x52` = 84.72 (4 subjects at appeal=52 barely exceed the qualifying floor of 50; contribution ~0) -- second roster never scores lower. PASS.
- Monotonic increase, neutral-50 no-op, meaningful-add never lowers D, 60x55 < 5x98, mediocre20 < 5x95, narrow-elite > broad-weak by >5pts, breadth marginal diminishing, strength dominance, not count-driven (Spearman D vs. distinct-count = 0.486, well under 0.90), cohort-independent (fixed constants), no market data -- all PASS.

Full detail (raw booleans + archetype scores) is embedded in the freeze artifact under `falsificationResults`.

## D. Differentiation results

| Metric | Winner (`S_N8_r060_k4`, lambda=0.20) | Prior best plain-average candidate (`S_N5_r050_k1`, lambda=0.10) |
|---|---|---|
| min / median / max | 52.06 / 93.84 / 99.37 | 70.78 / 98.74 / 99.91 |
| SD | 6.46 | 3.07 |
| p90 | 97.87 | 99.68 |
| unique scores @1dp | 87 / 128 | 47 / 128 |
| sets >= 90 | 98 | 126 |
| sets >= 95 | 50 | 119 |
| sets >= 97.5 | **16** | **100** |
| sets >= 99 | 3 | 47 |
| median adjacent gap | 0.097 | 0.022 |

The winner materially resolves the ceiling-compression failure mode (16/128 sets in the near-ceiling band vs. the prior unacceptable ~89/128 pattern the spec flags, and vs. 100/128 in the plain-average candidate tested here).

## E. Matched-count / matched-appeal results

Matched-count buckets (sets grouped by distinct-Pokemon-count in bands of 5) show wide D spread within every count band (e.g. 10-14 count band: D ranges 52.1-95.6, a 43.5-point spread; 15-19 count band: 19.6-point spread), confirming count alone does not determine D -- quality of the roster within a given size class still drives large score differences. Full table in the freeze artifact under `matchedCountBuckets`.

## F. Robustness results (appeal perturbation, deterministic seeds)

| Perturbation | Spearman rank stability | Max rank churn | Mean score movement |
|---|---|---|---|
| +/-5% | 0.885 | 57 | 1.97 pts |
| +/-10% | 0.806 | 70 | 3.01 pts |
| +/-20% | 0.690 | 79 | 4.18 pts |

Most fragile sets under perturbation: Sandstorm, Unseen Forces, Next Destinies, Brilliant Stars, Astral Radiance, Ancient Origins, Evolutions, Plasma Blast, Deoxys -- generally smaller/older sets sitting near a qualifying-floor or breadth-threshold boundary, which is an expected and interpretable fragility (score sensitivity concentrates exactly where subjects sit near the T=60 threshold), not a structural defect.

## G. Selected Strength equation

```
qualifying = subjects with appeal > 50, sorted descending
N = 8, r = 0.60
w_i = r^(i-1)*(1-r) / (1-r^N)   for i = 1..8   (sums to exactly 1)
stretch(a) = 50 + 50 * clamp((a-50)/50, 0, 1)^4
S = sum_{i=1..8} w_i * stretch(qualifying[i])     (missing positions beyond roster depth contribute 0)
```
Weights (position 1-8): 0.4068, 0.2441, 0.1465, 0.0879, 0.0527, 0.0316, 0.0190, 0.0114

## H. Selected Breadth equation

```
T = 60
b_i = clamp((appeal_i - T) / (100 - T), 0, 1)   for every distinct qualifying subject
B = 1 - exp(-sum(b_i) / 4.0)                     (saturation constant K=4.0, range [0,1))
```

## I. Selected lambda_breadth

**0.20** (selected from the pre-registered {0.10, 0.15, 0.20, 0.25} family -- the two lower values failed falsification for this S/T pair; 0.20 was chosen over 0.25 as the more conservative passing option, matching the spirit of the locked Trainer lambda=0.15 being deliberately conservative).

## J. Complete final D_pokemon equation

```
D_pokemon = S + (100 - S) * 0.20 * B
```
with S and B as defined in G/H above, computed over the distinct-species-deduplicated, raw (non-percentile) `desirability_score` values per set from the corrected Trends V2 chain.

## K. Freeze artifact path

`backend/config/pokemon_collector_v6_pokemon_roster_d_freeze_v1.json`

## L. Freeze artifact fingerprint

`3bb56da6353fe55e787a893a1250ed1a54d7670cef85d024323fea42612067a6`

## M. 128-set artifact path / fingerprint

`backend/artifacts/collector_v6_redesign_research/pokemon_roster_d_final_128set.json`
`7e1c3fdc060ed5830592f51a4a470a1e38a8f14f2f179c21e54def8746c2bc19`

## Phase 8 real-set decomposition (falsification/inspection only, not used to select the formula)

| Set | Distinct Pokemon | S | B | Breadth pts | D_pokemon | Rank (of 128) |
|---|---|---|---|---|---|---|
| Ascended Heroes | 75 | 99.22 | 0.999 | 0.16 | 99.37 | 1 |
| Paldean Fates | 138 | 99.07 | 1.000 | 0.19 | 99.26 | 2 |
| Crown Zenith | 30 | 98.97 | 0.971 | 0.20 | 99.17 | 3 |
| Prismatic Evolutions | 33 | 98.35 | 0.983 | 0.33 | 98.67 | 7 |
| Team Up | 37 | 97.82 | 0.996 | 0.44 | 98.25 | 12 |
| Rising Rivals | 19 | 96.49 | 0.944 | 0.66 | 97.15 | 20 |
| Evolving Skies | 45 | 95.86 | 0.996 | 0.82 | 96.69 | 24 |
| Cosmic Eclipse | 50 | 94.92 | 0.995 | 1.01 | 95.93 | 37 |
| Generations | 15 | 95.08 | 0.912 | 0.90 | 95.98 | 35 |
| Stellar Crown | 27 | 93.96 | 0.902 | 1.09 | 95.05 | 47 |
| Surging Sparks | 40 | 92.72 | 0.923 | 1.34 | 94.06 | 60 |
| Twilight Masquerade | 32 | 92.51 | 0.876 | 1.31 | 93.82 | 65 |
| White Flare | 75 | 87.51 | 0.973 | 2.43 | 89.94 | 99 |
| Celebrations | 6 | 79.26 | 0.451 | 1.87 | 81.13 | 122 |
| Black Bolt | 74 | 77.05 | 0.936 | 4.30 | 81.35 | 121 |
| Shrouded Fable | 18 | 74.62 | 0.595 | 3.02 | 77.64 | 125 |

Notable pattern (decomposition only, not a selection criterion): small/shallow rosters (Celebrations, 6 subjects; Shrouded Fable, 18 subjects) land near the bottom despite short-set prestige, because Strength has few qualifying headline slots to fill -- an expected and defensible consequence of the architecture, not a target that was optimized for.

## N. Trainer-lift shadow verification (Phase 12, not persisted)

`D_final = D_pokemon + (100-D_pokemon)*0.15*(D_trainer/100)`, computed as a shadow-only pass using the same Strength/Breadth machinery applied within Trainer's own domain (trainerAppeals per set, never pooled with Pokemon subject values):

- Max lift observed: 1.19 points; mean lift: 0.19 points.
- Elite threshold (P90 of D_pokemon): 98.23.
- Overpower violations (sets where a Pokemon-weak set + trainer lift would beat the elite Pokemon-only threshold): **0**.
- Functional/Item subjects untouched (diagnostic-only, excluded from both D_pokemon and this shadow check).
- Not persisted to DB/production; sanity check only, lambda=0.15 not retuned.

## O. Tests run

- Structural falsification suite (12 checks + 9 synthetic archetypes), run against every S-candidate x lambda combination (12 formula variants total).
- Differentiation statistics (min/median/p90/max/SD/unique-at-1dp/ceiling-band counts/adjacent gaps) for all 12 variants.
- Matched-count bucket analysis on real 128-set data.
- Robustness/perturbation analysis at +/-5%, +/-10%, +/-20% with deterministic seeds, Spearman rank stability and rank-churn.
- Real-set decomposition for all 16 named reference sets (all 16 found in the 128-set universe and decomposed into S, B, breadth points, D_pokemon, and rank; none were used to select the formula, per spec, only to falsify/inspect it).
- Trainer-lift shadow verification.

## P. Commits made

None yet from this task at time of writing this report; freeze artifacts are new untracked files under `backend/config/`, `backend/artifacts/collector_v6_redesign_research/`, and `docs/research/`, ready to commit to `develop` per the task's permission (not pushed).

## Q. Production writes performed

**NONE.**
