"""Contract tests for the coordinated daily opening-analytics publication.

These pin the ordering guarantee the pipeline previously lacked: simulations run
and are VERIFIED before the run may describe Opening Profit vs Cost as current.
No subprocess is ever launched — the command runners are injected.
"""

import pytest

from backend.scripts import run_daily_opening_publication as orchestrator
from backend.scripts.run_daily_opening_publication import (
    EXIT_CANNOT_START,
    EXIT_FAILED,
    EXIT_OK,
    PublicationSummary,
    orchestrate,
)
from backend.db.services.publication_gate import GATE_DEFERRED_EXIT_CODE

MARKET_DATE = "2026-08-01"
STALE_DATE = "2026-07-27"


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
    """Replays table rows; ``history_pages`` lets a run change between reads."""

    def __init__(self, *, sets_rows, history_pages, summary_rows):
        self._sets = sets_rows
        self._history_pages = list(history_pages)
        self._summary = summary_rows
        self.history_reads = 0

    def table(self, name):
        if name == "sets":
            return _Query(self._sets)
        if name == "simulation_run_summary":
            return _Query(self._summary)
        if name == "calculation_history_trend":
            index = min(self.history_reads, len(self._history_pages) - 1)
            self.history_reads += 1
            return _Query(self._history_pages[index])
        return _Query([])


def _history(date, run_id="run-a", set_id="id-a"):
    return [
        {
            "target_id": set_id,
            "snapshot_date": date,
            "calculation_run_id": run_id,
            "simulated_mean_pack_value_vs_pack_cost": 0.51,
            "simulated_median_pack_value_vs_pack_cost": 0.14,
        }
    ]


@pytest.fixture
def patched(monkeypatch):
    """Record the ordered sequence of orchestration steps."""
    calls = []

    def fake_resolve(_client, explicit):
        return (explicit or MARKET_DATE), None

    def fake_run_sims(set_keys, **_kwargs):
        calls.append(("simulate", list(set_keys)))
        return [
            orchestrator.SimulationOutcome(canonical_key=key, succeeded=True)
            for key in set_keys
        ]

    def fake_refresh(**_kwargs):
        calls.append(("refresh", []))
        return 0

    import backend.scripts.audit_opening_analytics_publication as audit_module

    monkeypatch.setattr(audit_module, "resolve_market_date", fake_resolve)
    monkeypatch.setattr(orchestrator, "run_simulations_for_sets", fake_run_sims)
    monkeypatch.setattr(orchestrator, "refresh_public_snapshots", fake_refresh)
    return calls


def _client(history_pages):
    return _Client(
        sets_rows=[{"id": "id-a", "name": "Alpha", "canonical_key": "alpha"}],
        history_pages=history_pages,
        summary_rows=[{"calculation_run_id": "run-a"}],
    )


def _orchestrate(client, **kwargs):
    # canonical_keys is threaded through the gate; restrict to the fake set.
    import backend.db.services.opening_simulation_gate as gate

    original = gate.supported_opening_set_keys
    gate.supported_opening_set_keys = lambda: ("alpha",)
    try:
        return orchestrate(client, **kwargs)
    finally:
        gate.supported_opening_set_keys = original


def test_simulations_run_before_snapshots_are_built(patched):
    # Stale first read, current after the simulation.
    client = _client([_history(STALE_DATE), _history(MARKET_DATE)])
    summary = _orchestrate(client)

    assert [step for step, _ in patched] == ["simulate", "refresh"], "simulate must precede refresh"
    assert patched[0][1] == ["alpha"]
    assert summary.exit_code == EXIT_OK
    assert summary.verification_passed is True
    assert summary.snapshot_publication_status == "published"


def test_a_set_already_current_is_skipped_so_reruns_do_no_work(patched):
    client = _client([_history(MARKET_DATE)])
    summary = _orchestrate(client)

    assert patched[0] == ("simulate", []), "a current set must not be re-simulated"
    assert summary.exit_code == EXIT_OK
    assert any(entry["set"] == "alpha" and "already current" in entry["reason"] for entry in summary.skipped)


def test_rerunning_the_same_market_date_is_idempotent(patched):
    client = _client([_history(MARKET_DATE)])
    first = _orchestrate(client)
    second = _orchestrate(client)

    assert first.exit_code == second.exit_code == EXIT_OK
    assert all(step_sets == [] for step, step_sets in patched if step == "simulate")


