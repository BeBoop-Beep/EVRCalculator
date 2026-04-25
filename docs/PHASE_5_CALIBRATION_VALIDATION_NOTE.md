# Phase 5 Calibration and Validation Note

## Purpose
Phase 5 adds a validation-first workflow on top of Monte Carlo V2 so model behavior can be audited against observed pull data before any fitting is attempted.

This phase answers:
- How close expected model behavior is to observed pulls
- Which states or rarity categories drive mismatch
- Which assumptions are most likely wrong
- How to create calibration artifacts without mutating sourced truth

## Truth Separation
The system keeps four layers separate:
- Source config truth: researched slot probabilities and structural set behavior in set configs
- Derived model: computed state probabilities from config and structural rules
- Observed validation data: empirical pull observations loaded at runtime
- Calibration artifacts: optional fitted outputs generated in separate files

Important: empirical values are never written back into source config as researched truth.

## New API Surface
Phase 5 utilities live in backend/simulations/validations/packStateCalibration.py.

Primary entrypoints:
- load_observed_pull_data(...)
- compare_model_to_observed(...)
- run_pack_state_validation(...)
- generate_calibration_artifact(...)
- generate_calibration_report(...)
- export_calibration_results(...)

These APIs are exported from backend/simulations/validations/__init__.py.

## Observed Data Format
Observed data can be provided as:
- dict payload
- JSON file
- CSV file
- pandas DataFrame

Normalized payload fields:
- set_id (optional)
- set_name (optional)
- sample_size (optional but recommended)
- source_metadata (optional)
- notes (optional)
- counts_by_dimension (required for comparison)
- dimension_sample_sizes (optional)

Supported dimensions:
- state
- rare_slot_rarity
- reverse_1_rarity
- reverse_2_rarity
- reverse_slot_rarity
- aggregate_hit_frequency

Example payload:
```json
{
  "set_id": "sv8",
  "set_name": "Surging Sparks",
  "sample_size": 1200,
  "source_metadata": {
    "source": "community-tracker-v1"
  },
  "notes": "Pack openings from mixed channels",
  "counts_by_dimension": {
    "state": {
      "baseline": 820,
      "double_rare_only": 210,
      "sir_only": 36
    },
    "rare_slot_rarity": {
      "rare": 968,
      "double rare": 210,
      "ultra rare": 22
    }
  }
}
```

## Validation Modes
Mode A: state-frequency comparison
- Compares derived expected state probabilities to observed state frequencies
- Optionally includes simulated frequencies from V2

Mode B: rarity-level comparison
- Compares rare-slot and reverse-slot rarity distributions
- Useful when observed data has no state labels

Mode C: Monte Carlo consistency check
- Compares expected distributions to V2-simulated frequencies
- Isolates simulation fidelity from model-vs-reality mismatch

## Metrics and Interpretation
Per category row includes:
- expected_probability
- simulated_probability (when simulation included)
- observed_probability
- observed_count
- expected_count_at_observed_n
- absolute_difference_observed_vs_expected
- relative_difference_observed_vs_expected (only when expected_probability > 0)
- difference_simulated_vs_expected
- difference_simulated_vs_observed

Goodness-of-fit metrics include:
- mean_absolute_error
- total_variation_distance
- chi_square (with explicit excluded categories)
- kl_divergence_observed_to_expected
- jensen_shannon_divergence

Interpretation guidance:
- The previous aggregate score was removed because it was a heuristic composite based on arbitrary thresholds, not a standard or source-grounded statistical metric.
- Primary practical mismatch metrics are mean absolute error and total variation distance.
- Chi-square is reported only on categories with sufficiently large expected counts.
- KL divergence and Jensen-Shannon divergence use epsilon smoothing for numerical stability and should be treated as secondary diagnostics.
- In code, the divergence smoothing parameter is explicit (default epsilon = 1e-12).
- TVD and MAE are the primary practical diagnostics for day-to-day validation decisions.

## Residual Analysis
State residual analysis reports:
- top_over_predicted states
- top_under_predicted states
- observed_only_states
- model_only_states

This is the primary ranking for follow-up investigation and assumption review.

## Calibration Artifacts
generate_calibration_artifact(...) produces a separate provisional object with:
- expected probabilities
- fitted probabilities (blend of expected and observed where counts are sufficient)
- probability deltas
- ranked categories for review

Calibration artifacts are heuristic empirical suggestions, not statistically fitted truth.
The current blend-weight logic is a practical review aid, not a formal inference procedure.
Fitted probabilities are exploratory and provisional.
Calibration artifacts do not overwrite sourced configuration truth and should not be promoted automatically.
Artifact labels explicitly mark outputs as fitted, empirical, and provisional.
No config files are patched by this workflow.

## Export Outputs
export_calibration_results(...) writes a non-destructive bundle:
- summary JSON
- per-dimension comparison CSV files
- state residuals JSON
- optional raw simulated distributions JSON

This supports external review in notebooks, spreadsheets, and BI tooling.

## Why Validation Precedes Calibration
Calibration without measured mismatch can hide simulation bugs, overfit noisy data, and contaminate source truth.

Phase 5 enforces this order:
1. Build expected from current derived model
2. Measure mismatch to observed and/or simulated
3. Explain residuals and uncertainty
4. Generate optional calibration artifacts as separate outputs
