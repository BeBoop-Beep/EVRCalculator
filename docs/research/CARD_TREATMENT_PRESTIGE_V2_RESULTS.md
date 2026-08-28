# Card Treatment Prestige V2 — Frozen-Cohort Round 4 Results

## Decision

`DO_NOT_APPROVE_CARD_TREATMENT_PRESTIGE_V2`

The corrected scientific status is `V2_LOCAL_COMMON_SUPPORT_EXISTS`. Common support is a prerequisite for estimation, not proof that a coefficient is identified or robust. No V2 score, database study row, production contract, or frontend change is approved.

## Frozen cohort and reconciliation

Study `card-treatment-b2-r4-7baa40c8c8fb299b` froze 22 supported sets and their exact authoritative calculation-run IDs. Its manifest hash is `7baa40c8c8fb299b2251d2c2ec0363e137b5eab959beeaae7891723871cc4cdd`; the canonical mapping hash is `7e0e9e2719aba8491fa777a1229cff52f23310e7fc49ca59f4a29e42fed29835`.

The frozen authority contains 7,619 exact variant rows. Of these, 7,597 join to canonical cards and 22 fail (0.289%), below the locked 5% gate. The remaining failures are classified as canonical-ID drift or missing canonical cards.

The earlier approximately 826-row live failure was not one stable broken cohort. Exact-run publication was advancing during the live audit, and the research bulk loader omitted valid direct identity paths. Two retained failed freeze attempts exposed those omissions. Direct variant/card reconciliation repaired the loader; it did not mutate production data or rewrite failed snapshots.

## Locked local contrasts

All 15 preregistered era-scoped rarity contrasts are accounted for. One Mega Evolution contrast fails the frozen common-support gate. The other 14 enter local estimation.

The model is `log(price)` on a pair indicator, exact log pull odds, set fixed effects, species fixed effects, and mechanic controls, restricted to the pair's empirical overlap. Inference uses 1,000 Rademacher wild-bootstrap draws clustered by set. Robustness covers nonlinear scarcity strata, mechanics exclusion, high-demand-species exclusion, leave-one-set-out, overlap balancing, and 199 within-set/scarcity-stratum permutations.

No contrast passes the complete robustness gate. Thirteen estimated contrasts are locally uncertain, chiefly because fixed-effect or leave-one-set-out designs become rank deficient; one contrast is support-failed. The apparent Scarlet & Violet Common→Rare association is about +51.8% (log coefficient 0.417; wild-bootstrap log CI 0.244 to 0.606; permutation p=0.005), but four leave-one-set-out fits are non-estimable. It is therefore `LOCAL_EFFECT_UNCERTAIN`, not `LOCALLY_VALIDATED`.

## Interpretation and scope

The data demonstrate local overlap, not a universal treatment hierarchy. Results apply only inside each era, pair, and frozen scarcity interval. Graph paths do not authorize transitive comparisons. Matched-card candidates are diagnostic only because treatment assignment is not random or plausibly exogenous.

V1 Card Appeal, RIP calculations, rankings, historical snapshots, and Card Detail remain unchanged. V3 was not entered. The next defensible task is additional local-identification data or a redesigned estimand, followed by a new preregistered study—not product promotion.

## Round 5 identification diagnosis

Round 5 preserves every Round 4 result and uses only its immutable cohort. Thirteen full matrices were rank deficient, but the causes differ: five contain redundant nuisance fixed-effect/mechanic columns while retaining an estimable treatment indicator; eight lose treatment variation through genuine set/species/mechanic nesting. The Common–Rare matrix remains full rank. Thus the Round 4 full-rank gate was appropriately conservative, but “rank deficient” was not a sufficiently precise scientific diagnosis.

All three high-product-relevance contrasts remain scientifically confounded. Mega Double Rare–Illustration Rare has two cross-treatment species, no same-species×set cells, and loses identification with set FE. S&V Illustration Rare–Special Illustration Rare has five cross-treatment species, no same-species×set cells, and zero comparable-mechanic species. S&V Illustration Rare–Ultra Rare has 29 cross-treatment species and four mixed species×set cells, but zero comparable-mechanic species; mechanics eliminate its remaining treatment variation.

The independent `pokemon_desirability_composite_v1` signal is based on Favorite Pokémon fan popularity and Google Trends rather than card prices or rarity. It is a plausible future demand control, but no contemporaneous snapshot was frozen in the Round 4 manifest. Current values cannot be mixed into the immutable study. Consequently V2B is ineligible and no V2B coefficient is calculated.

Primary status: `V2_ORIGINAL_ESTIMAND_REMAINS_PLAUSIBLY_IDENTIFIABLE_WITH_NEW_VARIATION`. Future releases could add the required cross-designation observations for the same Pokémon, inside common scarcity support and preferably within the same set and comparable mechanic class. Repeating rows in existing nested cells will not identify the effect. Production status remains `DO_NOT_APPROVE_CARD_TREATMENT_PRESTIGE_V2`; score and database writes remain zero.

## Round 6 valid local estimates

Round 6 reparameterized only redundant nuisance columns and fit the six treatment-estimable original-V2 contrasts. Two pass the complete robustness and Holm multiplicity gates:

* S&V Common→Rare: log coefficient 0.4174, conditional association +51.8%, 1,000-draw wild-cluster log interval 0.2523 to 0.6014, Holm-adjusted permutation p=0.03.
* S&V Rare→Uncommon: log coefficient -0.2635, meaning Uncommon is conditionally associated with 23.2% lower price than Rare, interval -0.3119 to -0.2160, Holm-adjusted p=0.03.

Mega Common–Rare, Mega Common–Uncommon, Mega Rare–Uncommon, and S&V Common–Uncommon remain uncertain because inference, functional-form, leave-one-set-out, or multiplicity evidence is incomplete or unstable. These are observational adjusted associations only within the frozen pair-specific exact-pull-scarcity overlap populations.

The scientific answer is `LOCAL_RARITY_DESIGNATION_EFFECTS_VALIDATED`: designation carries a measurable adjusted association in some Common/Rare/Uncommon comparisons. This does not establish an upper-tier rarity effect or universal hierarchy. Mega Double Rare–IR, S&V IR–SIR, and S&V IR–Ultra Rare remain scientifically unidentified and receive no Round 6 coefficient.

The independent-demand snapshot is frozen for future V2B research but is not used here. Universal status remains `DO_NOT_APPROVE_CARD_TREATMENT_PRESTIGE_V2`; production rows and behavior remain unchanged. The next direction is to preserve the local evidence without creating a product score, then separately decide whether to wait for new upper-tier identifying variation or begin V3 research.
