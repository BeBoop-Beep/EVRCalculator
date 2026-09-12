import pytest

import backend.sentinel.operational as operational
from backend.sentinel.config import SentinelConfig
from backend.sentinel.models import CheckResult
from backend.sentinel.registry import CheckRegistry
from backend.sentinel.state import MemoryStateStore


def _config(**overrides):
    values = dict(
        state_writes_enabled=False,
        persistence_schema_ready=False,
        recovery_enabled=False,
        recovery_execution_ready=False,
        ai_enabled=False,
        fail_on_no_checks=True,
        component="sentinel_vm",
        backend_base_url="",
        frontend_base_url="",
        public_http_timeout_seconds=12.0,
        expected_release_sha="",
        expected_release_branch="main",
        expected_frontend_environment="production",
        runtime_repo_path="",
        runtime_overlay_manifest_path="",
        watch_component="sentinel_vm",
        watch_host="",
        heartbeat_max_age_seconds=900,
        deadman_ping_url="",
        deadman_timeout_seconds=5.0,
    )
    values.update(overrides)
    return SentinelConfig(**values)


def _registry(outcome="healthy"):
    registry = CheckRegistry()
    if outcome == "healthy":
        registry.register(
            "test.ok",
            lambda ctx: CheckResult.healthy("test.ok", checked_at=ctx.now),
            confirm_after=1,
        )
    else:
        registry.register(
            "test.fail",
            lambda ctx: CheckResult.failure(
                "test.fail", failure_code="expected_test_failure", checked_at=ctx.now
            ),
            confirm_after=1,
        )
    return registry


def test_observation_runner_refuses_state_writes_before_schema_activation():
    with pytest.raises(RuntimeError, match="read-only"):
        operational.run_profile(
            "fast", config=_config(state_writes_enabled=True), client=object()
        )


def test_schema_ready_and_write_enabled_can_use_explicit_persistent_store(monkeypatch):
    registry = _registry()
    monkeypatch.setattr(operational, "build_profile_registry", lambda *a, **k: registry)
    store = MemoryStateStore()
    summary = operational.run_profile(
        "fast",
        config=_config(state_writes_enabled=True, persistence_schema_ready=True),
        store=store,
    )
    assert summary["healthy"] is True
    assert summary["state_store_persistent"] is True
    assert len(store.heartbeats) == 1


def test_observation_runner_still_fails_closed_on_recovery_and_ai():
    with pytest.raises(RuntimeError, match="RECOVERY"):
        operational.run_profile("fast", config=_config(recovery_enabled=True), client=object())
    with pytest.raises(RuntimeError, match="AI"):
        operational.run_profile("fast", config=_config(ai_enabled=True), client=object())


def test_public_profile_requires_explicit_backend_base_url():
    with pytest.raises(RuntimeError, match="SENTINEL_BACKEND_BASE_URL"):
        operational.run_profile("public", config=_config(), client=object())


def test_independent_profile_requires_explicit_target_host():
    with pytest.raises(RuntimeError, match="SENTINEL_WATCH_HOST"):
        operational.run_profile("independent", config=_config(), client=object())


def test_deploy_profile_requires_explicit_backend_frontend_and_release_sha():
    with pytest.raises(RuntimeError, match="SENTINEL_FRONTEND_BASE_URL"):
        operational.run_profile(
            "deploy",
            config=_config(backend_base_url="https://backend.example.test"),
        )
    with pytest.raises(RuntimeError, match="SENTINEL_EXPECTED_RELEASE_SHA"):
        operational.run_profile(
            "deploy",
            config=_config(
                backend_base_url="https://backend.example.test",
                frontend_base_url="https://index.example.test",
            ),
        )


def test_runtime_profile_requires_repo_and_overlay_manifest_authority():
    with pytest.raises(RuntimeError, match="SENTINEL_RUNTIME_REPO_PATH"):
        operational.run_profile("runtime", config=_config())
    with pytest.raises(RuntimeError, match="SENTINEL_RUNTIME_OVERLAY_MANIFEST"):
        operational.run_profile(
            "runtime", config=_config(runtime_repo_path="/repo")
        )


def test_p6_recovery_cannot_be_enabled_for_p7_detection_profiles():
    config = _config(
        state_writes_enabled=True,
        persistence_schema_ready=True,
        recovery_enabled=True,
        recovery_execution_ready=True,
        backend_base_url="https://backend.example.test",
        frontend_base_url="https://index.example.test",
        expected_release_sha="a" * 40,
    )
    with pytest.raises(RuntimeError, match="fast or all"):
        operational.run_profile("deploy", config=config, store=MemoryStateStore())


def test_deadman_pings_after_completed_cycle_even_when_semantic_check_failed(monkeypatch):
    registry = _registry("failure")
    monkeypatch.setattr(operational, "build_profile_registry", lambda *a, **k: registry)
    calls = []

    class Response:
        status_code = 204

    def deadman_get(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    secret_url = "https://heartbeat.example.test/secret-token"
    summary = operational.run_profile(
        "fast",
        config=_config(deadman_ping_url=secret_url),
        deadman_get=deadman_get,
    )
    assert summary["healthy"] is False
    assert summary["deadman"]["delivered"] is True
    assert calls[0][0] == secret_url
    assert secret_url not in str(summary)


def test_deadman_delivery_failure_degrades_otherwise_healthy_cycle(monkeypatch):
    registry = _registry()
    monkeypatch.setattr(operational, "build_profile_registry", lambda *a, **k: registry)

    class Response:
        status_code = 503

    summary = operational.run_profile(
        "fast",
        config=_config(deadman_ping_url="https://heartbeat.example.test/token"),
        deadman_get=lambda *a, **k: Response(),
    )
    assert summary["healthy"] is False
    assert summary["status"] == "deadman_delivery_failed"
    assert summary["deadman"]["error_type"] == "deadman_http_error"
