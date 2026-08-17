"""Queue behaviour when a set fails for INFRASTRUCTURE reasons.

The failing batch burned through its remaining sets because every set was
attempted the instant the previous one failed, straight back into the same
Cloudflare/PostgREST outage. Per-operation retries are the primary fix; this is
the queue-level backstop, and these tests pin both halves of its contract:
consecutive TRANSIENT failures back off, and everything else does not.
"""

from __future__ import annotations

import sys
import types

import pytest

from backend.scripts import run_all_v2_sets as batch


def test_cooldown_ladder_escalates_then_caps():
    ladder = [
        batch._cooldown_seconds_for_consecutive_transient_failures(count)
        for count in range(0, 6)
    ]
    assert ladder == [0.0, 30.0, 60.0, 120.0, 120.0, 120.0]


class _Config:
    ERA = "test"
    SET_NAME = "Test Set"


def _set_map(count: int) -> dict:
    return {f"set{index}": (lambda: _Config()) for index in range(1, count + 1)}


class _Orchestrator:
    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = []

    def run(self, **kwargs):
        self.calls.append(kwargs.get("target_set_identifier"))
        outcome = self._outcomes.pop(0)
        if outcome is not None:
            raise outcome
        return {"ok": True}


class _APIError(Exception):
    def __init__(self, message, code):
        super().__init__(message)
        self.code = str(code)


@pytest.fixture
def batch_harness(monkeypatch):
    slept = []
    monkeypatch.setattr(batch, "notify_slack", lambda *_args, **_kwargs: None)

    def _run(outcomes):
        orchestrator = _Orchestrator(outcomes)
        # `run_batch` imports the orchestrator lazily from `backend.jobs.evr_runner`.
        # A stub module keeps this test on the QUEUE, with no simulation engine,
        # no set configs and no Supabase environment behind it.
        stub = types.ModuleType("backend.jobs.evr_runner")
        stub.EVRRunOrchestrator = lambda: orchestrator
        monkeypatch.setitem(sys.modules, "backend.jobs.evr_runner", stub)
        results = batch.run_batch(_set_map(len(outcomes)), sleep=slept.append)
        return results, slept, orchestrator

    return _run


def test_consecutive_transient_failures_back_the_queue_off(batch_harness):
    transient = RuntimeError("Simulation input-card insert failed")
    transient.__cause__ = _APIError("JSON could not be generated", 502)

    results, slept, orchestrator = batch_harness([transient, transient, transient])

    assert [result["success"] for result in results] == [False, False, False]
    assert all(result["transient"] for result in results)
    # No cooldown before the first set; then the ladder.
    assert slept == [30.0, 60.0]
    assert len(orchestrator.calls) == 3


def test_a_deterministic_set_failure_does_not_slow_the_queue(batch_harness):
    deterministic = RuntimeError("Missing required field: pack_cost")

    results, slept, _orchestrator = batch_harness([deterministic, deterministic])

    assert [result["transient"] for result in results] == [False, False]
    assert slept == []


def test_one_success_resets_the_cooldown_ladder(batch_harness):
    transient = RuntimeError("gateway failure")
    transient.__cause__ = _APIError("JSON could not be generated", 503)

    _results, slept, _orchestrator = batch_harness([transient, None, transient, None])

    # 30s before set 2 only: the success in the middle clears the streak, so the
    # second transient failure starts the ladder over rather than escalating.
    assert slept == [30.0, 30.0]


def test_the_queue_still_attempts_every_set_after_a_transient_failure(batch_harness):
    transient = RuntimeError("edge failure")
    transient.__cause__ = _APIError("JSON could not be generated", 504)

    results, _slept, orchestrator = batch_harness([transient, None, None])

    assert len(orchestrator.calls) == 3
    assert [result["success"] for result in results] == [False, True, True]
