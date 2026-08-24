"""Dispatcher/worker orchestration tests (expanded for production reliability).

The worker must NOT create a batch, must claim under a lease with a worker id,
must finalize queue + diagnostics transactionally, and must record scheduled runs
as trigger_source=scheduled.
"""

import os

import pytest

import backend.scripts.run_next_scrape_job as dispatcher


@pytest.fixture(autouse=True)
def _base_patches(monkeypatch):
    monkeypatch.setattr(dispatcher, "_load_backend_env", lambda: None)
    monkeypatch.setattr(dispatcher, "_apply_safe_runtime_defaults", lambda: None)
    monkeypatch.delenv("SCRAPE_TRIGGER_SOURCE", raising=False)
    monkeypatch.setenv("SCRAPE_DRAIN_MAX_JOBS", "1")
    monkeypatch.setattr(dispatcher, "_install_signal_handlers", lambda: None)
    monkeypatch.setattr(dispatcher, "_market_date_iso", lambda: "2026-07-18")
    yield


def _capture_finalize(monkeypatch):
    calls = []
    monkeypatch.setattr(dispatcher, "finalize_scrape_job",
                        lambda *a, **k: calls.append((a, k)) or {"ok": True})
    return calls


def test_worker_does_not_create_a_batch_and_claims_with_lease(monkeypatch):
    claim_kwargs = {}

    def fake_claim(worker_id=None, lease_seconds=None, expected_market_date=None):
        claim_kwargs["worker_id"] = worker_id
        claim_kwargs["lease_seconds"] = lease_seconds
        claim_kwargs["expected_market_date"] = expected_market_date
        return None  # empty queue

    monkeypatch.setattr(dispatcher, "claim_next_scrape_job", fake_claim)
    idle = {"called": False}
    monkeypatch.setattr(dispatcher, "_run_idle_completion_check",
                        lambda *_args, **_kwargs: idle.__setitem__("called", True))
    # No enqueue/create-batch symbol should be referenced by the worker at all.
    assert not hasattr(dispatcher, "enqueue_missing_scrape_jobs_for_ready_sets")

    assert dispatcher.dispatch_next_scrape_job() == 0
    assert claim_kwargs["worker_id"]  # a worker id is supplied
    assert claim_kwargs["lease_seconds"] and claim_kwargs["lease_seconds"] >= 60
    assert claim_kwargs["expected_market_date"] == "2026-07-18"
    # idle queue triggers the batch completeness/repair check
    assert idle["called"] is True


def test_scheduled_dispatcher_records_trigger_source_scheduled(monkeypatch):
    monkeypatch.setattr(dispatcher, "claim_next_scrape_job", lambda **k: None)
    monkeypatch.setattr(dispatcher, "_run_idle_completion_check", lambda *_args: None)

    dispatcher.dispatch_next_scrape_job()

    assert os.environ.get("SCRAPE_TRIGGER_SOURCE") == "scheduled"


def test_manual_trigger_source_is_not_overridden(monkeypatch):
    monkeypatch.setenv("SCRAPE_TRIGGER_SOURCE", "manual")
    monkeypatch.setattr(dispatcher, "claim_next_scrape_job", lambda **k: None)
    monkeypatch.setattr(dispatcher, "_run_idle_completion_check", lambda *_args: None)

    dispatcher.dispatch_next_scrape_job()

    # setdefault must not clobber an operator's manual recovery override
    assert os.environ.get("SCRAPE_TRIGGER_SOURCE") == "manual"


def test_success_finalizes_completed_with_diag_and_metrics(monkeypatch):
    monkeypatch.setattr(dispatcher, "claim_next_scrape_job",
                        lambda **k: {"id": 101, "set_id": "set-a", "market_date": "2026-07-18"})
    monkeypatch.setattr(dispatcher, "get_set_by_id", lambda _sid: {"canonical_key": "blackBolt"})
    monkeypatch.setattr(dispatcher, "run_scraper",
                        lambda **k: {"sets_succeeded": 1, "sets_failed": 0,
                                     "diag_run_id": "diag-101", "market_date": "2026-07-18"})
    calls = _capture_finalize(monkeypatch)

    assert dispatcher.dispatch_next_scrape_job() == 0
    (args, kwargs) = calls[0]
    assert args[0] == 101
    assert kwargs["final_status"] == "completed"
    assert kwargs["succeeded"] == 1 and kwargs["failed"] == 0


def test_queue_success_metric_finalization_contract_is_unchanged(monkeypatch):
    report = {
        "results": [{"metadata": {
            "sourceCoverageRatio": 1.0,
            "acceptedVariantGroups": 9,
            "positiveNmObservationCount": 9,
            "notAQueueMetric": 123,
        }}],
        "http_requests_total": 4,
    }

    assert dispatcher._request_metrics(report) == {
        "http_requests_total": 4,
        "sourceCoverageRatio": 1.0,
        "acceptedVariantGroups": 9,
        "positiveNmObservationCount": 9,
    }


