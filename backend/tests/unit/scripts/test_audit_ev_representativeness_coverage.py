"""Contract tests for the EV Representativeness coverage audit.

Pins the classification the audit must produce for a current opening cohort:
healthy, legitimate-no-headline (exceeds_search_cap is NOT a failure), missing,
wrong-run (stale research keyed to a superseded calculation_run_id) and
version-mismatch. No live Supabase access - deterministic fake client rows
only, and no curve/session tables are ever queried.
"""

from __future__ import annotations

from backend.research.ev_representativeness.finite_sample import HORIZON_EXCEEDS_CAP
from backend.research.ev_representativeness.version import EV_REPRESENTATIVENESS_VERSION
from backend.scripts.audit_ev_representativeness_coverage import run_audit

MARKET_DATE = "2026-08-01"


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows):
        self._rows = rows

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def in_(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def execute(self):
        return _Result(self._rows)


class _Client:
    def __init__(self, tables):
        self._tables = tables

    def table(self, name):
        return _Query(self._tables.get(name, []))


def _set_row(key, set_id):
    return {"id": set_id, "name": key.title(), "canonical_key": key}


def _history_row(set_id, run_id, *, mean=1.2, median=0.8):
    return {
        "target_id": set_id,
        "snapshot_date": MARKET_DATE,
        "calculation_run_id": run_id,
        "simulated_mean_pack_value_vs_pack_cost": mean,
        "simulated_median_pack_value_vs_pack_cost": median,
    }


def _summary_row(run_id, set_id, *, version=EV_REPRESENTATIVENESS_VERSION, status="resolved"):
    return {
        "calculation_run_id": run_id,
        "set_id": set_id,
        "research_method_version": version,
        "horizon_r80_c80_status": status,
    }


def _client(*, sets_rows, history_rows, summary_rows, run_summary_rows=None):
    run_summary_rows = run_summary_rows if run_summary_rows is not None else [
        {"calculation_run_id": row["calculation_run_id"]} for row in history_rows
    ]
    return _Client(
        {
            "sets": sets_rows,
            "calculation_history_trend": history_rows,
            "simulation_run_summary": run_summary_rows,
            "ev_representativeness_run_summary": summary_rows,
        }
    )


def test_current_run_with_resolved_horizon_is_healthy():
    client = _client(
        sets_rows=[_set_row("alpha", "set-a")],
        history_rows=[_history_row("set-a", "run-1")],
        summary_rows=[_summary_row("run-1", "set-a", status="resolved")],
    )
    report = run_audit(client, market_date=MARKET_DATE, canonical_keys=["alpha"])
    assert report.error is None
    assert report.healthy == ["alpha"]
    assert report.unhealthy_count == 0


def test_exceeds_search_cap_is_legitimate_not_broken():
    client = _client(
        sets_rows=[_set_row("alpha", "set-a")],
        history_rows=[_history_row("set-a", "run-1")],
        summary_rows=[_summary_row("run-1", "set-a", status=HORIZON_EXCEEDS_CAP)],
    )
    report = run_audit(client, market_date=MARKET_DATE, canonical_keys=["alpha"])
    assert report.legitimate_no_headline == ["alpha"]
    assert report.unhealthy_count == 0


def test_no_research_row_for_current_run_is_missing():
    client = _client(
        sets_rows=[_set_row("alpha", "set-a")],
        history_rows=[_history_row("set-a", "run-1")],
        summary_rows=[],
    )
    report = run_audit(client, market_date=MARKET_DATE, canonical_keys=["alpha"])
    assert report.missing == ["alpha"]
    assert report.unhealthy_count == 1


def test_research_keyed_to_a_superseded_run_is_wrong_run_not_healthy():
    client = _client(
        sets_rows=[_set_row("alpha", "set-a")],
        history_rows=[_history_row("set-a", "run-2")],
        summary_rows=[_summary_row("run-1", "set-a", status="resolved")],
    )
    report = run_audit(client, market_date=MARKET_DATE, canonical_keys=["alpha"])
    assert report.wrong_run == ["alpha"]
    assert report.missing == []
    assert report.unhealthy_count == 1


def test_research_under_a_different_method_version_is_version_mismatch():
    client = _client(
        sets_rows=[_set_row("alpha", "set-a")],
        history_rows=[_history_row("set-a", "run-1")],
        summary_rows=[_summary_row("run-1", "set-a", version="ev_representativeness_v0")],
    )
    report = run_audit(client, market_date=MARKET_DATE, canonical_keys=["alpha"])
    assert report.version_mismatch == ["alpha"]
    assert report.unhealthy_count == 1
