# Collector Appeal formula fingerprint (Phase 7)

**Status:** implemented, tested, no production write. **Date:** 2026-07-15
**Module:** `backend/desirability/collector_appeal_fingerprint.py`
**Tests:** `backend/tests/unit/desirability/test_collector_appeal_fingerprint.py` (47 passed)

---

## The problem it solves

Staleness previously keyed on `set_id` + `config_fingerprint` + `current_trend_snapshot_ids`.
Those describe the **data**. Nothing described the **formula**.

Change λ from 0.50 to 0.75, recalibrate the 1-in-10 accessibility anchor, admit a
new rarity bucket to hit-eligibility, or alter how a printed rarity string
resolves to a key — and every stored Collector Appeal score becomes wrong while
the row looks untouched. Its data is fresh, its trend snapshots match, and its
score was computed under rules that no longer exist.

The fingerprint is a SHA-256 over a canonical representation of every assumption
capable of changing a computed result. A row whose fingerprint differs was
computed under different rules and is stale, however fresh its data.

---

## Current fingerprint

```
fbd2ccff9b8286e3dcdaf4e10283647834e3f761daf42341cc1b592d7f382764
```

Algorithm `sha256` · schema `collector_appeal_fingerprint_v1` · canonical
representation length 1,792 bytes.

## Exact fingerprint contents

```json
{
  "schema_version": "collector_appeal_fingerprint_v1",
  "formula": "CA7",
  "formula_expression": "CA7 = D + lambda * P * (1 - D)",
  "formula_version": "collector_appeal_ca7_bounded_bonus_v1",
  "lambda": 0.5,
  "dependencies": {
    "desirability_version": "universal_set_desirability_v3",
    "desirability_eligibility_version": "universal_desirability_eligibility_v2",
    "dual_path_version": "dual_path_depth_v1",
    "collector_appeal_module_version": "collector_appeal_v1_research",

    "access_transform_version": "access_transform_v1_log10_anchor_interpolation",
    "scarcity_transform_version": "scarcity_transform_v1_access_complement",
    "easy_probability_anchor": 0.1,
    "elite_probability_anchor": 0.001,
    "demand_baseline": 50.0,

    "hit_eligibility_version": "pokemon_card_desirability_hit_policy_v2_coverage_cleanup",
    "hit_buckets": ["accessible_hit", "major_hit", "premium_chase", "regular_hit"],
    "rarity_mapping_version": "rarity_normalization_v1_unicode_nfkd_snake_case",
    "rarity_override_version": "pokemon_set_desirability_card_rarity_overrides_v1",

    "subject_demand_source_version": "pokemon_desirability_composite_v1",
    "subject_weighting_version": "desirability_factor_v1",

    "product_classifier_version": "product_support_v1",
    "rankability_contract_version": "rankability_contract_v1",
    "set_components_version": "pokemon_set_desirability_components_v2_40_25_20_15",

    "missing_data_policy_version": "collector_appeal_missing_data_v1_none_never_zero",
    "missing_data_policy": {
      "missing_input_returns": "None",
      "never_substitutes_zero": true,
      "unmodeled_subjects": "renormalize_over_covered_demand_share",
      "no_desirable_subject": "dual_path_depth_is_None"
    },
    "rounding_policy_version": "collector_appeal_rounding_v1",
    "rounding_policy": {
      "clamp_domain": [0.0, 1.0],
      "clamp_applied_to": ["d", "p", "ca6", "ca7"],
      "round_half": "python_banker_default",
      "stored_decimal_places": 6
    }
  }
}
```

### Coverage against the brief's required list

| Required | Covered by |
|---|---|
| Collector Appeal formula identifier `CA7` | `formula` |
| λ value `0.50` | `lambda` |
| Universal Desirability scoring version | `desirability_version` + `desirability_eligibility_version` |
| Dual-Path Depth scoring version | `dual_path_version` |
| Access-transform version **and anchor constants** | `access_transform_version`, `easy_probability_anchor`, `elite_probability_anchor` |
| Scarcity-transform version **and anchor constants** | `scarcity_transform_version`, same anchors |
| Hit-eligibility policy version | `hit_eligibility_version` + `hit_buckets` membership |
| Rarity normalization/mapping version | `rarity_mapping_version` + `rarity_override_version` |
| Subject-linking / subject-weighting version | `subject_demand_source_version`, `subject_weighting_version` |
| Product-support classifier version | `product_classifier_version` |
| Missing-data policy version | `missing_data_policy_version` + the rules themselves |
| Rounding / clamping rules | `rounding_policy_version` + the rules themselves |
| Special-pack / product-subtype policy | `set_components_version` (encodes the 40/25/20/15 weights incl. special-pack chase appeal); subtype via `product_classifier_version` |

### Why anchors are included as **values**, not just versions

`easy_probability_anchor` and `elite_probability_anchor` are in the hash as
numbers. Recalibrating an anchor changes every score without any version string
necessarily moving — someone editing `EASY_PROBABILITY = 0.1` to `0.05` may
simply forget to bump a version. Including the value means the fingerprint
catches it whether or not anyone remembered. The same reasoning puts the
`missing_data_policy` and `rounding_policy` **rules** in the hash alongside their
version strings.

