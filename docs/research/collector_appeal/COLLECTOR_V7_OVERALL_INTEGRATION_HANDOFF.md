# Collector V7 → Future Overall RIP Integration Handoff

This is a research handoff, not an authorization to modify Overall RIP.

## Frozen comparison

Current control:

- Overall: `overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5`
- Financial: unchanged `financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5`
- Chase: unchanged `chase_accessibility_v1_hc_value_squared_modeled_probability`
- Collector: `collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2`
- Structure and weights: 86% Financial, 4% Chase Accessibility, 10% Collector

Future candidate:

- Use the same Financial authority, Chase authority, structure, weights, cohorts, missingness, and publication inputs.
- Replace only the 10% Collector input with final V7: `pokemon_collector_appeal_v7_expanded_price_blind_v1`.
- Pin the exact V7 model run and fingerprints before evaluation.

## Required analysis

Measure and preserve machine-readable results for:

1. Score deltas by set/product and distribution.
2. Rank deltas, top-N membership changes, and maximum/median movement.
3. Tier changes and threshold-adjacent cases.
4. Variance contribution from each pillar before and after substitution.
5. Collector contribution distribution in points and share of final variance.
6. Collector overlap/redundancy with Financial and Chase.
7. Stability under reasonable data perturbations without retuning V7.
8. Unsupported-set behavior and fail-closed missingness.
9. Public rankings behavior, pagination/topology, ties, and entitlement cohorts.
10. Exact source/model/run lineage and reproducible fingerprints.

## Acceptance boundary

Do not mutate V12. Any accepted integration requires a new Overall version, append-only result artifacts, explicit staging, controlled public cutover, rollback authority, and non-interference tests. V7’s modest and statistically uncertain incremental OOS improvement over V6 must remain visible; this task may assess Overall behavior but must not retune Collector Appeal against price.

No production action is authorized by this handoff.
