"""Fail-closed runtime configuration for the Sentinel kernel."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_true(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class SentinelConfig:
    """Runtime switches for Prompt-2 Sentinel.

    State persistence is optional and disabled by default because the Sentinel
    schema is not deployed by this phase. Recovery and AI are deliberately
    unavailable in the kernel and fail closed if someone attempts to enable
    them early.
    """

    state_writes_enabled: bool = False
    recovery_enabled: bool = False
    ai_enabled: bool = False
    fail_on_no_checks: bool = True
    component: str = "sentinel_vm"

    @classmethod
    def from_env(cls) -> "SentinelConfig":
        return cls(
            state_writes_enabled=_env_true("SENTINEL_STATE_WRITES_ENABLED"),
            recovery_enabled=_env_true("SENTINEL_RECOVERY_ENABLED"),
            ai_enabled=_env_true("SENTINEL_AI_ENABLED"),
            fail_on_no_checks=_env_true("SENTINEL_FAIL_ON_NO_CHECKS", "true"),
            component=os.getenv("SENTINEL_COMPONENT", "sentinel_vm").strip() or "sentinel_vm",
        )

    def validate_kernel_v1(self) -> None:
        if self.recovery_enabled:
            raise RuntimeError(
                "SENTINEL_RECOVERY_ENABLED=true is not supported by the Prompt-2 kernel"
            )
        if self.ai_enabled:
            raise RuntimeError(
                "SENTINEL_AI_ENABLED=true is not supported by the Prompt-2 kernel"
            )
