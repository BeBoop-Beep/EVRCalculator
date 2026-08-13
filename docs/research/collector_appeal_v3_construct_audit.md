# Collector Appeal V3 — Construct Audit

**Status:** research only. No production model, formula, weight, threshold, or data row was changed. Nothing was republished, redeployed, or re-simulated.

**Date:** 2026-08-12
**Cohort:** the 22 currently-scored public Collector Appeal sets
**Model under audit:** `collector_appeal_v3_balanced_d40_h35_p25` — `CA = 0.40·D + 0.35·H + 0.25·P`

**Artifacts**
- Script: `backend/scripts/audit_collector_appeal_v3_construct.py` (read-only)
- Table: `docs/research/collector_appeal_tables/collector_appeal_v3_decomposition.csv`
- Upstream input: `backend/scripts/audit_collector_appeal_v2.py --json` (existing, unmodified)

---

## 1. Executive summary

**The observation that motivated this audit is mostly not reproducible against current authoritative data.** Three of the four cited inversions do not exist:

| Claim | Reality (current data) |
|---|---|
| Mega Evolution above Scarlet & Violet 151 | **True** — ranks 4 and 5 |
| Pitch Black above Ascended Heroes | **False** — Pitch Black is 6th, Ascended Heroes 3rd |
| Perfect Order above Ascended Heroes | **False** — Perfect Order is 7th |
| Journey Together above Ascended Heroes | **False** — Journey Together is 8th |

Ascended Heroes ranks **3rd of 22** under V3, behind only Prismatic Evolutions and Phantasmal Flames, and it beats each of the three sets it was said to lose to by +1.81, +2.53 and +3.29 public points. The same ordering holds under the superseded V2. Whatever surface produced the original observation was not showing current canonical V3.

Beyond that, five findings stand on their own:

1. **V3 arithmetic is exactly correct.** The three weighted contributions reconstruct every set's score to ~1e-16.
2. **No data or mapping defect was found.** D recovery cross-validates against an independent stored table at 21/21; covered demand share is 1.0 for all 22 scored sets; a spot-trace of Ascended Heroes' Gengar shows all three printings correctly mapped across two slot groups and all three flagged dual-path eligible.
3. **Nominal weights badly understate P.** By dispersion of weighted contribution, influence is D 47.5% / H 26.4% / **P 26.1%** — P at a 0.25 coefficient has essentially the *same* practical leverage as H at 0.35, because P varies more across the cohort.
4. **P is largely a restatement of product rarity architecture.** Spearman(P, cards-per-desirable-subject) = **+0.825**. P is also *negatively* correlated with roster size (Spearman −0.412) while D is strongly positively correlated with it (+0.763) — so D and P structurally fight each other via roster size. This is the whole explanation for Ascended Heroes' profile, and it is not a bug.
5. **The metric measures opening experience, not collector demand.** The product name "Collector Appeal" communicates Interpretation A; the implementation is Interpretation B.

**Recommendation: keep V3 unchanged for now.** The motivating concern was largely a false premise, and no defect was found. The real findings are a naming/scoping problem and a P-vs-roster-size interaction, neither of which is fixed by reweighting.

---

## 2. Current V3 definition

```
CA = 0.40·D + 0.35·H + 0.25·P        (unit scale; public = 100 × unit)
```

- **D — Roster Desirability.** How desirable the roster is before pull difficulty.
- **H — Desirable Outcome Frequency.** `P(pack contains ≥1 card tied to an eligible desirable subject)`. Slot-aware union. Desirability sets *eligibility* only; magnitude is deliberately not multiplied in, because it already enters once through D.
- **P — Dual-Path Depth.** Demand-share-weighted degree to which desirable subjects offer both an attainable printing and an elite chase.

Weights are pre-registered module constants with an AST test forbidding any search loop over them. Protected weights are not exposed on public surfaces; this document references the existing source constants as permitted.

**How D was obtained.** The V2 audit emits H, P and legacy CA7 but leaves `d` null. D was recovered by inverting the CA7 identity `CA7 = D + 0.50·P·(1−D)` — exact algebra on a stored number, not a re-derivation. Verified two ways: round-trip through the canonical `compute_collector_appeal_ca7` (tolerance 5e-6, all pass), and cross-validation against `dual_path_set_rankings.csv` (**21 matched, 0 differed**). All scores come from the canonical `compute_collector_appeal_v3`; this audit contains no second implementation of the formula.

