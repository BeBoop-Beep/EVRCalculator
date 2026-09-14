# Pokémon Baseline Transform — Implementation Recommendation

Status: **research recommendation only. Nothing implemented. No production state changed.**

## Decision

`V6_POKEMON_BASELINE_TRANSFORM_READY`

## Selected transform

Replace `pranks(pokemon_raw)` percentile ranking with the **raw `pokemon_desirability_composite_scores.desirability_score`, used directly as Pokémon Subject Appeal**, feeding into the unchanged C3B bounded-Playability-lift and the unchanged (from the prior calibration pass) Strength + Bounded Breadth roster architecture, with the unchanged Trainer bounded-headroom lift (λ=0.15) on top.

This resolves the exact blocker from the prior pass (`V6_POKEMON_ROSTER_CALIBRATION_BLOCKED`): the compression was in the *input*, not the *combination formula*, and removing the percentile step restores real, matched-appeal-fair differentiation (largest count-driven swing at matched Strength: 9.91 points, down from 56–75 points under the rejected model) while every previously-validated falsification property carries over unchanged (the combination formula itself was not touched in this pass).

## Complete formula chain (proposed)

```
1. Pokémon Subject Appeal  = pokemon_desirability_composite_scores.desirability_score   (raw, no percentile)
2. Card Collector Appeal   = bounded_score(SubjectAppeal, Playability, λ=0.20)            (UNCHANGED)
3. D_pokemon               = Strength + (100-Strength) * 0.15 * Breadth
     Strength = 50 + 50*(1-exp(-raw/1.5)),  raw = Σ w_i*(appeal_i-50)/50 over top-5 positive subjects, w=[1.0,.6,.4,.25,.15]
     Breadth  = 1-exp(-Σ clamp((appeal_i-65)/(100-65),0,1)^1.3 / 8)
4. D_final                 = D_pokemon + (100-D_pokemon) * 0.15 * (D_trainer/100)        (UNCHANGED, locked)
5. F                       = existing generalized desirable-frequency computation, eligibility now driven by the new Card Collector Appeal >50 threshold
6. Combined Collector Appeal = existing C5 D/F combination with the existing ±2/−1 signed modifier (UNCHANGED transform, recomputed values)
```

Functional remains diagnostic-only, excluded from D. Artist, Treatment, price remain excluded. Energy remains excluded.

## Why each locked component survives unchanged

- **Trainer domain / cross-bucket architecture (Candidate B1)**: untouched — Trainer's own baseline computation was never in scope, and its bounded lift onto `D_pokemon` is agnostic to how `D_pokemon` itself was derived, as long as `D_pokemon` stays a valid 0–100 value (it does).
- **Strength + Bounded Breadth formula**: untouched, same constants — the fix was entirely upstream of this formula (it operates on whatever Card Collector Appeal values it's given; it was never the source of the compression).
- **C3B Playability lift**: untouched (`bounded_score()`, λ=0.20) — only the baseline argument passed into it changed.
- **C5's D/F combination and modifier**: not touched, and no structural reason found to expect it needs to change — it operates on D (still 0–100) and F (still a probability in [0,1]); neither's *type* changed, only F's *computed value* per set, which C5 already treats as an input to recompute against, not a fixed constant.

## What changed and needs explicit sign-off

- **Neutral semantics**: `50` moved from "population median by rank-construction" to "a fixed point on the composite's native scale, now representing roughly the top 30% of Pokémon by real demand" (Phase 4). This is a real, disclosed model-semantics change, not cosmetic.
- **F eligibility membership**: 2,764 Pokémon-subject cards (28% of the old eligible set) lose F-eligibility under the stricter raw-composite threshold; only 15 gain it. This is the direct, expected, and explainable consequence of the neutral-semantics change — not an error to be second-guessed against the old numbers.
- **Rank sensitivity to composite noise**: materially higher than the (degenerate) prior candidate's near-zero sensitivity — this is evidence the model now measures something real, not a regression. Operationally, this raises the importance of composite data quality, especially given the already-known Trends-coverage gap (49.7% zero) flagged in Phase 1.

## Required before implementation (mechanical, not research)

1. **Run the existing `research_collector_c4_set_components.py` F/roster pipeline against the reconstructed T1 C3B artifact** (substituting `c3b_reconstructed_T1_raw.json`'s card-level values, joined against live production pull-rate-model data) to produce the exact final F and C5-combined values for all 22 modeled sets. This is the same deterministic code already used to produce the frozen V6 numbers — no redesign required, just a re-run with new upstream inputs. This local research pass computed the eligibility delta (Section Phase 8) and confirmed Trainer-lift/D_pokemon correctness, but did not have production pull-rate-model access to finish this last mechanical join.
2. **Confirm C5's modifier and combination formula produce sane output** against the newly-computed F values (expected to be a non-event per the Phase 9 analysis, but should be verified against real numbers before publish, not assumed).
3. **New, append-only model identity and formula fingerprint** — this transform changes `subjectFingerprint`, `formulaFingerprint`, and every downstream C4/C5/C6 lineage hash. It must never be written into `pokemon_collector_appeal_v6_generalized_roster_frequency` / `0efa3c8f-918d-49d7-ad5e-3ae37278058f`, which remains the historical control.
4. **Naming**: per the task's explicit instruction, this is **not V7** (V7 is reserved for the future Artist/Treatment/Scarcity/full market-validation program). This is the corrected V6 control successor. A name reflecting its actual contents — corrected Pokémon baseline (raw composite, no percentile) + Strength/Bounded-Breadth roster + bounded Trainer lift + generalized F + Functional diagnostic-only — should be assigned at implementation time by whoever owns the model-naming convention; this research does not mint the final string.

## Production writes performed

**None.** All raw-composite data was read via read-only SQL against the production database (`pokemon_desirability_composite_scores`, `scoring_version='pokemon_desirability_composite_v1'`, `fan_popularity_snapshot_id=2`) solely to audit source semantics and reconstruct research artifacts locally; no writes, no pointer changes, no model mutation.

`V6_POKEMON_BASELINE_TRANSFORM_READY`
