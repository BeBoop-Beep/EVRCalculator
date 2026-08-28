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