---

## 3. Current 22-set decomposition

| # | Set | CA | D | rk | H | rk | P | rk | 0.40D | 0.35H | 0.25P | subj | cards |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Prismatic Evolutions | 54.26 | 0.9328 | 4 | 0.1995 | 7 | 0.3988 | 3 | 0.3731 | 0.0698 | 0.0997 | 19 | 38 |
| 2 | Phantasmal Flames | 54.08 | 0.9074 | 5 | 0.2427 | 2 | 0.3714 | 5 | 0.3630 | 0.0849 | 0.0928 | 14 | 24 |
| 3 | **Ascended Heroes** | 53.16 | **0.9548** | **1** | 0.2338 | 3 | 0.2714 | 15 | 0.3819 | 0.0818 | 0.0679 | 44 | 70 |
| 4 | Mega Evolution | 52.71 | 0.8720 | 12 | 0.1904 | 8 | 0.4466 | 2 | 0.3488 | 0.0666 | 0.1117 | 15 | 28 |
| 5 | Scarlet and Violet 151 | 51.94 | 0.9361 | 3 | 0.2072 | 6 | 0.2896 | 14 | 0.3745 | 0.0725 | 0.0724 | 21 | 35 |
| 6 | Pitch Black | 51.35 | 0.7990 | 19 | 0.2323 | 4 | **0.4502** | **1** | 0.3196 | 0.0813 | 0.1125 | 11 | 22 |
| 7 | Perfect Order | 50.63 | 0.8160 | 17 | **0.2659** | **1** | 0.3471 | 7 | 0.3264 | 0.0931 | 0.0868 | 13 | 25 |
| 8 | Journey Together | 49.87 | 0.8746 | 9 | 0.2117 | 5 | 0.2990 | 11 | 0.3498 | 0.0741 | 0.0748 | 18 | 27 |
| 9 | Paldean Fates | 49.37 | 0.9533 | 2 | 0.1791 | 10 | 0.1988 | 20 | 0.3813 | 0.0627 | 0.0497 | 46 | 52 |
| 10 | Surging Sparks | 48.94 | 0.8885 | 7 | 0.1244 | 15 | 0.3619 | 6 | 0.3554 | 0.0435 | 0.0905 | 15 | 28 |
| 11 | Destined Rivals | 48.13 | 0.8793 | 8 | 0.1410 | 11 | 0.3211 | 10 | 0.3517 | 0.0494 | 0.0803 | 18 | 31 |
| 12 | Paradox Rift | 46.96 | 0.8665 | 13 | 0.1384 | 13 | 0.2983 | 12 | 0.3466 | 0.0484 | 0.0746 | 21 | 37 |
| 13 | Twilight Masquerade | 45.46 | 0.8118 | 18 | 0.1384 | 12 | 0.3256 | 9 | 0.3247 | 0.0484 | 0.0814 | 12 | 28 |
| 14 | Temporal Forces | 45.03 | 0.8603 | 15 | 0.0960 | 19 | 0.2902 | 13 | 0.3441 | 0.0336 | 0.0725 | 15 | 19 |
| 15 | Stellar Crown | 44.80 | 0.8635 | 14 | 0.1081 | 16 | 0.2592 | 16 | 0.3454 | 0.0378 | 0.0648 | 11 | 15 |
| 16 | Obsidian Flames | 44.74 | 0.8732 | 10 | 0.1029 | 17 | 0.2484 | 17 | 0.3493 | 0.0360 | 0.0621 | 12 | 17 |
| 17 | Paldea Evolved | 44.65 | 0.9037 | 6 | 0.0933 | 20 | 0.2094 | 19 | 0.3615 | 0.0327 | 0.0524 | 19 | 27 |
| 18 | Chaos Rising | 43.57 | 0.6989 | 21 | 0.1803 | 9 | 0.3719 | 4 | 0.2796 | 0.0631 | 0.0930 | 10 | 18 |
| 19 | Scarlet and Violet Base Set | 42.19 | 0.7560 | 20 | 0.1029 | 18 | 0.3340 | 8 | 0.3024 | 0.0360 | 0.0835 | 10 | 17 |
| 20 | White Flare | 41.45 | 0.8730 | 11 | 0.0900 | 21 | 0.1351 | 22 | 0.3492 | 0.0315 | 0.0338 | 24 | 31 |
| 21 | Black Bolt | 41.40 | 0.8401 | 16 | 0.1254 | 14 | 0.1362 | 21 | 0.3361 | 0.0439 | 0.0341 | 19 | 30 |
| 22 | Shrouded Fable | 27.24 | 0.5107 | 22 | 0.0278 | 22 | 0.2337 | 18 | 0.2043 | 0.0097 | 0.0584 | 5 | 5 |

