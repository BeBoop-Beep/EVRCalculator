import pytest

import backend.sentinel.operational as operational
from backend.sentinel.config import SentinelConfig


def _config(**overrides):
    values = dict(
        state_writes_enabled=False,
        recovery_enabled=False,
        ai_enabled=False,
        fail_on_no_checks=True,
        component="sentinel_vm",
        backend_base_url="",
        public_http_timeout_seconds=12.0,
    )
    values.update(overrides)
    return SentinelConfig(**values)


def test_observation_runner_refuses_state_writes_before_schema_activation():
    with pytest.raises(RuntimeError, match="read-only"):
        operational.run_profile("fast", config=_config(state_writes_enabled=True), client=object())


def test_observation_runner_still_fails_closed_on_recovery_and_ai():
    with pytest.raises(RuntimeError, match="RECOVERY"):
        operational.run_profile("fast", config=_config(recovery_enabled=True), client=object())
    with pytest.raises(RuntimeError, match="AI"):
        operational.run_profile("fast", config=_config(ai_enabled=True), client=object())


def test_public_profile_requires_explicit_backend_base_url():
    with pytest.raises(RuntimeError, match="SENTINEL_BACKEND_BASE_URL"):
        operational.run_profile("public", config=_config(), client=object())
