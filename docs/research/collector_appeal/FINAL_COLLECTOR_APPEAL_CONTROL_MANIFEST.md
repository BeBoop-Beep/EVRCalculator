# Final Collector Appeal Control Manifest

Status: `COLLECTOR_APPEAL_FINAL_CONTROL_FROZEN`

Collector Appeal V7 is the complete current Collector model for this product and research cycle. This closure changes no formula, creates no V8, performs no production write, and does not alter Overall RIP.

## Production model

The production readback on 2026-09-11 confirmed:

- Version: `pokemon_collector_appeal_v7_expanded_price_blind_v1`
- Run: `e282f26e-2136-4105-b0a3-f0974c4d9d70`
- Model fingerprint: `3b781f4ec01ef8c74c77b34d2b91e9a90231d2feccf2ee41411de64606378c9d`
- Formula fingerprint: `06f5660047b9b8a4d7349d04b79547b1314c2be3720c245ba8780890db1c114b`
- Card fingerprint: `7dbe5e989c6eb7bcb9d4684707f9c239ab1ca701fc429a7a0605657d79f2ab90`
- Set fingerprint: `744f088e7e1e33e5f8b40aca707b8f7e0d93bf7def8308b860da0277257a4b52`
- 18,293 card rows and 128 set rows; 22 scored sets and 106 explicitly unavailable sets
- Published Set-page generation `6bd24a8e-e0e1-4b33-86a1-a16d483f1b24`: 210/210 members, 22 Collector rows, matching V7 run, validation passed

All six source runs are successful, healthy, reproducibly linked, and usable. Production card readback confirms price and Treatment are excluded for every row and hit eligibility remains independent.

## Frozen semantics

V7 retains the raw Pokémon 75/25 fan/Trends V2 authority without a percentile transform; Trainer 40/60 multi-horizon authority; Playability before Artist; Artist λ=0.10; missing Artist as neutral; confirmed zero distinct from missing; maximum independently scoreable Artist for multi-artist cards; Trainer set headroom λ=0.15; frozen D; generalized F with the `>50` card threshold; and frozen C5.

The canonical component register is [final_collector_appeal_component_register.json](final_collector_appeal_component_register.json). Its production boundary is unambiguous:

- Included: Pokémon, Trainer, Artist, Playability.
- `Treatment`: **NOT INCLUDED IN COLLECTOR APPEAL SCORE**.
- `Pull Scarcity`: **NOT INCLUDED IN COLLECTOR APPEAL SCORE**.

## Scientific conclusions

- Pokémon: `SUPPORTED`
- Trainer: `SUPPORTED`
- Artist: `PARTIALLY_SUPPORTED`; the bounded current implementation is sufficient for V7.
- Playability: `PARTIALLY_SUPPORTED`
- Pull Scarcity: `SCARCITY_DIAGNOSTIC_ONLY`
- Treatment: `TREATMENT_PREFERENCE_INSUFFICIENT_EVIDENCE` and `TREATMENT_SHOULD_REMAIN_DIAGNOSTIC`
- Overall pricing evidence: `APPEAL_PRICING_SIGNAL_PARTIAL`
- Promotion: `V7_PROMOTION_SUPPORTED_WITH_LIMITATIONS`

Artist direct-preference voting is `ARTIST_DIRECT_PREFERENCE_VOTING`, a non-blocking backlog item. Future collection may use site, social-media, email/newsletter, or community-campaign voting. The present limitations belong in research documentation and the future scientific article, not a public UI warning.

Treatment taxonomy V3 remains preserved with 18,040 of 18,293 V7 cards mapped and 253 unresolved. Its era semantics, matched cohorts, scarcity separation, and article evidence remain available for diagnostics, market-validation controls, future inDex Fair Value, and future preference research. They do not authorize a Collector score contribution.

## Validation

The frozen [market-validation register](final_collector_market_validation_register.json) preserves the final evidence without rerunning or retuning V7. The overall signal is partial: median within-set Spearman 0.3176, weighted mean 0.2991, 95.45% positive sets, controlled incremental OOS R² +0.02255, MAE improvement 5.76%, RMSE improvement 8.03%, held-out Spearman +0.0494, residual-price Spearman/Pearson 0.3314/0.3758, matched-pair win rate 84.92%, and median price ratio 2.3066.

The critical qualification is unchanged: V7 adds only +0.00089 OOS R² over V6 after controls, and the whole-set bootstrap interval crosses zero. V7 must not be described as demonstrably more price-predictive than V6.

## Operations and history

The existing daily publication chain owns scheduling. Its final step plans multi-horizon source freshness, selectively refreshes only due sources, verifies source contracts, rebuilds the unchanged frozen formula, validates deltas, stages a complete Set-page generation, atomically promotes matching model/generation authority, and appends daily history idempotently. No second scheduler or Overall publication path is involved.

Live history readback found 384 rows across two dates, 2026-09-08 and 2026-09-11, including 128 rows for the current V7 run. Forward collection operates, but depth remains immature. `HISTORICAL_QUALITY_RESEARCH_NOT_READY` is final for this cycle and is not reopened here.

## Collector Appeal versus inDex Fair Value

Collector Appeal asks: “How much intrinsic collector interest or desirability does this card represent?” It may use Pokémon, Trainer, Artist, and Playability. It must not use price, Pull Scarcity, Treatment market premium, age, grading population, supply, or liquidity.

Future inDex Fair Value asks: “What price is structurally consistent with this card’s demand and market characteristics?” It may use the final frozen Collector Appeal alongside Pull Scarcity, Treatment, release age, era/set, structural card metadata, and defensible future supply, grading, or liquidity features.

This separation is a hard architecture contract.

## Overall and article handoff

Overall RIP remains `overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5`, using legacy `collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2`. V7 has not been silently substituted. The controlled next-task specification is [COLLECTOR_V7_OVERALL_INTEGRATION_HANDOFF.md](COLLECTOR_V7_OVERALL_INTEGRATION_HANDOFF.md).

The [article-evidence manifest](collector_appeal_article_evidence_manifest.json) points to versioned machine-readable evidence for definitions, lineage, examples, controls, matched cards, correlations, validation, and limitations. The article itself is not written in this closure.

Non-blocking backlog: `ARTIST_DIRECT_PREFERENCE_VOTING`, `TREATMENT_DIRECT_PREFERENCE_VOTING`, and Historical Quality research after observation gates mature.
