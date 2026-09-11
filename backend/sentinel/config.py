"""Fail-closed runtime configuration for the Sentinel kernel."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_true(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = str(os.getenv(name, str(default))).strip()
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _env_int(name: str, default: int) -> int:
    raw = str(os.getenv(name, str(default))).strip()
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


@dataclass(frozen=True)
class SentinelConfig:
    """Runtime switches for the deterministic Sentinel kernel.

    Persistence requires TWO explicit switches: the operator must enable state
    writes and separately attest that the dedicated Sentinel schema has been
    deployed. P6 recovery requires a THIRD, separate execution-readiness gate.
    This keeps recovery code testable without making production mutation a
    side effect of merely enabling Sentinel persistence. AI remains disabled.

    P7 deployment/runtime canaries are detection-only and require explicit
    release/runtime authority inputs; they never infer what SHOULD be deployed.
    """

    state_writes_enabled: bool = False
    persistence_schema_ready: bool = False
    recovery_enabled: bool = False
    recovery_execution_ready: bool = False
    ai_enabled: bool = False
    fail_on_no_checks: bool = True
    component: str = "sentinel_vm"
    backend_base_url: str = ""
    frontend_base_url: str = ""
    public_http_timeout_seconds: float = 12.0
    expected_release_sha: str = ""
    expected_release_branch: str = "main"
    expected_frontend_environment: str = "production"
    runtime_repo_path: str = ""
    runtime_overlay_manifest_path: str = ""
    watch_component: str = "sentinel_vm"
    watch_host: str = ""
    heartbeat_max_age_seconds: int = 15 * 60
    deadman_ping_url: str = field(default="", repr=False, compare=False)
    deadman_timeout_seconds: float = 5.0

    @classmethod
    def from_env(cls) -> "SentinelConfig":
        return cls(
            state_writes_enabled=_env_true("SENTINEL_STATE_WRITES_ENABLED"),
            persistence_schema_ready=_env_true("SENTINEL_PERSISTENCE_SCHEMA_READY"),
            recovery_enabled=_env_true("SENTINEL_RECOVERY_ENABLED"),
            recovery_execution_ready=_env_true("SENTINEL_RECOVERY_EXECUTION_READY"),
            ai_enabled=_env_true("SENTINEL_AI_ENABLED"),
            fail_on_no_checks=_env_true("SENTINEL_FAIL_ON_NO_CHECKS", "true"),
            component=os.getenv("SENTINEL_COMPONENT", "sentinel_vm").strip() or "sentinel_vm",
            backend_base_url=os.getenv("SENTINEL_BACKEND_BASE_URL", "").strip().rstrip("/"),
            frontend_base_url=os.getenv("SENTINEL_FRONTEND_BASE_URL", "").strip().rstrip("/"),
            public_http_timeout_seconds=_env_float("SENTINEL_PUBLIC_HTTP_TIMEOUT_SECONDS", 12.0),
            expected_release_sha=os.getenv("SENTINEL_EXPECTED_RELEASE_SHA", "").strip(),
            expected_release_branch=(
                os.getenv("SENTINEL_EXPECTED_RELEASE_BRANCH", "main").strip() or "main"
            ),
            expected_frontend_environment=(
                os.getenv("SENTINEL_EXPECTED_FRONTEND_ENVIRONMENT", "production").strip()
                or "production"
            ),
            runtime_repo_path=os.getenv("SENTINEL_RUNTIME_REPO_PATH", "").strip(),
            runtime_overlay_manifest_path=os.getenv(
                "SENTINEL_RUNTIME_OVERLAY_MANIFEST", ""
            ).strip(),
            watch_component=os.getenv("SENTINEL_WATCH_COMPONENT", "sentinel_vm").strip() or "sentinel_vm",
            watch_host=os.getenv("SENTINEL_WATCH_HOST", "").strip(),
            heartbeat_max_age_seconds=_env_int("SENTINEL_HEARTBEAT_MAX_AGE_SECONDS", 15 * 60),
            deadman_ping_url=os.getenv("SENTINEL_DEADMAN_PING_URL", "").strip(),
            deadman_timeout_seconds=_env_float("SENTINEL_DEADMAN_TIMEOUT_SECONDS", 5.0),
        )

    def validate_kernel_v1(self) -> None:
        if self.recovery_enabled:
            missing = []
            if not self.state_writes_enabled:
                missing.append("SENTINEL_STATE_WRITES_ENABLED")
            if not self.persistence_schema_ready:
                missing.append("SENTINEL_PERSISTENCE_SCHEMA_READY")
            if not self.recovery_execution_ready:
                missing.append("SENTINEL_RECOVERY_EXECUTION_READY")
            if missing:
                raise RuntimeError(
                    "SENTINEL_RECOVERY_ENABLED=true requires explicit recovery gates: "
                    + ", ".join(missing)
                )
        if self.ai_enabled:
            raise RuntimeError(
                "SENTINEL_AI_ENABLED=true is not supported by the deterministic kernel"
            )
