from backend.scripts import run_pending_pokemon_set_onboarding as script


def job():
    return {
        "id": "job", "current_step": "publication_gate", "canonical_key": "futureSet",
        "source_set_name": "Future", "metadata_json": {}, "status": "running",
    }


def test_lost_ownership_prevents_success_update(monkeypatch):
    monkeypatch.setattr(script, "_load_backend_env", lambda: None)
    monkeypatch.setattr(script.repository, "claim_next", lambda *a, **k: job())
    monkeypatch.setattr(
        script.repository, "update_claimed",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("success update attempted")),
    )
    class Lost:
        def __init__(self, *a, **k):
            self.lost_ownership, self.failure, self.count = True, None, 1
        def __enter__(self): return self
        def __exit__(self, *a): return None
    monkeypatch.setattr(script, "LeaseHeartbeat", Lost)
    monkeypatch.setattr(script.OnboardingEngine, "run_step", lambda self, job: type(
        "O", (), {"kind": "advance", "step": "market_snapshots", "evidence": {}, "error_code": None}
    )())
    monkeypatch.setattr("sys.argv", ["worker", "--commit"])
    assert script.main() == 2


def test_dry_run_never_heartbeats(monkeypatch):
    monkeypatch.setattr(script, "_load_backend_env", lambda: None)
    monkeypatch.setattr(script.repository, "list_jobs", lambda **k: [job()])
    monkeypatch.setattr(
        script.repository, "heartbeat",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("heartbeat write")),
    )
    monkeypatch.setattr(script.OnboardingEngine, "run_step", lambda self, job: type(
        "O", (), {"__dict__": {"kind": "wait"}}
    )())
    monkeypatch.setattr("sys.argv", ["worker", "--dry-run"])
    assert script.main() == 0
