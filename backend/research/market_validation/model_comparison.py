"""FREEZE MODEL -> RUN OUTCOME VALIDATION workflow for comparing two Collector
models (e.g. V6 vs a future V7) against market outcomes.

The contract: a model's card/set-level records are snapshotted (frozen) BEFORE any
validation code runs, and the comparison functions only ever read that frozen
snapshot. There is no code path here that could feed a validation result back into
Collector construction -- these functions are pure readers, and freezing is
enforced structurally (FrozenModelSnapshot is immutable after construction).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from backend.research.market_validation.grouped_cv import leave_whole_set_out_folds
from backend.research.market_validation.incremental_models import build_design_matrix, fit_ols, predict
from backend.research.market_validation.raw_correlations import raw_relationship
from backend.research.validation_stats import paired, spearman

import numpy as np


@dataclass(frozen=True)
class FrozenModelSnapshot:
    """An immutable snapshot of one Collector model's card/set-level records, taken
    once and never mutated. `model_version`/`model_run_id` identify exactly which
    persisted model run this snapshot came from -- comparisons always report these
    alongside every number so results are traceable to a specific frozen run, never
    a moving target.
    """

    model_version: str
    model_run_id: str
    card_records: Tuple[Mapping[str, Any], ...]
    set_records: Tuple[Mapping[str, Any], ...]

    @staticmethod
    def freeze(model_version: str, model_run_id: str, card_records: Sequence[Mapping[str, Any]], set_records: Sequence[Mapping[str, Any]]) -> "FrozenModelSnapshot":
        for row in card_records:
            if row.get("collector_model_run_id") not in (None, model_run_id):
                raise ValueError(
                    f"Card row lineage mismatch: expected model_run_id={model_run_id!r}, "
                    f"found {row.get('collector_model_run_id')!r}. Refusing to freeze a "
                    "snapshot that mixes lineage from more than one model run."
                )
        return FrozenModelSnapshot(
            model_version=model_version,
            model_run_id=model_run_id,
            card_records=tuple(card_records),
            set_records=tuple(set_records),
        )


def overall_vs_market(snapshot: FrozenModelSnapshot, appeal_key: str = "final_card_collector_appeal", outcome_key: str = "log_market_price", seed: int = 0) -> Dict[str, Any]:
    result = raw_relationship(list(snapshot.card_records), appeal_key, outcome_key, seed=seed)
    result["modelVersion"] = snapshot.model_version
    result["modelRunId"] = snapshot.model_run_id
    return result


def component_deltas(snapshot_a: FrozenModelSnapshot, snapshot_b: FrozenModelSnapshot, component_keys: Sequence[str]) -> List[Dict[str, Any]]:
    """Per-component comparison between two frozen snapshots (e.g. V6 vs V7),
    matched by canonical_card_id. Reports each model's value and the delta -- does
    not compute or imply any correlation with price itself (see
    incremental_v7_after_v6 for that)."""
    by_id_a = {row.get("canonical_card_id"): row for row in snapshot_a.card_records}
    by_id_b = {row.get("canonical_card_id"): row for row in snapshot_b.card_records}
    shared_ids = sorted(set(by_id_a) & set(by_id_b))
    results = []
    for key in component_keys:
        deltas = []
        for cid in shared_ids:
            va, vb = by_id_a[cid].get(key), by_id_b[cid].get(key)
            if va is not None and vb is not None:
                deltas.append(float(vb) - float(va))
        results.append(
            {
                "component": key,
                "nSharedCards": len(shared_ids),
                "nBothPresent": len(deltas),
                "meanDelta": (sum(deltas) / len(deltas)) if deltas else None,
            }
        )
    return results


def incremental_v7_after_v6(
    snapshot_v6: FrozenModelSnapshot,
    snapshot_v7: FrozenModelSnapshot,
    outcome_key: str = "log_market_price",
    v6_appeal_key: str = "final_card_collector_appeal",
    v7_appeal_key: str = "final_card_collector_appeal",
    set_key: str = "set_id",
) -> Dict[str, Any]:
    """Does V7's Collector Appeal carry OOS predictive information beyond what V6
    already captured, on the shared card population? Joins the two snapshots by
    canonical_card_id, fits base=V6-appeal-only vs. base+V7-appeal, both under
    leave-whole-set-out CV, reports ΔR². This is the single most important V6-vs-V7
    market-validation number: it answers "did the V7 research program actually add
    market-relevant information," not just "does V7 also correlate with price."
    """
    by_id_v6 = {row.get("canonical_card_id"): row for row in snapshot_v6.card_records}
    by_id_v7 = {row.get("canonical_card_id"): row for row in snapshot_v7.card_records}
    shared_ids = sorted(set(by_id_v6) & set(by_id_v7))

    merged = []
    for cid in shared_ids:
        row_v6, row_v7 = by_id_v6[cid], by_id_v7[cid]
        outcome = row_v6.get(outcome_key) if row_v6.get(outcome_key) is not None else row_v7.get(outcome_key)
        if outcome is None:
            continue
        merged.append(
            {
                "canonical_card_id": cid,
                "set_id": row_v6.get("set_id") or row_v7.get("set_id"),
                outcome_key: outcome,
                "v6_appeal": row_v6.get(v6_appeal_key),
                "v7_appeal": row_v7.get(v7_appeal_key),
            }
        )

    def _oos_r2(predictor_keys: Sequence[str]) -> Optional[float]:
        columns, x_full, kept_idx = build_design_matrix(merged, predictor_keys, categorical_control_keys=())
        if x_full.shape[0] < len(columns) + 5:
            return None
        y_full = np.array([float(merged[i][outcome_key]) for i in kept_idx])
        folds = leave_whole_set_out_folds([merged[i] for i in kept_idx], set_key=set_key)
        preds_all, actual_all = [], []
        for train_idx, val_idx in folds:
            if len(train_idx) < len(columns) + 2 or not val_idx:
                continue
            coef, intercept = fit_ols(x_full[train_idx], y_full[train_idx])
            preds_all.extend(predict(x_full[val_idx], coef, intercept).tolist())
            actual_all.extend(y_full[val_idx].tolist())
        if len(actual_all) < 3:
            return None
        a, p = np.array(actual_all), np.array(preds_all)
        sse = float(np.sum((a - p) ** 2))
        sst = float(np.sum((a - np.mean(a)) ** 2))
        return (1.0 - sse / sst) if sst > 0 else None

    base_r2 = _oos_r2(["v6_appeal"])
    with_v7_r2 = _oos_r2(["v6_appeal", "v7_appeal"])
    delta = (with_v7_r2 - base_r2) if (base_r2 is not None and with_v7_r2 is not None) else None

    return {
        "v6ModelVersion": snapshot_v6.model_version,
        "v6ModelRunId": snapshot_v6.model_run_id,
        "v7ModelVersion": snapshot_v7.model_version,
        "v7ModelRunId": snapshot_v7.model_run_id,
        "nSharedCards": len(shared_ids),
        "nUsable": len(merged),
        "v6OnlyOosR2": base_r2,
        "v6PlusV7OosR2": with_v7_r2,
        "deltaOosR2": delta,
    }
