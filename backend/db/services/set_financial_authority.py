"""The exact Financial authority behind one RIP-statistics SET target.

WHAT THE EXISTING SET-LEVEL FINANCIAL RIP IS
--------------------------------------------
A Rankings set target's ``financialRipV4`` is not read from any sealed product. It is re-projected
(``project_financial_rip_v4_from_v3_payload``) from the ``financial_rip_v3_payload`` persisted on the set's
own calculation run (``simulation_derived_metrics``), and that payload was built at simulation time by
``derived_metrics.compute_derived_metrics`` as ``build_financial_rip_v3(values, pack_cost)`` over the run's
per-pack outcome vector. That vector is exactly what ``simulation_pack_outcome_artifacts`` stores for the
run (``load_pack_outcome_artifact``), and the payload records the ``packCost`` it used.

So the set's exact single-opening authority is::

    (calculation run's pack-outcome artifact, payload.packCost)

It is NOT a sealed-product row and does not depend on any product family. This module names that contract
so no caller has to rediscover it, verifies it against every persisted statistic on the run before use, and
scores Financial V5 from it with the SAME canonical implementation the sealed-product finalizer uses
(``score_row_v5``): the V5 result is recomputed from the exact vector, never derived from a V4 number.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional

import numpy as np

from backend.calculations.evr.financial_rip_v4 import project_financial_rip_v4_from_v3_payload
from backend.db.services.pack_outcome_artifact_service import load_pack_outcome_artifact
from backend.db.services.sealed_product_financial_v5_finalization_service import (
    V5RowUnavailable,
    score_row_v5,
)

SET_FINANCIAL_AUTHORITY_CONTRACT = "set_financial_authority_v1"
STAT_TOLERANCE = 1e-6

# persisted run-level column -> statistic recomputed from the artifact vector
_STAT_COLUMNS = {
    "mean_value": lambda v: float(v.mean()),
    "median_value": lambda v: float(np.median(v)),
    "tail_value_p05": lambda v: float(np.percentile(v, 5)),
    "financial_rip_v3_p95_threshold_value": lambda v: float(np.percentile(v, 95)),
    "financial_rip_v3_p99_threshold_value": lambda v: float(np.percentile(v, 99)),
}


class SetAuthorityError(RuntimeError):
    """The set target's Financial authority cannot be proven; carries a stable reason."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason, self.detail = reason, detail


@dataclass(frozen=True)
class SetFinancialAuthority:
    set_id: str
    calculation_run_id: str
    pack_cost: float
    outcomes: np.ndarray
    artifact_metadata: Mapping[str, Any]
    v3_payload: Mapping[str, Any]
    row: Mapping[str, Any]


def _parse_payload(value: Any) -> Mapping[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, Mapping) else {}


def resolve_set_financial_authority(
    row: Mapping[str, Any], *, client: Any,
    artifact_loader: Callable[[Any, Any], Any] = load_pack_outcome_artifact,
) -> SetFinancialAuthority:
    """Bind one run-level row to its exact artifact and verify every persisted statistic. Fails closed."""
    run_id = str(row.get("calculation_run_id") or "")
    set_id = str(row.get("set_id") or "")
    if not run_id or not set_id:
        raise SetAuthorityError("row_missing_run_or_set")
    payload = _parse_payload(row.get("financial_rip_v3_payload"))
    if not payload:
        raise SetAuthorityError("no_persisted_v3_payload", run_id)
    try:
        pack_cost = float(payload.get("packCost"))
    except (TypeError, ValueError):
        raise SetAuthorityError("payload_pack_cost_invalid", repr(payload.get("packCost")))
    if not math.isfinite(pack_cost) or pack_cost <= 0:
        raise SetAuthorityError("payload_pack_cost_invalid", repr(pack_cost))
    try:
        artifact = artifact_loader(client, run_id)
    except Exception as exc:  # unavailable / corrupt artifact: replay is impossible
        raise SetAuthorityError("artifact_unavailable", f"{type(exc).__name__}: {exc}"[:200]) from exc
    if str(artifact.metadata.get("calculation_run_id")) != run_id:
        raise SetAuthorityError("artifact_run_mismatch", f"row={run_id} artifact={artifact.metadata.get('calculation_run_id')}")
    vector = np.asarray(artifact.outcomes, dtype=float)
    stored_count = row.get("simulation_count")
    if stored_count is None or int(stored_count) != vector.size:
        raise SetAuthorityError("simulation_count_mismatch", f"stored={stored_count} artifact={vector.size}")
    v3_count = row.get("financial_rip_v3_simulation_count")
    if v3_count is not None and int(v3_count) != vector.size:
        raise SetAuthorityError("v3_simulation_count_mismatch", f"stored={v3_count} artifact={vector.size}")
    stored_cost = row.get("pack_cost")
    if stored_cost is not None and not math.isclose(float(stored_cost), pack_cost, rel_tol=1e-9, abs_tol=1e-9):
        raise SetAuthorityError("pack_cost_mismatch", f"row={stored_cost} payload={pack_cost}")
    for column, compute in _STAT_COLUMNS.items():
        stored, actual = row.get(column), compute(vector)
        if stored is None or not math.isclose(float(stored), actual, rel_tol=STAT_TOLERANCE, abs_tol=STAT_TOLERANCE):
            raise SetAuthorityError("persisted_statistic_mismatch", f"{column} stored={stored} artifact={actual}")
    return SetFinancialAuthority(set_id, run_id, pack_cost, vector, dict(artifact.metadata), payload, row)


def stored_v4_score(authority: SetFinancialAuthority) -> Optional[float]:
    """The set target's existing Financial V4 score (the persisted-V3 re-projection the builder emits)."""
    projected = project_financial_rip_v4_from_v3_payload(authority.v3_payload)
    score = projected.get("score")
    return None if score is None else float(score)


def compute_set_financial_v5(authority: SetFinancialAuthority) -> Dict[str, Any]:
    """Financial V5 (V5-only column set) recomputed from the exact vector by the canonical implementation.

    Reuses ``score_row_v5``, which re-verifies the vector against the run's statistics and asserts the V4
    control recomputed from the SAME vector reproduces the target's stored V4 score before scoring V5.
    """
    row = authority.row
    adapter = {
        "product_market_cost": authority.pack_cost, "simulation_count": int(authority.outcomes.size),
        "expected_value": row.get("mean_value"), "median_value": row.get("median_value"),
        "p05_value": row.get("tail_value_p05"),
        "p95_value": row.get("financial_rip_v3_p95_threshold_value"),
        "p99_value": row.get("financial_rip_v3_p99_threshold_value"),
        "financial_rip_v4_score": stored_v4_score(authority),
    }
    try:
        return score_row_v5(adapter, authority.outcomes)
    except V5RowUnavailable as exc:
        raise SetAuthorityError(exc.reason, getattr(exc, "detail", "")) from exc
