# Overall RIP — Current Methodology (V10 canonical, V12 validated-but-shadow)

Status: reference document. Historical decision records
(`OVERALL_RIP_ACCESSIBILITY_ARCHITECTURE_CLOSURE.md`,
`OVERALL_RIP_ACCESSIBILITY_SCORING_CORE_IMPLEMENTATION.md`,
`OVERALL_RIP_V12_PERSISTENCE_PUBLICATION_IMPLEMENTATION.md`) are UNCHANGED and
remain the primary sources of truth for how each decision was reached. This
document is a current-state summary for anyone implementing UI/consumer code
against the two live model lineages, not a replacement for those records.

## 1. What is canonical right now

`CANONICAL_OVERALL_RIP_VERSION` (`backend/desirability/scoring_config.py`)
resolves to **Overall RIP V10**:

```
Overall RIP V10 = 0.90 * Financial RIP V4 + 0.10 * Collector Appeal V5
```

This is the ONLY score any ranking, leaderboard, or public "Overall RIP" number
is currently computed from. Nothing in this document changes that. `V10` is
published under `publicRipContractV10` / `overallRipV10`.

## 2. Overall RIP V12 — validated, shadow-only

`compute_overall_rip_v12` (`backend/desirability/weighted_rip.py`) implements a
validated-but-not-canonical successor:

```
Overall RIP V12 = 0.86 * Financial RIP V4
                + 0.04 * ChaseAccessibilityScore(A_raw, k=0.002)
                + 0.10 * Collector Appeal V5
```

It is published, additively, only under the SHADOW contract key
`publicRipContractV11` (see `backend/desirability/public_rip_contract_v11.py`).
A consumer must explicitly fetch that key to see V12 data; nothing that reads
only `publicRipContractV10` / `overallRipV10` is affected by V12's existence.

### 2.1 The flat formula (86/4/10)

The three weights are fixed constants
(`OVERALL_RIP_V12_FINANCIAL_WEIGHT` / `_CHASE_ACCESSIBILITY_WEIGHT` /
`_COLLECTOR_APPEAL_WEIGHT` = 0.86 / 0.04 / 0.10) that sum to exactly 1.0
(asserted at import time). All three pillars are REQUIRED — a missing or
invalid pillar makes the whole V12 result unavailable; there is no
renormalization of the survivors and no fallback to V10 or V11.

### 2.2 The conceptual hierarchy (90% Market-Based / 10% Collector)

The SAME 86/4/10 formula can be read as a two-level hierarchy, purely by
regrouping terms:

```
Overall RIP V12 = 0.90 * "Market-Based Opening Quality" + 0.10 * Collector Appeal V5

where "Market-Based Opening Quality" (weight 0.86 + 0.04 = 0.90) itself splits:
    95.5556% Financial RIP V4        (0.86 / 0.90)
  +  4.4444% Chase Accessibility Score (0.04 / 0.90)
```

