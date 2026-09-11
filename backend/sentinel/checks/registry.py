"""Canonical Sentinel check profiles for inDex authorities and public surfaces."""

from __future__ import annotations

from typing import Any, Callable, Optional

from backend.sentinel.checks.authorities import (
    check_alert_delivery,
    check_market_freshness,
    check_post_scrape_publication_audit,
    check_publication_batch_gate,
    check_scrape_queue_leases,
    check_set_page_generation,
)
from backend.sentinel.checks.public_semantics import (
    DEFAULT_HTTP_TIMEOUT_SECONDS,
    check_backend_health,
    check_homepage_rankings,
    check_market_public_snapshot,
    check_rankings_lens,
    check_representative_set_page,
    check_tcg_directory,
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
PUBLIC_CHECK_KEYS = (
    "public.backend_health",
    "public.market",
    "public.rankings.homepage",
    "public.rankings.sets",
    "public.rankings.eras",
    "public.rankings.products",
    "public.tcgs",
    "public.setpage.representative",
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


def build_public_registry(
    *,
    backend_base_url: str = "",
    http_get: Optional[Callable[..., Any]] = None,
    timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
) -> CheckRegistry:
    """User-visible public HTTP contracts. No auth/cookie headers are sent."""
    registry = CheckRegistry()
    common = {
        "base_url": backend_base_url,
        "http_get": http_get,
        "timeout_seconds": timeout_seconds,
    }
    registry.register(
        "public.backend_health",
        lambda ctx: check_backend_health(ctx, **common),
        description="Backend liveness/build identity contract",
        confirm_after=2,
        exception_severity=Severity.CRITICAL,
    )
    registry.register(
        "public.market",
        lambda ctx: check_market_public_snapshot(ctx, **common),
        description="Public Market Set Value payload is nonempty and usable",
        confirm_after=2,
        exception_severity=Severity.CRITICAL,
    )
    registry.register(
        "public.rankings.homepage",
        lambda ctx: check_homepage_rankings(ctx, **common),
        description="Homepage public Set RIP projection has rankable rows",
        confirm_after=2,
        exception_severity=Severity.CRITICAL,
    )
    for lens in ("sets", "eras", "products"):
        registry.register(
            f"public.rankings.{lens}",
            lambda ctx, resolved_lens=lens: check_rankings_lens(
                ctx, lens=resolved_lens, **common
            ),
            description=f"Public Rankings {lens} lens is semantically nonempty",
            confirm_after=2,
            exception_severity=Severity.CRITICAL,
        )
    registry.register(
        "public.tcgs",
        lambda ctx: check_tcg_directory(ctx, **common),
        description="Public TCG directory includes Pokémon",
        confirm_after=2,
        exception_severity=Severity.CRITICAL,
    )
    registry.register(
        "public.setpage.representative",
        lambda ctx: check_representative_set_page(ctx, **common),
        description="Current #1 public ranked set resolves to a usable set page",
        confirm_after=2,
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


def _merge_registry(target: CheckRegistry, source: CheckRegistry) -> None:
    for check in source.all():
        target.register(
            check.key,
            check.run,
            description=check.description,
            confirm_after=check.confirm_after,
            exception_severity=check.exception_severity,
        )


def build_profile_registry(
    profile: str,
    *,
    client: Any = None,
    backend_base_url: str = "",
    http_get: Optional[Callable[..., Any]] = None,
    timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
) -> CheckRegistry:
    normalized = str(profile or "").strip().lower()
    if normalized == "fast":
        return build_fast_registry(client=client)
    if normalized == "public":
        return build_public_registry(
            backend_base_url=backend_base_url,
            http_get=http_get,
            timeout_seconds=timeout_seconds,
        )
    if normalized == "audit":
        return build_audit_registry(client=client)
    if normalized == "all":
        registry = build_fast_registry(client=client)
        _merge_registry(
            registry,
            build_public_registry(
                backend_base_url=backend_base_url,
                http_get=http_get,
                timeout_seconds=timeout_seconds,
            ),
        )
        _merge_registry(registry, build_audit_registry(client=client))
        return registry
    raise ValueError("Sentinel profile must be one of: fast, public, audit, all")
