# Collector Appeal CA7 — formula fingerprint (Phase 8.1)

**Metric:** `collector_appeal_ca7` · **Status:** `internal_candidate` ·
**Formula:** `CA7 = D + 0.50 * P * (1 - D)`
**Module:** `backend/desirability/collector_appeal_fingerprint.py`
**Tests:** `backend/tests/unit/desirability/test_collector_appeal_fingerprint.py`

| | Fingerprint |
|---|---|
| **Old (Phase 7/8)** | `fbd2ccff9b8286e3dcdaf4e10283647834e3f761daf42341cc1b592d7f382764` |
| **New (Phase 8.1)** | `a98b948c693b87afdb1e4b0d19df03aa3ae650d35ca62b38eea41c126240b774` |

The fingerprint **changed on purpose**. Section 2 lists exactly which assumptions
moved it. No stored row is affected: CA7 has never been persisted, so all 170
selectable rows are `fingerprint_missing` under both the old and the new hash.

---

## 1. The problem it solves

Staleness previously keyed on `set_id` + `config_fingerprint` +
`current_trend_snapshot_ids`. Those describe the **data**. Nothing described the
**formula**.

Change λ from 0.50 to 0.75, recalibrate the 1-in-10 accessibility anchor, admit a
new rarity bucket to hit-eligibility, or alter how a printed rarity string
resolves to a key — and every stored score becomes wrong while the row looks
untouched. Its data is fresh, its trend snapshots match, and its score was
computed under rules that no longer exist.

The fingerprint is a SHA-256 over a canonical representation of every assumption
capable of changing a computed result. It is built from **live module constants**,
never duplicated string literals — editing a constant at its source moves the
fingerprint automatically. A parallel copy would drift and quietly certify stale
rows as current.

### Formula identity is not source identity

This is the distinction Phase 8.1 exists to enforce.

- The **formula fingerprint** answers *"under what RULES was this computed?"*
- The **source identity** (`component_source.build_source_identity`) answers
  *"from WHICH ROW?"*

Conflating them is how a diagnostics block certifying
`hit_policy_version = ..._v2_coverage_cleanup` came to be proposed for rows
actually built under `..._v1`. The certificate was true about the rules and
**silent about the inputs**, so nothing contradicted it. Both are now stored, and
invariant 21 asserts the selected row's *actual* versions match the versions the
fingerprint represents. Neither identity is sufficient alone.

---

## 2. Why the fingerprint changed

Four groups of assumptions were added or renamed. Each was previously able to
change every computed CA7 score **without moving the hash**.

### 2.1 The metric identity was renamed (intentional)

| Was | Now |
|---|---|
| `collector_appeal_v1_research` | `collector_appeal_ca7_v1` |

`COLLECTOR_APPEAL_VERSION` is hashed as `collector_appeal_module_version`, so the
rename alone moves the fingerprint. The old string named a *study*; this constant
identifies a *formula proposed for production storage*.

### 2.2 Subject construction and demand aggregation (NEW)

Every step between "a printed card exists" and "subject *s* carries demand share
*q_s*" is a scoring decision. None were hashed before.

| Dependency | Constant | Defining module |
|---|---|---|
| `subject_construction_version` | `SUBJECT_CONSTRUCTION_VERSION` | `opening_appeal.py` |
| `subject_demand_aggregation_version` | `SUBJECT_DEMAND_AGGREGATION_VERSION` | `factorized_opening_appeal.py` |
| `card_link_source_version` | `CARD_DESIRABILITY_LINK_SOURCE_VERSION` | `card_links.py` |
| `card_link_aggregation_version` | `CARD_LINK_AGGREGATION_POLICY_VERSION` | `card_links.py` |
| `card_subject_assembly_version` | `CARD_SUBJECT_ASSEMBLY_VERSION` | `card_links.py` |

Why each is material:

- **Subject construction** — subjects group by `subject_key` (one Pokemon, all
  printings), demand is the **max** across printings, probability is the
  **slot-aware union**. Group by card name instead and every printing becomes its
  own subject, forcing P toward the single-printing bound of 0.25.
- **Demand aggregation** — only subjects with `appeal_excess > 0` participate, and
  `q_s = u_s / sum(u_s)` over exactly those. Widen the selection and every
  weighted structural score moves.
- **Card links** — a card with several links resolves by contribution-weighted
  **mean**, heaviest link naming the primary subject. "Weighted mean + heaviest
  primary" and "max + first primary" produce different numbers from identical rows.

### 2.3 The pull model (NEW)

P is a function of **modeled** probabilities. How they are read, and how a "1 in
N" denominator becomes a probability, are as material to the result as λ.

