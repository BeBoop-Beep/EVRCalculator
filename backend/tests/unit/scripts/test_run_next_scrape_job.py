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
    yield


def _capture_finalize(monkeypatch):
    calls = []
    monkeypatch.setattr(dispatcher, "finalize_scrape_job",
                        lambda *a, **k: calls.append((a, k)) or {"ok": True})
    return calls


def test_worker_does_not_create_a_batch_and_claims_with_lease(monkeypatch):
    claim_kwargs = {}

    def fake_claim(worker_id=None, lease_seconds=None):
        claim_kwargs["worker_id"] = worker_id
        claim_kwargs["lease_seconds"] = lease_seconds
        return None  # empty queue

    monkeypatch.setattr(dispatcher, "claim_next_scrape_job", fake_claim)
    idle = {"called": False}
    monkeypatch.setattr(dispatcher, "_run_idle_completion_check",
                        lambda: idle.__setitem__("called", True))
    # No enqueue/create-batch symbol should be referenced by the worker at all.
    assert not hasattr(dispatcher, "enqueue_missing_scrape_jobs_for_ready_sets")

    assert dispatcher.dispatch_next_scrape_job() == 0
    assert claim_kwargs["worker_id"]  # a worker id is supplied
    assert claim_kwargs["lease_seconds"] and claim_kwargs["lease_seconds"] >= 60
    # idle queue triggers the batch completeness/repair check
    assert idle["called"] is True


def test_scheduled_dispatcher_records_trigger_source_scheduled(monkeypatch):
    monkeypatch.setattr(dispatcher, "claim_next_scrape_job", lambda **k: None)
    monkeypatch.setattr(dispatcher, "_run_idle_completion_check", lambda: None)

    dispatcher.dispatch_next_scrape_job()

    assert os.environ.get("SCRAPE_TRIGGER_SOURCE") == "scheduled"


def test_manual_trigger_source_is_not_overridden(monkeypatch):
    monkeypatch.setenv("SCRAPE_TRIGGER_SOURCE", "manual")
    monkeypatch.setattr(dispatcher, "claim_next_scrape_job", lambda **k: None)
    monkeypatch.setattr(dispatcher, "_run_idle_completion_check", lambda: None)

    dispatcher.dispatch_next_scrape_job()

    # setdefault must not clobber an operator's manual recovery override
    assert os.environ.get("SCRAPE_TRIGGER_SOURCE") == "manual"


def test_success_finalizes_completed_with_diag_and_metrics(monkeypatch):
    monkeypatch.setattr(dispatcher, "claim_next_scrape_job",
                        lambda **k: {"id": 101, "set_id": "set-a"})
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


def test_scraper_failure_finalizes_failed(monkeypatch):
    monkeypatch.setattr(dispatcher, "claim_next_scrape_job",
                        lambda **k: {"id": 202, "set_id": "set-b"})
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
                        lambda **k: {"id": 303, "set_id": "set-c"})
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
