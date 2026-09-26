# Financial RIP V5 (Shortfall Resilience) - final production adjudication

## 1. Executive verdict

`FINANCIAL_RIP_V5_SHORTFALL_DEPTH_PRODUCTION_PROMOTION_APPROVED`

The exact frozen candidate is approved as a one-for-one replacement of Loss Resilience inside Financial RIP. Formula, weights and the other five components are unchanged. This is decision only: nothing was implemented, published, migrated or written to production.

The approval rests on **construct validity and absence of pathology**, not on a demonstrated empirical ranking improvement. The real evidence shows V5 is a small, stable, well-behaved correction (Financial rank Spearman 0.9976 vs V4). It does not show V5 uncovering large hidden ranking errors. That is stated plainly so Prompt 5 does not oversell it.

## 2. Evidence authority

- `develop` at `4860b437`; no commits since; V5 research and scoring files unchanged. Unrelated concurrent working-tree edits (eBay collector, Market Explorer) were left alone.
- Read in full: `financial_rip_v5_candidate.py`, shadow freeze, real-artifact validation (md + json), Best-Open live validation md, runtime remediation md. The Prompt 2 JSON per-product rows were queried directly. The blocked 2026-09-19 artifacts were treated as superseded history.
- One analysis was done here, read-only, from the Prompt 2 JSON rows (2026-09-14 and 2026-08-22 states): the redundancy of the *old* Loss Resilience against Typical Retention (section 5). It was not previously reported and is decision-critical.

## 3. Structural result (Gates 1 and 2)

PASS. Frozen formula `SR = 100*(1 - 0.70*E[(1-R)+] - 0.60*E[(0.50-R)+])`, direct-vs-prepared parity at 1e-10, V4 isolation, five unchanged components identical, score reconstructs from 25/20/15/25/10/5, SR bounded [0,100] analytically, 15 focused tests passing. Zero dominance violations at P(win) 0.30/0.50/0.70/0.90 for both the component and the six-pillar score. The three repaired constructions (distinct hard/soft-loss vectors, matched EV and P50, controlled P95 sweep) are valid and closed. Nothing in the repository contradicts these reports.

SR is an expectation of a non-increasing convex loss in R, so it respects first-order stochastic dominance: making any outcome better can never lower it. Old Loss Resilience conditions on losing runs only and lacks that guarantee. This holds at every P(win), including the low range where the real domain lives.

## 4. Real-product result (Gate 3)

138 products, 22 exact 1M-outcome runs, snapshot `0e65fb6d`. Every V4 score and rank reproduced; five components identical.

- V4/V5 Pearson 0.9957, Spearman 0.9976, Kendall 0.9664. Mean correction +2.33 (P10 1.64, P90 3.10).
- Rank movement mean 1.94; unchanged 38, 1-2 places 57, 3-5 places 33, >5 places 10 (max 10). Overlap top-5 5/5, top-10 8/10, top-20 19/20.
- The correction is `0.15 * (SR - old LR)`; movement is economically legible. Products with shallow downside (Pitch Black PC ETB: SR 73.09 vs LR 72.77) gain almost nothing. Products where old LR under-credited depth (Ascended Heroes PC ETB: LR 32.86, SR 54.74, 5.6% P(win)) gain about 3.3.
- The Stellar Crown / Surging Sparks ETB pair (Typical 33.15 / 34.00, P(win) 0.00% / 0.006%, similar cost, SR 36.83 / 40.52, EV $352.65 / $390.97) is a genuine case of SR separating downside depth where the median does not.

## 5. Redundancy assessment (the decisive question)

Observed: SR vs Typical Retention Pearson 0.9789 (Spearman 0.9822), set-balanced 0.9715, 0.955-0.996 by family, 0.9915 pooled across 1.2M Best-Open price states. SR vs BEE 0.938 / 0.949. SR vs P(win) about 0.03-0.28.

Findings that change the reading of those numbers:

