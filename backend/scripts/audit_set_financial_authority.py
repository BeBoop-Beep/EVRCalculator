"""READ-ONLY lineage audit: is each RIP-statistics set target's Financial V4 the run's exact single-pack authority?

For every set target in ``explore_rip_statistics_latest`` this binds the persisted V3 payload to the run's
pack-outcome artifact (``set_financial_authority``), recomputes the V3 payload, the V4 control and Financial
V5 from that exact vector, and compares against everything persisted. Classification per set:

  A  exact same authority (same run artifact; every persisted statistic, the recomputed V3 components and
     the V4 control reproduce the persisted values)
  B  equivalent through a different representation (not used here: there is no second representation)
  C  different authority (a comparison failed)
  D  unresolved (evidence unavailable)

No writes of any kind. Output: JSON under logs/v5_candidate and, with --out, a copy elsewhere.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
COMPONENT_TOLERANCE = 1e-6
SCORE_TOLERANCE = 5e-5  # scores are published to 4 dp
_ROW_COLUMNS = ("set_id,set_name,calculation_run_id,simulation_count,pack_cost,mean_value,median_value,tail_value_p05,"
                "financial_rip_v3_simulation_count,financial_rip_v3_p95_threshold_value,"
                "financial_rip_v3_p99_threshold_value,financial_rip_v3_payload")


def _components(payload: Mapping[str, Any]) -> Dict[str, float]:
    return {k: float(v["score"]) for k, v in (payload.get("components") or {}).items()
            if isinstance(v, Mapping) and v.get("score") is not None}


def audit_row(row: Mapping[str, Any], client: Any, *, artifact_loader=None, sealed_rows=()) -> Dict[str, Any]:
    from backend.calculations.evr.financial_rip_v3 import PreparedFinancialRipDistribution, build_financial_rip_v3
    from backend.calculations.evr.financial_rip_v4 import build_financial_rip_v4
    from backend.db.services import set_financial_authority as sfa

    record: Dict[str, Any] = {
        "setId": row.get("set_id"), "setName": row.get("set_name"), "calculationRunId": row.get("calculation_run_id"),
        "packCost": None, "v4Version": None, "v4Score": None, "classification": None, "reason": None, "checks": {}}
    loader = {} if artifact_loader is None else {"artifact_loader": artifact_loader}
    try:
        authority = sfa.resolve_set_financial_authority(row, client=client, **loader)
    except sfa.SetAuthorityError as exc:
        record["classification"] = "D" if exc.reason in ("artifact_unavailable", "no_persisted_v3_payload") else "C"
        record["reason"] = exc.reason
        record["detail"] = exc.detail
        return record
    record["packCost"] = authority.pack_cost
    record["artifact"] = {"rawSha256": authority.artifact_metadata.get("raw_sha256"),
                          "outcomeCount": authority.artifact_metadata.get("outcome_count")}
    projected_v4 = sfa.project_financial_rip_v4_from_v3_payload(authority.v3_payload)
    record["v4Version"] = projected_v4.get("scoreVersion")
    record["v4Score"] = projected_v4.get("score")
    checks = record["checks"]
    prepared = PreparedFinancialRipDistribution.prepare(authority.outcomes)
    # 1. the persisted V3 payload is reproduced from the artifact vector and the recorded pack cost
    v3 = build_financial_rip_v3(authority.outcomes, authority.pack_cost)
    persisted = _components(authority.v3_payload)
    recomputed = _components(v3)
    diffs = {k: abs(persisted[k] - recomputed[k]) for k in persisted if k in recomputed}
    checks["v3ComponentsMaxAbsDiff"] = max(diffs.values()) if diffs else None
    checks["v3ScoreAbsDiff"] = abs(float(authority.v3_payload.get("score")) - float(v3.get("score")))
    # 2. the V4 control recomputed from the vector equals the persisted-V3 re-projection
    control = build_financial_rip_v4(prepared, authority.pack_cost)
    checks["v4ControlAbsDiff"] = abs(float(control["score"]) - float(record["v4Score"]))
    v4_components = _components(projected_v4)
    control_components = _components(control)
    checks["v4ComponentsMaxAbsDiff"] = max(
        (abs(v4_components[k] - control_components[k]) for k in v4_components if k in control_components), default=None)
    # 3. Financial V5 from the exact vector via the canonical implementation
    try:
        v5 = sfa.compute_set_financial_v5(authority)
        record["v5Score"] = v5["financial_rip_v5_score"]
        record["v5Version"] = v5["financial_rip_v5_version"]
        record["v5LineageParity"] = (v5["financial_rip_v5_payload"].get("audit") or {}).get("v4LineageParity")
    except sfa.SetAuthorityError as exc:
        record["v5Reason"] = exc.reason
        checks["v5Computable"] = False
    # 4. informational: single-pack sealed rows of the same run (never used as authority)
    record["sameRunSealedRows"] = [
        {"family": r.get("product_family"), "packCount": r.get("pack_count"), "cost": r.get("product_market_cost"),
         "v4": r.get("financial_rip_v4_score")}
        for r in sealed_rows if str(r.get("calculation_run_id")) == str(row.get("calculation_run_id"))
        and int(r.get("pack_count") or 0) == 1]
    numeric = [checks["v3ScoreAbsDiff"], checks["v4ControlAbsDiff"]]
    ok = (all(x is not None and x <= SCORE_TOLERANCE for x in numeric)
          and (checks["v3ComponentsMaxAbsDiff"] or 0) <= COMPONENT_TOLERANCE
          and (checks["v4ComponentsMaxAbsDiff"] or 0) <= COMPONENT_TOLERANCE
          and checks.get("v5Computable", True))
    record["classification"] = "A" if ok else "C"
    if not ok:
        record["reason"] = "recomputation_disagrees_with_persisted_evidence"
    return record


def _target_rows(client: Any) -> List[Dict[str, Any]]:
    """Current per-set run rows joined to their run's persisted derived metrics.

    ``explore_rip_statistics_latest`` is a heavy view that times out on a full scan, so the runs are taken from
    the published snapshot's own targets (which is what the Rankings builder consumed) and the run-level rows
    are read by ``calculation_run_id`` from the base table.
    """
    # `explore_rip_statistics_latest` is a view over `__base` (run-level statistics) and an aggregate of
    # `simulation_derived_metrics` (the persisted V3 payload); both are read by run id.
    base = {str(r["calculation_run_id"]): r for r in (client.table("explore_rip_statistics_latest__base").select(
        "set_id,set_name,calculation_run_id,simulation_count,pack_cost,mean_value,median_value,tail_value_p05")
        .execute().data or [])}
    runs = sorted(base)
    v3 = {}
    for r in (client.table("simulation_derived_metrics").select(
            "calculation_run_id,financial_rip_v3_simulation_count,financial_rip_v3_p95_threshold_value,"
            "financial_rip_v3_p99_threshold_value,financial_rip_v3_payload")
            .in_("calculation_run_id", runs).execute().data or []):
        if r.get("financial_rip_v3_payload"):
            v3.setdefault(str(r["calculation_run_id"]), []).append(r)
    rows = []
    for run, b in base.items():
        candidates = v3.get(run, [])
        rows.append({**b, **(candidates[0] if candidates else {}), "v3RowCount": len(candidates)})
    return rows


def _retrying_loader(client: Any, run_id: Any, attempts: int = 6):
    """Artifact reads occasionally hit the statement timeout; retry the READ (no state involved)."""
    import time

    from backend.db.services.pack_outcome_artifact_service import load_pack_outcome_artifact

    for attempt in range(attempts):
        try:
            return load_pack_outcome_artifact(client, run_id)
        except Exception as exc:  # noqa: BLE001 - only transient statement timeouts are retried
            if "57014" not in str(exc) or attempt == attempts - 1:
                raise
            time.sleep(2 * (attempt + 1))


def run_audit(client: Any) -> Dict[str, Any]:
    rows = [r for r in _target_rows(client) if r.get("financial_rip_v3_payload")]
    run_ids = sorted({str(r["calculation_run_id"]) for r in rows})
    sealed = list(client.table("simulation_sealed_product_results").select(
        "calculation_run_id,product_family,pack_count,product_market_cost,financial_rip_v4_score")
        .in_("calculation_run_id", run_ids).execute().data or []) if run_ids else []
    records = [audit_row(r, client, sealed_rows=sealed, artifact_loader=_retrying_loader) for r in rows]
    counts: Dict[str, int] = {}
    for rec in records:
        counts[rec["classification"]] = counts.get(rec["classification"], 0) + 1
    return {"contract": "set_financial_authority_v1", "targets": len(records), "classificationCounts": counts,
            "allProven": bool(records) and set(counts) <= {"A", "B"}, "records": records}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    from backend.scripts.pokemon_snapshot_builders import get_client

    report = run_audit(get_client())
    out = Path(args.out) if args.out else ROOT / "logs" / "v5_candidate" / "set_financial_authority_lineage.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "records"}, indent=1))
    return 0 if report["allProven"] else 1


if __name__ == "__main__":
    sys.exit(main())
