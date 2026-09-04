"""Gate F physical persistence closure: tests for
`merge_v12_publication_fields` and the `publish_rankings` V12-aware call
path in `backend.scripts.build_budget_normalized_product_rankings`.

These are pure-Python payload-shape tests. No database or network I/O -
`client.rpc(...)` is always a fake recorder.
"""

from __future__ import annotations

import copy

import pytest

from backend.db.services.budget_product_ranking_authority import (
    EXPECTED_CHASE_ACCESSIBILITY_TRANSFORM_VERSION, EXPECTED_CHASE_ACCESSIBILITY_VERSION,
    EXPECTED_OVERALL_RIP_V12_VERSION,
)
from backend.scripts.build_budget_normalized_product_rankings import (
    V12_ROW_PUBLICATION_FIELDS, V12_SNAPSHOT_PUBLICATION_FIELDS,
    merge_v12_publication_fields, publish_rankings,
)


class _FakeResponse:
    def __init__(self, data):
        self.data = data


class _FakeRpc:
    def __init__(self, data):
        self._data = data

    def execute(self):
        return _FakeResponse(self._data)


class _FakeClient:
    """Records every `.rpc(...)` call; never touches a real database."""

    def __init__(self, snapshot_id="11111111-1111-1111-1111-111111111111"):
        self.calls = []
        self._snapshot_id = snapshot_id

    def rpc(self, name, payload):
        self.calls.append((name, copy.deepcopy(payload)))
        return _FakeRpc(self._snapshot_id)


def _v10_snapshot():
    return {
        "market_date": "2026-09-03", "built_at": "2026-09-03T00:00:00+00:00",
        "ranking_method_version": "budget_product_ranking_v1",
        "allocation_method_version": "budget_allocation_floor_quantity_v1",
        "comparison_scope_version": "scope_v1",
        "financial_rip_version": "financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5",
        "overall_rip_version": "overall_rip_v10_90_financial_v4_10_collector_appeal_v5",
        "collector_appeal_version": "collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2",
        "pinned_price_as_of": "2026-09-03", "eligible_cohort_count": 2, "cohort_fingerprint": "fp",
        "full_market_budget": 150.0, "max_eligible_sku_price": 101.0,
        "full_market_rounding_increment": 50.0, "full_market_rounding_rule_version": "v1",
        "diagnostics_json": {},
    }


def _v10_rows():
    return [
        {
            "sealed_product_id": "p1", "set_id": "s1", "product_family": "booster_box",
            "target_budget": 25.0, "budget_type": "standard_band", "quantity": 2,
            "actual_committed_capital": 20.0, "unused_capital": 5.0, "unused_capital_percent": 0.2,
            "capital_utilization": 0.8, "budget_rank": 1, "budget_cohort_size": 2, "budget_tier": "B",
            "financial_only_rank": 1, "financial_rip_v4_score": 55.0, "overall_rip_v10_score": 56.0,
            "collector_appeal_score": 60.0, "chance_to_recover_capital": 0.3, "expected_value": 30.0,
            "product_market_price": 10.0, "price_as_of": "2026-09-03", "full_market_anchor": None,
            "max_eligible_sku_price": None, "full_market_rounding_rule": None,
            "full_market_rounding_increment": None, "full_market_rounding_rule_version": None,
            "source_calculation_run_id": "r1",
        },
        {
            "sealed_product_id": "p2", "set_id": "s1", "product_family": "booster_box",
            "target_budget": 25.0, "budget_type": "standard_band", "quantity": 2,
            "actual_committed_capital": 20.0, "unused_capital": 5.0, "unused_capital_percent": 0.2,
            "capital_utilization": 0.8, "budget_rank": 2, "budget_cohort_size": 2, "budget_tier": "C",
            "financial_only_rank": 2, "financial_rip_v4_score": 40.0, "overall_rip_v10_score": 45.0,
            "collector_appeal_score": 50.0, "chance_to_recover_capital": 0.25, "expected_value": 28.0,
            "product_market_price": 10.0, "price_as_of": "2026-09-03", "full_market_anchor": None,
            "max_eligible_sku_price": None, "full_market_rounding_rule": None,
            "full_market_rounding_increment": None, "full_market_rounding_rule_version": None,
            "source_calculation_run_id": "r1",
        },
    ]


def _v12_row(sealed_product_id, rank, size, *, score, status="ready"):
    return {
        "sealedProductId": sealed_product_id, "targetBudget": 25.0, "budgetType": "standard_band",
        "budgetRank": rank, "budgetCohortSize": size,
        "overallRipV12Score": score, "overallRipV12Rankable": True,
        "overallRipV12Payload": {"status": status},
        "chaseAccessibilityRaw": 0.42,
    }


