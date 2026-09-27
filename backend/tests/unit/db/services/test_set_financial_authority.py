"""Set-level Financial authority: proven from the run artifact, and the proof can fail."""
import copy
from types import SimpleNamespace

import numpy as np
import pytest

from backend.calculations.evr.financial_rip_v3 import build_financial_rip_v3
from backend.calculations.evr.financial_rip_v5_config import FINANCIAL_RIP_V5_VERSION
from backend.db.services import set_financial_authority as sfa
from backend.scripts import audit_set_financial_authority as audit

RUN = "run-aaaa"
COST = 4.25


def _vector(seed=7, n=20000):
    rng = np.random.default_rng(seed)
    return np.round(rng.lognormal(mean=0.6, sigma=1.1, size=n), 4)


def _row(vector, run=RUN, cost=COST):
    v3 = build_financial_rip_v3(vector, cost)
    return {
        "set_id": "set-1", "set_name": "Alpha", "calculation_run_id": run, "simulation_count": int(vector.size),
        "financial_rip_v3_simulation_count": int(vector.size), "pack_cost": cost,
        "mean_value": float(vector.mean()), "median_value": float(np.median(vector)),
        "tail_value_p05": float(np.percentile(vector, 5)),
        "financial_rip_v3_p95_threshold_value": float(np.percentile(vector, 95)),
        "financial_rip_v3_p99_threshold_value": float(np.percentile(vector, 99)),
        "financial_rip_v3_payload": v3,
    }


def _loader(vector, run=RUN):
    return lambda client, run_id: SimpleNamespace(metadata={"calculation_run_id": run, "raw_sha256": "x", "outcome_count": vector.size},
                                                  outcomes=vector)


def test_exact_authority_resolves_and_scores_v5_from_the_exact_vector():
    v = _vector()
    row = _row(v)
    auth = sfa.resolve_set_financial_authority(row, client=None, artifact_loader=_loader(v))
    assert auth.calculation_run_id == RUN and auth.pack_cost == COST
    out = sfa.compute_set_financial_v5(auth)
    assert out["financial_rip_v5_status"] == "ready" and out["financial_rip_v5_version"] == FINANCIAL_RIP_V5_VERSION
    assert out["financial_rip_v5_payload"]["audit"]["v4LineageParity"] == "exact"   # V4 control reproduced from the vector
    assert audit.audit_row(row, None, artifact_loader=_loader(v))["classification"] == "A"


def _reason(row, loader):
    with pytest.raises(sfa.SetAuthorityError) as exc:
        sfa.resolve_set_financial_authority(row, client=None, artifact_loader=loader)
    return exc.value.reason


def test_proof_detects_wrong_calculation_run_and_same_name_wrong_run():
    v = _vector()
    assert _reason(_row(v), _loader(v, run="run-bbbb")) == "artifact_run_mismatch"
    same_name_other_run = _row(v, run="run-cccc")            # same set name, different run than the artifact
    assert _reason(same_name_other_run, _loader(v, run=RUN)) == "artifact_run_mismatch"


def test_proof_detects_wrong_distribution_mapping():
    v, other = _vector(7), _vector(99)
    assert _reason(_row(v), _loader(other)) == "persisted_statistic_mismatch"


def test_proof_detects_changed_quantity_cost_and_source_statistic():
    v = _vector()
    r = _row(v); r["simulation_count"] = v.size - 1
    assert _reason(r, _loader(v)) == "simulation_count_mismatch"
    r = _row(v); r["pack_cost"] = COST + 0.5
    assert _reason(r, _loader(v)) == "pack_cost_mismatch"
    r = _row(v); r["mean_value"] = r["mean_value"] * 1.01
    assert _reason(r, _loader(v)) == "persisted_statistic_mismatch"
    r = _row(v); r["financial_rip_v3_payload"] = {**r["financial_rip_v3_payload"], "packCost": None}
    assert _reason(r, _loader(v)) == "payload_pack_cost_invalid"


def test_audit_classifies_changed_opening_cost_and_altered_v4_component_as_different_authority():
    v = _vector()
    r = _row(v)
    r["financial_rip_v3_payload"] = {**r["financial_rip_v3_payload"], "packCost": COST + 1.0}
    r["pack_cost"] = COST + 1.0                                  # consistent metadata, wrong economic input
    assert audit.audit_row(r, None, artifact_loader=_loader(v))["classification"] == "C"
    r = _row(v)
    payload = copy.deepcopy(r["financial_rip_v3_payload"])
    payload["components"]["realistic_upside"]["score"] = float(payload["components"]["realistic_upside"]["score"]) + 3.0
    r["financial_rip_v3_payload"] = payload
    assert audit.audit_row(r, None, artifact_loader=_loader(v))["classification"] == "C"


def test_missing_artifact_is_unresolved_not_proven():
    v = _vector()

    def gone(client, run_id):
        raise RuntimeError("no artifact")
    rec = audit.audit_row(_row(v), None, artifact_loader=gone)
    assert rec["classification"] == "D" and rec["reason"] == "artifact_unavailable"
