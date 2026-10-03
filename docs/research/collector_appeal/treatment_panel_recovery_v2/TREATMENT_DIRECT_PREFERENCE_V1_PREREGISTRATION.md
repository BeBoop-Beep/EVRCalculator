# Treatment Direct Preference V1 — Preregistration

Status: `PREREGISTERED_BEFORE_HUMAN_PREFERENCE_OUTCOMES`

Date: 2026-10-03

## Objective

Estimate whether Pokémon card visual Treatment has intrinsic collector-preference value when market information is hidden.

This study is explicitly designed to avoid the Treatment/scarcity confounding that blocked Treatment V2.

The primary estimand is **human preference probability**, not market-price premium.

## Treatments in V1

Primary connected family:

- Double Rare
- Ultra Rare
- Special Illustration Rare

V1 does not estimate:

- Hyper Rare
- Mega Hyper Rare
- Illustration Rare

Those families require separate preregistered extensions after the primary design is validated.

## Experimental unit

One response to one blinded pairwise card-image comparison.

Each comparison asks:

> Which version would you rather own for the artwork/presentation itself?

The respondent must choose:

- Left
- Right
- No preference / effectively tied

No market-value framing is shown.

## Pair construction

### Primary matched pairs

Prefer exact same Subject identity within the same Set where multiple Treatments exist.

Allowed primary edges:

- SIR vs Double Rare
- SIR vs Ultra Rare
- Ultra Rare vs Double Rare

The starting candidate pool should come from the already frozen complete triad identities in the 2026-09-29 simulation/catalog authority, but **pair inclusion is chosen without using V2 prices or V2 effect magnitudes**.

### Pair eligibility

A pair is eligible when:

1. same canonical Subject identity,
2. same Set,
3. two distinct Treatment classes among DR/UR/SIR,
4. English card image available,
5. image legible enough for presentation comparison,
6. neither image contains a market-price overlay or externally added badge,
7. both cards are displayed at the same rendered dimensions.

Price, pull rate, rarity market ranking, and V2 market effect are not pair-selection variables.

## Frozen study subset

The complete price-independent candidate pool contains 103 eligible matched triads / 309 pair comparisons.

The primary V1 collection subset is frozen **before human outcomes** at:

- **45 matched triads**
- **135 pair comparisons**
- exactly 45 comparisons per Treatment edge

Selection rule:

1. include **all 21 eligible Mega Evolution triads**;
2. for Scarlet & Violet, include the stable-hash-min triad from every eligible Set;
3. allocate one additional triad to the ten Scarlet & Violet Sets with the largest eligible triad pools;
4. break eligible-pool ties by Set name;
5. within each selected Set, use the second stable-hash-min triad for the additional slot.

The stable hash is computed only from Set name + Subject key.

No price, pull-rate magnitude, V2 effect, rarity-market rank, image aesthetics, or future preference outcome is used to select the study subset.

Expected composition:

- Mega Evolution: **21 triads / 63 comparisons**
- Scarlet & Violet: **24 triads / 72 comparisons**
- total: **45 triads / 135 comparisons**

The generated subset must pass the preregistered <=10% Subject-concentration gate before collection starts.

## Visual masking

The experiment must remove or conceal information that directly reveals the experimental label where feasible without destroying the visual Treatment itself.

Do not display:

- market price,
- rarity name,
- pull probability,
- card number in surrounding UI,
- score/rank,
- treatment label,
- “SIR”, “Ultra Rare”, or “Double Rare” text in the survey interface.

The physical card art/frame/foil-treatment appearance remains visible because that is the treatment being evaluated.

## Randomization

For every response:

- randomize left/right assignment independently,
- never permanently map one Treatment to one side,
- randomize question order per respondent,
- do not show aggregate results until the respondent has completed the assigned block.

Each underlying pair must receive approximately balanced left/right exposure.

## Respondent blocks

To reduce fatigue and repeated-subject anchoring:

- target block size: 12 pairwise questions,
- maximum block size: 18,
- do not show the same exact card pair twice to one respondent,
- avoid showing the same Subject more than twice in one block where possible.

## Target sample

Primary minimum:

- **40 independent evaluable responses per underlying pair**
- at least **20 non-tie responses per underlying pair**

Preferred target:

- **60 independent evaluable responses per underlying pair**

Primary collection coverage gate:

- at least 90% of the 45 frozen triads must have all three pair edges reach the primary minimum,
- both eras must retain at least 80% of their frozen triads,
- no pair may be removed because its observed preference direction is weak or inconvenient.

If the coverage gate fails, the confirmatory preference fit is not promoted; collection may continue on the same frozen manifest.

A response is evaluable if the respondent selects Left, Right, or Tie and the client records the randomized orientation.

No pair is dropped post-hoc because its preference result is weak or surprising.

## Independence and duplicate controls

The collection system should record a privacy-preserving respondent/session identifier sufficient to prevent accidental duplicate submissions within the same study block.

Do not require personally identifying information.

Repeated submissions from the same study session for the same pair count once.

## Primary estimator

The primary analysis is **equal-weight across underlying matched card pairs**, not pooled across raw responses.

For each underlying pair `i` on one Treatment edge, exclude ties and compute continuity-corrected pair log-odds:

