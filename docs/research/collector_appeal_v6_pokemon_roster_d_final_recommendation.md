# Pokémon Roster Desirability — Final Calibration Decision

Status: **research only. Nothing implemented. No production state changed.**

## Decision

`V6_POKEMON_ROSTER_CALIBRATION_BLOCKED`

## Exact unresolved issue

No Strength+Bounded-Breadth calibration within the pre-registered families (Strength S1–S4, λ ∈ {0.10, 0.15, 0.20, 0.25}) can simultaneously satisfy:

1. Strength remains the dominant signal (Primary Goal #1), **and**
2. strong sets retain useful differentiation (Phase 5), **and**
3. breadth has a hard bounded influence / cannot dominate (Primary Goal #3, Phase 4).

All three were individually achievable; not together. The corrected additive-Strength formula (the fix for the mean-dilution monotonicity bug this pass discovered) satisfies (1) and (3) cleanly — every hard falsification test passes — but in doing so compresses 70% of the 128-set cohort (89/128 sets) into a 1.3-point band near the ceiling (78.91–91.31 overall range, SD=1.45 vs. the rejected model's SD=11.86), which fails (2) outright.

**Root cause, not a calibration mistake**: the frozen C3B Subject Appeal input for Pokémon is a **percentile rank** of a fan-popularity/Trends composite. Popular, frequently-reprinted Pokémon occupy the top percentiles in nearly every set they appear in, and most sets include several of them. Consequently, the top-5-to-20 subjects of most real sets are already sitting at 75–99% of the theoretical maximum "headline strength" raw score, regardless of window width (tested top-5 through top-15) or aggregation shape (weighted mean, weighted sum, geometric decay). The percentile transform has already consumed most of the cross-set discriminating signal at the top of the distribution before any roster-aggregation formula sees it. Any Strength function anchored to a small-to-moderate number of a set's best subjects inherits this compression; any Strength function drawn from a much larger slice of the roster reintroduces the basket-size dominance this whole research program exists to eliminate.

## What was proven, and should not be re-tested

- **The mean-dilution monotonicity bug is real and important**, independent of the differentiation blocker. Any future Strength candidate — including outside this pre-registered family — must be additive (a sum of non-negative, rank-weighted terms), never an average or count-normalized mean, or it will fail monotonicity whenever a set has fewer positive subjects than the averaging window. This is documented with a concrete counterexample (`1×100` scoring lower than `1×100+4×52` under a naive top-K mean) and should be treated as a standing implementation constraint for any future Strength design.
- **Top-K truncation of the old mass formula remains rejected** (confirmed again indirectly — this pass did not need to re-test it, per the prior audit's locked finding).
- **The basket-size-dominance falsification battery (broad-weak-vs-narrow-elite, n-mediocre-to-overpower-elite, neutral-add-is-zero) is fully solvable** by an additive bounded-breadth architecture — this pass's corrected formula passes every one of these tests cleanly. The blocker is exclusively the differentiation/compression requirement, not the original construct-validity defect.
- **F is provably unaffected** by any outcome of this calibration question (card-level, C3B-anchored, verified 0 differences against all 22 modeled sets) — this does not need to be re-proven once a Strength+Breadth formula is eventually accepted.

## What would need to change to unblock this

This is out of scope to decide unilaterally in a research-only pass (it edges toward redesigning the input, not just the combination formula, and touching C3B's percentile transform is explicitly outside this task's boundary), but the options a future research pass would need to evaluate are:

1. **A less-saturating transform of the existing percentile input** for the specific purpose of the Strength component only (e.g., a secondary rescaling anchored to fixed semantic points rather than population percentile) — would need its own construct-validity audit, since it changes what "Strength" numerically means.
2. **Accept lower differentiation among the top tier as a legitimate finding**, not a defect — i.e., conclude that most modern/popular sets genuinely do have comparably strong headline rosters, and let Breadth (already meaningfully bounded and falsification-clean) carry more of the ranking weight than originally intended, revisiting whether "Strength must dominate" is the right requirement given what the data actually supports. This would require the requesting stakeholder to explicitly relax Primary Goal #1, which this pass is not authorized to do unilaterally.
3. **Escalate to the C3B subject-appeal authority itself** (percentile transform) as a candidate research question for whatever future program is scoped to revisit input construction — explicitly out of bounds for this V6-correction research line per the task's own boundaries (no Artist/Treatment/Scarcity additions, no re-opening the cross-bucket or C3B decisions).

## Explicitly not touched by this blocker

- Cross-domain architecture (Candidate B1, λ_trainer=0.15): remains valid as designed, pending a corrected `D_pokemon` to sit on top of. Not invalidated by this finding.
- Functional diagnostic-only status: unaffected.
- Generalized F: proven unaffected (Phase 9 partial, this pass).
- C5's D/F combination transform and modifier: not touched, not evaluated (gated on an accepted D_pokemon, per the task's own phase ordering).
- Published V6 model `0efa3c8f-918d-49d7-ad5e-3ae37278058f`: untouched, remains the historical control.

## Production writes performed

**None.**

`V6_POKEMON_ROSTER_CALIBRATION_BLOCKED`