This matters concretely here: the rollout's largest known limitation is that the
1-in-10 accessible anchor is mismatched to the hit-eligible card population
(§6.3 of the rollout doc). Recalibrating it is a live future possibility, and per
decision 4 it is explicitly deferred. When it happens, every stored score must
invalidate automatically.

### Three new version constants were added

Nothing existed to identify these, so they were created at their defining sites
rather than duplicated into the fingerprint:

| Constant | Added to | Why |
|---|---|---|
| `ACCESS_TRANSFORM_VERSION`, `SCARCITY_TRANSFORM_VERSION` | `backend/desirability/opening_appeal.py` | The transforms had anchors but no identity for their shape |
| `RARITY_NORMALIZATION_VERSION` | `backend/calculations/utils/rarity_classification.py` | Rarity→key normalization can silently re-bucket cards |
| `CA7_FORMULA`, `CA7_FORMULA_VERSION`, `CA7_PRODUCTION_LAMBDA`, `MISSING_DATA_POLICY*`, `ROUNDING_POLICY*` | `backend/desirability/collector_appeal.py` | The selected production candidate needed to be separable from the research grid |

`collect_assumptions()` reads these **live from their defining modules**. A
duplicated copy inside the fingerprint would drift and quietly certify stale rows
as current — the exact failure the fingerprint exists to prevent.

---

## What is deliberately excluded

**No git commit SHA.** Requirement 7, and it is right: source-control identity is
not scoring identity. A commit editing a docstring would invalidate every stored
row; a commit changing a constant via config would not. The fingerprint is built
from the scoring assumptions themselves, so it moves when and only when the
mathematics moves. `build_collector_appeal_identity(source_control_ref=...)`
records provenance **alongside** the hash and is excluded from it — pinned by
`test_source_control_ref_is_recorded_but_excluded_from_the_hash`.

**No timestamps, paths, hostnames, env or run IDs.** Including any volatile value
would produce a new fingerprint every run and mark every row permanently stale —
functionally identical to having no fingerprint at all.

**No database access.** Pure function over module constants; callable in a unit
test with no network and no credentials. Asserted by source inspection.

**No price or market input**, consistent with the construct.

---

## Determinism

`canonical_representation` recursively sorts keys, sorts sets, serializes with
fixed separators and `ensure_ascii`, and normalizes floats through `repr` so
`0.50` and `0.5` agree. Sequence order is preserved (it can be semantically
meaningful, e.g. slot weights); `frozenset`/`set` are sorted.

`test_fingerprint_is_stable_across_processes` runs the hash in three
subprocesses under `PYTHONHASHSEED` 0, 1 and `random` and asserts a single
output — guarding against interpreter hash randomization leaking in through set
or dict iteration order.

---

## Staleness

| Status | Meaning | Requires rebuild |
|---|---|---|
| `current` | stored fingerprint == today's | No |
| `stale` | stored fingerprint differs — computed under different rules | Yes |
| `missing` | no fingerprint stored at all | Yes |

`missing` and `stale` are kept **distinct**. "Never computed" and "computed under
rules that have since changed" are different facts calling for different
responses; collapsing them into one "needs rebuild" flag would hide the fact that
a formula moved underneath existing rows. Both return `True` from `is_row_stale`.

Requirement 9 — *staleness detection must not silently overwrite rows* — is met
structurally: detection lives in `collector_appeal_fingerprint`, which contains
no write surface at all. The only write site in the rollout is
`execute_plan(..., commit=True)`, which refuses without an explicit fingerprint
and source manifest.

Requirement 10 — **no migration required.** The fingerprint lives at
`diagnostics_json.collector_appeal.fingerprint`, inside the existing JSONB
column. No DDL, no new column.

---

## Test coverage (47 passed)

| Requirement | Test |
|---|---|
| identical assumptions → identical hashes | `test_identical_assumptions_produce_identical_hashes` |
| reordered mappings → identical hashes | `test_reordered_mappings_produce_identical_hashes`, `test_nested_mapping_reordering_...` |
| λ change invalidates | parametrized `test_changing_any_material_assumption_changes_the_fingerprint[lambda]` |
| CA7 formula-version change invalidates | same, `formula_version` / `formula` |
| anchor change invalidates | same, `easy_probability_anchor` / `elite_probability_anchor` |
| hit-eligibility change invalidates | same, `hit_eligibility_version`, plus `test_hit_bucket_membership_change_invalidates` |
| rarity-mapping change invalidates | same, `rarity_mapping_version` |
| product-classifier change invalidates | same, `product_classifier_version` |
| missing-data-policy change invalidates | same, plus `test_changing_a_nested_policy_rule_changes_the_fingerprint` |
| missing fingerprints are stale | `test_missing_fingerprint_is_classified_missing_not_current` |
| mismatched fingerprints are stale | `test_mismatched_fingerprint_is_stale` |
| matching fingerprints are current | `test_matching_fingerprint_is_current` |
| no database access | `test_fingerprint_generation_performs_no_database_access` |
| price-independent | `test_score_computation_remains_price_independent`, `test_fingerprint_module_imports_no_client_or_price_surface` |
| no volatile timestamps / env paths | `test_fingerprint_contains_no_timestamps_or_paths_or_environment` |
| no git SHA | `test_fingerprint_does_not_use_a_git_commit_sha` |

The invalidation test is parametrized across **23 assumptions** — every key in
the fingerprint is proved to move the hash.
