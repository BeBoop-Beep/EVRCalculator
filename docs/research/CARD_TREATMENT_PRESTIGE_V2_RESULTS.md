# Card Treatment Prestige V2 — Results

## Decision

`DO_NOT_APPROVE_CARD_TREATMENT_PRESTIGE_V2`

The exact-printing scarcity cohort available on 2026-08-27 contained 366 single-subject variants, but all were from one set and treatment scarcity distributions had no common support. Study A’s broader analytic snapshot read also encountered repeated live database statement timeouts during this implementation run. Those facts fail the preregistered set-diversity, common-support, robustness, and matched-finish gates. No V2 score is approved, persisted, or shown as production truth.

## Data audit

Live successful reads found 20,651 canonical cards, 19,779 priced canonical cards across the previously observed 163-set cohort, 40,654 variants, 210 catalog sets, 17 eras, 17,244 card/species links, 1,025 desirability rows, 499,332 historical simulation inputs, 933 exact-variant pull rows, and eight conditions. The 4.4-million-row price table exact count timed out and was not substituted with an estimate. The latest-price table still contains 19,779 rows. Counts are observations, not acceptance constants.

## Primary and matched cohorts

The completed exact-variant audit yielded 366 single-subject rows, 175 species, one set, one era, nine unmapped treatments, and two failed canonical joins. Cohort fingerprint: `b7bf10f4c3f53585bab0686da33dec2e0a18ba0ca92c94d45b49e7b9336f09f2`.

| Treatment | N | Sets | Adjusted Premium | 95% CI | Score /10 | Score CI | Stability | Scope | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| All classes | 366 | 1 | unavailable | unavailable | unavailable | unavailable | no common support | global | insufficient evidence |

| Finish | Matched Cards | Pull-Covered Matches | Adjusted Premium | 95% CI | Status |
| --- | ---: | ---: | ---: | ---: | --- |
| All finishes | unavailable | below gate | unavailable | unavailable | insufficient pull-scarcity coverage |

## Common support, era stability, and robustness

The intersection of treatment p10–p90 log-odds ranges was empty, so the common-support cohort had zero rows. One set and one era cannot support leave-set-out or era-heterogeneity inference. Consequently temporal, popularity-outlier, artist, permutation, and alternate-popularity stability cannot collectively pass. Reporting coefficients in this state would turn extrapolation into false precision.

## Database publication and production integration

Run ID: none. Rows persisted: zero. The migration defines service-role-only research and score tables plus a latest-approved, security-invoker read view. It was not applied because the Supabase CLI/database DDL channel is unavailable in this environment. Card Detail now has additive `treatmentV1` and `treatmentPrestige` semantics; Treatment Prestige fails closed as “researching/unavailable.” Legacy Card Appeal remains V1 and is unchanged. Canonical RIP and rankings are untouched.

## Card Detail tooltip

It begins: “How much extra value does the market give a card just because of its treatment, once we remove the effects of Pokémon popularity and rarity/pull odds?” Until an approved run exists, it explains that approved scarcity-adjusted evidence has not been published.

## Remaining limitations

The live snapshot payload query repeatedly exceeded the database statement timeout. The exact-variant pipeline covers too little set diversity, and no supported treatment pair had usable shared scarcity support in the completed audit. A later run needs healthy snapshot access, broader exact-variant recalculation across supported sets, Study B matched pairs, and every preregistered sensitivity before approval.