def test_scraper_failure_finalizes_failed(monkeypatch):
    monkeypatch.setattr(dispatcher, "claim_next_scrape_job",
                        lambda **k: {"id": 202, "set_id": "set-b", "market_date": "2026-07-18"})
    monkeypatch.setattr(dispatcher, "get_set_by_id", lambda _sid: {"canonical_key": "surgingSparks"})
    monkeypatch.setattr(dispatcher, "run_scraper",
                        lambda **k: {"sets_succeeded": 0, "sets_failed": 1,
                                     "results": [{"error": "zero cards"}],
                                     "diag_run_id": "diag-202"})
    calls = _capture_finalize(monkeypatch)

    assert dispatcher.dispatch_next_scrape_job() == 0
    (args, kwargs) = calls[0]
    assert args[0] == 202
    assert kwargs["final_status"] == "failed"


def test_scraper_exception_finalizes_failed(monkeypatch):
    monkeypatch.setattr(dispatcher, "claim_next_scrape_job",
                        lambda **k: {"id": 303, "set_id": "set-c", "market_date": "2026-07-18"})
    monkeypatch.setattr(dispatcher, "get_set_by_id", lambda _sid: {"canonical_key": "prismaticEvolutions"})

    def boom(**k):
        raise RuntimeError("network exploded")

    monkeypatch.setattr(dispatcher, "run_scraper", boom)
    calls = _capture_finalize(monkeypatch)

    assert dispatcher.dispatch_next_scrape_job() == 0
    (args, kwargs) = calls[0]
    assert args[0] == 303
    assert kwargs["final_status"] == "failed"
    assert "network exploded" in kwargs["error_summary"]


def test_worker_drains_jobs_sequentially_and_finalizes_before_next_claim(monkeypatch):
    monkeypatch.setenv("SCRAPE_DRAIN_MAX_JOBS", "10")
    jobs = [{"id": 1, "set_id": "a", "market_date": "2026-07-18"},
            {"id": 2, "set_id": "b", "market_date": "2026-07-18"}]
    events = []
    def claim(**_kwargs):
        events.append("claim")
        if len([event for event in events if event == "claim"]) == 2:
            assert events[-2] == "finalize-1"
        return jobs.pop(0) if jobs else None
    monkeypatch.setattr(dispatcher, "claim_next_scrape_job", claim)
    monkeypatch.setattr(dispatcher, "_process_claimed_job",
                        lambda job, _date: events.append(f"finalize-{job['id']}"))
    monkeypatch.setattr(dispatcher, "_run_idle_completion_check", lambda *_args: {"requeued": 0})
    assert dispatcher.dispatch_next_scrape_job() == 0
    assert events == ["claim", "finalize-1", "claim", "finalize-2", "claim"]


def test_idle_repair_requeue_continues_immediately(monkeypatch):
    monkeypatch.setenv("SCRAPE_DRAIN_MAX_JOBS", "10")
    claims = iter([None, {"id": 1, "set_id": "a", "market_date": "2026-07-18"}, None])
    processed = []
    repairs = iter([{"requeued": 1}, {"requeued": 0}])
    monkeypatch.setattr(dispatcher, "claim_next_scrape_job", lambda **_kwargs: next(claims))
    monkeypatch.setattr(dispatcher, "_process_claimed_job",
                        lambda job, _date: processed.append(job["id"]))
    monkeypatch.setattr(dispatcher, "_run_idle_completion_check", lambda *_args: next(repairs))
    dispatcher.dispatch_next_scrape_job()
    assert processed == [1]


def test_idle_repair_cannot_spin_forever(monkeypatch):
    monkeypatch.setenv("SCRAPE_DRAIN_MAX_JOBS", "10")
    claims = []
    monkeypatch.setattr(dispatcher, "claim_next_scrape_job",
                        lambda **_kwargs: claims.append(1) or None)
    monkeypatch.setattr(dispatcher, "_run_idle_completion_check", lambda *_args: {"requeued": 1})
    dispatcher.dispatch_next_scrape_job()
    assert len(claims) == dispatcher.MAX_CONSECUTIVE_EMPTY_REPAIRS


def test_max_jobs_guard_stops_after_current_job(monkeypatch):
    monkeypatch.setenv("SCRAPE_DRAIN_MAX_JOBS", "2")
    processed = []
    monkeypatch.setattr(dispatcher, "claim_next_scrape_job",
                        lambda **_kwargs: {"id": len(processed) + 1, "set_id": "a",
                                          "market_date": "2026-07-18"})
    monkeypatch.setattr(dispatcher, "_process_claimed_job",
                        lambda job, _date: processed.append(job["id"]))
    dispatcher.dispatch_next_scrape_job()
    assert processed == [1, 2]


