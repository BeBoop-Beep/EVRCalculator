"""Set-target Financial V5 / Overall V14 blocks (release V14): exact authority, no fallback."""
import numpy as np

from backend.db.services import set_rankings_v14 as sr14
from backend.desirability.chase_accessibility_overall_score import chase_accessibility_overall_score
from backend.desirability.scoring_config import (
    OVERALL_RIP_V14_VERSION,
    overall_rip_v14_required_chase_accessibility_version,
    overall_rip_v14_required_collector_appeal_version,
)
from backend.tests.unit.db.services.test_set_financial_authority import COST, RUN, _loader, _row, _vector

CHASE_V = overall_rip_v14_required_chase_accessibility_version()
COLLECTOR_V = overall_rip_v14_required_collector_appeal_version()


def _acc(run=RUN, status="ready", version=CHASE_V, raw=0.35):
    return {"calculation_run_id": run, "status": status, "version": version, "accessibility": raw}


def _blocks(row=None, *, acc=None, score=61.0, collector_version=COLLECTOR_V, run=RUN, loader=None):
    v = _vector()
    return sr14.build_v14_target_blocks(
        {"calculation_run_id": run, "target_id": "set-1"}, authority_row=_row(v) if row is None else row,
        client=None, collector_score=score, collector_version=collector_version,
        accessibility_row=_acc() if acc is None else acc, artifact_loader=loader or _loader(v))


def test_ready_blocks_use_v5_from_the_exact_run_vector_and_the_locked_v14_blend():
    out = _blocks()
    fin, overall = out["financialRipV5"], out["overallRipV14"]
    assert fin["status"] == "ready" and fin["version"] == fin["scoreVersion"]
    assert fin["source"]["calculationRunId"] == RUN and fin["source"]["packCost"] == COST
    expected = 0.86 * fin["score"] + 0.04 * chase_accessibility_overall_score(0.35, k=0.002) + 0.10 * 61.0
    assert overall["status"] == "ready" and overall["version"] == OVERALL_RIP_V14_VERSION
    assert abs(overall["score"] - round(expected, 4)) < 1e-3
    assert set(out) == {"financialRipV5", "overallRipV14"}       # never V4 / V12 keys


def test_missing_set_authority_makes_the_target_unavailable_with_no_v4_fallback():
    out = sr14.build_v14_target_blocks({"calculation_run_id": RUN}, authority_row=None, client=None, collector_score=61.0,
                                       collector_version=COLLECTOR_V, accessibility_row=_acc())
    assert out["financialRipV5"]["status"] == "unavailable" and out["financialRipV5"]["score"] is None
    assert out["overallRipV14"]["score"] is None and out["overallRipV14"]["missingInputs"] == ["financial_rip_v5"]


def test_authority_built_from_the_wrong_run_is_refused():
    v = _vector()
    out = _blocks(row=_row(v, run="other-run"), loader=_loader(v, run="other-run"))
    assert out["financialRipV5"]["status"] == "unavailable"
    assert out["financialRipV5"]["statusReason"] == "authority_run_mismatch"
    assert out["overallRipV14"]["score"] is None


def test_wrong_run_chase_row_and_wrong_input_versions_are_refused_not_renormalized():
    mismatch = _blocks(acc=_acc(run="another-run"))["overallRipV14"]
    assert mismatch["score"] is None and mismatch["status"] == "unavailable_authority_mismatch"
    assert _blocks(acc=_acc(status="pending"))["overallRipV14"]["score"] is None
    assert _blocks(collector_version="collector_appeal_ca7_v1")["overallRipV14"]["score"] is None
    assert _blocks(acc=_acc(version="chase_v0"))["overallRipV14"]["score"] is None
    assert _blocks(score=None)["overallRipV14"]["score"] is None


def test_read_set_authority_rows_is_read_only_and_keyed_by_run():
    class Q:
        def __init__(self, rows): self.rows = rows
        def select(self, *_): return self
        def in_(self, *_): return self
        def execute(self): return type("R", (), {"data": self.rows})()

    class C:
        def table(self, name):
            return Q([{"set_id": "s", "set_name": "n", "calculation_run_id": RUN, "simulation_count": 3}]
                     if name.endswith("__base") else
                     [{"calculation_run_id": RUN, "financial_rip_v3_payload": {"packCost": 1}}])
    rows = sr14.read_set_authority_rows(C(), [RUN, RUN, None])
    assert list(rows) == [RUN] and rows[RUN]["financial_rip_v3_payload"] == {"packCost": 1}