1. **Old Loss Resilience is also highly redundant.** Computed here from the Prompt 2 rows: LR vs Typical Pearson 0.921 (Spearman 0.950) on 2026-09-14, 0.924 on 2026-08-22; LR vs BEE 0.934 / 0.936, versus SR vs BEE 0.938 / 0.932. High overlap of downside-flavoured pillars with each other is a property of the six-pillar layout in this domain, not something V5 introduces. V5 does not add a redundant pillar; it swaps one already-correlated pillar for a cleaner one. The relevant comparison is V5 vs V4, not V5 vs an orthogonal ideal.
2. **SR is less idiosyncratic than LR, and this is the honest cost.** Residual SD after regressing on Typical: LR 5.4-5.5 points, SR 2.4 points. At 15% weight, SR's independent contribution to the Financial score is about 0.36 points of SD, versus 0.82 for LR. That is why V4 and V5 rank almost identically.
3. **Not all of LR's extra variance is signal.** LR conditions on losing runs only, so part of its residual is the conditioning artifact that constitutes the proven defect (P(win) is not correlated with either LR or SR, so that is not the driver). Lower SR residual is partly the removal of that artifact. This cannot be split precisely with the current data. It is the same reason redundancy alone cannot condemn the swap.
4. **The 0.9915 price-domain figure overstates redundancy.** It pools 1.2M price states from 138 products; states of the same product share one distribution and differ mostly by cost scale, which moves Typical and SR together. The state count is not an independent sample. It confirms that within a product's price sweep the two co-move (expected). It is weaker evidence about cross-product distinctness than the 138-product 0.979.
5. Same-family discordant pairs exist (section 4), and a mathematically separable construct exists, so SR is not degenerate.

Judgment: SR is a distinct construct (expected shortfall depth incl. deep tail) that is strongly correlated with median retention in Pokemon because downside shape in this domain is near-scale-uniform. In practice it adds modest independent information. But the 15% slot is already occupied by a component that is nearly as redundant and demonstrably defective. Whether ~15% of the Financial score should carry downside-depth information at all was settled by the earlier six-pillar audit (architecture broadly supported); this gate does not reopen it. Independent-variance smallness is a reason not to expect large ranking gains, not a reason to keep a component with a known monotonicity defect.

## 6. Temporal result (Gate 4)

Seven exact replayable states, 2026-08-22 to 2026-09-14 (08-21 correctly excluded, no exact source row). V4/V5 Pearson 0.9955-0.9964, Spearman 0.9976-0.9983, mean correction +2.31 to +2.37, SR/Typical 0.9767-0.9789. Median score variance V4 0.1837, V5 0.1870; median variance of the correction 0.00117. The largest movers (Obsidian Flames PC ETB: quantity 1 to 2, correction 2.4 to 0) are explained by allocation and cost regime changes. No evidence contradicts stability; no temporal blocker.

## 7. Best-Open result (Gate 5)

138/138 products, four authorities, 552/552 exact thresholds (winning cent wins, adjacent cent loses), 0 unresolved searches, 0 monotonicity fallbacks. Each axis used its own benchmark. Runtime remediation preserved search semantics (126 tests passing; 1.96x speedup on the high-quantity case; thresholds matched retained evidence).

- Financial: mean -242 c, median -139 c, within +/-5% for 98.6%, >5% for 1.4%, >10% for 0%. Benchmark changes 0, leader changes 0, quantity changes 81.
- Overall shadow: mean -264 c, within +/-5% for 97.8%, >10% 0%. 0 benchmark and leader changes. Maximum residual from the fixed 86% propagation 0.000096 points, so no hidden Chase/Collector interaction.
- Threshold direction is mechanical: V5 lifts nearly every score by about 2.3, so the benchmark score rises and most thresholds fall. Largest absolute drops are expensive PC ETBs whose old LR was already about equal to SR (local score gain 0.04-0.2 against a benchmark gain near 3). That is a relative-position effect that follows from the correction being small for shallow-downside products, not an instability.
- Pathology: 1,195,080 same-quantity adjacent-cent transitions, 0 V5 inversions, 0 V4 inversions; largest same-quantity step +0.336; the largest overall step (-9.40) is a 6 to 7 pack allocation boundary (+$185.65 committed), present in V4 too (-8.09). Not an SR cliff.

## 8. High-win limitation (Interpretation A vs B)

Fact: 0 of 1,200,199 real candidate-price states and 0 products reach P(win) 30% (29 states at 20-30%, one product). Current-market maximum P(win) is 15.9%. The V4 high-win plateau and SR's continued sensitivity there are **proven only synthetically, not observed on real Pokemon trajectories**. This adjudication does not claim otherwise.

Adjudication: **Interpretation A, with the reason made explicit.** High P(win) is not merely unsampled: Best-Open thresholds are by construction located where the product first wins the ranking, and the cohort's P(win) lives below 20%. The high-win region is outside the operating domain of both rankings and thresholds today, so V5's plateau advantage neither helps nor is required now. Interpretation B would be right only if the high-win benefit were V5's sole justification. It is not: the FOSD/monotonicity property and removal of the loss-only conditioning defect hold at every P(win), and V5 shows no pathology at the P(win) values that do occur. The high-win benefit is a bounded-risk hedge for a future regime (cheaper products, new formats), not the basis of this decision. Requiring live >=50% observations would demand evidence from a regime the product universe does not currently reach.

## 9. Evidence table

