"""Allowlisted public and internal-history reads for EV Representativeness.

Raw research tables remain service-role-only.  This module is the sole boundary
that turns a same-run V1 research result into a small product contract.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from backend.research.ev_representativeness.version import EV_REPRESENTATIVENESS_VERSION
from backend.research.opening_outcome_profile import (
    CONTRACT_VERSION as OUTCOME_CONTRACT_VERSION,
    RESEARCH_METHOD_VERSION as OUTCOME_RESEARCH_METHOD_VERSION,
    profile_from_persisted,
)

PUBLIC_CONTRACT_VERSION = "ev_representativeness_public_v1"
PUBLIC_PACK_COUNTS = (1, 6, 9, 11, 18, 36, 50, 100)
# Both of these are genuinely resolved horizons per
# backend.research.ev_representativeness.finite_sample.resolve_horizon:
# "resolved" is the normal case, "resolved_at_minimum_grid_point" is a
# resolved horizon that happens to land on the very first grid point (a
# small/cheap set where even 1 pack already clears the threshold). Neither
# "exceeds_search_cap" nor "degenerate_ev" belongs here - those never
# fabricate a pack count.
CONFIRMED_HORIZON_STATUSES = ("resolved", "resolved_at_minimum_grid_point")
logger = logging.getLogger(__name__)


def _rows(response: Any) -> List[Dict[str, Any]]:
    return list((response.data if response else []) or [])


def _number(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _confirmed_horizon(row: Mapping[str, Any], *, kind: str) -> Optional[Dict[str, Any]]:
    if kind == "realization":
        status = row.get("horizon_r80_c80_status")
        count = row.get("horizon_r80_c80_stable")
        parameters = {"targetEvRatio": 0.80, "openerProbability": 0.80}
    else:
        status = row.get("horizon_tau20_c80_status")
        count = row.get("horizon_tau20_c80_stable")
        parameters = {"tolerance": 0.20, "openerProbability": 0.80}
    if status not in CONFIRMED_HORIZON_STATUSES or count is None:
        return None
    return {**parameters, "packCount": int(count), "status": "confirmed"}


def project_public_v1(
    research_row: Mapping[str, Any],
    curve_rows: Sequence[Mapping[str, Any]],
    *,
    expected_calculation_run_id: str,
) -> Optional[Dict[str, Any]]:
    """Project one exact same-run V1 row; never fall back across runs/versions."""
    run_id = str(research_row.get("calculation_run_id") or "")
    if run_id != str(expected_calculation_run_id or ""):
        return None
    if research_row.get("research_method_version") != EV_REPRESENTATIVENESS_VERSION:
        return None

    # Curve rows may contain multiple stages.  At these natural counts confirm
    # or refine rows are preferred when present, otherwise the coarse estimate
    # remains the correct V1 empirical estimate.
    stage_rank = {"coarse": 0, "refine": 1, "confirm": 2}
    by_count: Dict[int, Mapping[str, Any]] = {}
    for item in curve_rows:
        if str(item.get("calculation_run_id") or "") != run_id:
            continue
        if item.get("research_method_version") != EV_REPRESENTATIVENESS_VERSION:
            continue
        if item.get("scope_kind") != "pack_grid" or item.get("metric_key") != "realization_ge_0.80":
            continue
        count = int(item.get("pack_count") or 0)
        if count not in PUBLIC_PACK_COUNTS:
            continue
        existing = by_count.get(count)
        if existing is None or stage_rank.get(str(item.get("stage")), -1) > stage_rank.get(str(existing.get("stage")), -1):
            by_count[count] = item

    realization = []
    for count in PUBLIC_PACK_COUNTS:
        item = by_count.get(count)
        estimate = _number(item.get("estimate")) if item else None
        if estimate is not None:
            realization.append({"packCount": count, "probabilityAtLeast80PercentEv": estimate})

    return {
        "contractVersion": PUBLIC_CONTRACT_VERSION,
        "methodVersion": EV_REPRESENTATIVENESS_VERSION,
        "calculationRunId": run_id,
        "marketDate": str(research_row.get("market_date") or "")[:10] or None,
        "sourceArtifactSha256": research_row.get("source_artifact_sha256"),
        "typicalCapture": _number(research_row.get("typical_capture")),
        "top1OutcomeEvShare": _number(research_row.get("top1_outcome_ev_share")),
        "realizationHorizon": _confirmed_horizon(research_row, kind="realization"),
        "convergenceHorizon": _confirmed_horizon(research_row, kind="convergence"),
        "realizationByPackCount": realization,
        "disclosures": {
            "independentPackAssumption": True,
            "grossMarketValue": True,
            "currentMarketPrices": True,
            "notOpeningRecommendation": True,
        },
    }


def project_opening_outcome_profile_v1(
    research_row: Mapping[str, Any], *, expected_calculation_run_id: str,
) -> Optional[Dict[str, Any]]:
    """Allowlisted exact-run projection of the persisted return-ratio partition."""
    run_id = str(research_row.get("calculation_run_id") or "")
    if run_id != str(expected_calculation_run_id or ""):
        return None
    if research_row.get("research_method_version") != EV_REPRESENTATIVENESS_VERSION:
        return None
    try:
        profile = profile_from_persisted(research_row.get("return_ratio_buckets_json") or {})
    except (TypeError, ValueError):
        return None
    return {
        "contractVersion": OUTCOME_CONTRACT_VERSION,
        "researchMethodVersion": OUTCOME_RESEARCH_METHOD_VERSION,
        "calculationRunId": run_id,
        "marketDate": str(research_row.get("market_date") or "")[:10] or None,
        "sourceArtifactSha256": research_row.get("source_artifact_sha256"),
        "openingCost": profile["openingCost"],
        "expectedValue": _number(research_row.get("ev")),
        "medianValue": _number(research_row.get("p50")),
        "sampleSize": profile["sampleSize"],
        "buckets": profile["buckets"],
        "cumulativeProbabilities": profile["cumulativeProbabilities"],
        "disclosures": {"grossMarketValue": True, "sellingFeesExcluded": True,
                        "gradingExcluded": True, "liquidityExcluded": True},
    }


def attach_public_v1_to_targets(client: Any, targets: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Attach projections without ever making public snapshot publication fail."""
    copied = [dict(target) for target in targets]
    try:
        return _attach_public_v1_to_targets(client, copied)
    except Exception:
        logger.exception("EV Representativeness public projection unavailable; omitting optional block")
        return copied