| Dependency | Constant | Defining module |
|---|---|---|
| `pull_model_loader_version` | `PULL_MODEL_LOADER_VERSION` | `pull_model.py` |
| `pull_probability_mapping_version` | `PULL_PROBABILITY_MAPPING_VERSION` | `pull_model.py` |

These constants are the **source of truth**, not a description of one:
`build_opening_appeal_study.load_pull_rate_model` imports and uses them
(`PULL_MODEL_SOURCE_TABLE`, `PULL_MODEL_GROUP_PRIORITY`,
`probability_from_denominator`, `slot_group_of`), so policy and version cannot
drift apart.

### 2.4 The component source contract (NEW)

Which row the formula is applied to. A change here means the same formula against
a *different set of inputs*, so rows computed under the old contract are stale.

| Dependency | Value |
|---|---|
| `component_source_contract_version` | `component_source_contract_v1_version_exact` |
| `component_source_scoring_version` | `pokemon_set_desirability_components_v2_40_25_20_15` |
| `component_source_hit_policy_version` | `pokemon_card_desirability_hit_policy_v2_coverage_cleanup` |
| `component_source_composite_scoring_version` | `pokemon_desirability_composite_v1` |

---

## 3. What is deliberately NOT in the hash

- **No git commit SHA.** Source-control identity is not scoring identity. A commit
  editing a docstring would invalidate every row; a commit editing a constant via
  config would not. `source_control_ref` may be recorded alongside as provenance.
- **No timestamps, paths, hostnames, environment or run IDs.** Volatile: including
  any would make every run produce a new fingerprint and mark every row
  permanently stale — the same as having no fingerprint at all.
- **No database access.** Fingerprinting reads module constants only; callable in
  a unit test with no network and no credentials.
- **No price or market input**, consistent with the construct.
- **No product name or product status** *(new in 8.1)*. `metric_name` and
  `product_status` are recorded in the identity block but excluded from the hash:
  renaming a metric or promoting it out of `internal_candidate` changes no
  computed number, and hashing them would mark every row stale for a relabelling.

---

## 4. Full dependency set

```
formula, formula_version, formula_expression, lambda

dependencies:
  # constructs
  desirability_version, desirability_eligibility_version,
  dual_path_version, collector_appeal_module_version        [8.1: RENAMED]
  # transforms + anchor VALUES (an anchor moves every score with no version bump)
  access_transform_version, scarcity_transform_version,
  easy_probability_anchor, elite_probability_anchor, demand_baseline
  # eligibility + rarity
  hit_eligibility_version, hit_buckets,
  rarity_mapping_version, rarity_override_version
  # subjects
  subject_demand_source_version, subject_weighting_version,
  subject_construction_version,                             [8.1: NEW]
  subject_demand_aggregation_version,                       [8.1: NEW]
  card_link_source_version,                                 [8.1: NEW]
  card_link_aggregation_version,                            [8.1: NEW]
  card_subject_assembly_version                             [8.1: NEW]
  # pull model
  pull_model_loader_version,                                [8.1: NEW]
  pull_probability_mapping_version                          [8.1: NEW]
  # component source contract
  component_source_contract_version,                        [8.1: NEW]
  component_source_scoring_version,                         [8.1: NEW]
  component_source_hit_policy_version,                      [8.1: NEW]
  component_source_composite_scoring_version                [8.1: NEW]
  # product policy
  product_classifier_version, rankability_contract_version, set_components_version
  # policies
  missing_data_policy_version, missing_data_policy,
  rounding_policy_version, rounding_policy
```

Algorithm `sha256` · schema `collector_appeal_fingerprint_v1`.

---

## 5. Determinism

`canonical_representation` sorts keys recursively and serializes with fixed
separators, so dict insertion order, input ordering and interpreter hash
randomization cannot move the hash. Floats normalize via `repr`, so `0.5` and
`0.50` agree while a genuinely different value still forks the hash.

---

## 6. Tests

`test_collector_appeal_fingerprint.py` pins:

- every dependency above moves the hash when mutated (one parametrized case each);
- every material path is **present** in the dependency set — enumerated, because a
  dependency that is simply *absent* cannot be caught by a mutation test. That is
  exactly how the subject, card-link and pull-model paths stayed outside the hash
  while being able to change every stored number;
- dependency versions are read live from their defining modules;
- the fingerprint's hit policy equals the source contract's expected hit policy —
  the two disagreeing *is* the original defect;
- `metric_name` / `product_status` do **not** move the hash, and promoting the
  metric out of `internal_candidate` leaves it unchanged;
- a fingerprint is read only from `diagnostics_json.collector_appeal_ca7`, never
  from the generic `collector_appeal` key (which belongs to the existing public
  metric);
- no volatile input (clock, path, environment, commit) moves it.
