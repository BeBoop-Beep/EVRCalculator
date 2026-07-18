"""Batch completion + cohort repair behavior (Phase 6)."""

import pytest

import backend.db.services.scrape_batch_service as svc


@pytest.fixture(autouse=True)
def _no_alert(monkeypatch):
    calls = []
    monkeypatch.setattr(svc, "alert_batch_incomplete", lambda *a, **k: calls.append((a, k)))
    return calls


def _batch(monkeypatch, active=0):
    monkeypatch.setattr(svc, "get_active_batch",
                        lambda md=None: {"id": 1, "market_date": "2026-07-18"})
    monkeypatch.setattr(svc, "count_active_scrape_jobs", lambda bid: active)


def test_complete_cohort_is_promoted_without_alert(monkeypatch, _no_alert):
    _batch(monkeypatch, active=0)
    monkeypatch.setattr(svc, "requeue_missing_scrape_jobs_for_batch", lambda bid: 0)
    monkeypatch.setattr(svc, "complete_scrape_batch_if_ready",
                        lambda bid: {"status": "complete", "missing_set_count": 0, "promoted": True})

    result = svc.run_batch_completion_and_repair()

    assert result["status"] == "complete"
    assert result["promoted"] is True
    assert _no_alert == []  # a complete batch never alerts


def test_missing_sets_are_automatically_requeued(monkeypatch, _no_alert):
    _batch(monkeypatch, active=0)
    monkeypatch.setattr(svc, "requeue_missing_scrape_jobs_for_batch", lambda bid: 3)
    # completion should not even be evaluated while repair produced new work
    monkeypatch.setattr(svc, "complete_scrape_batch_if_ready",
                        lambda bid: pytest.fail("should not complete while draining"))

    result = svc.run_batch_completion_and_repair()

    assert result["status"] == "running"
    assert result["requeued"] == 3


def test_partial_cohort_cannot_be_promoted_and_alerts(monkeypatch, _no_alert):
    _batch(monkeypatch, active=0)
    monkeypatch.setattr(svc, "requeue_missing_scrape_jobs_for_batch", lambda bid: 0)
    monkeypatch.setattr(svc, "complete_scrape_batch_if_ready",
                        lambda bid: {"status": "incomplete", "missing_set_count": 2,
                                     "promoted": False, "succeeded_set_count": 164,
                                     "failed_set_count": 2})
    monkeypatch.setattr(svc, "get_scrape_missing_sets",
                        lambda md: [{"canonical_key": "neoGenesis"}, {"canonical_key": "pokMonGO"}])

    result = svc.run_batch_completion_and_repair()

    assert result["status"] == "incomplete"
    assert result["promoted"] is False
    assert len(_no_alert) == 1  # actionable alert queued
    assert _no_alert[0][1]["missing_set_count"] == 2


def test_running_queue_skips_completion(monkeypatch, _no_alert):
    _batch(monkeypatch, active=5)
    monkeypatch.setattr(svc, "complete_scrape_batch_if_ready",
                        lambda bid: pytest.fail("must not complete while jobs are active"))

    result = svc.run_batch_completion_and_repair()

    assert result["status"] == "running"
    assert result["active"] == 5
    assert _no_alert == []


def test_no_batch_is_reported(monkeypatch, _no_alert):
    monkeypatch.setattr(svc, "get_active_batch", lambda md=None: None)
    result = svc.run_batch_completion_and_repair()
    assert result["ok"] is False
    assert result["reason"] == "no_batch"