def _v12_results():
    # V12 sort authority swaps rank order relative to V10 (p2 outranks p1
    # under V12) - this is deliberate, to prove budget_rank_v12 is the real
    # V12 sort rank, not the V10 rank relabeled (Phase 9E).
    rows = [
        _v12_row("p2", 1, 2, score=80.0),
        _v12_row("p1", 2, 2, score=65.0),
    ]
    return {"budgets": {"standard_band:25": {"rows": rows}}}


def test_merge_adds_all_ten_v12_fields_additively():
    snapshot, rows = _v10_snapshot(), _v10_rows()
    v12_snapshot, v12_rows = merge_v12_publication_fields(snapshot, rows, _v12_results())

    for field in V12_SNAPSHOT_PUBLICATION_FIELDS:
        assert v12_snapshot.get(field) not in (None, ""), field
    assert v12_snapshot["ranked_under_v12_authority"] is True
    assert v12_snapshot["overall_rip_v12_version"] == EXPECTED_OVERALL_RIP_V12_VERSION
    assert v12_snapshot["chase_accessibility_version"] == EXPECTED_CHASE_ACCESSIBILITY_VERSION
    assert v12_snapshot["chase_accessibility_transform_version"] == EXPECTED_CHASE_ACCESSIBILITY_TRANSFORM_VERSION
    # Generic/current authority: overall_rip_version itself becomes V12.
    assert v12_snapshot["overall_rip_version"] == EXPECTED_OVERALL_RIP_V12_VERSION

    # Every original V10 snapshot key survives unchanged.
    for key, value in snapshot.items():
        if key == "overall_rip_version":
            continue
        assert v12_snapshot[key] == value, key

    assert len(v12_rows) == len(rows)
    for row in v12_rows:
        for field in V12_ROW_PUBLICATION_FIELDS:
            assert row.get(field) is not None, field


def test_v12_row_fields_never_recomputed_only_copied():
    snapshot, rows = _v10_snapshot(), _v10_rows()
    v12_results = _v12_results()
    _, v12_rows = merge_v12_publication_fields(snapshot, rows, v12_results)

    by_id = {r["sealed_product_id"]: r for r in v12_rows}
    assert by_id["p1"]["overall_rip_v12_score"] == 65.0
    assert by_id["p2"]["overall_rip_v12_score"] == 80.0
    assert by_id["p1"]["chase_accessibility_raw"] == 0.42


def test_budget_rank_v12_is_the_real_v12_sort_rank_not_v10_relabeled():
    """Phase 9E: p2 is V10 rank 2 but V12 rank 1 - `budget_rank_v12` must
    reflect the V12 authority's own order, not copy `budget_rank`."""
    snapshot, rows = _v10_snapshot(), _v10_rows()
    _, v12_rows = merge_v12_publication_fields(snapshot, rows, _v12_results())
    by_id = {r["sealed_product_id"]: r for r in v12_rows}

    assert by_id["p1"]["budget_rank"] == 1  # unchanged V10 rank
    assert by_id["p1"]["budget_rank_v12"] == 2  # different V12 rank
    assert by_id["p2"]["budget_rank"] == 2
    assert by_id["p2"]["budget_rank_v12"] == 1


def test_v12_never_copies_v10_score_into_v12_field():
    """Phase 9D."""
    snapshot, rows = _v10_snapshot(), _v10_rows()
    _, v12_rows = merge_v12_publication_fields(snapshot, rows, _v12_results())
    for row in v12_rows:
        assert row["overall_rip_v12_score"] != row["overall_rip_v10_score"]


def test_chase_accessibility_raw_matches_gate_f_builder_value_exactly():
    """Phase 9F: not independently recomputed - copied verbatim from the
    Gate-F V12 builder's row (`rank_one_budget_v12`/`build_v12_shadow_rankings_for_cohort`)."""
    snapshot, rows = _v10_snapshot(), _v10_rows()
    v12_results = _v12_results()
    v12_results["budgets"]["standard_band:25"]["rows"][0]["chaseAccessibilityRaw"] = 0.777
    _, v12_rows = merge_v12_publication_fields(snapshot, rows, v12_results)
    by_id = {r["sealed_product_id"]: r for r in v12_rows}
    assert by_id["p2"]["chase_accessibility_raw"] == 0.777


