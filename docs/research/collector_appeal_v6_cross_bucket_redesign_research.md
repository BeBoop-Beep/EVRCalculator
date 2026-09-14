# Collector Appeal V6 — Cross-Bucket Roster Aggregation Redesign Research

Status: **RESEARCH ONLY — no production writes, no pointer cutover, no model mutation.**
Frozen control preserved untouched: `pokemon_collector_appeal_v6_generalized_roster_frequency`, run `0efa3c8f-918d-49d7-ad5e-3ae37278058f`.
Overall RIP V12 unaffected (still Collector Appeal V5).

## 1. Locked finding (input to this research, not re-litigated)

Current C4 pools Pokémon-group, Trainer-group, and Functional-group `final_card_collector_appeal` representative values directly into one shared mass:

```
M = Σ sqrt(max((A_g - 50)/50, 0))     across ALL group types together
D = 100*(1 - exp(-M/6))
```

Pokémon baselines are a percentile of Pokémon-specific fan-popularity/Trends evidence; Trainer baselines are a percentile of a separate tournament-entity-observation evidence population; Functional baselines are a hardcoded 50 constant. There is no cross-domain calibration step. Empirically this produces rank distortions up to **41 positions** and score deltas up to **+7.5 points** on individual sets relative to a Pokémon-only control, against a backdrop where Trainer/Functional evidence is only 6.1% of total roster mass across the 128-set cohort — i.e. the distortion is concentrated on specific sets, not diffuse noise.

## 2. Domain definitions (Phase 1)

- **Pokémon domain**: unchanged — frozen Pokémon subject authority, distinct-group roster mass, existing saturation (`k=6.0`).
- **Trainer domain**: unchanged evidence source (12m/5y blended entity-observation percentile), but computed as its own **within-domain roster score** `D_trainer` using only Trainer groups, never mixed with Pokémon appeal values directly.
- **Functional domain**: no independent collector-demand evidence exists (baseline is a bare 50 constant; only Playability can move it). Per the locked finding's explicit instruction, Functional does **not** enter Collector Roster Appeal. It is retained only as a diagnostic (`D_functional_diag`, computed with the same roster formula but labeled a Playability/Utility index, never a demand signal) — Phase 1 option **B**.

## 3. Candidate architectures tested (Phase 2)

All candidates share `D_pokemon = roster_score(pokemon groups)` and `D_trainer = roster_score(trainer groups)` computed independently within their own domains (never pooling raw subject values across domains). `BETA = 0.15` is a pre-registered conservative constant (more conservative than the existing card-level Playability-lift `λ=0.20`), chosen for architectural consistency with the existing bounded-lift precedent — not tuned against price or any outcome variable.

- **Candidate A — Pokémon-only control**: `D = D_pokemon`. Trainer/Functional reported as diagnostics only.
- **Candidate B1 — Bounded Trainer headroom lift**: `D = D_pokemon + (100 - D_pokemon) * BETA * (D_trainer/100)`. Structurally identical in form to the already-accepted card-level `bounded_score()` lift — same "compress toward ceiling, positive-only, saturating" shape, applied one level up at the roster/bucket level instead of the card level.
- **Candidate B2 — Presence-aware bounded lift**: same as B1, additionally scaled by a `presence_factor = min(1, trainerGroupShare/0.15)` so that a set with only a token Trainer group (e.g., one weak Trainer among 40 Pokémon groups) gets a proportionally smaller lift than a set with a real Trainer roster presence.
- **Candidate C — Domain-normalized pooled representation**: tested a set-level z-score/percentile transform of `D_pokemon` and `D_trainer` before pooling. **Rejected as not mathematically defensible**: percentile-of-a-roster-score changes the score's meaning per set (it becomes "how this set's Pokémon roster ranks among other sets' Pokémon rosters," not "how strong is the Pokémon roster") and reintroduces a comparability assumption at one remove — it does not demonstrate the two domains now share semantics, it just moves the unverified assumption from the card level to the set level. Not carried into Phase 4/5 empirical testing beyond this note.
- **Candidate D — Separate visible axes only**: operationally identical to Candidate A for the purposes of what enters V6 Collector Appeal (Pokémon roster only), but frames Trainer Appeal and Functional Utility as permanently separate, independently-surfaced axes rather than "future inputs pending calibration." This is a labeling/product-contract distinction from A, not a different formula.

