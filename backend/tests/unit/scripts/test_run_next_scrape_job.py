import backend.scripts.run_next_scrape_job as dispatcher


def test_dispatcher_syncs_missing_jobs_before_claiming(monkeypatch):
    call_order = []

    monkeypatch.setattr(dispatcher, "_load_backend_env", lambda: call_order.append("load_env"))
    monkeypatch.setattr(dispatcher, "_apply_safe_runtime_defaults", lambda: call_order.append("runtime_defaults"))
    monkeypatch.setattr(
        dispatcher,
        "enqueue_missing_scrape_jobs_for_ready_sets",
        lambda: call_order.append("enqueue_missing") or 0,
    )
    monkeypatch.setattr(dispatcher, "claim_next_scrape_job", lambda: call_order.append("claim_next") or None)

    assert dispatcher.dispatch_next_scrape_job() == 0
    assert call_order == ["load_env", "runtime_defaults", "enqueue_missing", "claim_next"]