**This grouping is EXPLANATORY ONLY.** "Market-Based Opening Quality" is never
computed, persisted, or returned as its own numeric field by any backend
service, and no frontend surface may render it as an independent third pillar
alongside Financial RIP, Chase Accessibility, and Collector Appeal — it is
Financial + Accessibility, described as one bucket, nothing more. The 90/10 and
95.5556/4.4444 shares are always DERIVED from the two source weights (division),
never hand-typed as separate literals, in both the backend
(`OVERALL_RIP_V12_MARKET_BASED_WEIGHT`,
`OVERALL_RIP_V12_FINANCIAL_SHARE_OF_MARKET_BASED`,
`OVERALL_RIP_V12_CHASE_ACCESSIBILITY_SHARE_OF_MARKET_BASED` in
`scoring_config.py`) and the frontend
(`overallRipExplanationHierarchySelector.mjs`'s `buildMarketBasedGrouping`).

## 3. Financial RIP — six scored components, EV is context only

Financial RIP V4 (the input to both V10 and V12) is a weighted sum of exactly
SIX components. EV (expected value) is reported as supporting simulation
context on the set page — it is not a seventh weighted component and carries no
weight in the formula.

| Component | Weight |
|---|---|
| True Win Frequency | 25% |
| Typical Retention | 20% |
| Loss Resilience | 15% |
| Realistic Upside | 25% |
| Jackpot Upside | 10% |
| Base Economic Efficiency | 5% |

(`FINANCIAL_RIP_V4_WEIGHTS`, imported into `scoring_config.py` as
`_FINANCIAL_RIP_V4_WEIGHTS`.) These six weights sum to exactly 1.00.

## 4. Chase Accessibility — raw metric vs Overall-scoring transform

Two DISTINCT numbers exist and must never be confused or mislabeled:

* **Raw Chase Accessibility (`A_raw`)** — the PUBLIC metric, a decimal
  fraction (e.g. `0.002` = `0.20%`), published under `chaseAccessibility.value`
  / `.percent` in every contract. This is the number a "Chase Accessibility"
  label may ever be attached to on a public surface.
* **A_score** — an Overall-RIP-scoring-ONLY transform of `A_raw`, computed by
  the one canonical function
  `backend/desirability/chase_accessibility_overall_score.chase_accessibility_overall_score`:

  ```
  A_score(k) = 100 * A_raw / (A_raw + k),   k = 0.002 (fixed, never re-anchored)
  ```

  `A_score` is a larger-scale, saturating transform used ONLY inside
  `overallRipV12.components.chaseAccessibility.score` and
  `overallRipV12Composition`. It must never be presented under a raw
  "Chase Accessibility" label. Where exposed for audit/reconstruction, it must
  be labelled explicitly as an Overall-RIP scoring input, distinct from the
  public raw metric.

### Anchor semantics (NOT literal chase-hit odds)

The transform is a saturating curve, fixed at `k = 0.002` by a pre-registered
log2-uniform grid search (`{0.0005, 0.001, 0.002, 0.004, 0.008}`), never
re-derived from an observed cohort. Representative anchor points:

| A_raw | A_score |
|---|---|
| 0.0005 (0.05%) | ≈ 20.0 |
| 0.001 (0.10%) | ≈ 33.3 |
| 0.002 (0.20%) | 50.0 |
| 0.004 (0.40%) | ≈ 66.7 |
| 0.008 (0.80%) | ≈ 80.0 |

These are NOT literal chase-hit odds and must never be phrased as "a 25%/50%/75%
chance of pulling a chase card" or any variant of "chance of a chase" /
"probability of a chase" — Chase Accessibility measures HC-value-squared,
modeled-probability reachability, not a discrete chase event.

Approved copy (locked, reused verbatim everywhere Chase Accessibility is
described):

* Public question: *"How reachable are this set's most important cards from a
  pack?"*
* Technical tooltip: *"How accessible the set's most important collectible
  value is from one pack."*

## 5. Collector Appeal — two scored factors only

Collector Appeal V5 is explained through exactly TWO parallel scored factors,
not a sequential pipeline:

* **Roster Desirability** — *"How desirable the modeled cards and Pokémon are
  independent of price."* / component-level copy: *"How desirable the modeled
  Pokémon roster is before pull difficulty is considered."*
* **Desirable Outcome Frequency** — *"How often a modeled pack can deliver at
  least one card tied to a currently desirable Pokémon."* Always paired with
  the disclaimer *"A desirable outcome can still be worth less than the pack
  price."* Never labelled Hit Rate, Win Frequency, Profit Frequency, or Chance
  to Recover Cost — those are Financial RIP vocabulary for a different
  statistic (`True Win Frequency = P(pack value >= pack cost)`).

Trainer and artist desirability are not modeled; their absence is stated, never
scored as zero.

## 6. Diagnostics — never scored inputs

* **Chase Depth** (Financial RIP's `depthAndRobustness` diagnostic) — *"How
  concentrated or spread out the set's important collectible value is."* Plus:
  *"Not part of the Chase Accessibility score or Overall RIP."* Shown, where
  shown at all, under "Additional Chase Context". Never a literal count of
  chase cards.
* **Dual-Path Depth** — computed and published under
  `collectorAppeal.diagnostics.dualPathDepth`, but NOT consumed by Collector
  Appeal V4/V5 scoring (ablation: 3/231 pairwise ordering changes, Spearman
  0.9966). Shown, where shown at all, under "Additional Collector Context"
  with the copy *"Not included in Collector Appeal."*

## 7. Explicitly NOT Overall RIP inputs

* **Treatment** (card-level "Card Treatment" / Treatment Prestige V2) — a
  card-detail metric, and an input to the card-level "Card Appeal" composite
  (Pokémon Demand + Card Treatment). It is NOT a Collector Appeal factor and
  must never be presented as one.
* **ECE (Economic Chase Efficiency) / Premium Product Chase Efficiency /
  O_budget** — product-level, Premium-tier concepts, entirely out of scope for
  Overall RIP and for the current Plus-tier Product RIP surface
  (`ProductRipSection.jsx`). Not implemented by this document's scope, and not
  to be leaked onto any Plus-tier surface.
* **Core K / Chase Opportunity V1** — the Overall RIP V11 lineage's chase
  pillar (`chase_opportunity_v1`, product-level, 3x pack-equivalent cost). It
  is a SEPARATE, SUPERSEDED-for-this-purpose lineage from V12's Chase
  Accessibility; V11 remains computable and historically meaningful but is not
  part of the V10-canonical / V12-shadow story this document describes.

## 8. Frontend implementation surface

* `frontend/components/explore/overallRipExplanationHierarchySelector.mjs` —
  the ONE version-aware selector. Detects V10 vs V12 by which contract shape
  was actually supplied (`publicRipContractV11` opt-in for V12; otherwise the
  canonical V10 resolver), never by a hardcoded assumption. Performs no Overall
  RIP scoring arithmetic — V12 weights are read verbatim from
  `overallRipV12Composition`; V10's fixed 90/10 split is stated as approved
  copy, matching the precedent already used by `ProductRipSection.jsx`.
* `frontend/components/explore/OverallRipExplanationHierarchy.jsx` — the ONE
  shared render component consuming that selector's view model. Reused by
  `PokemonSetAnalysisClient.jsx` (Set Analysis) and `RipStatisticsPageClient.jsx`
  (Explore/rankings) rather than each building a second, parallel V12
  explanation.
* `frontend/components/explore/OverallRipExplanationHierarchy.contract.test.mjs`
  — semantic contract tests: version-aware rendering, Market-Based
  explanatory-only status, no-frontend-scoring, and shadow safety (an ambient
  fixture carrying both V10 and V12 data still resolves V10 unless the caller
  explicitly supplies the V11 contract).

## 9. Backend status-label alignment (Phase 2)

`explore_rip_statistics_service.py`'s `_align_overall_rip_v12_authority_status`
relabels a rejected V12 result's generic `unavailable_missing_input` status to
the more specific `unavailable_authority_mismatch` when the underlying cause is
an Accessibility row that exists but was built under a different
`calculation_run_id` than the target's own coherent cohort run — matching the
label `_overall_rip_v12_for` in `sealed_product_rip_finalization_service.py`
already used for the identical condition. This changes ONLY the reported status
string; a mismatched row is still refused and its score is still `None` on both
paths, exactly as before.
