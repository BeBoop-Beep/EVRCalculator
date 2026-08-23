"""Contract: the builder's publication payload matches the storage schema.

These tests exist because a field can be added to the migration and the RPC
and still be silently absent from the payload the builder sends — which then
fails only at publish time, against production. Every column the RPC inserts
is checked against what `to_publication_payload` actually emits.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from backend.calculations.evr.budget_normalized_product_ranking import (
    BUDGET_COMPARISON_SCOPE_VERSION,
    BUDGET_TYPE_FULL_MARKET,
    BUDGET_TYPE_STANDARD,
    FULL_MARKET_ROUNDING_RULE_VERSION,
)
from backend.scripts.build_budget_normalized_product_rankings import to_publication_payload

MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "db" / "migrations" / "20260822213027_create_budget_normalized_product_rankings.sql"
)


def _row(pid, budget, budget_type, rank, *, full_market=None):
    row = {
        "sealedProductId": pid,
        "setId": "set-%s" % pid,
        "productFamily": "booster_box",
        "productName": "P%s" % pid,
        "productMarketPrice": 100.0,
        "priceAsOf": "2026-08-21",
        "collectorAppealScore": 55.0,
        "sourceCalculationRunId": "run-1",
        "budgetType": budget_type,
        "targetBudget": budget,
        "quantity": int(budget // 100.0),
        "actualCommittedCapital": int(budget // 100.0) * 100.0,
        "unusedCapital": budget - int(budget // 100.0) * 100.0,
        "unusedCapitalPercent": (budget - int(budget // 100.0) * 100.0) / budget,
        "capitalUtilization": (int(budget // 100.0) * 100.0) / budget,
        "budgetRank": rank,
        "budgetCohortSize": 2,
        "budgetTier": "B",
        "financialOnlyRank": rank,
        "financialRipV4Score": 40.0,
        "overallRipV10Score": 42.0,
        "chanceToRecoverCapital": 0.25,
    }
    if full_market:
        row.update({
            "fullMarketAnchor": full_market["budget"],
            "maxEligibleSkuPrice": full_market["maxEligibleSkuPrice"],
            "fullMarketRoundingIncrement": full_market["roundingIncrement"],
            "fullMarketRoundingRule": full_market["roundingRule"],
            "fullMarketRoundingRuleVersion": full_market["roundingRuleVersion"],
        })
    return row


FULL_MARKET = {
    "budget": 1350.0,
    "maxEligibleSkuPrice": 1331.19,
    "roundingIncrement": 50.0,
    "roundingRule": "ceil(maxEligibleSkuPrice / 50) * 50",
    "roundingRuleVersion": FULL_MARKET_ROUNDING_RULE_VERSION,
}


def _results():
    return {
        "authority": {
            "financialRipVersion": "financial_rip_v4_x",
            "overallRipVersion": "overall_rip_v10_x",
            "collectorAppealVersion": "collector_appeal_v5_x",
            "pinnedPriceAsOf": "2026-08-21",
            "excludedRows": [{"noise": True}],
            "productCount": 2,
        },
        "marketDate": "2026-08-21",
        "builtAt": "2026-08-23T00:00:00+00:00",
        "rankingMethodVersion": "budget_product_ranking_v1",
        "allocationMethodVersion": "budget_allocation_floor_quantity_v1",
        "comparisonScopeVersion": BUDGET_COMPARISON_SCOPE_VERSION,
        "fullMarketRoundingRuleVersion": FULL_MARKET_ROUNDING_RULE_VERSION,
        "productCount": 2,
        "cohortFingerprint": "abc123",
        "fullMarket": FULL_MARKET,
        "timings": {},
        "health": {"healthy": True},
        "budgets": {
            "standard_band:250": {
                "rows": [_row("a", 250.0, BUDGET_TYPE_STANDARD, 1), _row("b", 250.0, BUDGET_TYPE_STANDARD, 2)],
            },
            "full_market:1350": {
                "rows": [_row("a", 1350.0, BUDGET_TYPE_FULL_MARKET, 1, full_market=FULL_MARKET)],
            },
        },
    }


def _rpc_row_columns() -> list:
    """Columns the RPC's INSERT INTO ... budget_product_ranking_rows names."""
    sql = MIGRATION.read_text(encoding="utf-8")
    block = sql[sql.index("INSERT INTO public.budget_product_ranking_rows ("):]
    columns = block[block.index("(") + 1: block.index(")")]
    columns = re.sub(r"--[^\n]*", "", columns)
    return [c.strip() for c in columns.split(",") if c.strip() and c.strip() != "snapshot_id"]


