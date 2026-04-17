# Phase 6 Research Validation and Inference Support

## Purpose
Phase 6 adds confidence-aware research workflows on top of Monte Carlo V2 validation.

This phase is designed to answer practical research questions:
- Is a mismatch likely real, or likely sample noise?
- Which assumptions are strongly contradicted vs weakly supported?
- Which sets/eras should be prioritized for additional research?
- How should partially known models be represented without claiming certainty?
- How can multiple candidate models be compared on the same observed data?

## Sourced Truth Boundary
Phase 6 preserves strict separation between:
- sourced config truth
- derived model outputs
- observed validation data
- provisional empirical artifacts
- research/inference outputs

Research outputs are inferred/provisional/review-only and are not automatically adopted.
No source config truth is mutated by Phase 6 workflows.

## Confidence Interval Method
Observed category proportions now include confidence intervals using the Wilson score interval.

Method details:
- method: Wilson interval
- default confidence level: 95%
- scope: category-level observed proportions where observed count and sample size are available
- dimensions: state, rarity dimensions, and aggregate hit frequency

Wilson intervals are used because they are a standard, defensible proportion interval and are more stable than naive Wald intervals for finite samples.

## Flagging and Materiality Framing
Phase 6 uses careful review language and avoids overclaiming.

Per-category outputs include:
- observed probability
- observed CI lower and upper bound
- expected-within-CI boolean
- review flag and review priority

Flagging guidance:
- flagged_for_review: expected falls outside observed CI and residual is material at adequate sample size
- flagged_for_review_low_confidence: expected falls outside observed CI but confidence is limited
- possible_sampling_noise: residual exists but evidence is weaker
- insufficient_observed_data: not enough observed data for confidence framing

"Flagged for review" means "investigate", not "proven true".

## Candidate Model Comparison
Phase 6 supports side-by-side candidate comparison against the same observed data.

For each candidate model, reporting includes:
- MAE
- TVD
- chi-square (when valid)
- JS divergence
- major residual contributors
- confidence-interval overlap counts

Candidate comparison is a research aid and does not auto-promote a model into sourced truth.

## Assumption Inventory and Audit
Phase 6 includes a model assumption inventory that records:
- era/model resolution path
- whether explicit model truth is present
- active constraints
- slot probability source presence vs missing/fallback areas
- special pack toggles
- known sourced assumptions
- inferred assumptions
- unresolved assumptions
- review-required assumptions

This inventory makes fallback and uncertainty visible instead of implicit.

## Partial and Provisional Model Handling
Partially known sets are supported through explicit assumption-status metadata.

Outputs distinguish:
- known sourced assumptions
- inferred assumptions
- unresolved assumptions
- review-required assumptions

Partially known models are not presented as equally certain as fully researched models.

## Confidence-Aware Residual Triage
Residual review includes confidence context and ranked triage groups:
- high-confidence mismatch candidates
- low-confidence mismatch candidates
- likely noise-only categories
- categories needing more data

This is intended for research prioritization and follow-up planning.

## Artifact Comparison Boundary
Phase 6 supports comparing:
- current derived model
- artifact-adjusted candidate model
- additional candidate hypotheses

Artifact comparison is allowed for review, but artifact outputs are still provisional and not auto-promoted.

## Research Bundle Exports
Phase 6 research bundle exports include:
- summary JSON
- per-dimension comparison CSV tables
- per-dimension confidence interval CSV tables
- confidence-aware residual JSON
- model assumption inventory JSON
- candidate model comparison summary JSON
- calibration artifact comparison summary JSON (when provided)
- manifest JSON with export provenance

## High-Level Research APIs
Phase 6 exposes research-oriented APIs:
- compute_wilson_interval(...)
- compare_candidate_models(...)
- build_model_assumption_inventory(...)
- run_confidence_aware_validation(...)
- generate_research_bundle(...)

These APIs are separated from normal EV simulation execution paths and are intended for validation, inference support, and research triage.
