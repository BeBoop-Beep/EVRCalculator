import backend.alerts.pipeline_alerts as alerts


def _capture(monkeypatch):
    calls = []
    monkeypatch.setattr(alerts, "queue_alert", lambda *a, **k: calls.append((a, k)) or {"id": "1"})
    return calls


def test_major_pipeline_helpers_have_stable_types_and_dedupe(monkeypatch):
    calls = _capture(monkeypatch)
    alerts.alert_daily_batch_created(market_date="2026-08-25", batch_id=1,
        expected_set_count=163, queued_set_count=163, trigger_source="scheduled", runtime_git_sha="abcdef")
    alerts.alert_scrape_batch_complete(market_date="2026-08-25", batch_id=1,
        succeeded_set_count=163, expected_set_count=163)
    alerts.alert_market_quality(market_date="2026-08-25", status="READY",
        qualifying_set_count=22, cohort_set_count=22)
    alerts.alert_market_index(market_date="2026-08-25", raw_latest_date="2026-08-25",
        top10_latest_date="2026-08-25")
    alerts.alert_global_market(market_date="2026-08-25", row_market_date="2026-08-25",
        payload_market_date="2026-08-25", overview_market_date="2026-08-25", set_count=22)
    alerts.alert_market_audit(market_date="2026-08-25", passed=True)
    alerts.alert_market_pipeline_complete(market_date="2026-08-25", scrape_progress="163/163",
        quality_progress="22/22", raw_index_date="2026-08-25", top10_index_date="2026-08-25",
        global_market_date="2026-08-25")
    assert [call[0][0] for call in calls] == [
        "pokemon_daily_batch_created", "pokemon_scrape_batch_complete",
        "pokemon_market_quality_ready", "pokemon_market_index_published",
        "pokemon_global_market_published", "pokemon_market_audit_passed",
        "pokemon_market_pipeline_complete"]
    assert len({call[1]["dedupe_key"] for call in calls}) == len(calls)
    assert "Public Market is current" in calls[-1][0][2]


def test_failure_helpers_name_exact_blockage(monkeypatch):
    calls = _capture(monkeypatch)
    alerts.alert_set_scrape_failed(market_date="2026-08-25", batch_id=1, queue_job_id=2,
        canonical_key="blackBolt", attempts=3, max_attempts=3, error_code="exhausted",
        retryable=False, error_summary="provider failed")
    alerts.alert_market_quality(market_date="2026-08-25", status="INCOMPLETE",
        qualifying_set_count=19, cohort_set_count=22, missing_canonical_keys=["blackBolt"],
        previous_accepted_market_date="2026-08-24")
    alerts.alert_market_index(market_date="2026-08-25", raw_latest_date="2026-08-25",
        top10_latest_date="2026-08-24")
    alerts.alert_global_market(market_date="2026-08-25", row_market_date="2026-08-25",
        payload_market_date="2026-08-25", overview_market_date="2026-08-24")
    alerts.alert_market_audit(market_date="2026-08-25", passed=False,
        failing_surfaces=["Top10 Index"], expected_date="2026-08-25")
    assert [call[0][0] for call in calls] == ["pokemon_set_scrape_failed",
        "pokemon_market_quality_blocked", "pokemon_market_index_failed",
        "pokemon_global_market_failed", "pokemon_market_audit_failed"]
    assert "manual action required" in calls[0][0][2]
    assert "blackBolt" in calls[1][0][2]
    assert "2026-08-24" in calls[2][0][2]


def test_transient_attempt_is_not_a_helper_call_and_success_can_be_disabled(monkeypatch):
    calls = _capture(monkeypatch)
    monkeypatch.setenv("PIPELINE_SUCCESS_ALERTS", "false")
    assert alerts.alert_daily_batch_created(market_date="2026-08-25", batch_id=1,
        expected_set_count=1, queued_set_count=1, trigger_source="scheduled", runtime_git_sha=None) is None
    assert calls == []


def test_simulation_phase_is_visibly_distinct(monkeypatch):
    calls = _capture(monkeypatch)
    for state in ("started", "failed", "complete", "publication_failed"):
        alerts.alert_simulation_stage(market_date="2026-08-25", state=state, set_count=22)
    assert [call[0][0] for call in calls] == ["pokemon_simulation_pipeline_started",
        "pokemon_simulation_pipeline_failed", "pokemon_full_publication_complete",
        "pokemon_full_publication_failed"]