Covered demand share is 1.0 for every row above. **Cohort coverage caveat:** 34 sets were considered and only 22 scored — 11 lack a pull model entirely (Sword & Shield through Silver Tempest, i.e. essentially all of SWSH). Those are correctly returned as unavailable rather than zero, but it means the public cohort is Scarlet & Violet forward.

---

## 4. Ascended Heroes case study

**Ascended Heroes ranks 3rd, not below the sets in the brief.** Pairwise, with contributions on the unit scale (reconstruction error ≤ 5.6e-17 in every row — the three deltas sum to the score gap exactly):

| vs | ΔCA (public) | ΔD contrib | ΔH contrib | ΔP contrib |
|---|---|---|---|---|
| Mega Evolution | **+0.45** | +0.0331 | +0.0152 | −0.0438 |
| Scarlet and Violet 151 | **+1.22** | +0.0075 | +0.0093 | −0.0046 |
| Pitch Black | **+1.81** | +0.0623 | +0.0005 | −0.0447 |
| Perfect Order | **+2.53** | +0.0555 | −0.0112 | −0.0189 |
| Journey Together | **+3.29** | +0.0321 | +0.0077 | −0.0069 |

The consistent shape: Ascended Heroes wins on D in every pairing, wins or draws on H in four of five, and **loses on P in all five**. It is 3rd rather than 1st because its P deficit (rank 15) eats part of its D lead (rank 1) — but never all of it.

### Input integrity — is the low P genuine?

Yes, and it is structural rather than a defect.

Ascended Heroes has **44 eligible desirable subjects and 70 eligible cards** — the largest desirable roster in the cohort bar Paldean Fates. That is *why* D is 0.9548 (rank 1). But P is a demand-share-weighted **per-subject average**, i.e. an intensive quantity. Ascended Heroes offers 1.59 eligible cards per desirable subject; the top-P sets offer close to 2.00:

| Set | subjects | cards | cards/subject | P | P rank |
|---|---|---|---|---|---|
| Pitch Black | 11 | 22 | 2.00 | 0.4502 | 1 |
| Mega Evolution | 15 | 28 | 1.87 | 0.4466 | 2 |
| Prismatic Evolutions | 19 | 38 | 2.00 | 0.3988 | 3 |
| **Ascended Heroes** | **44** | **70** | **1.59** | **0.2714** | **15** |
| Paldean Fates | 46 | 52 | 1.13 | 0.1988 | 20 |
| White Flare | 24 | 31 | 1.29 | 0.1351 | 22 |

Across the cohort, **Spearman(cards-per-subject, P) = +0.825**. A wide roster necessarily spreads demand share across many subjects, most of which get a single printing, so P falls. Ascended Heroes is not being penalised by a mapping error; it is being measured by a metric that rewards *concentration*.

**Spot-check of the mapping itself.** `ascended_heroes_anchor_card_trace.csv` shows Gengar with three distinct printings correctly attached to one canonical subject:

| card | number | rarity | slot group | pull prob | dual-path eligible |
|---|---|---|---|---|---|
| Mega Gengar ex | 125 | Double Rare | Rare slot model | 1-in-191 | yes |
| Mega Gengar ex | 269 | MEGA_ATTACK_RARE | Rare slot model | 1-in-202 | yes |
| Mega Gengar ex | 284 | Special Illustration Rare | Reverse slot model | 1-in-1,533 | yes |

Multiple legitimate variants are neither collapsed nor omitted; accessible and elite paths are both present; slot groups are distinct; probabilities are sane. No defect found. This is a spot-check, not an exhaustive per-subject audit of all 44 subjects — see §15.

---

## 5. Mega Evolution vs Scarlet & Violet 151

This is the one real inversion, and it is entirely a P effect.

| | D | H | P | 0.40D | 0.35H | 0.25P | CA |
|---|---|---|---|---|---|---|---|
| Mega Evolution | 0.8720 | 0.1904 | 0.4466 | 0.3488 | 0.0666 | **0.1117** | 52.71 |
| Scarlet & Violet 151 | 0.9361 | 0.2072 | 0.2896 | 0.3745 | 0.0725 | 0.0724 | 51.94 |
| **Δ (ME − 151)** | −0.0641 | −0.0168 | **+0.1570** | **−0.0257** | **−0.0059** | **+0.0393** | **+0.77** |

