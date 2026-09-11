"""Observation-only check adapters for inDex Sentinel."""

from backend.sentinel.checks.authorities import (
    CANONICAL_LEGACY_RUNNING_GRACE_SECONDS,
    check_alert_delivery,
    check_market_freshness,
    check_post_scrape_publication_audit,
    check_publication_batch_gate,
    check_scrape_queue_leases,
    check_set_page_generation,
)
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
from backend.sentinel.checks.registry import (
    AUDIT_CHECK_KEYS,
    FAST_CHECK_KEYS,
    INDEPENDENT_CHECK_KEYS,
    PUBLIC_CHECK_KEYS,
    build_audit_registry,
    build_fast_registry,
    build_independent_registry,
    build_profile_registry,
    build_public_registry,
)

__all__ = [
    "AUDIT_CHECK_KEYS",
    "CANONICAL_LEGACY_RUNNING_GRACE_SECONDS",
    "DEFAULT_HEARTBEAT_MAX_AGE_SECONDS",
    "DEFAULT_HTTP_TIMEOUT_SECONDS",
    "FAST_CHECK_KEYS",
    "INDEPENDENT_CHECK_KEYS",
    "PUBLIC_CHECK_KEYS",
    "build_audit_registry",
    "build_fast_registry",
    "build_independent_registry",
    "build_profile_registry",
    "build_public_registry",
    "check_alert_delivery",
    "check_backend_health",
    "check_component_heartbeat",
    "check_homepage_rankings",
    "check_market_freshness",
    "check_market_public_snapshot",
    "check_post_scrape_publication_audit",
    "check_publication_batch_gate",
    "check_rankings_lens",
    "check_representative_set_page",
    "check_scrape_queue_leases",
    "check_set_page_generation",
    "check_tcg_directory",
]
