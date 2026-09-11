"""Existing-authority check adapters for inDex Sentinel."""

from backend.sentinel.checks.authorities import (
    CANONICAL_LEGACY_RUNNING_GRACE_SECONDS,
    check_alert_delivery,
    check_market_freshness,
    check_post_scrape_publication_audit,
    check_publication_batch_gate,
    check_scrape_queue_leases,
    check_set_page_generation,
)
from backend.sentinel.checks.registry import (
    AUDIT_CHECK_KEYS,
    FAST_CHECK_KEYS,
    build_audit_registry,
    build_fast_registry,
    build_profile_registry,
)

__all__ = [
    "AUDIT_CHECK_KEYS",
    "CANONICAL_LEGACY_RUNNING_GRACE_SECONDS",
    "FAST_CHECK_KEYS",
    "build_audit_registry",
    "build_fast_registry",
    "build_profile_registry",
    "check_alert_delivery",
    "check_market_freshness",
    "check_post_scrape_publication_audit",
    "check_publication_batch_gate",
    "check_scrape_queue_leases",
    "check_set_page_generation",
]