Mega Evolution **loses on both D and H** — a combined −3.16 public points — and wins purely because its P advantage is worth +3.93. A single pillar with a 0.25 nominal coefficient overturns the other two combined. This is the clearest demonstration in the cohort that the nominal weights do not describe the real influence.

Whether this is *wrong* depends entirely on the construct. Under Interpretation B (opening experience) it is defensible: Mega Evolution genuinely gives more of its desirable characters both a reachable and a chase printing. Under Interpretation A (collector demand) it is indefensible: 151 has the more desirable roster and should win.

---

## 6–7. Pitch Black and Perfect Order

Neither beats Ascended Heroes. Both are interesting for *why they rank as highly as they do* on weak rosters.

**Pitch Black** (rank 6) has **D rank 19** — nearly the worst roster in the cohort — and reaches 6th on the strength of **P rank 1** (0.4502) and H rank 4. Only 11 subjects across 22 cards, i.e. an almost perfect 2.00 printings per subject. It is the purest case of rarity architecture substituting for roster quality: it beats White Flare by +9.90 points with ΔP contribution +0.0788 despite a worse roster, and beats Paldean Fates (D rank 2) by +1.98 with ΔD = −0.1543.

**Perfect Order** (rank 7) is the H analogue: **H rank 1** (0.2659, the cohort maximum) on a D rank of 17. It accounts for six of the top H-driven inversions, beating White Flare (+9.18), Paldea Evolved (+5.98), Obsidian Flames (+5.89), Stellar Crown (+5.82), Temporal Forces (+5.60) and Surging Sparks (+1.69) — every one of them a set with a better roster.

**Journey Together** (rank 8) needs no special explanation: it is middling on all three pillars (D 9, H 5, P 11) and lands where the arithmetic puts it.

---

## 8. H analysis — Desirable Outcome Frequency

| statistic | value |
|---|---|
| range | 0.0278 – 0.2659 (**9.57×**) |
| mean / SD | 0.1560 / 0.0619 |
| Pearson(H, CA) | **+0.831** |
| Spearman(H, CA) | **+0.832** |
| Pearson(H, D) | +0.431 |
| Spearman(H, D) | **+0.303** |
| H-driven inversions | 18 |

Two things matter here.

**H is not a restatement of D.** Spearman(H, D) = 0.303 is weak. H carries genuinely independent information, which is the main thing V2 was reweighted to let through.

**H is the single best predictor of V3's ordering** — Spearman 0.832, versus 0.589 for D and 0.563 for P. A metric whose nominal top weight is D produces an ordering that tracks H more closely than D. That is a direct consequence of D's compression: 19 of 22 sets sit between D = 0.79 and D = 0.96, so D's *rank* ordering is fragile even though its *dispersion* is the largest.

**The binary-eligibility consequence is real and measurable.** The brief asked whether many easy cards on moderately desirable Pokémon can beat few cards on extremely desirable ones. They can: Perfect Order (D rank 17) outranks six better-rostered sets purely on H, by up to +9.18 points. Because desirability magnitude is dropped after the eligibility threshold, a card attached to a marginally-qualifying subject contributes to H exactly as much as a Charizard does.

**The tradeoff, stated fairly.** Weighting H by desirability magnitude would apply the same signal twice — once in D, once inside H — and the second application would be invisible in the formula. The current binary design is the *correct* choice for avoiding double-counting. Its cost is that H answers "how often does *something you'd want* show up" rather than "how often does something you'd want *badly* show up." That is a defensible construct, not a bug. It becomes a problem only if the product name promises the second thing.

---

## 9. P analysis — Dual-Path Depth

| statistic | value |
|---|---|
| range | 0.1351 – 0.4502 (**3.33×**) |
| mean / SD | 0.2999 / 0.0858 |
| Pearson(P, CA) | +0.526 |
| Spearman(P, CA) | +0.563 |
| Pearson(P, D) | **−0.038** |
| Spearman(P, D) | **−0.173** |
| Spearman(P, cards-per-subject) | **+0.825** |
| Spearman(P, subject count) | **−0.412** |
| P-driven inversions | **49** |

