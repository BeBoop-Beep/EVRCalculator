"""Bounded deterministic check registry for Sentinel."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, Iterable

from backend.sentinel.models import CheckResult, RunnerIdentity, Severity


_CHECK_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_.:-]{2,119}$")


@dataclass(frozen=True)
class CheckContext:
    now: datetime
    runner_identity: RunnerIdentity


CheckCallable = Callable[[CheckContext], CheckResult]


@dataclass(frozen=True)
class RegisteredCheck:
    key: str
    run: CheckCallable
    description: str
    confirm_after: int
    exception_severity: Severity


class CheckRegistry:
    def __init__(self) -> None:
        self._checks: Dict[str, RegisteredCheck] = {}

    def register(
        self,
        key: str,
        run: CheckCallable,
        *,
        description: str = "",
        confirm_after: int = 2,
        exception_severity: Severity = Severity.CRITICAL,
    ) -> RegisteredCheck:
        if not _CHECK_KEY_RE.fullmatch(key):
            raise ValueError(
                "check key must be 3-120 chars of lowercase letters, numbers, _ . : -"
            )
        if key in self._checks:
            raise ValueError(f"duplicate Sentinel check key: {key}")
        if confirm_after < 1:
            raise ValueError("confirm_after must be >= 1")
        if not callable(run):
            raise TypeError("run must be callable")
        registered = RegisteredCheck(
            key=key,
            run=run,
            description=description,
            confirm_after=confirm_after,
            exception_severity=exception_severity,
        )
        self._checks[key] = registered
        return registered

    def get(self, key: str) -> RegisteredCheck:
        return self._checks[key]

    def all(self) -> Iterable[RegisteredCheck]:
        return tuple(self._checks[key] for key in sorted(self._checks))

    def keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._checks))

    def __len__(self) -> int:
        return len(self._checks)
