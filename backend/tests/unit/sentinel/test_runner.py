from datetime import datetime, timezone

import pytest

from backend.sentinel.config import SentinelConfig
from backend.sentinel.models import CheckResult, RunnerIdentity
from backend.sentinel.registry import CheckRegistry
from backend.sentinel.runner import run_once
from backend.sentinel.state import MemoryStateStore, NoopStateStore


NOW = datetime(2026, 9, 11, 20, 0, tzinfo=timezone.utc)
IDENTITY = RunnerIdentity(component="sentinel_vm", host="vm", build_sha="sha")


def _config(**overrides):
    values = dict(
        state_writes_enabled=False,
        recovery_enabled=False,
        ai_enabled=False,
        fail_on_no_checks=True,
        component="sentinel_vm",
    )
    values.update(overrides)
    return SentinelConfig(**values)


def test_no_checks_fails_closed():
    result = run_once(
        CheckRegistry(),
        config=_config(),
        store=NoopStateStore(),
        now=NOW,
        identity=IDENTITY,
    )
    assert result["healthy"] is False
    assert result["status"] == "no_checks_registered"
    assert result["check_count"] == 0


def test_healthy_check_produces_healthy_summary():
    registry = CheckRegistry()
    registry.register(
        "kernel.example",
        lambda ctx: CheckResult.healthy("kernel.example", checked_at=NOW),
        confirm_after=1,
    )
    result = run_once(
        registry,
        config=_config(),
        store=NoopStateStore(),
        now=NOW,
        identity=IDENTITY,
    )
    assert result["healthy"] is True
    assert result["results"][0]["transition"]["action"] == "healthy"
    assert result["recovery_enabled"] is False
    assert result["ai_enabled"] is False


def test_check_exception_is_structured_not_raised():
    registry = CheckRegistry()

    def boom(_ctx):
        raise TimeoutError("dependency timed out")

    registry.register("backend.health", boom, confirm_after=1)
    result = run_once(
        registry,
        config=_config(),
        store=MemoryStateStore(),
        now=NOW,
        identity=IDENTITY,
    )
    assert result["healthy"] is False
    check = result["results"][0]["check"]
    assert check["outcome"] == "error"
    assert check["failure_code"] == "check_execution_failed"
    assert "TimeoutError" in str(check["evidence"])


def test_mismatched_check_key_becomes_execution_error():
    registry = CheckRegistry()
    registry.register(
        "backend.health",
        lambda ctx: CheckResult.healthy("wrong.key", checked_at=NOW),
        confirm_after=1,
    )
    result = run_once(
        registry,
        config=_config(),
        store=MemoryStateStore(),
        now=NOW,
        identity=IDENTITY,
    )
    assert result["results"][0]["check"]["outcome"] == "error"


def test_persistent_store_records_heartbeat_only_when_supplied():
    registry = CheckRegistry()
    registry.register(
        "backend.health",
        lambda ctx: CheckResult.healthy("backend.health", checked_at=NOW),
    )
    store = MemoryStateStore()
    result = run_once(
        registry,
        config=_config(state_writes_enabled=True),
        store=store,
        now=NOW,
        identity=IDENTITY,
    )
    assert result["state_store_persistent"] is True
    assert ("sentinel_vm", "vm") in store.heartbeats


def test_recovery_enable_fails_closed_before_any_check_runs():
    registry = CheckRegistry()
    registry.register(
        "backend.health",
        lambda ctx: (_ for _ in ()).throw(AssertionError("must not execute")),
    )
    with pytest.raises(RuntimeError, match="RECOVERY"):
        run_once(
            registry,
            config=_config(recovery_enabled=True),
            store=NoopStateStore(),
            now=NOW,
            identity=IDENTITY,
        )


def test_ai_enable_fails_closed_before_any_check_runs():
    with pytest.raises(RuntimeError, match="AI"):
        run_once(
            CheckRegistry(),
            config=_config(ai_enabled=True),
            store=NoopStateStore(),
            now=NOW,
            identity=IDENTITY,
        )


def test_observation_mode_reports_nonpersistent_store():
    registry = CheckRegistry()
    registry.register(
        "backend.health",
        lambda ctx: CheckResult.healthy("backend.health", checked_at=NOW),
    )
    result = run_once(
        registry,
        config=_config(state_writes_enabled=False),
        store=NoopStateStore(),
        now=NOW,
        identity=IDENTITY,
    )
    assert result["state_writes_enabled"] is False
    assert result["state_store_persistent"] is False