`l_i = log((wins_high_i + 0.5) / (wins_low_i + 0.5))`

The primary edge effect is:

`L_edge = mean_i(l_i)`

with multiplier-style preference odds:

`PreferenceOdds_edge = exp(L_edge)`

Each underlying same-Subject / same-Set pair receives equal weight regardless of how many usable responses it receives above the minimum gate.

This prevents:

- high-traffic pairs from dominating,
- one popular Subject from defining the Treatment result,
- respondent-count imbalance from masquerading as Treatment strength.

The three primary edges are estimated directly:

- SIR vs Double Rare
- SIR vs Ultra Rare
- Ultra Rare vs Double Rare

A secondary connected three-node Bradley-Terry summary may be reported from the three frozen edge estimates, with Double Rare anchored at zero, but it is **not** the primary decision authority.

Raw pooled respondent preference shares are descriptive only.

## Tie handling

Primary analysis:

- ties are excluded from each pair's primary log-odds calculation,
- tie rate is reported independently by pair and Treatment edge.

Sensitivity analysis:

- split each tie as 0.5 / 0.5 preference weight and recompute equal-weight pair log-odds.

The primary decision may not be changed based on the sensitivity result.

## Primary contrasts

Report:

- SIR vs Double Rare preference odds
- SIR vs Ultra Rare preference odds
- Ultra Rare vs Double Rare preference odds

Also report intuitive preference probabilities on a neutral matched pair.

## Bootstrap

Use whole-underlying-pair resampling.

- 2,000 deterministic bootstrap draws
- seed: `20261003`
- resample matched underlying pairs with replacement **within each Treatment edge**
- retain each sampled pair's frozen pair-level log-odds
- recompute the equal-weight edge mean

This measures transport across card identities rather than only respondent sampling noise.

A secondary nested bootstrap may additionally resample respondents within sampled pairs, but it cannot replace the whole-pair primary bootstrap.

## Primary support gates

A Treatment relationship is supported only if all applicable gates pass.

### SIR vs Double Rare

1. point log-odds > 0
2. whole-pair bootstrap 95% lower bound > 0
3. >=70% of underlying pairs have >50% non-tie SIR preference
4. leave-one-pair-out aggregate sign remains positive
5. left/right orientation effect is not materially directional

### SIR vs Ultra Rare

Same five gates.

### Ultra Rare vs Double Rare

Descriptive unless its own five gates pass.

No universal order is forced.

## Orientation-bias gate

Fit/report:

`P(left chosen)`

aggregated across randomized assignments.

The frozen orientation diagnostic has two gates:

1. absolute non-tie left-choice deviation from 50% must be <= **7.5 percentage points**;
2. in a logistic model of whether Treatment A wins, with one intercept per Treatment edge plus an indicator for Treatment A being displayed on the left, the **95% Wald interval for the A-on-left coefficient must include zero**.

Both gates must pass.

A failed orientation result blocks promotion of the preference authority until corrected and independently recollected.

## Subject concentration gate

No single Subject identity may contribute more than 10% of the effective pair weight in the primary Treatment contrast.

If the candidate pool mechanically violates this before outcomes are collected, rebalance the pair assignment **before** collection begins.

Do not rebalance after preference outcomes are observed.

## Era reporting

If both Mega Evolution and Scarlet & Violet provide sufficient matched pairs:

- report era-specific Treatment contrasts,
- require the primary SIR relationship to have the same positive point direction in both eras for cross-era authority.

Era-specific bootstrap lower bounds are reported but are not promotion gates in V1 unless frozen before collection begins.

## Normalization

Do not define the final 0–100 Treatment Appeal transform before the direct-preference study passes.

If V1 passes, a separate normalization preregistration must map preference log-odds to a bounded Treatment Appeal scale.

The failed market-derived V2 normalization is not reused.

## Comparison with V2 market signal

Only after the direct-preference result is frozen may the study compare:

- direct preference Treatment contrasts,
- V2 descriptive market-direction results.

This comparison is diagnostic.

Agreement would strengthen interpretation.
Disagreement would indicate that market premium is driven by scarcity/structure or other non-preference factors.

The V2 price result never enters the direct-preference fit.

## Collector Appeal entry gate

A direct-preference Treatment authority may enter a Collector Appeal shadow study only if:

1. both SIR vs DR and SIR vs UR primary gates pass,
2. orientation-bias gate passes,
3. subject concentration gate passes,
4. collection protocol is reproducible,
5. independent replication plan is defined,
6. score remains price-independent.

No production Collector mutation is authorized by V1 alone.

## Data contract

Each response should minimally contain:

- study_version
- anonymous_session_id
- underlying_pair_id
- set_id
- subject_key
- left_card_id
- right_card_id
- left_treatment
- right_treatment
- randomized_orientation_receipt: exactly `A_LEFT` or `B_LEFT`
- response: LEFT / RIGHT / TIE
- submitted_at

Treatment labels may be stored server-side but must not be shown in the respondent UI.

## Safety / privacy

Do not collect unnecessary personal information.

No respondent-level preference data is published with an identifying account field.

## Production boundary

Research only.

- Collector Appeal mutation: NONE
- Fair Value mutation: NONE
- Overall RIP mutation: NONE
- Rankings mutation: NONE
- pricing mutation: NONE
