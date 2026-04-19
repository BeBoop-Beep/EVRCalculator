# EV Math Audit (Reverse EV Focus)

Date: 2026-04-17
Scope: End-to-end EV math path used by backend/jobs/evr_runner.py, with emphasis on reverse EV inflation.

## 1) Active Runtime Path (What Actually Runs)

Entry and orchestration path:

1. backend/jobs/evr_runner.py
- EVRRunOrchestrator.run(...)
- Resolves set config class from SET_CONFIG_MAP/SET_ALIAS_MAP
- Calls calculate_pack_stats(calculation_input, config)
- Calls calculate_pack_simulations(calculation_input, config)
- Uses pack_metrics.total_ev (simulation mean) as primary total EV output

2. backend/calculations/packCalcsRefractored/__init__.py
- calculate_pack_stats(...) -> PackCalculationOrchestrator.calculate_pack_ev(...)

3. backend/calculations/packCalcsRefractored/packCalculationOrchestrator.py
- calculate_pack_ev(...)
- calculate_evr_calculations(df): manual EV decomposition
  - calculate_reverse_ev(df)
  - calculate_rarity_ev_totals(df, ev_reverse_total)
  - calculate_total_ev(ev_totals, df)
  - build_hit_and_non_hit_ev_contributions(df)

4. backend/simulations/evrSimulator.py
- calculate_evr_simulations(df)
- Branch selected by config.USE_MONTE_CARLO_V2
- Active for Scarlet/Violet configs: USE_MONTE_CARLO_V2 = True in base config
- Therefore runtime uses make_simulate_pack_fn_v2 + run_simulation_v2 from backend/simulations/monteCarloSimV2.py

5. V2 state model source
- backend/simulations/utils/packStateModels/scarletAndVioletPackStateModel.py
- Derives normal-pack state probabilities from config RARE_SLOT_PROBABILITY and REVERSE_SLOT_PROBABILITIES

Important runtime note:
- Runner computes both manual EV decomposition and simulation EV.
- Persisted and returned total EV is simulation-based (pack_metrics.total_ev), not manual total_manual_ev.

## 2) Config Inputs Audited

- backend/constants/tcg/pokemon/scarletAndVioletEra/baseConfig.py
  - RARITY_MAPPING
  - SLOTS_PER_RARITY
  - USE_MONTE_CARLO_V2 = True
  - get_reverse_eligible_rarities()
- backend/constants/tcg/pokemon/scarletAndVioletEra/setMap.py
  - set config resolution map/aliases
- representative set configs define:
  - RARE_SLOT_PROBABILITY
  - REVERSE_SLOT_PROBABILITIES

## 3) Component-by-Component EV Formula Audit

### A) Common expected contribution

Current formula path:
- Effective pull rate for common card i:
  - effective_rate_i = base_pull_rate_i / common_slots
- Per-card EV:
  - EV_i = price_i / effective_rate_i = price_i * common_slots / base_pull_rate_i
- Group total:
  - EV_common_total = sum(EV_i over rarity common)

Intended expectation formula:
- E_common = sum_i price_i * P(card i appears in common slots)
- With replacement and equal chance within common pool:
  - P(i per pack) = common_slots / N_common (if base pull denominator equals N_common)

Verdict: Correct (assuming Pull Rate (1/X) for commons is the pool size denominator).

Notes:
- Implementation is consistent with 4 common slots model in SLOTS_PER_RARITY.

### B) Uncommon expected contribution

Current formula path:
- effective_rate_i = base_pull_rate_i / uncommon_slots
- EV_i = price_i / effective_rate_i = price_i * uncommon_slots / base_pull_rate_i
- EV_uncommon_total = sum(EV_i over uncommon)

Intended expectation formula:
- E_uncommon = sum_i price_i * uncommon_slots / N_uncommon

Verdict: Correct (same assumption as common).

### C) Rare expected contribution (non-hit rare slot outcome)

Current formula path:
- For rarity_group == rare:
  - effective_probability_i = P(rare outcome in rare slot) * (1 / base_pull_rate_i)
  - effective_rate_i = 1 / effective_probability_i
  - EV_i = price_i / effective_rate_i = price_i * effective_probability_i