## 4. Synthetic falsification (Phase 3)

12 hand-built archetypes (`backend/artifacts/collector_v6_redesign_research/synthetic_archetypes.txt`), evaluated against Candidate B1:

| Archetype | D_pokemon | D_trainer | Cand A | Cand B1 | Lift |
|---|---|---|---|---|---|
| 1. Elite Pokémon, no Trainer | 51.37 | n/a | 51.37 | 51.37 | 0.000 |
| 2. Weak Pokémon, elite Trainer | 9.31 | 37.76 | 9.31 | 14.45 | 5.137 |
| 3. Elite Pokémon + elite Trainer | 36.40 | 26.45 | 36.40 | 38.92 | 2.523 |
| 4. Weak Pokémon + many mediocre Trainers | 7.15 | 65.15 | 7.15 | 16.22 | 9.074 |
| 5. One elite Trainer only, no Pokémon | 0.00 | 15.21 | 0.00 | 2.28 | 2.281 |
| 6. Many barely-above-neutral Trainers | 10.00 | 10.58 | 10.00 | 11.43 | 1.428 |
| 7. Trainer-heavy historical set | 13.17 | 30.04 | 13.17 | 17.08 | 3.913 |
| 8. Functional-heavy modern set | 20.01 | 7.18 | 20.01 | 20.87 | 0.862 |
| 9. Pokémon-only vintage set | 38.85 | n/a | 38.85 | 38.85 | 0.000 |
| 10. Duplicated Pokémon printings (dedup check) | 13.85 | n/a | 13.85 | 13.85 | 0.000 |
| 11. Duplicated Trainer printings (dedup check) | 10.00 | 13.02 | 10.00 | 11.76 | 1.757 |
| 12. Mixed multi-subject card | 21.88 | 10.00 | 21.88 | 23.05 | 1.172 |

