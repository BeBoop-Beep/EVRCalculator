"""Overall V14 per-row finalization and the inactive generic-ledger candidate."""
import pytest

from backend.calculations.evr.financial_rip_v5_config import FINANCIAL_RIP_V5_VERSION
from backend.db.services import overall_v14_candidate_publication as cand
from backend.db.services.sealed_product_financial_v5_finalization_service import overall_rip_v14_for
from backend.desirability import scoring_config as sc
from backend.desirability.chase_accessibility import CHASE_ACCESSIBILITY_VERSION
from backend.desirability.chase_accessibility_overall_score import chase_accessibility_overall_score
from backend.desirability.weighted_rip import compute_overall_rip_v12

COLLECTOR_V5 = sc.overall_rip_v14_required_collector_appeal_version()


def _row(i=1, score=50.0, run="run-a", **kw):
    return dict(id=f"00000000-0000-0000-0000-{i:012d}", sealed_product_id=f"00000000-0000-0000-0000-{100 + i:012d}",
                set_id="set-a", calculation_run_id=run, financial_rip_v5_score=score,
                financial_rip_v5_status="ready", financial_rip_v5_rankable=True,
                financial_rip_v5_version=FINANCIAL_RIP_V5_VERSION, financial_rip_v4_score=45.0,
                financial_rip_v4_version=sc.FINANCIAL_RIP_V4_VERSION, **kw)


ACC = dict(calculation_run_id="run-a", status="ready", accessibility=0.01, version=CHASE_ACCESSIBILITY_VERSION)


def test_v14_formula_exact_and_v12_unchanged():
    r = overall_rip_v14_for(_row(score=50.0), 60.0, COLLECTOR_V5, ACC, expected_run_id="run-a")
    a = chase_accessibility_overall_score(0.01)
    assert r["status"] == "ready" and r["score"] == round(.86 * 50.0 + .04 * a + .10 * 60.0, 4)
    assert r["version"] == sc.OVERALL_RIP_V14_VERSION and r["weights"] == {
        "financial_rip": .86, "chase_accessibility": .04, "collector_appeal": .10}
    v12 = compute_overall_rip_v12(45.0, 0.01, 60.0)
    assert v12["version"] == sc.OVERALL_RIP_V12_VERSION and v12["score"] != r["score"]
    assert sc.CANONICAL_OVERALL_RIP_VERSION == sc.OVERALL_RIP_V12_VERSION  # no canonical selection


@pytest.mark.parametrize("kw", [
    dict(financial_rip_v5_version=sc.FINANCIAL_RIP_V4_VERSION),
    dict(financial_rip_v5_score=None),
    dict(financial_rip_v5_status="unavailable"),
    dict(financial_rip_v5_rankable=False)])
def test_v4_or_unavailable_financial_is_refused_no_fallback(kw):
    row = dict(_row(), **kw)
    r = overall_rip_v14_for(row, 60.0, COLLECTOR_V5, ACC, expected_run_id="run-a")
    assert r["score"] is None and r["rankable"] is False and r["missingInputs"] == ["financial_rip_v5"]
    only_v4 = {k: v for k, v in _row().items() if not k.startswith("financial_rip_v5")}
    assert overall_rip_v14_for(only_v4, 60.0, COLLECTOR_V5, ACC, expected_run_id="run-a")["score"] is None


def test_same_run_chase_accepted_stale_run_refused_wrong_version_refused():
    assert overall_rip_v14_for(_row(), 60.0, COLLECTOR_V5, ACC, expected_run_id="run-a")["score"] is not None
    stale = overall_rip_v14_for(_row(), 60.0, COLLECTOR_V5, dict(ACC, calculation_run_id="yesterday"),
                                expected_run_id="run-a")
    assert stale["score"] is None and stale["status"] == "unavailable_authority_mismatch"
    wrong = overall_rip_v14_for(_row(), 60.0, COLLECTOR_V5, dict(ACC, version="chase_accessibility_v9"),
                                expected_run_id="run-a")
    assert wrong["score"] is None and wrong["rankable"] is False
    assert overall_rip_v14_for(_row(), 60.0, COLLECTOR_V5, None, expected_run_id="run-a")["score"] is None
    assert overall_rip_v14_for(_row(), 60.0, COLLECTOR_V5, dict(ACC, status="pending"), expected_run_id="run-a")["score"] is None
    assert overall_rip_v14_for(_row(), 60.0, COLLECTOR_V5, ACC, expected_run_id=None)["score"] is None


def test_collector_v5_accepted_other_versions_refused():
    assert overall_rip_v14_for(_row(), 60.0, COLLECTOR_V5, ACC, expected_run_id="run-a")["score"] is not None
    for bad in ("collector_appeal_v7_x", None):
        r = overall_rip_v14_for(_row(), 60.0, bad, ACC, expected_run_id="run-a")
        assert r["score"] is None and r["rankable"] is False
    assert overall_rip_v14_for(_row(), None, COLLECTOR_V5, ACC, expected_run_id="run-a")["score"] is None


# ------------------------------------------------------------------ candidate generation

def _cohort(n=3, break_row=None):
    rows = [_row(i, score=60.0 - i) for i in range(1, n + 1)]
    if break_row is not None:
        rows[break_row]["financial_rip_v5_score"] = None
    return dict(rows=rows, collector={"set-a": {"score": 60.0, "version": COLLECTOR_V5}},
                acc={"set-a": ACC}, runs={"set-a": "run-a"})


