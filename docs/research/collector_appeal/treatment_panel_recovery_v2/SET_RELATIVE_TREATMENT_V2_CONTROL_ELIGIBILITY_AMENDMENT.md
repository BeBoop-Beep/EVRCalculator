# Set-Relative Treatment V2 — Control Eligibility Implementation Amendment

Status: `FROZEN_RULE_IMPLEMENTATION_FIX_BEFORE_MODEL_RESULT`

Date: 2026-10-03 UTC

## Why this amendment exists

The frozen Set-relative Treatment V2 preregistration required exact matched Subject identity and frozen V7 Playability matching within each triad.

The fresh expansion capture successfully cleared its historical coverage gate, but the first estimator invocation stopped before producing any fitted Treatment result because one fresh triad violated the already-frozen Playability matching requirement:

- Set: `Pitch Black`
- Subject: `pokemon:pokemon:609`
- Card family: Mega Chandelure ex
- Double Rare Playability: `58.19568575255092`
- Ultra Rare Playability: `58.19568575255092`
- SIR Playability: `0`
- Subject baseline: identical across all three cards

No fitted Set-relative Treatment coefficients, bootstrap intervals, era results, sign shares, or final decision token were produced before this implementation defect was identified.

## Defect

The V2 fresh-panel builder froze complete rarity triads and historical readiness, but it did not apply the preregistered frozen-control equality rule before marking a triad eligible for the estimator.

The estimator correctly rejected the mismatch, but it did so as a hard runtime error rather than as a deterministic eligibility exclusion.

## Frozen correction

The correction is limited to enforcing the preregistered control rule mechanically:

1. Begin with the frozen 56-triad target. Do not substitute any subject or Set.
2. Apply the original history readiness rule.
3. For each history-ready fresh triad, require:
   - exact Subject baseline equality across Double Rare, Ultra Rare, and SIR;
   - exact frozen V7 Playability equality across Double Rare, Ultra Rare, and SIR.
4. A mismatch makes that triad unavailable for the confirmatory fit.
5. Record every exclusion explicitly in the result artifact, including Set, subject, reason, card IDs, and control values.
6. Recompute the existing preregistered coverage gate after these deterministic exclusions.
7. Do not inspect Treatment price-effect direction or magnitude when deciding eligibility.
8. Do not replace an excluded triad.
9. Do not change the model, bootstrap, temporal split, influence analysis, thresholds, Set weighting, or final support gates.

Artist differences remain allowed and continue to enter only through the already-frozen Artist nuisance coefficient.

## Observed eligibility impact before refit

The control audit found exactly one complete fresh triad with a Subject/Playability mismatch: Pitch Black `pokemon:pokemon:609`.

No other complete fresh target triad had a Subject or Playability mismatch.

Applying the frozen rule mechanically changes the fresh eligible cohort from:

- history-ready triads: 50
- control-eligible ready triads: 49
- Pitch Black: 4 -> 3

All existing coverage thresholds still clear before fitting:

- eligible fresh triads: 49 >= 45
- Pitch Black: 3 >= 3
- qualifying Scarlet & Violet Sets: 8 >= 7
- fresh cards with captured history: 162 >= 120
- production writes: 0

This statement is a coverage/eligibility check only. It is not a Treatment effect result.

## Provider boundary

The successful provider capture is frozen and reused.

- capture workflow run: `37083526829`
- capture artifact: `11260560244`
- provider credits used by Treatment capture: `15359`
- provider calls: `307`
- production writes: `0`

No additional PkmnPrices calls are authorized or required for this correction.

## Scientific boundary

This amendment repairs implementation of a rule that was already preregistered.

It does **not**:

- alter the 56-triad target fingerprint,
- add replacement identities,
- change historical prices,
- change pull probabilities,
- change nuisance controls,
- change the Set-relative model,
- change the 2,000-draw bootstrap,
- change temporal or leave-one-triad-out rules,
- change support thresholds,
- rescue a failed statistical result.

The next valid action is to rerun the existing estimator on the frozen capture after this deterministic control-eligibility correction passes unit tests.
