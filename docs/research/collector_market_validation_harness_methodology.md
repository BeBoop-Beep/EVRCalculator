# Collector Appeal Market-Validation Research Harness — Methodology & Runbook

Status: **framework only, tested against synthetic fixtures. No production data pulled, no Collector model evaluated for real, no V6/V7 relationship declared.** Built in parallel with the running Pokémon Trends V2 capture — does not touch it, its checkpoint, its manifest, or any Collector scoring code.

## Purpose

Measure how Collector Appeal and its subcomponents relate to market outcomes **without letting price influence Collector Appeal's own construction**. This is purely an evaluation harness — nothing in this package writes to a Collector component, a model run, or a current pointer.

## The one rule everything else follows: PRICE IS OUTCOME ONLY

Enforced in `backend/research/market_validation/price_separation.py`:
- `assert_no_price_in_predictor_keys()` raises `PriceContaminationError` the moment any price-shaped field (`market_price`, `log_market_price`, `market_price_rank_in_universe`, `canonical_set_value`, `top10_value`, `other_market_aggregate`) appears among predictor/control keys passed into a model-construction function. Called automatically inside `incremental_models.build_design_matrix()` — every entry point into the nested-model framework goes through it.
- `assert_scoring_config_price_free()` audits an arbitrary `scoring_config_json`-shaped mapping (the same shape Collector model runs already persist) for any price-shaped key, recursively, for use by Collector builder code that wants to self-certify.
- `strip_price_fields()` is a defensive default for anything building a feature matrix from a raw record.

## Package layout

```
backend/research/market_validation/
  schema.py             — CardLevelRecord / SetLevelRecord TypedDict contracts + structural validators
  price_separation.py   — the contract above
  raw_correlations.py   — signal-vs-outcome Spearman/Pearson/bootstrap CI, era/rarity breakdowns, coverage
  grouped_cv.py          — leave-whole-set-out, grouped K-fold by set, era-held-out folds, leakage guard
  incremental_models.py — pre-registered nested M0..M7 ladder, OLS via numpy, grouped-CV OOS metrics
  redundancy.py          — pairwise correlation, VIF, incremental-contribution-after-competitor
  master_table.py        — | Signal | n | raw Spearman | controlled effect | ΔOOS R² | era stability | price-independent | status | table generator
  model_comparison.py    — FrozenModelSnapshot + V6-vs-V7 comparison (overall, per-component, incremental)
  historical_fixtures.py — prior-study reference values + discrepancy classifier
```

Built on top of the existing `backend/research/validation_stats.py` (Spearman/Pearson/bootstrap CI/partial correlation — reused, not reimplemented) to stay consistent with this repo's existing small-cohort discipline (deterministic seeded RNG, explicit `n` on every payload, wide-interval flags).

## 1–2. Card-level and set-level dataset contracts

`schema.py`'s `CardLevelRecord`/`SetLevelRecord` are plain-dict contracts (not ORM models) — callers assemble rows from whatever source-of-truth is current (Collector persistence tables, snapshot artifacts, market-price tables) and pass lists of dicts in. Every predictor category from the task (Pokémon/Trainer Appeal, Playability raw+lift, Artist/Treatment/Scarcity, rarity/era/age/promo/variant/supertype/subject identity, Collector model lineage) has its own named field, kept separate — nothing is pre-combined. Fields for signals that don't exist yet (`artist_recognition_score`, `treatment_prestige_score`, `pull_scarcity_score`) are `Optional`, so the schema doesn't need a breaking change when V7 lands; the framework already skips any stage of the nested ladder whose required columns are entirely absent (`build_nested_ladder`), so an unfinished V7 signal never gets fabricated data or a fabricated row.

Set-level records carry `is_canonical_root` / `canonical_root_set_id`; `validate_set_records()` flags a subset that doesn't declare its root, preventing a subset from silently being treated as an independent market alongside its own root.

## 3. Strict price-separation contract

Covered above. Tested in `test_schema_and_price_separation.py` (raising on a price key in predictors, on a price-shaped scoring-config key, and confirming the legitimate `price_policy` self-declaration field is never flagged).

## 4. Raw relationship metrics

`raw_correlations.raw_relationship()`: n, Spearman, Pearson, bootstrap CI (via `validation_stats.bootstrap_correlation_ci`), coverage, missingness. `raw_relationship_by_group()` for era/rarity breakdowns. **Explicitly documented as not proof of independent signal** — that's what sections 5 and 8 are for.

## 5. Controlled / incremental models (M0–M7)

`incremental_models.NESTED_LADDER` pre-registers the exact ladder from the task: M0 (structural controls only) → M1 (+Pokémon Appeal) → M2 (+Scarcity) → M3 (+Treatment) → M4 (+Playability) → M5 (+Artist) → M6 (+Trainer/Functional) → M7 (pre-registered interactions only: Subject Appeal×Scarcity, Artist×Treatment, Trainer×Playability). `build_nested_ladder()` filters this down to stages whose required columns actually exist in the supplied dataset — a stage for an unavailable signal is dropped, never faked. `evaluate_nested_ladder()` fits every surviving stage under leave-whole-set-out CV and reports incremental ΔOOS-R²/MAE/RMSE vs. the previous stage.

## 6. Cross-validation

`grouped_cv.py`: `leave_whole_set_out_folds()` (one fold per set — the default and preferred method per the task), `grouped_kfold_by_set()` (deterministic seeded shuffle, sets never split across folds), `era_held_out_folds()`. `assert_no_set_leakage()` is a standing guard any fold can be checked against; unit-tested to raise on a synthetically-leaking fold.