def test_every_rpc_row_column_is_emitted_by_the_builder():
    """The gap this test was written to catch: a column added to the migration
    and the RPC but never added to the payload fails only at publish time."""
    _, rows = to_publication_payload(_results())
    emitted = set(rows[0])
    missing = [c for c in _rpc_row_columns() if c not in emitted]
    assert not missing, "RPC inserts columns the builder never emits: %s" % missing


def test_builder_emits_no_column_the_rpc_cannot_store():
    _, rows = to_publication_payload(_results())
    known = set(_rpc_row_columns())
    unknown = sorted(set(rows[0]) - known)
    assert not unknown, "builder emits columns the RPC does not insert: %s" % unknown


def test_capital_fields_reconcile_in_the_emitted_payload():
    _, rows = to_publication_payload(_results())
    for row in rows:
        assert row["actual_committed_capital"] + row["unused_capital"] == pytest.approx(
            row["target_budget"], abs=0.01
        )
        assert row["capital_utilization"] + row["unused_capital_percent"] == pytest.approx(1.0, abs=1e-6)


def test_chance_to_recover_capital_is_populated_not_null():
    """It was historically hard-coded to None, leaving tie-break 3 inert."""
    _, rows = to_publication_payload(_results())
    assert all(row["chance_to_recover_capital"] is not None for row in rows)


def test_financial_only_rank_is_emitted_for_every_row():
    _, rows = to_publication_payload(_results())
    assert all(isinstance(row["financial_only_rank"], int) for row in rows)
    assert all(row["financial_only_rank"] <= row["budget_cohort_size"] for row in rows)


def test_full_market_provenance_is_all_or_nothing():
    """Matches the migration's CHECK: full_market rows carry every anchor
    field; other budget types must carry none of them."""
    _, rows = to_publication_payload(_results())
    fields = (
        "full_market_anchor", "max_eligible_sku_price", "full_market_rounding_rule",
        "full_market_rounding_increment", "full_market_rounding_rule_version",
    )
    for row in rows:
        present = [row.get(f) is not None for f in fields]
        if row["budget_type"] == BUDGET_TYPE_FULL_MARKET:
            assert all(present), "full_market row missing anchor provenance: %s" % row
        else:
            assert not any(present), "non-full-market row carries anchor provenance: %s" % row


def test_snapshot_pins_authority_and_full_market_metadata():
    snapshot, _ = to_publication_payload(_results())
    assert snapshot["pinned_price_as_of"] == "2026-08-21"
    assert snapshot["comparison_scope_version"] == BUDGET_COMPARISON_SCOPE_VERSION
    assert snapshot["full_market_budget"] == 1350.0
    assert snapshot["max_eligible_sku_price"] == 1331.19
    assert snapshot["full_market_rounding_increment"] == 50.0
    assert snapshot["full_market_rounding_rule_version"] == FULL_MARKET_ROUNDING_RULE_VERSION


def test_every_row_price_as_of_matches_the_pinned_authority():
    """The RPC rejects any mismatch; the builder must never construct one."""
    snapshot, rows = to_publication_payload(_results())
    assert all(row["price_as_of"] == snapshot["pinned_price_as_of"] for row in rows)


def test_budget_identity_is_unique_per_product_budget_and_type():
    _, rows = to_publication_payload(_results())
    keys = [(r["sealed_product_id"], r["target_budget"], r["budget_type"]) for r in rows]
    assert len(keys) == len(set(keys))
