"""Operational runner for Sentinel observation and gated P6 recovery profiles."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from backend.sentinel.checks.registry import build_profile_registry
from backend.sentinel.config import SentinelConfig
from backend.sentinel.deadman import ping_deadman
from backend.sentinel.models import RunnerIdentity
from backend.sentinel.recovery.engine import RecoveryRegistry, RecoveryRunner
from backend.sentinel.recovery.runbooks import build_safe_recovery_registry
from backend.sentinel.runner import run_once
from backend.sentinel.state import (
    NoopStateStore,
    SentinelStateStore,
    SupabaseStateStore,
    build_state_store,
)


_PUBLIC_PROFILES = {"public", "all"}
_RECOVERY_PROFILES = {"fast", "all"}


def _state_store(
    resolved: SentinelConfig,
    *,
    client: Any = None,
    store: Optional[SentinelStateStore] = None,
) -> SentinelStateStore:
    if not resolved.state_writes_enabled:
        if store is not None and bool(getattr(store, "persistent", False)):
            raise RuntimeError(
                "Persistent Sentinel state store supplied while "
                "SENTINEL_STATE_WRITES_ENABLED=false"
            )
        return store or NoopStateStore()

    if not resolved.persistence_schema_ready:
        raise RuntimeError(
            "Sentinel observation profiles are read-only until schema activation; "
            "SENTINEL_PERSISTENCE_SCHEMA_READY must be true before state writes"
        )
    if store is not None:
        if not bool(getattr(store, "persistent", False)):
            raise RuntimeError(
                "SENTINEL_STATE_WRITES_ENABLED=true requires a persistent state store"
            )
        return store
    if client is not None:
        return SupabaseStateStore(client)
    return build_state_store(True)


def _parsed_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _run_recovery_pass(
    summary: dict,
    *,
    check_registry,
    store: SentinelStateStore,
    recovery_registry: RecoveryRegistry,
) -> dict:
    runner_data = dict(summary.get("runner") or {})
    identity = RunnerIdentity(
        component=str(runner_data.get("component") or "unknown"),
        host=str(runner_data.get("host") or "unknown"),
        build_sha=str(runner_data.get("build_sha") or "unknown"),
    )
    now = _parsed_utc(summary["checked_at"])
    runner = RecoveryRunner(store, recovery_registry)
    reports = []
    failed_keys = set()
    recovered_keys = set()

    for rendered in list(summary.get("results") or []):
        check = dict(rendered.get("check") or {})
        if check.get("outcome") == "healthy":
            continue
        check_key = str(check.get("check_key") or "")
        if check_key:
            failed_keys.add(check_key)
        transition = dict(rendered.get("transition") or {})
        incident_id = transition.get("incident_id")
        if not incident_id:
            continue
        incident = store.get_incident(str(incident_id))
        if incident is None:
            reports.append(
                {
                    "action": "blocked",
                    "reason_code": "incident_state_missing",
                    "incident_id": str(incident_id),
                    "check_key": check_key,
                }
            )
            continue
        registered = check_registry.get(check_key)
        report = runner.attempt(
            incident,
            registered,
            identity=identity,
            now=now,
        )
        reports.append(report)
        if report.get("action") == "recovered":
            recovered_keys.add(check_key)

    if failed_keys and failed_keys.issubset(recovered_keys):
        summary["healthy"] = True
        summary["status"] = "recovered"

    return {
        "enabled": True,
        "allowlist": [
            {"check_key": check_key, "failure_code": failure_code}
            for check_key, failure_code in recovery_registry.matches()
        ],
        "attempts": reports,
        "recovered_check_keys": sorted(recovered_keys),
        "unrecovered_check_keys": sorted(failed_keys - recovered_keys),
    }


def run_profile(
    profile: str,
    *,
    config: Optional[SentinelConfig] = None,
    client: Any = None,
    http_get: Optional[Callable[..., Any]] = None,
    deadman_get: Optional[Callable[..., Any]] = None,
    store: Optional[SentinelStateStore] = None,
    recovery_registry: Optional[RecoveryRegistry] = None,
    git_runner=None,
    manifest_loader=None,
):
    resolved = config or SentinelConfig.from_env()
    resolved.validate_kernel_v1()
    normalized = str(profile or "").strip().lower()
    if normalized in _PUBLIC_PROFILES and not resolved.backend_base_url:
        raise RuntimeError(
            "SENTINEL_BACKEND_BASE_URL is required for the public Sentinel profile"
        )
    if normalized == "independent" and not resolved.watch_host:
        raise RuntimeError(
            "SENTINEL_WATCH_HOST is required for the independent Sentinel profile"
        )
    if normalized == "deploy":
        missing = []
        if not resolved.backend_base_url:
            missing.append("SENTINEL_BACKEND_BASE_URL")
        if not resolved.frontend_base_url:
            missing.append("SENTINEL_FRONTEND_BASE_URL")
        if not resolved.expected_release_sha:
            missing.append("SENTINEL_EXPECTED_RELEASE_SHA")
        if missing:
            raise RuntimeError(
                "deploy Sentinel profile requires explicit release authority: "
                + ", ".join(missing)
            )
    if normalized == "runtime":
        missing = []
        if not resolved.runtime_repo_path:
            missing.append("SENTINEL_RUNTIME_REPO_PATH")
        if not resolved.runtime_overlay_manifest_path:
            missing.append("SENTINEL_RUNTIME_OVERLAY_MANIFEST")
        if missing:
            raise RuntimeError(
                "runtime Sentinel profile requires explicit VM provenance authority: "
                + ", ".join(missing)
            )
    if resolved.recovery_enabled and normalized not in _RECOVERY_PROFILES:
        raise RuntimeError(
            "P6 recovery is only supported for the fast or all Sentinel profile"
        )

    resolved_store = _state_store(resolved, client=client, store=store)
    profile_kwargs = dict(
        client=client,
        backend_base_url=resolved.backend_base_url,
        frontend_base_url=resolved.frontend_base_url,
        expected_release_sha=resolved.expected_release_sha,
        expected_release_branch=resolved.expected_release_branch,
        expected_frontend_environment=resolved.expected_frontend_environment,
        http_get=http_get,
        timeout_seconds=resolved.public_http_timeout_seconds,
        watch_component=resolved.watch_component,
        watch_host=resolved.watch_host,
        heartbeat_max_age_seconds=resolved.heartbeat_max_age_seconds,
        runtime_repo_path=resolved.runtime_repo_path,
        runtime_overlay_manifest_path=resolved.runtime_overlay_manifest_path,
        git_runner=git_runner,
    )
    if manifest_loader is not None:
        profile_kwargs["manifest_loader"] = manifest_loader
    registry = build_profile_registry(normalized, **profile_kwargs)
    summary = run_once(registry, config=resolved, store=resolved_store)

    if resolved.recovery_enabled:
        safe_registry = recovery_registry or build_safe_recovery_registry(client=client)
        summary["recovery"] = _run_recovery_pass(
            summary,
            check_registry=registry,
            store=resolved_store,
            recovery_registry=safe_registry,
        )
    else:
        summary["recovery"] = {
            "enabled": False,
            "allowlist": [],
            "attempts": [],
            "recovered_check_keys": [],
            "unrecovered_check_keys": [],
        }

    deadman = ping_deadman(
        resolved.deadman_ping_url,
        timeout_seconds=resolved.deadman_timeout_seconds,
        http_get=deadman_get,
    )
    summary["deadman"] = deadman.to_dict()
    if deadman.configured and not deadman.delivered:
        summary["healthy"] = False
        if summary.get("status") in {"healthy", "recovered"}:
            summary["status"] = "deadman_delivery_failed"
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=("fast", "public", "independent", "deploy", "runtime", "audit", "all"),
        default="fast",
        help=(
            "Profile to evaluate. Independent must run outside the watched "
            "component's failure domain; deploy/runtime require explicit authority; "
            "audit is intentionally heavier."
        ),
    )
    parser.add_argument(
        "--list-checks",
        action="store_true",
        help="List registered check keys without executing external reads.",
    )
    args = parser.parse_args()

    if args.list_checks:
        registry = build_profile_registry(
            args.profile,
            client=object(),
            backend_base_url="https://backend.sentinel.invalid",
            frontend_base_url="https://frontend.sentinel.invalid",
            expected_release_sha="0" * 40,
            watch_host="watched-host.invalid",
            runtime_repo_path="/sentinel/invalid",
            runtime_overlay_manifest_path="/sentinel/invalid/manifest.json",
        )
        print(
            json.dumps(
                {"profile": args.profile, "checks": list(registry.keys())},
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    try:
        summary = run_profile(args.profile)
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
    return 0 if summary.get("healthy") else 1


if __name__ == "__main__":
    raise SystemExit(main())