**P is functioning substantially as a product-architecture metric.** Spearman(P, cards-per-desirable-subject) = +0.825 means P is close to a monotone transform of "how many printings does this set give each desirable character." That is a fact about how the product was designed, not about collector quality.

**P is orthogonal-to-slightly-hostile to D.** Spearman(P, D) = −0.173, and the mechanism is roster size: subject count correlates +0.763 with D and −0.412 with P. The two pillars are pulling on the same underlying variable in opposite directions. Every large-roster set in the cohort — Ascended Heroes, Paldean Fates, White Flare, Paldea Evolved — sits in the bottom half of P.

**P produces more inversions than H** — 49 versus 18 — despite the lower coefficient. Single-printing subjects behave correctly (they contribute no dual-path credit), and demand-share weighting behaves correctly (the weighting is what makes P intensive). The math matches the intended construct. The issue is not that P is broken; it is that P's observed range (3.33×, SD 0.0858) gives it leverage its 0.25 coefficient does not advertise.

---

## 10. Effective influence / variance analysis

| pillar | nominal wt | raw SD | raw range | **contribution SD** | **share of contrib SD** | Pearson w/ CA | Spearman w/ CA |
|---|---|---|---|---|---|---|---|
| D | 0.40 | 0.0974 | 0.4441 | **0.0390** | **47.5%** | +0.790 | +0.589 |
| H | 0.35 | 0.0619 | 0.2381 | **0.0217** | **26.4%** | +0.831 | **+0.832** |
| P | 0.25 | 0.0858 | 0.3150 | **0.0214** | **26.1%** | +0.526 | +0.563 |

**The headline: 40/35/25 nominal is 47.5/26.4/26.1 effective, and H and P are practically indistinguishable in leverage.** P's larger raw dispersion (0.0858 vs H's 0.0619) almost exactly cancels its smaller coefficient. So the answer to "can a 25% coefficient matter more than expected" is yes — P behaves like a 35% pillar.

**H and P jointly (52.5%) outweigh D (47.5%).** The structural pillars together decide more of the score's spread than the roster does, even though the roster holds the largest single nominal weight.

