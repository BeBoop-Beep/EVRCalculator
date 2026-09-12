# Pokémon Roster Desirability (D_pokemon) — Recommendation

Status: **research recommendation only. Nothing implemented. No production state changed.**

## Decision

Current `D_pokemon` fails direct falsification on three of nine pre-registered criteria — most importantly, it allows a broad roster of only-just-positive Pokémon to outrank a small roster of near-maximal Pokémon (60×appeal-55 scores higher than 3×appeal-98), and set-level breadth alone produces 50–75 point score swings between sets with matched mean appeal (Ascended Heroes vs. Celebrations: nearly identical mean appeal, 56-point D gap driven entirely by group count). This is not a benign correlation artifact — it was established by direct construction of matched-count and matched-appeal comparisons and synthetic archetypes, per the task's own decisive-test requirement.

`V6_POKEMON_ROSTER_D_REDESIGN_READY`

## Why not CONFIRMED

The ~0.995–0.999 correlation between `D_pokemon` and group/card-count proxies is not shown to be benign. The matched-appeal test is the direct falsification the task asked for, and it fails: at matched mean Pokémon appeal, D varies by up to 75 points purely as a function of how many eligible Pokémon groups a set happens to contain. A construct meant to measure "roster desirability" should not let two sets with statistically indistinguishable average subject quality land 56–75 points apart on breadth alone.

## Why not BLOCKED

The data was sufficient to distinguish the designs honestly. The matched-count test shows appeal still matters conditional on breadth (Spearman 0.94–1.00 within bands), which rules out "these designs are indistinguishable" — the population simply has enough real variation (Detective Pikachu at n=4 vs. Paldean Fates at n=138, both represented in the same cohort) to run a clean falsification test, and it produced a clear, reproducible answer.

## Recommended replacement direction (not final formula)

A **Strength + Bounded Breadth** two-part architecture — separating "how good are the headline subjects" (strength) from "how many qualifying subjects exist" (breadth), with breadth entering only as a bounded headroom lift on top of strength — is the one tested family that satisfies all nine falsification criteria (see the companion audit's Phase 7 table). It is architecturally consistent with the already-accepted bounded-lift pattern used for both the card-level Playability lift and the Trainer-domain cross-bucket lift (Candidate B1), rather than introducing a new mechanism.

The exact tested parameterization (`strength = mean(top-5 appeal)`, `breadth = 100(1-exp(-positiveGroupCount/15))`, `GAMMA=0.5`) is **not** recommended for direct implementation as-is: it passes every hard falsification requirement, but produces very large rank churn (max |rank delta| 102, mean 19.4 across the 128-set cohort) and compresses differentiation among strong sets because the `top-5 mean` strength anchor saturates near 100 for most modern curated sets. Before this becomes an implementation candidate, the strength anchor and/or breadth saturation constant need a dedicated calibration pass — evaluating a broader top-N window, a less-saturating strength transform, or a different headroom weight — using the same falsification battery (not price) as the acceptance test.

**Note on Candidate B1 (the accepted cross-bucket architecture from the prior research phase):** B1 sits on top of `D_pokemon` (`D_combined = D_pokemon + (100-D_pokemon)*0.15*(D_trainer/100)`). Because `D_pokemon` itself requires correction, B1's formula shape remains valid, but it should be re-anchored to the corrected `D_pokemon` once that replacement is finalized — not implemented against the current, construct-invalid `D_pokemon`.

## What was explicitly ruled out

**Top-K truncation of the existing mass formula** (tested at K=25/20/15/12 with multiple saturation constants) does **not** fix the falsification failures at any tested parameterization — the sqrt-mass/exponential-saturation transform treats "many weak" and "few strong" subjects as fungible regardless of how many groups are allowed to contribute, so truncating the group count alone does not address the underlying mechanism.

## What remains untouched and correct

- Card-level C3B scoring (Pokémon/Trainer/Functional subject baselines, positive-only Playability lift) — not in scope, not touched.
- Duplicate-printing compression (max-per-group) — confirmed intact under every tested candidate.
- Neutral-50 addition producing exactly zero score change — confirmed intact under every tested candidate.
- Price/Artist/Treatment/Scarcity exclusion — untouched, no candidate introduces any of these inputs.
- Overall RIP V12 (still Collector V5) — untouched, not referenced by any part of this research.

## Required before implementation

1. A calibration pass on the Strength+BoundedBreadth parameters against the same falsification battery used here (not against price), specifically targeting the top-end differentiation/rank-churn concern.
2. Re-validation of Candidate B1 (Trainer headroom lift) against the corrected `D_pokemon`, since B1's headroom term depends on `D_pokemon`'s absolute scale.
3. A new, append-only model identity and formula fingerprint — the existing published V6 run (`0efa3c8f-918d-49d7-ad5e-3ae37278058f`) remains historical and untouched throughout.

`V6_POKEMON_ROSTER_D_REDESIGN_READY`