## 7. Metrics

OOS R², MAE, RMSE, held-out Spearman, incremental Δ of each, all computed in `incremental_models._oos_metrics()` / `evaluate_nested_ladder()`. Bootstrap CIs come from the reused `validation_stats` primitives (naturally cluster-aware in spirit — the existing module's discipline already treats small-n as fragile and reports it per-payload).

## 8. Redundancy testing

`redundancy.py`: `pairwise_redundancy()` (Spearman/Pearson between any two components), `variance_inflation_factor()`/`vif_report()` (regression-based VIF via numpy, no sklearn needed), `incremental_contribution_after()` (the direct "does B add anything once A is present" test, under the same grouped-CV discipline as the main ladder — not an in-sample comparison). `COMPONENT_PAIRS_OF_INTEREST` pre-registers the exact pairs named in the task (Subject Appeal vs Artist, vs Playability, Treatment vs Scarcity, Artist vs Treatment, D vs F, Collector Appeal vs Scarcity); `redundancy_matrix()` only evaluates pairs actually present in a given dataset.

## 9. Master result table

`master_table.build_master_table()` produces exactly the requested columns. `classify_signal_status()` is deliberately conservative and mechanical: a price-*dependent* signal (per a caller-supplied `price_independence_flags` map — this harness cannot audit a signal's own upstream construction history, only refuse to let price be a predictor itself) is always `REJECT` regardless of its numbers, because construct validity gates eligibility before market performance is even considered. `n < 30` is always `INSUFFICIENT_EVIDENCE`. Unfinished V7 signals are never classified — `build_master_table()` skips any signal key absent from the dataset entirely, so this task deliberately produces zero classified rows for Artist/Treatment/Scarcity, matching the instruction not to classify unfinished V7 signals.

## 10. V6/V7 comparison contract

`model_comparison.FrozenModelSnapshot` is an immutable (`frozen=True` dataclass) snapshot of one model's records, keyed by `model_version`/`model_run_id`; `.freeze()` refuses to build a snapshot whose rows mix lineage from more than one `collector_model_run_id` — this is the structural enforcement of "no model is allowed to change after viewing the final frozen validation result": you cannot even construct a mixed-lineage snapshot, let alone evaluate one. `overall_vs_market()`, `component_deltas()` (per-component mean delta between two snapshots, matched by `canonical_card_id`), and `incremental_v7_after_v6()` (does V7's appeal carry OOS information beyond V6's, on the shared card population, under leave-whole-set-out CV) complete the FREEZE → VALIDATE workflow.

## 11. Historical study compatibility

`historical_fixtures.py` records the three supplied prior card-level Spearman figures (Pure Pokémon Demand ≈0.370, Treatment ≈0.582, old merged Card Appeal ≈0.569) and the qualitative set-level scarcity-dominance finding. `classify_discrepancy()` bands a new estimate as `CONSISTENT_WITH_PRIOR_STUDY` (≤0.05 gap), `MODERATE_DRIFT_REVIEW_COHORT` (≤0.15), or `MATERIAL_DISCREPANCY_INVESTIGATE` (>0.15) — it never adjusts either number to force agreement.

## 12. Corrected V6 validation — explicitly NOT run

No real Collector data was pulled into this harness. Every test in `backend/tests/unit/research/market_validation/` runs against a small, deterministic synthetic fixture (`conftest.py`: 12 sets × 15 cards, `pokemon_subject_appeal` genuinely drives `log_market_price` with noise + a per-set random effect + an era control, `trainer_appeal` is pure noise by construction) — chosen specifically so the tests can assert the harness recovers the *correct qualitative answer* (real driver shows positive OOS R² and gets classified CORE/POSITIVE_LIFT; noise variable doesn't) without needing production data or claiming anything about the actual frozen V6 model, which does not exist yet (the Trends V2 capture it depends on is still running).

## Runbook (once a corrected V6 — and later V7 — model run exists)

```python
from backend.research.market_validation.model_comparison import FrozenModelSnapshot, overall_vs_market
from backend.research.market_validation.master_table import build_master_table
from backend.research.market_validation.incremental_models import evaluate_nested_ladder

# 1. Assemble card_records: list[CardLevelRecord] from Collector + market-price sources.
# 2. Freeze once the model run is finalized:
snapshot = FrozenModelSnapshot.freeze(model_version, model_run_id, card_records, set_records)
# 3. Raw + controlled + master table:
overall = overall_vs_market(snapshot)
table = build_master_table(card_records, signal_keys=[...], base_predictor_keys=["release_age_days", ...])
ladder = evaluate_nested_ladder(card_records)
# 4. When V7 exists: incremental_v7_after_v6(snapshot_v6, snapshot_v7)
```

## Tests

66 tests across 5 files in `backend/tests/unit/research/market_validation/`, all passing: schema/price-separation contract, grouped CV (no-leakage proofs), raw correlations + nested ladder (recovers true driver vs. rejects noise), redundancy + master table + status classification, model comparison + historical-fixture classification. `python -m py_compile` clean, `git diff --check` clean.

## What remains once a corrected V6 (and later V7) model exists

1. Assemble real `CardLevelRecord`/`SetLevelRecord` datasets from the persisted Collector model run + market-price tables (not built here — this task is the framework only).
2. Run `evaluate_nested_ladder()` and `build_master_table()` against that real dataset.
3. Compare against `historical_fixtures.py`'s prior figures via `classify_discrepancy()`.
4. Once V7 exists, run `incremental_v7_after_v6()`.
5. None of the above may feed back into Collector Appeal's construction — this harness has no write path into any Collector component, and none should ever be added to it.
