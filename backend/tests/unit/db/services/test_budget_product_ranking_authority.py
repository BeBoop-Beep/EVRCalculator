"""Contract: budget-ranking price authority resolves ONE coherent cohort.

The V1 methodology validation watched production grow from 477 to 614 rows
mid-session and end with TWO complete 137-SKU cohorts (`price_as_of`
2026-08-17 and 2026-08-21) plus partial single-set refresh runs in between.

The dangerous resolution is "newest row wins, per SKU": it always returns a
full-looking cohort, so it fails SILENTLY while blending price dates and
calculation runs into one apparently complete ranking. These tests pin the
fail-closed behaviour that prevents it.
"""

from __future__ import annotations

import pytest

from backend.db.services.budget_product_ranking_authority import (
    AuthorityResolutionError,
    EXPECTED_FINANCIAL_RIP_VERSION,
    EXPECTED_OVERALL_RIP_VERSION,
    assert_expected_model_versions,
    load_pinned_cohort,
)

FINANCIAL = EXPECTED_FINANCIAL_RIP_VERSION
OVERALL = EXPECTED_OVERALL_RIP_VERSION
APPEAL = "collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2"


def _row(pid, run, as_of, price=100.0, **overrides):
    row = {
        "sealed_product_id": pid,
        "set_id": "set-%s" % pid,
        "product_family": "booster_box",
        "product_name": "Product %s" % pid,
        "pack_count": 36,
        "random_pack_count": 36,
        "guaranteed_component_count": 0,
        "guaranteed_component_market_value": None,
        "product_market_cost": price,
        "price_as_of": as_of,
        "collector_appeal_score": 55.0,
        "collector_appeal_version": APPEAL,
        "calculation_run_id": run,
        "financial_rip_v4_status": "ready",
        "financial_rip_v4_score": 40.0,
        "financial_rip_v4_version": FINANCIAL,
        "overall_rip_v10_score": 42.0,
        "overall_rip_v10_version": OVERALL,
        "accessory_value_included": False,
    }
    row.update(overrides)
    return row


class _FakeClient:
    """Minimal stand-in for the supabase client's fluent select/eq/execute."""

    def __init__(self, rows):
        self._rows = rows

    def table(self, _name):
        return self

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self._rows = [r for r in self._rows if r.get(column) == value]
        return self

    def execute(self):
        return type("R", (), {"data": list(self._rows)})()


def test_one_coherent_cohort_resolves_without_a_pin():
    client = _FakeClient([_row("a", "run1", "2026-08-21"), _row("b", "run1", "2026-08-21")])
    products, authority = load_pinned_cohort(client)
    assert len(products) == 2
    assert authority["pinnedPriceAsOf"] == "2026-08-21"
    assert authority["pinMode"] == "resolved_by_coverage"
    assert authority["excludedRowCount"] == 0


def test_two_complete_cohorts_without_a_pin_fails_closed():
    """THE critical case. Both dates cover the same SKUs, so coverage cannot
    break the tie and the resolver must refuse rather than guess."""
    client = _FakeClient([
        _row("a", "run1", "2026-08-17"), _row("b", "run1", "2026-08-17"),
        _row("a", "run2", "2026-08-21"), _row("b", "run2", "2026-08-21"),
    ])
    with pytest.raises(AuthorityResolutionError, match="AMBIGUOUS AUTHORITY"):
        load_pinned_cohort(client)


def test_explicit_price_as_of_selects_only_that_cohort():
    rows = [
        _row("a", "run1", "2026-08-17", price=10.0), _row("b", "run1", "2026-08-17", price=20.0),
        _row("a", "run2", "2026-08-21", price=11.0), _row("b", "run2", "2026-08-21", price=21.0),
    ]
    products, authority = load_pinned_cohort(_FakeClient(list(rows)), "2026-08-17")
    assert authority["pinnedPriceAsOf"] == "2026-08-17"
    assert authority["pinMode"] == "explicit"
    assert {p["calculation_run_id"] for p in products} == {"run1"}
    assert sorted(float(p["product_market_cost"]) for p in products) == [10.0, 20.0]
    # The other complete cohort is recorded as excluded provenance, not dropped silently.
    assert authority["excludedRowCount"] == 2
    assert authority["excludedRunCount"] == 1


