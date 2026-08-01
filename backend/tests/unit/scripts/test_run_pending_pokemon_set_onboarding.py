from backend.scripts import run_pending_pokemon_set_onboarding as script
from types import SimpleNamespace


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


def test_more_than_eight_successful_real_runner_claims_complete_without_attempt_exhaustion(monkeypatch):
    state = {
        **job(), "current_step": script.STEP_ORDER[0], "status": "detected",
        "attempt_count": 0, "max_attempts": 8,
    }

    def claim_next(worker_id, _lease_seconds, **_kwargs):
        if state["status"] not in {"detected", "ready", "retry"}:
            return None
        if state["status"] == "retry":
            if state["attempt_count"] >= state["max_attempts"]:
                return None
            state["attempt_count"] += 1
        state["status"] = "running"
        state["worker_id"] = worker_id
        return dict(state)

    def update_claimed(_job_id, _worker_id, fields):
        state.update(fields)
        return dict(state)

    def run_step(_engine, claimed):
        index = script.STEP_ORDER.index(claimed["current_step"])
        if index == len(script.STEP_ORDER) - 1:
            return SimpleNamespace(kind="complete", step=None, evidence={}, error_code=None)
        return SimpleNamespace(
            kind="advance", step=script.STEP_ORDER[index + 1], evidence={}, error_code=None,
        )

    class HealthyHeartbeat:
        def __init__(self, *_args, **_kwargs):
            self.lost_ownership, self.failure, self.count = False, None, 1
        def __enter__(self): return self
        def __exit__(self, *_args): return None

    monkeypatch.setattr(script, "_load_backend_env", lambda: None)
    monkeypatch.setattr(script.repository, "claim_next", claim_next)
    monkeypatch.setattr(script.repository, "update_claimed", update_claimed)
    monkeypatch.setattr(script.OnboardingEngine, "run_step", run_step)
    monkeypatch.setattr(script, "LeaseHeartbeat", HealthyHeartbeat)
    monkeypatch.setattr("sys.argv", ["worker", "--commit"])

    assert len(script.STEP_ORDER) > state["max_attempts"]
    for _step in script.STEP_ORDER:
        assert script.main() == 0
    assert state["status"] == "completed"
    assert state["attempt_count"] == 0
