from backend.sentinel.checks.registry import (
    AUDIT_CHECK_KEYS,
    DEPLOY_CHECK_KEYS,
    FAST_CHECK_KEYS,
    INDEPENDENT_CHECK_KEYS,
    PUBLIC_CHECK_KEYS,
    RUNTIME_CHECK_KEYS,
    build_audit_registry,
    build_deploy_registry,
    build_fast_registry,
    build_independent_registry,
    build_profile_registry,
    build_public_registry,
    build_runtime_registry,
)


def test_fast_registry_has_only_bounded_operational_checks():
    registry = build_fast_registry(client=object())
    assert registry.keys() == tuple(sorted(FAST_CHECK_KEYS))
    assert "publication.audit.post_scrape" not in registry.keys()


def test_public_registry_has_only_public_semantic_checks():
    registry = build_public_registry(
        backend_base_url="https://api.example.test", http_get=lambda *a, **k: None
    )
    assert registry.keys() == tuple(sorted(PUBLIC_CHECK_KEYS))
    assert all(registry.get(key).confirm_after == 2 for key in PUBLIC_CHECK_KEYS)


def test_independent_registry_is_separate_and_heartbeat_age_is_its_confirmation_window():
    registry = build_independent_registry(
        client=object(),
        watch_component="sentinel_vm",
        watch_host="tcgplayer-scraper-pokemon",
        max_age_seconds=900,
    )
    assert registry.keys() == tuple(sorted(INDEPENDENT_CHECK_KEYS))
    assert registry.get("watcher.component_heartbeat").confirm_after == 1


def test_deploy_registry_is_explicit_and_immediate():
    registry = build_deploy_registry(
        backend_base_url="https://backend.example.test",
        frontend_base_url="https://index.example.test",
        expected_release_sha="a" * 40,
        http_get=lambda *a, **k: None,
    )
    assert registry.keys() == tuple(sorted(DEPLOY_CHECK_KEYS))
    assert registry.get("deployment.release_identity").confirm_after == 1


def test_runtime_registry_is_explicit_and_immediate():
    registry = build_runtime_registry(
        repo_path="/repo",
        overlay_manifest_path="/repo/manifest.json",
    )
    assert registry.keys() == tuple(sorted(RUNTIME_CHECK_KEYS))
    assert registry.get("runtime.vm_provenance").confirm_after == 1


def test_heavy_audit_is_separate_profile():
    registry = build_audit_registry(client=object())
    assert registry.keys() == tuple(sorted(AUDIT_CHECK_KEYS))


def test_all_profile_combines_without_special_failure_domain_canaries():
    registry = build_profile_registry(
        "all",
        client=object(),
        backend_base_url="https://api.example.test",
        http_get=lambda *a, **k: None,
    )
    assert registry.keys() == tuple(
        sorted((*FAST_CHECK_KEYS, *PUBLIC_CHECK_KEYS, *AUDIT_CHECK_KEYS))
    )
    assert not set(INDEPENDENT_CHECK_KEYS).intersection(registry.keys())
    assert not set(DEPLOY_CHECK_KEYS).intersection(registry.keys())
    assert not set(RUNTIME_CHECK_KEYS).intersection(registry.keys())


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
        assert "fast, public, independent, deploy, runtime, audit, all" in str(exc)
    else:
        raise AssertionError("unknown profile must fail")