Intended expectation formula:
- E_rare = sum_i price_i * P(rare outcome) * P(i | rare outcome)

Verdict: Likely correct if base_pull_rate_i represents within-rare conditional denominator; unclear if source pull rates are already unconditional.

Notes:
- This component is not the primary reverse inflation driver.

### D) Hit rarity contributions (double rare, ultra rare, IR, SIR, hyper rare, ace spec, patterns)

Current formula path:
- Hit card EVs are computed as EV = price / Effective_Pull_Rate during data preparation.
- Contributions are later bucketed into hit/non-hit by RARITY_MAPPING in filter_card_ev_by_hits.
- In simulation (active total EV), hit outcomes are sampled via state outcomes and slot-specific rarity outcomes in monteCarloSimV2.py.

Intended expectation formula:
- Slot/state model expectation:
  - E_hit = sum_over_states P(state) * sum_over_hit_slots E[value | slot outcome in that state]

Verdict: Correct in active V2 simulation path; manual decomposition is partially model-mixed but not the main inflation source.

Notes:
- Hit contribution reporting from manual EV columns is not identical to state-conditioned simulation decomposition.

### E) Reverse EV contribution

Current formula path (manual decomposition):
- For each reverse slot s:
  - p_rr_s = REVERSE_SLOT_PROBABILITIES[s][regular reverse]
  - eligible_df = rows not excluded by hardcoded filter + has Reverse Variant Price
  - slot_reverse_EV_s = sum_j reverse_price_j * (p_rr_s / len(eligible_df))
- total_reverse_EV = sum_s slot_reverse_EV_s

Intended expectation formula:
- For each reverse slot s:
  - E_s = p_rr_s * mean(reverse_price among reverse-eligible regular cards)
- total_reverse_EV = sum_s E_s
- Eligibility should match config-defined reverse-eligible rarities (common/uncommon/rare mapping), excluding hits and special pattern slots.

Verdict: Incorrect in manual path due to eligibility filter bug and mismatch with config-driven eligibility.

Notes:
- Root-cause details below.

### F) God / demi-god pack contributions

Current formula path:
- If enabled:
  - EV_special = pull_rate * expected_pack_value_under_strategy
- total adds god and demi-god EV contributions.

Intended expectation formula:
- E_special = P(special pack) * E[value | special pack]

Verdict: Correct structure.

Notes:
- Not implicated in reverse inflation.

### G) Total EV aggregation

Current formula path:
- Manual:
  - total_manual_ev = sum(ev_totals by rarity including reverse) + god_pack_ev + demi_god_pack_ev
- Active runtime output:
  - total_ev = Monte Carlo simulation mean from run_simulation_v2

Intended expectation formula:
- total_EV = E[pack value across all pack paths and slot outcomes]

Verdict: Active runtime total is correct by construction of V2 simulation sampling; manual total can be inflated by reverse bug.

Notes:
- Reverse inflation can still contaminate manual reports/debug outputs and any logic that reuses manual reverse totals.

## 4) Explicit Root-Cause Analysis: Inflated Reverse EV

Primary root cause in backend/calculations/packCalcsRefractored/evrCalculator.py (calculate_reverse_ev_for_slot):

1. Eligibility filter is hardcoded and case-sensitive against mixed-case labels:
- Excludes only ['Illustration Rare', 'Special Illustration Rare']
- Data path normalizes rarities to lowercase strings in many places.
- If df Rarity values are lowercase (illustration rare/special illustration rare), this exclusion does not fire.

2. Eligibility source is not config-driven:
- Reverse regular pool should be based on config.get_reverse_eligible_rarities() (typically common/uncommon/rare mapped raw rarities).
- Current filter can include non-eligible high-value cards when reverse variant prices exist, inflating mean reverse price.

3. Inflation mechanism:
- slot_reverse_EV_s = p_rr_s * mean(reverse_price over eligible_df)
- If eligible_df contains hit-tier cards or misclassified rarities, mean(reverse_price) rises significantly.
- Both reverse slots add this inflated mean, amplifying error.

4. Evidence of model mismatch with active simulation:
- Active simulation reverse pool is built via extract_scarletandviolet_card_groups using config.get_reverse_eligible_rarities() and numeric Reverse Variant Price.
- Therefore simulation reverse sampling is better aligned with intended eligibility than manual reverse EV function.