Properties verified against the Phase 3 checklist:
- **No cross-domain subject comparison**: confirmed — `D_pokemon` and `D_trainer` are each computed from only their own groups; the formula never compares an individual Trainer's appeal number to an individual Pokémon's appeal number.
- **Duplicate safety**: archetypes 10/11 confirm max-per-identity-group compression is preserved (three identical Pikachu printings score identically to one).
- **Monotonicity within domain**: by construction (`roster_score` is monotone increasing in each domain's group appeals).
- **No reward for neutral-only breadth**: archetype 6 (15 Trainers all at 50.1) contributes almost nothing (`D_trainer=10.58`, lift=1.43) — the `max((A_g-50)/50,0)` term is near-zero for near-neutral scores regardless of count.
- **Missing Trainer evidence ≠ zero (data-contract requirement)**: mathematically, "no Trainer groups" and "Trainer groups present but D_trainer=0" both yield zero lift under B1/B2, so the *score* is unaffected either way — but the **data contract must still distinguish `trainer_unavailable` from `trainer_scored_zero`** at the field level (analogous to how missing F is never fabricated as zero), so downstream consumers don't misread "no Trainer subjects in this set" as "this set's Trainers tested poorly."
- **Functional cannot manufacture collector demand from Playability alone**: confirmed by design — Functional is excluded from all candidate formulas; archetype 8 shows Functional groups present but contributing 0 to any candidate score (only reported as `D_functional_diag`, unused).
- **Weak Trainers cannot lower Pokémon appeal**: confirmed — `D_pokemon` term is computed independently and never decremented by anything Trainer-side; B1/B2 are strictly additive-or-neutral (`lift ≥ 0` always, since `D_trainer ≥ 0` and `(100-D_pokemon) ≥ 0`).
- **One high Trainer cannot overpower an elite Pokémon roster via scale mismatch**: archetype 5 (one elite Trainer=99, no Pokémon at all) only reaches `B1=2.28`, far below even the weakest real Pokémon-only archetype (1: 51.37) — the headroom term `(100-D_pokemon)` combined with `BETA=0.15` structurally caps how much Trainer evidence alone can contribute.

## 5. Empirical impact on the 128-set frozen cohort (Phase 4)

Computed directly from the frozen `collector_c3b_card_appeal_shadow_v2.json` (18,293 cards) / `collector_c4_set_components_shadow_v1.json` artifacts — no DB writes. Full table: `backend/artifacts/collector_v6_redesign_research/full_128_set_comparison.json`.

| Set | D_pokemon | D_trainer | Current (flawed) D | Cand A | Cand B1 | Cand B2 | rank(current) | rank(pokéOnly) | rank(B1) | Δrank current−pokéOnly | Δrank current−B1 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Perfect Order | 86.74 | 30.93 | 93.88 | 86.74 | 87.35 | 87.35 | 42 | 83 | 81 | **−41** | −39 |
| Twilight Masquerade | 86.74 | 43.75 | 93.50 | 86.74 | 87.61 | 87.61 | 47 | 84 | 78 | **−37** | −31 |
| Ultra Prism | 91.72 | 58.92 | 96.60 | 91.72 | 92.45 | 92.45 | 26 | 55 | 48 | −29 | −22 |
| Crown Zenith | 94.61 | 61.78 | 97.94 | 94.61 | 95.11 | 95.11 | 10 | 34 | 32 | −24 | −22 |
| Champion's Path | 85.84 | 34.43 | 90.71 | 85.84 | 86.57 | 86.57 | 67 | 89 | 87 | −22 | −20 |
| Mega Evolution | 92.89 | 29.79 | 97.07 | 92.89 | 93.21 | 93.13 | 20 | 40 | 39 | −20 | −19 |
| Prismatic Evolutions | 95.79 | 46.45 | 97.75 | 95.79 | 96.09 | 96.09 | 14 | 25 | 22 | −11 | −8 |
| Chilling Reign | 94.73 | 31.44 | 96.38 | 94.73 | 94.98 | 94.98 | 30 | 33 | 33 | −3 | −3 |
| Team Up | 99.08 | 25.99 | 99.32 | 99.08 | 99.12 | 99.12 | 5 | 6 | 6 | −1 | −1 |
| Cosmic Eclipse | 99.49 | 72.23 | 99.86 | 99.49 | 99.55 | 99.55 | 3 | 3 | 3 | 0 | 0 |
| Evolving Skies | 99.11 | 21.12 | 99.30 | 99.11 | 99.14 | 99.12 | 6 | 5 | 5 | 1 | 1 |
| Generations | 87.59 | n/a | 87.59 | 87.59 | 87.59 | 87.59 | 83 | 77 | 79 | 6 | 4 |
| Rising Rivals | 89.07 | n/a | 89.07 | 89.07 | 89.07 | 89.07 | 77 | 68 | 69 | 9 | 8 |

**Distortion removal, full 128-set cohort:**

| Metric | Current (flawed) vs Pokémon-only | Cand A vs Pokémon-only | Cand B1 vs Pokémon-only | Cand B2 vs Pokémon-only |
|---|---|---|---|---|
| Max |rank delta| | **41** | 0 (identical by definition) | **7** | 7 |
| Mean |rank delta| | 6.56 | 0.00 | 0.84 | 0.73 |
| Sets with |rank delta| > 10 | 24 | 0 | 0 | 0 |

Both bounded-lift candidates (B1, B2) eliminate every double-digit rank distortion found in the current flawed model while still incorporating real, bounded Trainer signal (Perfect Order and Twilight Masquerade move from a 41/37-position inflation down to a 7-or-fewer-position residual, which is attributable to legitimate bounded Trainer contribution rather than cross-domain scale mismatch). This is not simply reverting all Trainer information to zero — Trainer evidence still moves scores (e.g., Cosmic Eclipse's real Trainer strength of 72.23 still contributes a visible +0.06 lift), it just can no longer swing rank by dozens of positions.

## 6. Information / redundancy analysis (Phase 5)

- **corr(D_pokemon, D_trainer)** across the 68 sets with Trainer evidence: **0.989** (Spearman). This is very high, but driven almost entirely by set-size confounding, not by the two domains measuring the same construct — see below.
- **corr(D_pokemon, Candidate)** for A/B1/B2: **1.0000 / 1.0000 / 1.0000** (Spearman) — the bounded-lift candidates preserve the Pokémon-only rank ordering almost exactly, consistent with the Phase 4 distortion-removal result.
- **Dependence on scale, not domain semantics**: `D_pokemon` correlates 0.999 with `pokemonGroupCount`, 0.998 with `totalCards`, and — notably — 0.995 with `trainerGroupCount` and `functionalGroups` too. This is because roster mass (`Σ√u_g`) is fundamentally a **set-size/basket-size** statistic: bigger sets have more of every group type simultaneously, so all four counts move together across the 128-set cohort. This mirrors the previously-documented basket-size degeneracy in Set Chase Efficiency Stage I — it is a known category of confound in this codebase's set-level roster metrics, not new to this analysis. It means the very high `D_pokemon`/`D_trainer` correlation should **not** be read as evidence the two domains are semantically comparable; it is largely a byproduct of both being computed on the same larger-or-smaller set.
- **Sensitivity to Trainer source uncertainty** (±5%/±10%/±20% multiplicative noise on `D_trainer`, 30 Monte Carlo trials per level, measuring rank churn of Candidate B1 across all 128 sets):

| Perturbation | Max rank shift (any set, any trial) | Mean rank shift |
|---|---|---|
| ±5% | 2 | 0.030 |
| ±10% | 2 | 0.062 |
| ±20% | 2 | 0.108 |
| combined 3,840 observations | 0/3,840 shifted by >2 positions | — |

Candidate B1 is highly robust to Trainer-source measurement uncertainty — even a ±20% perturbation of every set's Trainer roster score never moves any set's rank by more than 2 positions. This robustness is a direct consequence of the bounded-lift architecture: because the lift term is capped by `(100-D_pokemon)*BETA`, Trainer-side noise can only ever perturb the final score by a small, ceiling-bounded amount.

## 7. Price / market usage disclosure (Phase 6 compliance)

No candidate weight, normalization, or selection decision in this research used market price data. `BETA=0.15` was chosen by architectural analogy to the existing card-level lift constant (`λ=0.20`, made more conservative for a roster-level aggregate), not by optimizing against price correlation. No candidate was rejected on the basis of price relationship. Market validation is explicitly deferred to the future V7 research program per the task's instructions.

## 8. Files produced

- `docs/research/collector_appeal_v6_cross_bucket_redesign_research.md` (this file)
- `backend/artifacts/collector_v6_redesign_research/full_128_set_comparison.json` (Phase 4 full table, all 128 sets)
- `backend/artifacts/collector_v6_redesign_research/candidate_formula_manifest.json` (Phase 2 formula specification)
- `backend/artifacts/collector_v6_redesign_research/synthetic_archetypes.txt` (Phase 3 raw output)
- `docs/research/collector_appeal_v6_cross_bucket_redesign_recommendation.md` (Phase 7 recommendation)

## 9. Recommendation

See `collector_appeal_v6_cross_bucket_redesign_recommendation.md` for the Phase 7 classification and final recommendation.