def _build(c):
    return cand.build_v14_candidate(c["rows"], market_date="2026-09-14", collector_by_set_id=c["collector"],
                                    accessibility_by_set_id=c["acc"], run_id_by_set_id=c["runs"])


def test_candidate_is_generic_ranked_tiered_and_identifies_all_inputs():
    c = _build(_cohort())
    run = c["run"]
    assert run["model_version"] == sc.OVERALL_RIP_V14_VERSION and run["status"] == "staged"
    assert (run["financial_version"], run["chase_version"], run["collector_version"]) == (
        FINANCIAL_RIP_V5_VERSION, CHASE_ACCESSIBILITY_VERSION, COLLECTOR_V5)
    assert run["expected_row_count"] == 3 and len(run["cohort_fingerprint"]) == 64 and len(run["formula_fingerprint"]) == 64
    assert [r["rank"] for r in sorted(c["rows"], key=lambda r: r["rank"])] == [1, 2, 3]
    assert all(r["tier"] and r["eligibility_state"] == "ready" and r["component_lineage"]["chaseRunId"] == "run-a"
               for r in c["rows"])
    assert cand.validate_v14_candidate(c)["passed"] is True and c["cohortComplete"] is True


def test_partial_v14_cohort_cannot_pass_validation():
    c = _build(_cohort(break_row=1))
    v = cand.validate_v14_candidate(c)
    assert c["cohortComplete"] is False and v["passed"] is False
    assert any(p.startswith("incomplete_v14_cohort") for p in v["problems"])
    unavailable = [r for r in c["rows"] if r["eligibility_state"] != "ready"]
    assert len(unavailable) == 1 and unavailable[0]["score"] is None and unavailable[0]["rank"] is None


class FakeTable:
    def __init__(self, client, name):
        self.client, self.name, self.op, self.payload, self.filters = client, name, None, None, []

    def select(self, *a, **k):
        self.op = "select"
        return self

    def insert(self, payload):
        self.op, self.payload = "insert", payload
        return self

    def update(self, payload):
        self.op, self.payload = "update", payload
        return self

    def eq(self, k, v):
        self.filters.append((k, v))
        return self

    def execute(self):
        self.client.calls.append((self.name, self.op, self.payload, tuple(self.filters)))
        if self.op == "select":
            return type("R", (), {"data": self.client.existing.get(self.name, [])})()
        rows = self.payload if isinstance(self.payload, list) else [self.payload]
        return type("R", (), {"data": [{"id": f"id-{self.name}-{len(self.client.calls)}", **r} for r in rows]})()


class FakeClient:
    def __init__(self, existing=None):
        self.calls, self.existing, self.rpcs = [], existing or {}, []

    def table(self, name):
        return FakeTable(self, name)

    def rpc(self, *a, **k):
        self.rpcs.append(a)
        raise AssertionError("no RPC may be called")


def test_writing_a_candidate_never_touches_the_current_pointer_or_promote_rpc():
    client = FakeClient()
    out = cand.write_v14_candidate(client, _build(_cohort()))
    assert out["activated"] is False and out["created"] is True
    tables = {t for t, *_ in client.calls}
    assert cand.CURRENT_POINTER not in tables and not client.rpcs
    runs_written = [p for t, op, p, _ in client.calls if t == cand.RUNS and op == "insert"]
    assert runs_written and all(p["status"] == "staged" for p in runs_written)
    final = [p for t, op, p, _ in client.calls if t == cand.RUNS and op == "update"][-1]
    # no set-page generation yet -> not promotable, stays staged
    assert final["status"] == "staged" and final["validation_json"]["promotable"] is False
    assert "set_page_generation_not_built" in final["validation_json"]["problems"]


def test_candidate_with_set_page_projection_becomes_validated_but_still_inactive():
    client = FakeClient()

    def proj(rows):
        return [dict(entity_id="set-a", projection_json={"overallModelVersion": sc.OVERALL_RIP_V14_VERSION})]
    out = cand.write_v14_candidate(client, _build(_cohort()), set_page_projection_fn=proj)
    assert out["status"] == "validated" and out["validation"]["promotable"] is True and out["activated"] is False
    assert cand.CURRENT_POINTER not in {t for t, *_ in client.calls} and not client.rpcs


def test_partial_cohort_write_never_validates_even_with_a_set_page():
    client = FakeClient()
    out = cand.write_v14_candidate(client, _build(_cohort(break_row=0)),
                                   set_page_projection_fn=lambda rows: [dict(entity_id="set-a", projection_json={})])
    assert out["status"] == "staged" and out["validation"]["passed"] is False


def test_existing_published_run_is_never_rewritten_and_existing_candidate_is_idempotent():
    with pytest.raises(ValueError, match="already-published"):
        cand.write_v14_candidate(FakeClient({cand.RUNS: [{"id": "x", "status": "published"}]}), _build(_cohort()))
    again = cand.write_v14_candidate(FakeClient({cand.RUNS: [{"id": "x", "status": "staged"}]}), _build(_cohort()))
    assert again["created"] is False and again["publicationRunId"] == "x" and again["activated"] is False