| Question | Evidence for promotion | Evidence against promotion | Adjudication |
|---|---|---|---|
| Structural correctness | Frozen formula, parity 1e-10, V4 isolation, 5 components identical, bounds, 15 tests | None found | Pass |
| Dominance behavior | 0 violations at 0.3/0.5/0.7/0.9 (component and six-pillar); FOSD-respecting by construction | Proven synthetically only | Pass; property holds everywhere |
| Distinctness from Typical Retention | Same-family discordant pairs (ETB pair); mathematically separable | Pearson 0.979 current, 0.9915 pooled; residual SD only 2.4 | Weak-to-moderate independent info; but old LR is 0.92 redundant too, so not a differentiator against V4 |
| Distinctness from BEE | SR/BEE 0.938 equals LR/BEE 0.934 | 0.949 Pearson across price states | No change vs V4 |
| Current rank behavior | Tau 0.966; legible movers; top-5 5/5 | 10 products move >5 places; top-10 8/10 | Real but modest; acceptable |
| Temporal stability | 7 states, Pearson 0.9955-0.9964, delta variance 0.00117 | 08-21 unreplayable (excluded, not substituted) | Stable |
| Best-Open impact | 552/552 exact; 98.6% within 5%; 0 benchmark/leader changes; Overall propagation exact | Absolute cent shifts large for expensive PC ETBs; 81/85 quantity changes | Acceptable; mechanically explained |
| High-win evidence | Synthetic proof of plateau escape | 0 real states >=30%; benefit unobserved | Not required for current domain; not claimed as validated |
| Pathology / monotonicity | 0 same-quantity inversions in 1.195M transitions; no cliffs | Quantity-boundary steps (shared with V4) | Pass |
| Production interpretability | Internal component; no public vocabulary change | Downside pillar now reads as less distinct from Typical | Pass |

## 10. Production interpretation

Two questions were kept separate. (A) Old Loss Resilience is defective: yes. (B) Exact-frozen SR at 15% earns promotion: yes, because it removes a proven monotonicity defect, is at least as well behaved as V4 on every real and price-domain check, and its higher redundancy with Typical is a small (about 0.5 point of SD) reduction in an already redundant slot. Weighing cost: promotion carries a real model-version cutover (new Overall lineage, snapshots, historical comparability), and the observable ranking gain is small. That cost is justified because the alternative is keeping a known-defective component whose failure will surface as the product universe or price regime moves, and the cutover is contained to one component with a verified 86% propagation. If future work wants a lower SR weight or a Typical/SR rebalance, that is a separate research cycle and is not decided here.

## 11. Final decision

`FINANCIAL_RIP_V5_SHORTFALL_DEPTH_PRODUCTION_PROMOTION_APPROVED`

Approved exactly as frozen:

- Formula: `SR = 100*(1 - 0.70*E[(1-R)+] - 0.60*E[(0.50-R)+])`, `R = X/C` (equivalently 100*(0.70*CappedRecovery + 0.30*DepthResilience)).
- Component key `shortfall_resilience`, replacing `loss_resilience`.
- Weights 25/20/15/25/10/5; the other five components identical to V4.
- Exact raw artifact or prepared distribution required; payload-only projection stays unavailable.

Why the following do not block: (1) ~0.98-0.99 SR/Typical correlation - old LR is 0.92 redundant, the swap does not add a new redundant pillar, and price-state correlation is inflated by non-independent states; (2) no real >=30/50% P(win) - outside the operating domain of both cohort and thresholds, and not V5's sole justification; (3) ranking/Best-Open movement - small, stable, mechanically explained, zero benchmark or leader changes; (4) construct validity - FOSD monotonicity and no loss-only conditioning.

## 12. Next action

Stop here. Implementation is a separate Prompt 5. It must not mutate Financial V4, Overall V12 or Overall V13 identity, and should version at least:

- new Financial version/config constants and weights (V5), with the V4 scorer retained;
- a new Overall lineage using Financial V5 at the fixed 86% weight;
- ranking/publication snapshot method identities and fingerprints (`budget_product_ranking_v1` and successors);
- Best-Open method identity (v2 dual-authority) and threshold artifacts;
- per-set/product simulation snapshot payloads and any frontend/API contract fields naming Loss Resilience, with the raw shortfall inputs persisted so V5 is reconstructable;
- stored-version checks, staleness/config fingerprints, and rebuild/backfill plan;
- historical comparability tooling and cutover/rollback, plus regression tests and live QA before any pointer flip.

Standing caveat for Prompt 5: post-cutover, monitor whether real P(win) ever enters the >=30% region and whether SR/Typical redundancy drifts, as a monitoring item and not a gate.
