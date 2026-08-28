# Card Treatment Prestige V2 — Frozen-Cohort Method

## Estimand and containment

The question is whether market price differs by card rarity/treatment after accounting for Pokémon identity, exact pull scarcity, set, and mechanics. V2 is research-only. It cannot alter V1 Card Appeal, RIP metrics, rankings, snapshots, Card Detail, or frontend behavior without a later explicitly approved production study.

## Immutable authority

For every supported set, freeze exactly one authority: the newest published exact `simulation_card_variant_pull_rates` run, falling back to the set-page `sourceCalculationRunId`. Persist the set/run manifest and every canonical mapping used by the analysis, with content hashes. Subsequent estimation must use `--use-existing-freeze`; it must not refresh production rows.

Canonical reconciliation follows exact variant ID, its legacy card ID, API identity, set, and canonical mapping. The preregistered join gate is at most 5% failed exact rows. Failures are reported, never silently dropped. Failed frozen attempts remain immutable audit evidence.

## Local-support gate

Universal common support is not required for a narrowly scoped pair, but every pair is tested within era. A direct edge requires at least 50 observations per treatment, 25 from each treatment inside overlap, 25% overlap coverage on each side, five sets, and 20 species. Indirect graph connectivity is never interpreted as direct identification.

Round 4 locks 15 rarity contrasts: eight in Scarlet & Violet and seven in Mega Evolution. Missing retained edges are reported as `PAIR_SUPPORT_FAILED`, not omitted.

## Estimation and robustness

For a supported pair, restrict observations to its frozen empirical log-scarcity overlap and single-subject cards with positive Near Mint prices:

`log(price_i) = pair indicator + log(1/pull probability) + set FE + species FE + mechanic controls + error_i`

The pair coefficient is converted with `100 × (exp(beta) - 1)`. Primary uncertainty uses 1,000 Rademacher wild-bootstrap draws clustered by set with seed `20260828`. Sensitivities use scarcity quartiles, mechanics removal, top-demand exclusion, scarcity-cell balance weights, leave-one-set-out fits, and 199 within-set/scarcity-stratum permutations.

`LOCALLY_VALIDATED` requires a full-rank primary model, a bootstrap interval excluding zero, permutation p below 0.05, stable sign and magnitude across sensitivities, and every leave-one-set-out fit to remain estimable with the same sign. Missing or rank-deficient robustness fits yield `LOCAL_EFFECT_UNCERTAIN`; sign or material effect instability yields `LOCAL_EFFECT_UNSTABLE`.

## Decision rule

Local overlap alone is `V2_LOCAL_COMMON_SUPPORT_EXISTS`. Only a pair passing all estimation and robustness gates may be `LOCALLY_VALIDATED`, and even that would remain pair/era/cohort-specific. Universal V2 production approval remains prohibited when global support fails. Database and production writes are zero for this round.

## Round 5 rank decomposition

Round 5 reuses the Round 4 mapping and hashes without any `latest` lookup. It builds six nested matrices per retained pair: treatment only; treatment plus scarcity; then set FE; species FE; set and species FE; and finally mechanics. Treatment estimability is tested from the residual variance of the treatment indicator after projecting it on every nuisance column. Full-matrix rank deficiency alone is not treated as proof that the treatment coefficient is unidentified.

Aliased nuisance dummies are classified as mathematical redundancy when the treatment residual remains nonzero. When set, species, or mechanic controls reduce treatment residual variation to numerical zero, the result is scientific nesting: deleting that control would change the identifying assumption rather than merely reparameterize the same estimand.

An alternative `V2B_ADJUSTED_DEMAND_ASSOCIATION` is eligible only with at least 90% frozen-cohort coverage from a contemporaneously frozen, price-independent species-demand signal, plus the existing support, balance, estimability, and robustness gates. No such demand snapshot was included in Round 4, so Round 5 does not estimate V2B.

## Round 6 nuisance reparameterization

Round 6 estimates only the six contrasts whose treatment indicators remain outside the complete nuisance-control column space. Pivoted QR selects a full-rank basis of the original nuisance columns while keeping treatment explicit. A removed column is accepted only when the selected basis has the same rank and reconstructs the original nuisance matrix to numerical tolerance. This changes parameterization, not the scientific model or treatment estimand.

Inference uses 1,000 Rademacher wild-bootstrap draws clustered by set. Robustness includes every leave-one-set-out refit under the same reparameterization, scarcity strata, the locked top-5% species-price outlier diagnostic, mechanics sensitivity, scarcity-cell balance weighting, and 199 within-set/exact-pull-scarcity-stratum permutations. Six permutation p-values are adjusted with the preregistered Holm family-wise procedure. Validation requires complete estimable and stable leave-one-set-out results, stable sensitivity signs and magnitudes, a wild-bootstrap interval excluding zero, and Holm-adjusted p below 0.05.

The independent demand signal is frozen separately for future work and is not used in Round 6 estimation.