def test_a_simulation_failure_prevents_claiming_full_freshness(monkeypatch, patched):
    def failing_sims(set_keys, **_kwargs):
        patched.append(("simulate", list(set_keys)))
        return [
            orchestrator.SimulationOutcome(canonical_key=key, succeeded=False, reason="boom")
            for key in set_keys
        ]

    monkeypatch.setattr(orchestrator, "run_simulations_for_sets", failing_sims)
    # Still stale on the verification read — the simulation did not land.
    client = _client([_history(STALE_DATE), _history(STALE_DATE)])
    summary = _orchestrate(client)

    assert summary.exit_code == EXIT_FAILED
    assert summary.simulation_failed == 1
    assert summary.verification_passed is False
    assert "NOT current" in summary.error


def test_verification_failure_alone_fails_even_when_simulations_reported_success(patched):
    # The runner exited 0 but no row landed for the market date. Trusting the
    # exit code alone is exactly how a frozen series looks healthy.
    client = _client([_history(STALE_DATE), _history(STALE_DATE)])
    summary = _orchestrate(client)

    assert summary.simulation_failed == 0
    assert summary.verification_passed is False
    assert summary.exit_code == EXIT_FAILED
    assert summary.latest_simulation_date_by_set["alpha"] == STALE_DATE


def test_a_missing_summary_join_blocks_publication(patched):
    client = _Client(
        sets_rows=[{"id": "id-a", "name": "Alpha", "canonical_key": "alpha"}],
        history_pages=[_history(MARKET_DATE), _history(MARKET_DATE)],
        summary_rows=[],  # the join target is absent
    )
    summary = _orchestrate(client)
    assert summary.verification_passed is False
    assert summary.exit_code == EXIT_FAILED


def test_unsupported_sets_are_skipped_with_a_reason(patched):
    client = _client([_history(STALE_DATE), _history(STALE_DATE)])
    summary = _orchestrate(client, unsupported_keys=["alpha"])

    assert summary.exit_code == EXIT_OK
    assert summary.verification_passed is True
    assert summary.skipped == [
        {"set": "alpha", "reason": "explicitly excepted from opening analytics"}
    ]
    assert patched[0] == ("simulate", [])


def test_an_unresolvable_market_date_cannot_start(monkeypatch):
    import backend.scripts.audit_opening_analytics_publication as audit_module

    monkeypatch.setattr(
        audit_module, "resolve_market_date", lambda *_a, **_k: (None, "no promoted batch")
    )
    summary = _orchestrate(_client([_history(MARKET_DATE)]))
    assert summary.exit_code == EXIT_CANNOT_START
    assert "no promoted batch" in summary.error


def test_a_deferred_cohort_propagates_exit_3(monkeypatch, patched):
    monkeypatch.setattr(
        orchestrator, "refresh_public_snapshots", lambda **_k: GATE_DEFERRED_EXIT_CODE
    )
    client = _client([_history(STALE_DATE), _history(MARKET_DATE)])
    summary = _orchestrate(client)

    assert summary.exit_code == GATE_DEFERRED_EXIT_CODE
    assert summary.snapshot_publication_status == "deferred_cohort_not_ready"


def test_a_snapshot_build_failure_fails_the_run(monkeypatch, patched):
    monkeypatch.setattr(orchestrator, "refresh_public_snapshots", lambda **_k: 7)
    client = _client([_history(STALE_DATE), _history(MARKET_DATE)])
    summary = _orchestrate(client)

    assert summary.exit_code == EXIT_FAILED
    assert summary.snapshot_publication_status == "failed_exit_7"


def test_summary_reports_every_required_field(patched):
    client = _client([_history(STALE_DATE), _history(MARKET_DATE)])
    text = "\n".join(_orchestrate(client).lines())

    for expected in (
        f"market_date={MARKET_DATE}",
        "eligible_sets=",
        "simulations_succeeded=",
        "simulations_failed=",
        "skipped_sets=",
        "latest_simulation_date_by_set:",
        "snapshot_publication_status=",
        "verification_passed=",
        "exit_code=",
    ):
        assert expected in text, f"summary is missing {expected!r}"


def test_the_market_date_is_never_taken_from_wall_clock():
    from pathlib import Path

    source = Path(orchestrator.__file__).read_text(encoding="utf-8")
    assert "datetime.now()" not in source
    assert "date.today()" not in source


def test_snapshot_builders_are_not_asked_to_run_simulations():
    # The separation of responsibilities this incident depended on: publication
    # republishes, it never computes.
    from pathlib import Path

    source = Path(orchestrator.__file__).read_text(encoding="utf-8")
    assert "refresh_stale_public_snapshots.py" in source
    assert "run_all_v2_sets.py" in source
    # The refresh command must not be handed a simulation flag.
    assert "--simulate" not in source


def test_default_summary_is_a_failure_until_proven_otherwise():
    assert PublicationSummary().exit_code == EXIT_CANNOT_START
    assert PublicationSummary().verification_passed is False