**Pillar-alone orderings** (Spearman of V3's ranking against each pillar used alone):

| | Spearman vs CA | top-5 overlap with V3 |
|---|---|---|
| D only | 0.589 | 4 / 5 |
| H only | **0.832** | 2 / 5 |
| P only | 0.563 | 3 / 5 |

V3's top 5 is Ascended Heroes, Mega Evolution, Phantasmal Flames, Prismatic Evolutions, Scarlet & Violet 151 — of which D alone recovers 4. So D dominates the *top* of the table while H dominates the *ordering as a whole*. Both statements are true and they are not in conflict: D separates the elite tier, H sorts the middle.

---

## 11. Construct-definition analysis

**What does the current implementation measure?**

Unambiguously **Interpretation B — Collector Opening Appeal**: how appealing the experience of opening this set is. Two of its three pillars (H, P) are properties of pull structure, not of roster content, and together they carry 52.5% of the effective influence. Two of the top seven sets (Pitch Black at D rank 19, Perfect Order at D rank 17) rank there on pull structure alone.

Under **Interpretation A — Collector demand / set desirability**, the current output is wrong in specific, defensible-to-criticise ways: Mega Evolution should not beat 151, and Pitch Black should not be 6th.

**Does the name communicate the construct?** No. "Collector Appeal" reads as Interpretation A — a statement about the *content*. A user seeing Pitch Black at 6th and Paldean Fates at 9th will reasonably conclude the roster scoring is broken, when in fact the roster scoring put them at 19th and 2nd respectively and the pull structure moved them.

This naming hazard is already documented in the codebase: `collector_appeal.py` warns that the shipping `collector_appeal_score` column is Pure/Universal Desirability — *a different construct that happens to share the product name*. There are now at least two distinct constructs circulating under one label. **That is the most likely explanation for the original observation in the brief**, and it is worth running down independently of anything in this audit.

---

## 12. Possible metric separation

| Metric | Construct | Inputs |
|---|---|---|
| **Collector Appeal** | Pure nonfinancial collector demand | D alone (or D plus future demand signals) |
| **Collector Opening Experience** | How often desirable things appear and how the chase feels | H, P, accessibility/chase structure |
| **Financial RIP** | Financial opening quality | unchanged |
| **Overall RIP** | Defined blend of the pillars | unchanged methodology |

**Advantages.** Each name would mean what it says. The Mega-Evolution-over-151 result stops being an anomaly and becomes the correct answer to a clearly different question. It removes the pressure to reweight D/H/P to satisfy two incompatible constructs at once. The data requirements are nil — every input already exists, and D is already computed and stored.

**Disadvantages.** Two public metrics where there was one, and users must learn the difference. "Collector Appeal = D alone" makes the flagship metric a single input, which is thin and, per this repo's own prior finding, rank-fragile (19 of 22 sets fall inside D ∈ [0.79, 0.96]). Splitting also changes what Overall RIP consumes, which the brief explicitly puts out of scope.

**Not implemented.** Evaluation only, per instruction.

---

## 13. Alternative model comparison

| | Question answered | Form | Double-count risk | Expected movement | Interpretability |
|---|---|---|---|---|---|
| **Option 0 — keep V3** | "How appealing is opening this set?" | `0.40D + 0.35H + 0.25P` | none | — | Good, if renamed |
| **Option 1 — rebalance D/H/P** | same as V3 | same, new coefficients | none | Moderate; raising D to ~0.55 would restore 151 over Mega Evolution | Unchanged |
| **Option 2 — desirability-weighted H** | "How often does something you want *badly* appear?" | H weighted by subject demand share | **High** — D enters twice, invisibly | Would amplify large-roster sets | Worse; the double-count is not visible in the formula |
| **Option 3 — reduce/restructure P** | same as V3, less architecture | lower P coefficient, or normalise P for roster size | none | Would lift Ascended Heroes, Paldean Fates; drop Pitch Black, Mega Evolution | Good |
| **Option 4 — separate the metrics** | two questions, separately | §12 | none | n/a — different products | **Best** |
| **Option 5 — roster-size-corrected P** | "Do desirable subjects get both paths, controlling for roster breadth?" | residualise P on cards-per-subject | Low | Would substantially reorder the P column | Moderate; harder to explain |

Spearman-vs-V3, top-5 overlap and full rank-movement tables were **not** computed for Options 1–5. Producing them means scoring the cohort under each alternative, and doing that before the construct question in §11 is settled would be choosing a formula by the rankings it produces — precisely the fitting this module's design forbids. They should be computed *after* a construct decision, not to inform one.

---

## 14. Recommendation

**Keep V3 unchanged.** Concretely:

1. **Do not reweight.** The motivating observation was three-quarters false. There is no defect to correct, and the one real inversion (Mega Evolution over 151) is the *correct* answer under the construct V3 actually implements.
2. **Resolve the naming first.** Establish whether the product intends Interpretation A or B, and find out which construct the surface that produced the original observation was displaying. Two constructs already share the name "Collector Appeal" in this codebase; that is the highest-value thing to run down, and it is a labelling problem, not a modelling one.
3. **Then, if the answer is Interpretation B**, consider Option 3 or 5 — P's 3.33× range and +0.825 correlation with cards-per-subject give it more leverage than intended and make it partly a measure of product design. That is a real, independently-supported finding.
4. **If the answer is Interpretation A**, Option 4 is the honest fix, not a reweighting.
5. **Reject Option 2.** Desirability-weighted H double-counts D invisibly.

Next concrete step: identify the surface that showed Pitch Black / Perfect Order / Journey Together above Ascended Heroes and determine which metric and which vintage it was serving.

---

## 15. Explicitly NOT changed, and not done

**Not changed.** No formula, weight, threshold, version string, or fingerprint. No production data row. No snapshot rebuilt, no simulation rerun, no model published, no Overall RIP methodology touched. No protected weight exposed on any public frontend or API surface. Nothing committed, pushed, merged or deployed.

**Not done — known gaps in this audit.**
- The Ascended Heroes input-integrity audit is a **spot-check** (Gengar, plus roster-level aggregates and coverage share), not an exhaustive per-subject trace of all 44 subjects. Charizard and Pikachu were not individually verified — the available trace file contains 7 rows, not the full roster. A complete trace requires a dedicated per-subject extract.
- Rank-movement, Spearman-vs-V3 and top-5-overlap tables for Options 1–5 were not computed; see §13 for why.
- Universal Desirability global ranks were not joined into the cohort table.
- Accessible-path and elite-path *selection logic* was read but not independently re-derived per subject.
- The 11 sets with no pull model were not investigated; they are correctly unavailable, but the public cohort is therefore Scarlet & Violet forward.