def _attach_public_v1_to_targets(client: Any, copied: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Implementation: one summary read plus deterministically paged curve reads."""
    run_ids = sorted({str(t.get("calculation_run_id")) for t in copied if t.get("calculation_run_id")})
    if not run_ids:
        return copied
    summaries: Dict[str, Dict[str, Any]] = {}
    curves: Dict[str, List[Dict[str, Any]]] = {run_id: [] for run_id in run_ids}
    for start in range(0, len(run_ids), 50):
        chunk = run_ids[start:start + 50]
        for row in _rows(
            client.table("ev_representativeness_run_summary").select("*")
            .eq("research_method_version", EV_REPRESENTATIVENESS_VERSION)
            .in_("calculation_run_id", chunk).execute()
        ):
            summaries[str(row["calculation_run_id"])] = row
        offset = 0
        while True:
            page = _rows(
                client.table("ev_representativeness_curve")
                .select("calculation_run_id,research_method_version,scope_kind,pack_count,metric_key,estimate,stage")
                .eq("research_method_version", EV_REPRESENTATIVENESS_VERSION)
                .eq("scope_kind", "pack_grid").eq("metric_key", "realization_ge_0.80")
                .in_("pack_count", list(PUBLIC_PACK_COUNTS)).in_("calculation_run_id", chunk)
                .order("calculation_run_id").order("pack_count").order("stage")
                .range(offset, offset + 999).execute()
            )
            for row in page:
                curves.setdefault(str(row["calculation_run_id"]), []).append(row)
            if len(page) < 1000:
                break
            offset += 1000
    for target in copied:
        run_id = str(target.get("calculation_run_id") or "")
        row = summaries.get(run_id)
        if row:
            projection = project_public_v1(row, curves.get(run_id, []), expected_calculation_run_id=run_id)
            if projection:
                target["evRepresentativeness"] = projection
            outcome_profile = project_opening_outcome_profile_v1(row, expected_calculation_run_id=run_id)
            if outcome_profile:
                target["openingOutcomeProfile"] = outcome_profile
    return copied


def get_set_history(
    client: Any,
    *,
    set_id: Optional[str] = None,
    canonical_key: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    method_version: str = EV_REPRESENTATIVENESS_VERSION,
    descending: bool = False,
) -> List[Dict[str, Any]]:
    """Internal ordered time series. Method versions are never spliced."""
    if not set_id and not canonical_key:
        raise ValueError("set_id or canonical_key is required")
    query = client.table("ev_representativeness_run_summary").select(
        "set_id,set_canonical_key,market_date,calculation_run_id,research_method_version,"
        "source_artifact_sha256,built_at,ev,p50,pack_cost,typical_capture,coefficient_of_variation,"
        "top1_outcome_ev_share,top5_outcome_ev_share,top10_outcome_ev_share,"
        "horizon_r80_c80_stable,horizon_r80_c80_status,"
        "horizon_tau20_c80_stable,horizon_tau20_c80_status"
    ).eq("research_method_version", method_version)
    query = query.eq("set_id", set_id) if set_id else query.eq("set_canonical_key", canonical_key)
    if start_date:
        query = query.gte("market_date", str(start_date)[:10])
    if end_date:
        query = query.lte("market_date", str(end_date)[:10])
    rows = _rows(query.order("market_date", desc=descending).order("calculation_run_id", desc=descending).execute())
    return sort_history_rows(rows, descending=descending)


def sort_history_rows(rows: Iterable[Dict[str, Any]], *, descending: bool = False) -> List[Dict[str, Any]]:
    """Keep history deterministic even when a data adapter ignores secondary ordering."""
    return sorted(
        (dict(row) for row in rows),
        key=lambda row: (str(row.get("market_date") or ""), str(row.get("calculation_run_id") or "")),
        reverse=descending,
    )
