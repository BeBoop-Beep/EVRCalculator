"""Read-only operational runner for Sentinel authority and public profiles."""

from __future__ import annotations

import argparse
import json
from typing import Any, Callable, Optional

from backend.sentinel.checks.registry import build_profile_registry
from backend.sentinel.config import SentinelConfig
from backend.sentinel.runner import run_once
from backend.sentinel.state import NoopStateStore


_PUBLIC_PROFILES = {"public", "all"}


def run_profile(
    profile: str,
    *,
    config: Optional[SentinelConfig] = None,
    client: Any = None,
    http_get: Optional[Callable[..., Any]] = None,
):
    resolved = config or SentinelConfig.from_env()
    resolved.validate_kernel_v1()
    if resolved.state_writes_enabled:
        raise RuntimeError(
            "Sentinel observation profiles are read-only; "
            "SENTINEL_STATE_WRITES_ENABLED must remain false until schema activation"
        )
    normalized = str(profile or "").strip().lower()
    if normalized in _PUBLIC_PROFILES and not resolved.backend_base_url:
        raise RuntimeError(
            "SENTINEL_BACKEND_BASE_URL is required for the public Sentinel profile"
        )
    registry = build_profile_registry(
        normalized,
        client=client,
        backend_base_url=resolved.backend_base_url,
        http_get=http_get,
        timeout_seconds=resolved.public_http_timeout_seconds,
    )
    return run_once(registry, config=resolved, store=NoopStateStore())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=("fast", "public", "audit", "all"),
        default="fast",
        help="Profile to evaluate. Audit is intentionally separate/heavier.",
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
        )
        print(json.dumps({"profile": args.profile, "checks": list(registry.keys())}, indent=2, sort_keys=True))
        return 0

    try:
        summary = run_profile(args.profile)
    except RuntimeError as exc:
        print(json.dumps({"healthy": False, "status": "configuration_error", "error": str(exc)}, indent=2, sort_keys=True))
        return 2

    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0 if summary.get("healthy") else 1


if __name__ == "__main__":
    raise SystemExit(main())
