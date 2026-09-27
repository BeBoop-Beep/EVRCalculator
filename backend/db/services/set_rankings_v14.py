"""Financial RIP V5 / Overall RIP V14 blocks for one RIP-statistics SET target (release V14 only).

The set-level Financial authority is proven and named in ``set_financial_authority`` (22/22 targets are
reproduced exactly from the run's pack-outcome artifact). This module composes, per target:

  financialRipV5  <- ``compute_set_financial_v5`` (the canonical ``build_financial_rip_v5`` on the exact vector)
  overallRipV14   <- ``overall_rip_v14_for`` (the finalizer's own V14 discipline: exact V5, run-matched Chase
                     Accessibility V1, exact Collector Appeal V5, no renormalization, no V4/V12 fallback)

Missing or mismatched authority makes the target UNAVAILABLE; nothing falls back to V4/V12. The V4 / V12 blocks
on the same target are never touched, and V14 values are never written under V12-named keys.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Mapping, Optional, Sequence

from backend.calculations.evr.financial_rip_v5_config import FINANCIAL_RIP_V5_VERSION
from backend.db.services import set_financial_authority as sfa
from backend.db.services.sealed_product_financial_v5_finalization_service import overall_rip_v14_for

BASE_COLUMNS = "set_id,set_name,calculation_run_id,simulation_count,pack_cost,mean_value,median_value,tail_value_p05"
V3_COLUMNS = ("calculation_run_id,financial_rip_v3_simulation_count,financial_rip_v3_p95_threshold_value,"
              "financial_rip_v3_p99_threshold_value,financial_rip_v3_payload")


def read_set_authority_rows(client: Any, run_ids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    """Run-level rows (statistics + persisted V3 payload) for the given runs, keyed by calculation run id.

    ``explore_rip_statistics_latest`` is a view over ``__base`` plus an aggregate of ``simulation_derived_metrics``;
    the view times out on a scan, so both sources are read by run id. Read-only.
    """
    runs = sorted({str(r) for r in run_ids if r})
    if not runs:
        return {}
    base = {str(r["calculation_run_id"]): dict(r) for r in (
        client.table("explore_rip_statistics_latest__base").select(BASE_COLUMNS)
        .in_("calculation_run_id", runs).execute().data or [])}
    for r in (client.table("simulation_derived_metrics").select(V3_COLUMNS)
              .in_("calculation_run_id", runs).execute().data or []):
        run = str(r["calculation_run_id"])
        if run in base and r.get("financial_rip_v3_payload") and "financial_rip_v3_payload" not in base[run]:
            base[run].update({k: v for k, v in r.items() if k != "calculation_run_id"})
    return base


def _v5_unavailable(reason: str, detail: str = "") -> Dict[str, Any]:
    return {"score": None, "status": "unavailable", "statusReason": reason, "detail": detail or None,
            "rankable": False, "version": FINANCIAL_RIP_V5_VERSION, "scoreVersion": FINANCIAL_RIP_V5_VERSION,
            "components": {}}


def build_v14_target_blocks(
    target: Mapping[str, Any], *, authority_row: Optional[Mapping[str, Any]], client: Any,
    collector_score: Any, collector_version: Any, accessibility_row: Optional[Mapping[str, Any]],
    artifact_loader: Optional[Callable[[Any, Any], Any]] = None,
) -> Dict[str, Dict[str, Any]]:
    """``{"financialRipV5": ..., "overallRipV14": ...}`` for one target. Never raises for missing authority."""
    run_id = target.get("calculation_run_id")
    if authority_row is None:
        financial = _v5_unavailable("set_authority_row_missing", str(run_id))
    else:
        loader = {} if artifact_loader is None else {"artifact_loader": artifact_loader}
        try:
            authority = sfa.resolve_set_financial_authority(authority_row, client=client, **loader)
            if str(authority.calculation_run_id) != str(run_id):
                raise sfa.SetAuthorityError("authority_run_mismatch", f"target={run_id} authority={authority.calculation_run_id}")
            fields = sfa.compute_set_financial_v5(authority)
            payload = dict(fields["financial_rip_v5_payload"])
            financial = {
                **payload, "score": fields["financial_rip_v5_score"], "status": fields["financial_rip_v5_status"],
                "rankable": fields["financial_rip_v5_rankable"], "version": fields["financial_rip_v5_version"],
                "scoreVersion": fields["financial_rip_v5_version"],
                "source": {"contract": sfa.SET_FINANCIAL_AUTHORITY_CONTRACT, "calculationRunId": authority.calculation_run_id,
                           "artifactRawSha256": authority.artifact_metadata.get("raw_sha256"),
                           "packCost": authority.pack_cost, "outcomeCount": int(authority.outcomes.size)}}
            v5_row = {**fields, "calculation_run_id": run_id}
        except sfa.SetAuthorityError as exc:
            financial = _v5_unavailable(exc.reason, exc.detail)
    if financial.get("status") != "ready":
        overall = {"score": None, "status": "unavailable_missing_input", "rankable": False,
                   "statusReason": "no ready exact Financial RIP V5 for this set target (%s)" % financial.get("statusReason"),
                   "components": {}, "missingInputs": ["financial_rip_v5"]}
    else:
        overall = overall_rip_v14_for(v5_row, collector_score, collector_version, accessibility_row,
                                      expected_run_id=None if run_id is None else str(run_id))
    return {"financialRipV5": financial, "overallRipV14": dict(overall)}