Secondary issue (not primary current inflation source for active V2 total, but high-risk):
- In initializeCalculations._calculate_ev_columns, EV_Reverse is set as:
  - EV_Reverse = reverse_price * Effective_Pull_Rate
- This is dimensionally opposite of EV (which divides by rate) and can produce extreme values if consumed directly.
- In active simulation, reverse pool recomputes EV_Reverse from Reverse Variant Price, mitigating impact there.

## 5) Minimal Recommended Fixes (No Implementation in This Step)

1. Patch target: backend/calculations/packCalcsRefractored/evrCalculator.py
- Function: calculate_reverse_ev_for_slot
- Replace hardcoded eligibility logic with config-driven reverse eligibility:
  - eligible if rarity_raw in config.get_reverse_eligible_rarities()
- Normalize rarity strings before filtering.
- Keep pattern exclusions only if truly outside reverse-eligible mapping.

2. Patch target: backend/calculations/packCalcsRefractored/evrCalculator.py
- Add consistency guard/assertion:
  - Verify each reverse slot probability map sums to ~1.0
  - Verify regular reverse probability is present and bounded [0,1]

3. Patch target: backend/calculations/packCalcsRefractored/initializeCalculations.py
- Revisit EV_Reverse column formula for semantic correctness.
- If EV_Reverse is intended as sampled reverse-card value, it should be raw reverse price (or clearly renamed), not reverse_price * Effective_Pull_Rate.

4. Patch target: backend/calculations/packCalcsRefractored/packCalculationOrchestrator.py
- Add explicit note or field indicating manual decomposition is diagnostic and simulation mean is canonical runtime total.

## 6) Audited Files and Functions

Core runtime and orchestration:
- backend/jobs/evr_runner.py
  - EVRRunOrchestrator.run
- backend/calculations/packCalcsRefractored/__init__.py
  - calculate_pack_stats
- backend/calculations/packCalcsRefractored/packCalculationOrchestrator.py
  - calculate_pack_ev
  - calculate_evr_calculations

Manual EV formulas:
- backend/calculations/packCalcsRefractored/evrCalculator.py
  - calculate_effective_pull_rate
  - _calculate_guaranteed_slot_rate
  - _calculate_probability_based_rate
  - calculate_reverse_ev_for_slot
  - calculate_reverse_ev
  - calculate_rarity_ev_totals
  - calculate_total_ev
- backend/calculations/packCalcsRefractored/otherCalculations.py
  - calculate_pack_metrics
  - calculate_hit_probability

Simulation path:
- backend/simulations/__init__.py
  - calculate_pack_simulations export
- backend/simulations/evrSimulator.py
  - calculate_evr_simulations
  - simulate_pack_ev
- backend/simulations/monteCarloSim.py
  - make_simulate_pack_fn (V1 fallback)
- backend/simulations/monteCarloSimV2.py
  - make_simulate_pack_fn_v2
  - sample_cards_for_slot_outcomes
  - run_simulation_v2
  - validate_pack_state_model

State-model derivation/config glue:
- backend/simulations/utils/packStateModels/packStateModelOrchestrator.py
- backend/simulations/utils/packStateModels/scarletAndVioletPackStateModel.py
- backend/simulations/utils/packStateModels/derivePackStateProbabilities.py
- backend/simulations/utils/extractScarletAndVioletCardGroups.py

Set/config constants:
- backend/constants/tcg/pokemon/scarletAndVioletEra/baseConfig.py
- backend/constants/tcg/pokemon/scarletAndVioletEra/setMap.py
- representative set files with RARE_SLOT_PROBABILITY and REVERSE_SLOT_PROBABILITIES

## 7) Final Verdict

- Active runtime total EV path is simulation-first (V2) and not directly using manual reverse total as canonical pack EV output.
- Reverse EV inflation root cause is in manual reverse eligibility logic (non-config, case-sensitive exclusion), which can include non-eligible high-value cards in reverse average and inflate reverse contribution.
- Minimal patch should start with calculate_reverse_ev_for_slot eligibility normalization/config alignment, then EV_Reverse semantic cleanup for safety and future consistency.
