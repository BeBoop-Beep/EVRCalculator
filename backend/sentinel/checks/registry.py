"""Canonical Sentinel check profiles for existing inDex authorities."""

from __future__ import annotations

from typing import Any

from backend.sentinel.checks.authorities import (
    check_alert_delivery,
    check_market_freshness,
    check_post_scrape_publication_audit,
    check_publication_batch_gate,
    check_scrape_queue_leases,
    check_set_page_generation,
)
from backend.sentinel.models import Severity
from backend.sentinel.registry import CheckRegistry


FAST_CHECK_KEYS = (
    "alerts.delivery",
    "market.freshness",
    "publication.batch_gate",
    "scrape.queue_leases",
    "setpage.generation",
)
AUDIT_CHECK_KEYS = ("publication.audit.post_scrape",)


def build_fast_registry(*, client: Any = None) -> CheckRegistry:
    registry = CheckRegistry()
    registry.register(
        "alerts.delivery",
        lambda ctx: check_alert_delivery(ctx),
        description="Alert dispatcher configuration and backlog health",
        confirm_after=1,
        exception_severity=Severity.CRITICAL,
    )
    registry.register(
        "market.freshness",
        lambda ctx: check_market_freshness(ctx, client=client),
        description="Existing Phoenix market freshness watchdog in read-only mode",
        confirm_after=2,
        exception_severity=Severity.CRITICAL,
    )
    registry.register(
        "publication.batch_gate",
        lambda ctx: check_publication_batch_gate(ctx, client=client),
        description="Canonical scrape-batch publication gate contract",
        confirm_after=1,
        exception_severity=Severity.CRITICAL,
    )
    registry.register(
        "scrape.queue_leases",
        lambda ctx: check_scrape_queue_leases(ctx, client=client),
        description="Expired running scrape-job leases",
        confirm_after=1,
        exception_severity=Severity.CRITICAL,
    )
    registry.register(
        "setpage.generation",
        lambda ctx: check_set_page_generation(ctx, client=client),
        description="Current set-page generation pointer and publication contract",
        confirm_after=1,
        exception_severity=Severity.CRITICAL,
    )
    return registry


def build_audit_registry(*, client: Any = None) -> CheckRegistry:
    registry = CheckRegistry()
    registry.register(
        "publication.audit.post_scrape",
        lambda ctx: check_post_scrape_publication_audit(ctx, client=client),
        description="Heavy canonical post-scrape publication audit",
        confirm_after=1,
        exception_severity=Severity.CRITICAL,
    )
    return registry


def build_profile_registry(profile: str, *, client: Any = None) -> CheckRegistry:
    normalized = str(profile or "").strip().lower()
    if normalized == "fast":
        return build_fast_registry(client=client)
    if normalized == "audit":
        return build_audit_registry(client=client)
    if normalized == "all":
        registry = build_fast_registry(client=client)
        audit = build_audit_registry(client=client)
        for check in audit.all():
            registry.register(
                check.key,
                check.run,
                description=check.description,
                confirm_after=check.confirm_after,
                exception_severity=check.exception_severity,
            )
        return registry
    raise ValueError("Sentinel profile must be one of: fast, audit, all")
