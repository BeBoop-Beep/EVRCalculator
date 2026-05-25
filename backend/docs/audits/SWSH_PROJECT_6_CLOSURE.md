# SWSH Project 6 Closure

Generated: 2026-05-24T00:06:30Z

Project 6 final decision:

- closed_runtime_validated_persistence_blocked_on_metric_semantics

## Final Status

- Scope: swsh6, swsh7 only
- Runtime enabled state: swsh6=True, swsh7=True
- Production probability table equals draft: swsh6=True, swsh7=True
- Strict DB input status: strict_db_input_passed
- Production smoke status: passed
- Production job dry-run status: blocked_on_roi_semantic_mismatch
- Actual writes performed total: 0
- Intended writes captured total: 646
- Reverse-holo leakage status: not_detected
- SV/Mega guardrail status: unchanged
- Other SWSH guardrail status: unchanged
- Critical warning status: present (roi_semantic_mismatch)

## Set-Level Closure Status

### Chilling Reign (swsh6)

- final status: runtime_validated_persistence_blocked_on_metric_semantics
- runtime enabled: True
- production probability equals draft: True
- strict DB input passed: True
- production smoke passed: True
- production job dry-run passed: False
- actual writes performed: 0
- intended writes captured: 321
- ROI semantic status:
  - reported ROI (legacy ratio): 0.30054931506849314
  - formula ROI: -0.6994506849315069
  - absolute delta: 1.0
  - passed: False
- probability-to-beat-cost semantic status:
  - reported probability_to_beat_pack_cost: 0.02939
  - value-derived probability_to_beat_pack_cost: 0.02939
  - absolute delta: 0.0
  - passed: True
- reverse-holo leakage: not_detected

### Evolving Skies (swsh7)

- final status: runtime_validated_persistence_blocked_on_metric_semantics
- runtime enabled: True
- production probability equals draft: True
- strict DB input passed: True
- production smoke passed: True
- production job dry-run passed: False
- actual writes performed: 0
- intended writes captured: 325
- ROI semantic status:
  - reported ROI (legacy ratio): 0.16867851940689055
  - formula ROI: -0.8313214805931094
  - absolute delta: 1.0
  - passed: False
- probability-to-beat-cost semantic status:
  - reported probability_to_beat_pack_cost: 0.01467
  - value-derived probability_to_beat_pack_cost: 0.01467
  - absolute delta: 0.0
  - passed: True
- reverse-holo leakage: not_detected

## Root Cause and Fix Scope

- Root cause (ROI): real job output exposes pack_value_vs_cost_comparison.*.roi as a legacy value/cost ratio, not formula ROI.
- Root cause (probability mismatch from prior artifact): dry-run extraction previously used pack_metrics.pack_cost (missing), resulting in pack_cost_used=0 and probability=1.0.
- Applied fix scope: audit-only.
- Production job logic changed: no.
- Persisted/intended payload semantics changed: no.

## Remaining Caveats

- Persistence remains blocked while ROI semantic mismatch is unresolved at output semantics level.
- Any persistence approval requires either output-layer ROI alignment to formula ROI or explicit schema-versioned field semantics.

## Explicit Next Recommended Phase

- project_7_metric_semantics_alignment_and_persistence_contract_hardening