def test_partial_newer_cohort_does_not_win_on_coverage():
    """A single-set refresh run must never displace the complete cohort."""
    rows = [
        _row("a", "run1", "2026-08-17"), _row("b", "run1", "2026-08-17"), _row("c", "run1", "2026-08-17"),
        _row("a", "run2", "2026-08-21"),
    ]
    products, authority = load_pinned_cohort(_FakeClient(rows))
    assert authority["pinnedPriceAsOf"] == "2026-08-17"
    assert len(products) == 3


def test_same_sku_twice_within_one_pinned_date_fails_closed():
    """Two runs for one SKU inside the pinned date is mixed authority."""
    client = _FakeClient([_row("a", "run1", "2026-08-21"), _row("a", "run2", "2026-08-21")])
    with pytest.raises(AuthorityResolutionError, match="MIXED AUTHORITY"):
        load_pinned_cohort(client)


def test_mixed_model_versions_within_one_cohort_fail_closed():
    client = _FakeClient([
        _row("a", "run1", "2026-08-21"),
        _row("b", "run1", "2026-08-21", financial_rip_v4_version="financial_rip_v5_something"),
    ])
    with pytest.raises(AuthorityResolutionError, match="distinct financial_rip_v4_version"):
        load_pinned_cohort(client)


def test_missing_collector_appeal_score_fails_closed():
    client = _FakeClient([
        _row("a", "run1", "2026-08-21"),
        _row("b", "run1", "2026-08-21", collector_appeal_score=None),
    ])
    with pytest.raises(AuthorityResolutionError, match="missing a financial or collector-appeal score"):
        load_pinned_cohort(client)


def test_unpriced_products_are_excluded_not_ranked_at_zero():
    client = _FakeClient([_row("a", "run1", "2026-08-21"), _row("b", "run1", "2026-08-21", product_market_cost=0)])
    products, _ = load_pinned_cohort(client)
    assert [p["sealed_product_id"] for p in products] == ["a"]


def test_accessory_inclusive_product_fails_closed():
    client = _FakeClient([_row("a", "run1", "2026-08-21", accessory_value_included=True)])
    with pytest.raises(AuthorityResolutionError, match="accessory value"):
        load_pinned_cohort(client)


def test_requesting_an_absent_price_as_of_fails_closed():
    client = _FakeClient([_row("a", "run1", "2026-08-21")])
    with pytest.raises(AuthorityResolutionError, match="no V4-ready rows"):
        load_pinned_cohort(client, "1999-01-01")


def test_empty_source_fails_closed():
    with pytest.raises(AuthorityResolutionError, match="no V4-ready"):
        load_pinned_cohort(_FakeClient([]))


def test_model_drift_is_reported_not_raised():
    """Drift must be visible to an audit run without failing it."""
    clean = {"financialRipVersion": FINANCIAL, "overallRipVersion": OVERALL, "collectorAppealVersion": APPEAL}
    assert assert_expected_model_versions(clean) == []

    drifted = dict(clean, overallRipVersion="overall_rip_v11_something")
    warnings = assert_expected_model_versions(drifted)
    assert len(warnings) == 1
    assert "overall_rip_version drift" in warnings[0]


def test_collector_appeal_drift_is_detected_by_major_version_prefix():
    drifted = {
        "financialRipVersion": FINANCIAL,
        "overallRipVersion": OVERALL,
        "collectorAppealVersion": "collector_appeal_v6_new_model",
    }
    warnings = assert_expected_model_versions(drifted)
    assert any("collector_appeal_version drift" in w for w in warnings)