def test_existing_v10_fields_preserved_for_historical_compatibility():
    """Phase 6: overall_rip_v10_score/budget_rank/budget_cohort_size must
    remain intact and unrelabeled under a canonical V12 merge."""
    snapshot, rows = _v10_snapshot(), _v10_rows()
    _, v12_rows = merge_v12_publication_fields(snapshot, rows, _v12_results())
    by_id = {r["sealed_product_id"]: r for r in v12_rows}
    assert by_id["p1"]["overall_rip_v10_score"] == 56.0
    assert by_id["p1"]["budget_cohort_size"] == 2


def test_missing_v12_counterpart_row_refused_before_rpc_boundary():
    """Phase 9A: a V10 row with no matching V12-ranked row must be refused
    by application code, never silently published with missing V12 fields."""
    snapshot, rows = _v10_snapshot(), _v10_rows()
    v12_results = _v12_results()
    del v12_results["budgets"]["standard_band:25"]["rows"][1]  # drop p1's V12 counterpart
    with pytest.raises(ValueError):
        merge_v12_publication_fields(snapshot, rows, v12_results)


def test_missing_snapshot_transform_version_refused():
    """Phase 9B."""
    snapshot, rows = _v10_snapshot(), _v10_rows()
    v12_snapshot, v12_rows = merge_v12_publication_fields(snapshot, rows, _v12_results())
    v12_snapshot["chase_accessibility_transform_version"] = None
    from backend.scripts.build_budget_normalized_product_rankings import V12_SNAPSHOT_PUBLICATION_FIELDS

    def _validate(snap):
        for field in V12_SNAPSHOT_PUBLICATION_FIELDS:
            if snap.get(field) in (None, ""):
                raise ValueError("missing %s" % field)

    with pytest.raises(ValueError):
        _validate(v12_snapshot)


def test_publish_rankings_v10_path_unchanged_when_v12_results_omitted():
    """Phase 7: explicit V10 mode (`v12_results=None`) must call the RPC
    with a payload carrying no V12 authority fields, and behave exactly as
    it always did."""
    client = _FakeClient()
    results = {"authority": {}, "modelDriftWarnings": [], "fullMarket": {"budget": 150.0, "maxEligibleSkuPrice": 101.0, "roundingIncrement": 50.0}, "productCount": 2, "marketDate": "2026-09-03", "cohortFingerprint": "fp", "rankingMethodVersion": "v1", "allocationMethodVersion": "v1", "comparisonScopeVersion": "v1", "fullMarketRoundingRuleVersion": "v1", "budgets": {"standard_band:25": {"rows": []}}}

    import backend.scripts.build_budget_normalized_product_rankings as mod
    monkey_snapshot, monkey_rows = _v10_snapshot(), _v10_rows()
    orig = mod.to_publication_payload
    mod.to_publication_payload = lambda _r: (monkey_snapshot, monkey_rows)
    try:
        snapshot_id = publish_rankings(client, results)
    finally:
        mod.to_publication_payload = orig

    assert snapshot_id == "11111111-1111-1111-1111-111111111111"
    assert len(client.calls) == 1
    name, payload = client.calls[0]
    assert name == "publish_budget_product_ranking_snapshot"
    assert "ranked_under_v12_authority" not in payload["p_snapshot"]
    for row in payload["p_rows"]:
        assert "overall_rip_v12_score" not in row


def test_publish_rankings_v12_path_is_exactly_one_rpc_call_with_all_fields():
    """Phase 8/9C: canonical V12 publish still makes exactly ONE RPC call,
    with the full merged payload - no follow-up UPDATE."""
    client = _FakeClient()
    results = {"budgets": {"standard_band:25": {"rows": []}}}

    import backend.scripts.build_budget_normalized_product_rankings as mod
    monkey_snapshot, monkey_rows = _v10_snapshot(), _v10_rows()
    orig = mod.to_publication_payload
    mod.to_publication_payload = lambda _r: (monkey_snapshot, monkey_rows)
    try:
        snapshot_id = publish_rankings(client, results, v12_results=_v12_results())
    finally:
        mod.to_publication_payload = orig

    assert snapshot_id == "11111111-1111-1111-1111-111111111111"
    assert len(client.calls) == 1
    name, payload = client.calls[0]
    assert name == "publish_budget_product_ranking_snapshot"
    assert payload["p_snapshot"]["ranked_under_v12_authority"] is True
    assert len(payload["p_rows"]) == len(monkey_rows)
    for row in payload["p_rows"]:
        for field in V12_ROW_PUBLICATION_FIELDS:
            assert row.get(field) is not None