def test_max_runtime_guard_stops_after_current_job(monkeypatch):
    monkeypatch.setenv("SCRAPE_DRAIN_MAX_JOBS", "10")
    monkeypatch.setenv("SCRAPE_DRAIN_MAX_RUNTIME_SECONDS", "1")
    ticks = iter([0.0, 2.0])
    monkeypatch.setattr(dispatcher.time, "monotonic", lambda: next(ticks))
    processed = []
    monkeypatch.setattr(dispatcher, "claim_next_scrape_job",
                        lambda **_kwargs: {"id": 1, "set_id": "a", "market_date": "2026-07-18"})
    monkeypatch.setattr(dispatcher, "_process_claimed_job",
                        lambda job, _date: processed.append(job["id"]))
    dispatcher.dispatch_next_scrape_job()
    assert processed == [1]


def test_phoenix_rollover_stops_before_second_claim(monkeypatch):
    monkeypatch.setenv("SCRAPE_DRAIN_MAX_JOBS", "10")
    dates = iter(["2026-07-18", "2026-07-18", "2026-07-19"])
    monkeypatch.setattr(dispatcher, "_market_date_iso", lambda: next(dates))
    claims = []
    monkeypatch.setattr(dispatcher, "claim_next_scrape_job",
                        lambda **_kwargs: claims.append(1) or
                        {"id": 1, "set_id": "a", "market_date": "2026-07-18"})
    monkeypatch.setattr(dispatcher, "_process_claimed_job", lambda *_args: None)
    dispatcher.dispatch_next_scrape_job()
    assert len(claims) == 1


def test_midnight_after_precheck_still_passes_start_date_to_atomic_claim(monkeypatch):
    monkeypatch.setenv("SCRAPE_DRAIN_MAX_JOBS", "10")
    dates = iter(["2026-08-19", "2026-08-19"])
    monkeypatch.setattr(dispatcher, "_market_date_iso", lambda: next(dates))
    observed = []
    def claim(**kwargs):
        # The database clock may now be Aug20; qualification remains the
        # explicit worker date rather than an implicit DB-current date.
        observed.append(kwargs["expected_market_date"])
        return None
    monkeypatch.setattr(dispatcher, "claim_next_scrape_job", claim)
    monkeypatch.setattr(dispatcher, "_run_idle_completion_check",
                        lambda market_date: {"market_date": market_date, "requeued": 0})
    dispatcher.dispatch_next_scrape_job()
    assert observed == ["2026-08-19"]


def test_wrong_market_date_claim_is_contract_violation_without_scrape_or_finalize(monkeypatch):
    calls = _capture_finalize(monkeypatch)
    monkeypatch.setattr(dispatcher, "run_scraper",
                        lambda **_kwargs: pytest.fail("wrong-date job must not scrape"))
    with pytest.raises(RuntimeError, match="date-qualified claim contract violation"):
        dispatcher._process_claimed_job(
            {"id": 9, "set_id": "a", "market_date": "2026-07-17"}, "2026-07-18")
    assert calls == []


def test_signal_stops_only_after_current_job(monkeypatch):
    monkeypatch.setenv("SCRAPE_DRAIN_MAX_JOBS", "10")
    processed = []
    monkeypatch.setattr(dispatcher, "claim_next_scrape_job",
                        lambda **_kwargs: {"id": 1, "set_id": "a", "market_date": "2026-07-18"})
    def process(job, _date):
        processed.append(job["id"])
        dispatcher._request_stop(15, None)
    monkeypatch.setattr(dispatcher, "_process_claimed_job", process)
    dispatcher.dispatch_next_scrape_job()
    assert processed == [1]


def test_failed_set_finalizes_then_worker_continues(monkeypatch):
    monkeypatch.setenv("SCRAPE_DRAIN_MAX_JOBS", "10")
    jobs = iter([{"id": 1, "set_id": "a", "market_date": "2026-07-18"},
                 {"id": 2, "set_id": "b", "market_date": "2026-07-18"}, None])
    monkeypatch.setattr(dispatcher, "claim_next_scrape_job", lambda **_kwargs: next(jobs))
    monkeypatch.setattr(dispatcher, "get_set_by_id",
                        lambda set_id: {"canonical_key": f"key-{set_id}"})
    reports = iter([
        {"sets_succeeded": 0, "sets_failed": 1,
         "run_abort_reason": "invalid_set_key_filter"},
        {"sets_succeeded": 1, "sets_failed": 0},
    ])
    monkeypatch.setattr(dispatcher, "run_scraper", lambda **_kwargs: next(reports))
    monkeypatch.setattr(dispatcher, "_run_idle_completion_check", lambda *_args: {"requeued": 0})
    calls = _capture_finalize(monkeypatch)
    dispatcher.dispatch_next_scrape_job()
    assert [call[0][0] for call in calls] == [1, 2]
    assert [call[1]["final_status"] for call in calls] == ["failed", "completed"]
