"""Contract-alignment regressions for the resilient market publication audit."""

from __future__ import annotations

from backend.scripts import audit_pokemon_market_publication as core
from backend.scripts import audit_pokemon_market_publication_resilient as runtime


DATE = "2026-09-15"


def _page(*, explicit_market_date=None, as_of="2026-09-17T04:30:00+00:00"):
    snapshot = {}
    if explicit_market_date is not None:
        snapshot["marketAsOfDate"] = explicit_market_date
    return {
        "set_id": "set-1",
        "payload_json": {"meta": {"snapshot": snapshot}},
        "title_card_json": {},
        "market_summary_json": {},
        "as_of": as_of,
    }


def _global_target(*, history_point_count=1, windows=None):
    return {
        "setId": "set-1",
        "currentSetValue": 100.0,
        "setValueAsOf": DATE,
        "windows": {} if windows is None else windows,
        "historyStartDate": DATE,
        "historyEndDate": DATE,
        "historyPointCount": history_point_count,
    }


def test_header_does_not_treat_generic_as_of_build_time_as_market_date():
    verdict = runtime._runtime_audit_header_summary(DATE, _page(), [])

    assert verdict.passed is True
    assert verdict.applicable is False
    assert verdict.observed_date is None
    assert "not used as market-date authority" in verdict.detail


def test_header_still_fails_an_explicit_future_market_date():
    verdict = runtime._runtime_audit_header_summary(
        DATE,
        _page(explicit_market_date="2026-09-17"),
        [],
    )

    assert verdict.applicable is True
    assert verdict.passed is False
    assert verdict.observed_date == "2026-09-17"
    assert "ahead of the promoted market date" in verdict.detail


def test_header_still_fails_when_explicit_date_is_ahead_of_a_dependency():
    dependency = core.SectionVerdict(
        section=core.SECTION_SEALED_MARKET,
        observed_date="2026-09-14",
    )
    verdict = runtime._runtime_audit_header_summary(
        DATE,
        _page(explicit_market_date=DATE),
        [dependency],
    )

    assert verdict.applicable is True
    assert verdict.passed is False
    assert "sealed_market@2026-09-14" in verdict.detail


def test_global_set_value_cohort_uses_market_root_authority_resolver(monkeypatch):
    marker = object()
    captured = {}

    def fake_resolver(client, *, market_date=None):
        captured["client"] = client
        captured["market_date"] = market_date
        return ["root-a", "root-b"]

    monkeypatch.setattr(runtime, "resolve_market_root_ids", fake_resolver)

    assert runtime._runtime_global_set_value_cohort_ids(marker, DATE) == ["root-a", "root-b"]
    assert captured == {"client": marker, "market_date": DATE}


def test_runtime_query_supports_authority_lte_filter():
    query = (
        runtime._RetryingQuery("pokemon_market_root_authority")
        .select("set_id")
        .eq("enabled", True)
        .lte("activated_market_date", DATE)
    )

    assert query._operations[-1] == ("lte", ("activated_market_date", DATE), {})


def test_single_current_set_value_point_does_not_owe_movement_windows():
    verdict = runtime._runtime_audit_global_set_value(
        DATE,
        target=_global_target(),
        canonical_set_value=100.0,
        in_cohort=True,
    )

    assert verdict.passed is True
    assert verdict.applicable is True
    assert "single-point current Set Value history" in verdict.detail


def test_multi_point_set_value_still_fails_when_windows_are_missing():
    target = _global_target(history_point_count=2)
    target["historyStartDate"] = "2026-09-14"
    verdict = runtime._runtime_audit_global_set_value(
        DATE,
        target=target,
        canonical_set_value=100.0,
        in_cohort=True,
    )

    assert verdict.passed is False
    assert "missing window metadata" in verdict.detail


def test_stale_sealed_snapshot_is_truthful_when_source_never_reached_market_date():
    verdict = runtime._runtime_audit_sealed(
        DATE,
        {"market_date": "2026-08-15", "product_count": 1},
        True,
        sealed_source_latest_date=None,
    )

    assert verdict.passed is True
    assert verdict.applicable is True
    assert verdict.observed_date == "2026-08-15"
    assert "no observation on/after" in verdict.detail


def test_sealed_snapshot_still_fails_when_source_reached_market_date():
    verdict = runtime._runtime_audit_sealed(
        DATE,
        {"market_date": "2026-08-15", "product_count": 1},
        True,
        sealed_source_latest_date=DATE,
    )

    assert verdict.passed is False
    assert "source has an observation" in verdict.detail


def test_runtime_temporarily_installs_and_restores_all_contract_adapters(monkeypatch):
    original_global = core.global_set_value_cohort_ids
    original_header = core._audit_header_summary
    original_global_audit = core._audit_global_set_value
    original_sealed_audit = core._audit_sealed
    original_loader = core._load_rows
    captured = {}

    monkeypatch.setattr(runtime, "resolve_market_root_ids", lambda _client, *, market_date=None: ["root-a"])

    def fake_core_run(client, *, market_date=None, canonical_keys=None, phase=None):
        captured["cohort"] = core.global_set_value_cohort_ids([{"id": "simulation-only"}])
        captured["header"] = core._audit_header_summary(DATE, _page(), [])
        captured["global"] = core._audit_global_set_value(
            DATE,
            target=_global_target(),
            canonical_set_value=100.0,
            in_cohort=True,
        )
        captured["sealed"] = core._audit_sealed(
            DATE,
            {"market_date": "2026-08-15", "product_count": 1},
            True,
            sealed_source_latest_date=None,
        )
        return core.MarketAuditReport(market_date=DATE, rows=[])

    monkeypatch.setattr(core, "run_market_publication_audit", fake_core_run)
    runtime.run_market_publication_audit(market_date=DATE, phase=core.PHASE_POST_SCRAPE)

    assert captured["cohort"] == ["root-a"]
    assert captured["header"].applicable is False
    assert captured["global"].passed is True
    assert captured["sealed"].passed is True
    assert core.global_set_value_cohort_ids is original_global
    assert core._audit_header_summary is original_header
    assert core._audit_global_set_value is original_global_audit
    assert core._audit_sealed is original_sealed_audit
    assert core._load_rows is original_loader
