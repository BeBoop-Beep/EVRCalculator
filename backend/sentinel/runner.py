"""One-shot deterministic Sentinel check/incident runner.

The kernel evaluates registered checks and updates incident state. P6 recovery
is orchestrated by ``backend.sentinel.operational`` after this observation pass,
so mutation can never occur before a confirmed incident has been persisted.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.sentinel.config import SentinelConfig
from backend.sentinel.incidents import IncidentManager
from backend.sentinel.models import (
    CheckOutcome,
    CheckResult,
    RunnerIdentity,
    Severity,
)
from backend.sentinel.registry import CheckContext, CheckRegistry
from backend.sentinel.state import NoopStateStore, SentinelStateStore, build_state_store


def _identity(config: SentinelConfig) -> RunnerIdentity:
    build_sha = (
        os.getenv("SENTINEL_RUNNER_BUILD_SHA")
        or os.getenv("RENDER_GIT_COMMIT")
        or os.getenv("GIT_SHA")
        or "unknown"
    )
    host = os.getenv("SENTINEL_RUNNER_HOST") or socket.gethostname() or "unknown"
    return RunnerIdentity(
        component=config.component,
        host=host,
        build_sha=build_sha.strip() or "unknown",
    )


def _safe_exception_message(exc: Exception) -> str:
    text = str(exc).replace("\n", " ").strip()
    return text[:500] if text else exc.__class__.__name__


def run_once(
    registry: CheckRegistry,
    *,
    config: Optional[SentinelConfig] = None,
    store: Optional[SentinelStateStore] = None,
    now: Optional[datetime] = None,
    identity: Optional[RunnerIdentity] = None,
) -> Dict[str, Any]:
    resolved_config = config or SentinelConfig.from_env()
    resolved_config.validate_kernel_v1()
    resolved_now = now or datetime.now(timezone.utc)
    resolved_identity = identity or _identity(resolved_config)
    resolved_store = store or build_state_store(resolved_config.state_writes_enabled)

    registered_checks = list(registry.all())
    if not registered_checks:
        return {
            "healthy": not resolved_config.fail_on_no_checks,
            "status": "no_checks_registered",
            "checked_at": resolved_now.isoformat(),
            "check_count": 0,
            "results": [],
            "runner": resolved_identity.to_dict(),
            "state_writes_enabled": resolved_config.state_writes_enabled,
            "state_store_persistent": bool(resolved_store.persistent),
            "recovery_enabled": resolved_config.recovery_enabled,
            "ai_enabled": resolved_config.ai_enabled,
        }

    resolved_store.record_heartbeat(
        resolved_identity,
        resolved_now,
        {
            "check_count": len(registered_checks),
            "recovery_enabled": resolved_config.recovery_enabled,
            "ai_enabled": resolved_config.ai_enabled,
        },
    )

    manager = IncidentManager(resolved_store)
    rendered_results = []
    all_healthy = True

    for registered in registered_checks:
        context = CheckContext(now=resolved_now, runner_identity=resolved_identity)
        try:
            result = registered.run(context)
            if result.check_key != registered.key:
                raise ValueError(
                    f"check returned key={result.check_key!r}; expected {registered.key!r}"
                )
        except Exception as exc:
            result = CheckResult.execution_error(
                registered.key,
                severity=registered.exception_severity,
                evidence={
                    "stage": "check_execution",
                    "exception_type": exc.__class__.__name__,
                    "message": _safe_exception_message(exc),
                },
                checked_at=resolved_now,
            )

        transition = manager.process(registered, result, resolved_identity)
        if result.outcome != CheckOutcome.HEALTHY:
            all_healthy = False
        rendered_results.append(
            {
                "check": result.to_dict(),
                "transition": {
                    "action": transition.action,
                    "check_status": transition.check_status.value,
                    "incident_id": transition.incident_id,
                    "fingerprint": transition.fingerprint,
                },
            }
        )

    return {
        "healthy": all_healthy,
        "status": "healthy" if all_healthy else "unhealthy",
        "checked_at": resolved_now.isoformat(),
        "check_count": len(registered_checks),
        "results": rendered_results,
        "runner": resolved_identity.to_dict(),
        "state_writes_enabled": resolved_config.state_writes_enabled,
        "state_store_persistent": bool(resolved_store.persistent),
        "recovery_enabled": resolved_config.recovery_enabled,
        "ai_enabled": resolved_config.ai_enabled,
    }


def _self_test_registry(now: datetime) -> CheckRegistry:
    registry = CheckRegistry()
    registry.register(
        "sentinel.kernel.self_test",
        lambda _ctx: CheckResult.healthy(
            "sentinel.kernel.self_test",
            expected={"kernel": "healthy"},
            observed={"kernel": "healthy"},
            checked_at=now,
        ),
        description="Local deterministic kernel smoke test",
        confirm_after=1,
        exception_severity=Severity.CRITICAL,
    )
    return registry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run one in-memory healthy kernel check; never persists or recovers",
    )
    parser.add_argument(
        "--list-checks",
        action="store_true",
        help="List checks registered by the bare kernel runner",
    )
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    registry = _self_test_registry(now) if args.self_test else CheckRegistry()

    if args.list_checks:
        print(json.dumps({"checks": list(registry.keys())}, indent=2, sort_keys=True))
        return 0

    config = SentinelConfig.from_env()
    if args.self_test:
        # Self-test is guaranteed inert even if production persistence/recovery
        # switches are present in the surrounding shell.
        config = SentinelConfig(
            state_writes_enabled=False,
            persistence_schema_ready=False,
            recovery_enabled=False,
            recovery_execution_ready=False,
            ai_enabled=False,
            fail_on_no_checks=True,
            component=config.component,
        )

    try:
        summary = run_once(
            registry,
            config=config,
            store=NoopStateStore() if args.self_test else None,
            now=now,
        )
    except RuntimeError as exc:
        print(
            json.dumps(
                {"healthy": False, "status": "configuration_error", "error": str(exc)},
                indent=2,
                sort_keys=True,
            )
        )
        return 2

    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    if summary["healthy"]:
        return 0
    return 2 if summary["status"] == "no_checks_registered" else 1


if __name__ == "__main__":
    raise SystemExit(main())
