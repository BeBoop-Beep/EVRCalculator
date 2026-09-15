import json

from backend.scripts import run_pending_pokemon_set_onboarding as script
from backend.db.repositories.pokemon_set_onboarding_repository import LeaseFencingError
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


def test_zero_row_update_during_persist_is_treated_as_failure(monkeypatch):
    monkeypatch.setattr(script, "_load_backend_env", lambda: None)
    monkeypatch.setattr(script.repository, "claim_next", lambda *a, **k: job())

    def strict_update_claimed(_job_id, _worker_id, _fields, *, strict=False):
        if strict:
            raise LeaseFencingError("simulated lease loss during persist")
        return None

    monkeypatch.setattr(script.repository, "update_claimed", strict_update_claimed)
    released = []
    monkeypatch.setattr(
        script.repository, "release_for_retry",
        lambda job_id, worker_id, **k: released.append((job_id, k.get("code"))),
    )
    monkeypatch.setattr(script, "queue_alert", lambda *a, **k: None)

    class Healthy:
        def __init__(self, *a, **k):
            self.lost_ownership, self.failure, self.count = False, None, 1
        def __enter__(self): return self
        def __exit__(self, *a): return None

    monkeypatch.setattr(script, "LeaseHeartbeat", Healthy)
    monkeypatch.setattr(script.OnboardingEngine, "run_step", lambda self, job: type(
        "O", (), {"kind": "advance", "step": "market_snapshots", "evidence": {}, "error_code": None}
    )())
    monkeypatch.setattr("sys.argv", ["worker", "--commit"])
    assert script.main() == 2
    assert released and released[0][1] == "unhandled_worker_error"


def test_resume_all_alone_does_not_force_retry_manual_review_jobs(monkeypatch):
    monkeypatch.setattr(script, "_load_backend_env", lambda: None)
    seen_list_jobs_kwargs = {}

    def list_jobs(**kwargs):
        seen_list_jobs_kwargs.update(kwargs)
        return []

    monkeypatch.setattr(script.repository, "list_jobs", list_jobs)
    monkeypatch.setattr("sys.argv", ["worker", "--commit", "--resume-all"])
    assert script.main() == 0
    assert seen_list_jobs_kwargs["include_manual_review"] is False
    assert seen_list_jobs_kwargs["due_only"] is True


def test_resume_all_does_not_force_retry_claim(monkeypatch):
    monkeypatch.setattr(script, "_load_backend_env", lambda: None)
    monkeypatch.setattr(script.repository, "list_jobs", lambda **k: [job()])
    seen_claim_kwargs = {}

    def claim_next(_worker_id, _lease_seconds, **kwargs):
        seen_claim_kwargs.update(kwargs)
        return None

    monkeypatch.setattr(script.repository, "claim_next", claim_next)
    monkeypatch.setattr("sys.argv", ["worker", "--commit", "--resume-all"])
    assert script.main() == 0
    assert seen_claim_kwargs["force_retry"] is False


def test_max_jobs_is_clamped_to_ceiling(monkeypatch, capsys):
    monkeypatch.setattr(script, "_load_backend_env", lambda: None)
    monkeypatch.setattr(script.repository, "list_jobs", lambda **k: [])
    monkeypatch.setattr(
        "sys.argv", ["worker", "--dry-run", "--max-jobs", str(script.MAX_JOBS_CEILING * 10)],
    )
    assert script.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["bounds"]["max_jobs"] == script.MAX_JOBS_CEILING


def test_dry_run_bounds_are_visible_in_json_output(monkeypatch, capsys):
    monkeypatch.setattr(script, "_load_backend_env", lambda: None)
    monkeypatch.setattr(script.repository, "list_jobs", lambda **k: [job()])
    monkeypatch.setattr(script.OnboardingEngine, "run_step", lambda self, job: type(
        "O", (), {"__dict__": {"kind": "wait"}}
    )())
    monkeypatch.setattr("sys.argv", ["worker", "--dry-run", "--max-jobs", "1"])
    assert script.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["bounds"] == {
        "max_jobs": 1, "max_jobs_ceiling": script.MAX_JOBS_CEILING,
        "jobs_processed": 1, "bound_reached": True,
    }


def test_commit_bounds_report_reached_when_max_jobs_hit(monkeypatch, capsys):
    monkeypatch.setattr(script, "_load_backend_env", lambda: None)
    monkeypatch.setattr(script.repository, "claim_next", lambda *a, **k: job())
    monkeypatch.setattr(script.repository, "update_claimed", lambda *a, **k: dict(job()))
    monkeypatch.setattr(script.OnboardingEngine, "run_step", lambda self, job: type(
        "O", (), {"kind": "advance", "step": "market_snapshots", "evidence": {}, "error_code": None}
    )())

    class Healthy:
        def __init__(self, *a, **k):
            self.lost_ownership, self.failure, self.count = False, None, 1
        def __enter__(self): return self
        def __exit__(self, *a): return None

    monkeypatch.setattr(script, "LeaseHeartbeat", Healthy)
    monkeypatch.setattr("sys.argv", ["worker", "--commit", "--max-jobs", "1"])
    assert script.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["bounds"]["jobs_claimed"] == 1
    assert payload["bounds"]["bound_reached"] is True
    assert payload["bounds"]["max_jobs"] == 1


def test_commit_bounds_report_not_reached_when_queue_smaller_than_max_jobs(monkeypatch, capsys):
    monkeypatch.setattr(script, "_load_backend_env", lambda: None)
    calls = {"count": 0}

    def claim_next(*_a, **_k):
        calls["count"] += 1
        return job() if calls["count"] == 1 else None

    monkeypatch.setattr(script.repository, "claim_next", claim_next)
    monkeypatch.setattr(script.repository, "update_claimed", lambda *a, **k: dict(job()))
    monkeypatch.setattr(script.OnboardingEngine, "run_step", lambda self, job: type(
        "O", (), {"kind": "advance", "step": "market_snapshots", "evidence": {}, "error_code": None}
    )())

    class Healthy:
        def __init__(self, *a, **k):
            self.lost_ownership, self.failure, self.count = False, None, 1
        def __enter__(self): return self
        def __exit__(self, *a): return None

    monkeypatch.setattr(script, "LeaseHeartbeat", Healthy)
    monkeypatch.setattr("sys.argv", ["worker", "--commit", "--max-jobs", "5"])
    assert script.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["bounds"]["jobs_claimed"] == 1
    assert payload["bounds"]["bound_reached"] is False


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

    def update_claimed(_job_id, _worker_id, fields, **_kwargs):
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
