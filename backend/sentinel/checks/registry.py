"""Canonical Sentinel check profiles for inDex authorities and public surfaces."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Sequence, Tuple

from backend.sentinel.checks.authorities import (
    check_alert_delivery,
    check_market_freshness,
    check_post_scrape_publication_audit,
    check_publication_batch_gate,
    check_scrape_queue_leases,
    check_set_page_generation,
)
from backend.sentinel.checks.deployment import check_release_identity
from backend.sentinel.checks.independent import (
    DEFAULT_HEARTBEAT_MAX_AGE_SECONDS,
    check_component_heartbeat,
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
from backend.sentinel.checks.runtime_provenance import (
    check_vm_runtime_provenance,
    load_vm_overlay_manifest,
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
INDEPENDENT_CHECK_KEYS = ("watcher.component_heartbeat",)
DEPLOY_CHECK_KEYS = ("deployment.release_identity",)
RUNTIME_CHECK_KEYS = ("runtime.vm_provenance",)
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


def build_independent_registry(
    *,
    client: Any = None,
    watch_component: str = "sentinel_vm",
    watch_host: str,
    max_age_seconds: int = DEFAULT_HEARTBEAT_MAX_AGE_SECONDS,
) -> CheckRegistry:
    """Watch a Sentinel heartbeat from a DIFFERENT host/failure domain."""
    registry = CheckRegistry()
    registry.register(
        "watcher.component_heartbeat",
        lambda ctx: check_component_heartbeat(
            ctx,
            client=client,
            component=watch_component,
            host=watch_host,
            max_age_seconds=max_age_seconds,
        ),
        description="Independent stale/missing Sentinel component heartbeat",
        confirm_after=1,
        exception_severity=Severity.CRITICAL,
    )
    return registry


def build_deploy_registry(
    *,
    backend_base_url: str,
    frontend_base_url: str,
    expected_release_sha: str,
    expected_release_branch: str = "main",
    expected_frontend_environment: str = "production",
    http_get: Optional[Callable[..., Any]] = None,
    timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
) -> CheckRegistry:
    """Explicit post-deploy release identity canary; not part of continuous `all`."""
    registry = CheckRegistry()
    registry.register(
        "deployment.release_identity",
        lambda ctx: check_release_identity(
            ctx,
            backend_base_url=backend_base_url,
            frontend_base_url=frontend_base_url,
            expected_sha=expected_release_sha,
            expected_branch=expected_release_branch,
            expected_environment=expected_frontend_environment,
            http_get=http_get,
            timeout_seconds=timeout_seconds,
        ),
        description="Backend + frontend serve the explicitly expected release SHA",
        confirm_after=1,
        exception_severity=Severity.CRITICAL,
    )
    return registry


def build_runtime_registry(
    *,
    repo_path: str,
    overlay_manifest_path: str,
    git_runner: Optional[Callable[[str, Sequence[str]], Tuple[int, str, str]]] = None,
    manifest_loader: Callable[[str], Dict[str, Any]] = load_vm_overlay_manifest,
) -> CheckRegistry:
    """Production VM main-release + approved-overlay provenance check."""
    registry = CheckRegistry()
    registry.register(
        "runtime.vm_provenance",
        lambda ctx: check_vm_runtime_provenance(
            ctx,
            repo_path=repo_path,
            manifest_path=overlay_manifest_path,
            git_runner=git_runner,
            manifest_loader=manifest_loader,
        ),
        description="VM remains main-based with only explicitly approved overlay paths",
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
    frontend_base_url: str = "",
    expected_release_sha: str = "",
    expected_release_branch: str = "main",
    expected_frontend_environment: str = "production",
    http_get: Optional[Callable[..., Any]] = None,
    timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
    watch_component: str = "sentinel_vm",
    watch_host: str = "",
    heartbeat_max_age_seconds: int = DEFAULT_HEARTBEAT_MAX_AGE_SECONDS,
    runtime_repo_path: str = "",
    runtime_overlay_manifest_path: str = "",
    git_runner: Optional[Callable[[str, Sequence[str]], Tuple[int, str, str]]] = None,
    manifest_loader: Callable[[str], Dict[str, Any]] = load_vm_overlay_manifest,
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
    if normalized == "independent":
        return build_independent_registry(
            client=client,
            watch_component=watch_component,
            watch_host=watch_host,
            max_age_seconds=heartbeat_max_age_seconds,
        )
    if normalized == "deploy":
        return build_deploy_registry(
            backend_base_url=backend_base_url,
            frontend_base_url=frontend_base_url,
            expected_release_sha=expected_release_sha,
            expected_release_branch=expected_release_branch,
            expected_frontend_environment=expected_frontend_environment,
            http_get=http_get,
            timeout_seconds=timeout_seconds,
        )
    if normalized == "runtime":
        return build_runtime_registry(
            repo_path=runtime_repo_path,
            overlay_manifest_path=runtime_overlay_manifest_path,
            git_runner=git_runner,
            manifest_loader=manifest_loader,
        )
    if normalized == "audit":
        return build_audit_registry(client=client)
    if normalized == "all":
        # Deliberately excludes `independent`, `deploy`, and `runtime`: those
        # require distinct failure domains or explicit release/runtime authority.
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
    raise ValueError(
        "Sentinel profile must be one of: fast, public, independent, deploy, runtime, audit, all"
    )
