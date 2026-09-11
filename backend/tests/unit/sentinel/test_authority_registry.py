from backend.sentinel.checks.registry import (
    AUDIT_CHECK_KEYS,
    FAST_CHECK_KEYS,
    build_audit_registry,
    build_fast_registry,
    build_profile_registry,
)


def test_fast_registry_has_only_bounded_operational_checks():
    registry = build_fast_registry(client=object())
    assert registry.keys() == tuple(sorted(FAST_CHECK_KEYS))
    assert "publication.audit.post_scrape" not in registry.keys()


def test_heavy_audit_is_separate_profile():
    registry = build_audit_registry(client=object())
    assert registry.keys() == tuple(sorted(AUDIT_CHECK_KEYS))


def test_all_profile_combines_without_duplicates():
    registry = build_profile_registry("all", client=object())
    assert registry.keys() == tuple(sorted((*FAST_CHECK_KEYS, *AUDIT_CHECK_KEYS)))


def test_market_freshness_keeps_confirmation_window_while_deterministic_checks_are_immediate():
    registry = build_fast_registry(client=object())
    assert registry.get("market.freshness").confirm_after == 2
    assert registry.get("scrape.queue_leases").confirm_after == 1
    assert registry.get("publication.batch_gate").confirm_after == 1
    assert registry.get("setpage.generation").confirm_after == 1
    assert registry.get("alerts.delivery").confirm_after == 1


def test_unknown_profile_is_rejected():
    try:
        build_profile_registry("unknown", client=object())
    except ValueError as exc:
        assert "fast, audit, all" in str(exc)
    else:
        raise AssertionError("unknown profile must fail")
