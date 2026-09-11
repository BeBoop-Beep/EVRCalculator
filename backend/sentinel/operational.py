"""Operational runner for Sentinel authority, public, and watcher profiles."""

from __future__ import annotations

import argparse
import json
from typing import Any, Callable, Optional

from backend.sentinel.checks.registry import build_profile_registry
from backend.sentinel.config import SentinelConfig
from backend.sentinel.deadman import ping_deadman
from backend.sentinel.runner import run_once
from backend.sentinel.state import (
    NoopStateStore,
    SentinelStateStore,
    SupabaseStateStore,
    build_state_store,
)


_PUBLIC_PROFILES = {"public", "all"}


def _state_store(
    resolved: SentinelConfig,
    *,
    client: Any = None,
    store: Optional[SentinelStateStore] = None,
) -> SentinelStateStore:
    if store is not None:
        return store
    if not resolved.state_writes_enabled:
        return NoopStateStore()
    if not resolved.persistence_schema_ready:
        raise RuntimeError(
            "Sentinel observation profiles are read-only until schema activation; "
            "SENTINEL_PERSISTENCE_SCHEMA_READY must be true before state writes"
        )
    if client is not None:
        return SupabaseStateStore(client)
    return build_state_store(True)


def run_profile(
    profile: str,
    *,
    config: Optional[SentinelConfig] = None,
    client: Any = None,
    http_get: Optional[Callable[..., Any]] = None,
    deadman_get: Optional[Callable[..., Any]] = None,
    store: Optional[SentinelStateStore] = None,
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

    resolved_store = _state_store(resolved, client=client, store=store)
    registry = build_profile_registry(
        normalized,
        client=client,
        backend_base_url=resolved.backend_base_url,
        http_get=http_get,
        timeout_seconds=resolved.public_http_timeout_seconds,
        watch_component=resolved.watch_component,
        watch_host=resolved.watch_host,
        heartbeat_max_age_seconds=resolved.heartbeat_max_age_seconds,
    )
    summary = run_once(registry, config=resolved, store=resolved_store)

    # A dead-man ping proves that a Sentinel cycle reached completion. It is
    # intentionally sent whether semantic checks passed or failed; missing pings
    # mean the watcher itself stopped running/completing, not merely that one
    # monitored business surface is unhealthy.
    deadman = ping_deadman(
        resolved.deadman_ping_url,
        timeout_seconds=resolved.deadman_timeout_seconds,
        http_get=deadman_get,
    )
    summary["deadman"] = deadman.to_dict()
    if deadman.configured and not deadman.delivered:
        summary["healthy"] = False
        if summary.get("status") == "healthy":
            summary["status"] = "deadman_delivery_failed"
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=("fast", "public", "independent", "audit", "all"),
        default="fast",
        help=(
            "Profile to evaluate. Independent must run outside the watched "
            "component's failure domain; audit is intentionally heavier."
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
            backend_base_url="https://sentinel.invalid",
            watch_host="watched-host.invalid",
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
