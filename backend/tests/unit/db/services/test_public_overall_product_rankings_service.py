from backend.db.services import public_overall_product_rankings_service as service
from backend.calculations.evr import budget_normalized_product_ranking as bnpr


def test_overall_projection_preserves_loose_pack_artwork_identity(monkeypatch):
    monkeypatch.setattr(service, "load_latest_snapshot", lambda _client: {"full_market_budget": 150.0})
    monkeypatch.setattr(service, "load_full_market_ranking", lambda _client, **_kwargs: {
        "rows": [{
            "sealed_product_id": "pack-1", "set_id": "set-1", "product_family": "loose_booster_pack",
            "budget_rank": 1, "budget_cohort_size": 1, "quantity": 1,
            "actual_committed_capital": 10, "unused_capital": 140,
            "overall_rip_v10_score": 50, "financial_rip_v4_score": 40,
            "collector_appeal_score": 30, "product_market_price": 10,
            "expected_value": 8, "chance_to_recover_capital": .25,
        }],
        "authority": {},
    })
    monkeypatch.setattr(service, "public_budget_cohort_presentation", lambda _rows, _snapshot: {"pack-1": {
        "publicTier": "S", "overallRipLeaderScore": 100, "financialRipLeaderScore": 100,
        "overallRipScore": 50, "budgetRank": 1, "budgetCohortSize": 1,
    }})
    family_payload = {"families": {"loose_booster_pack": {"products": [{
        "sealedProductId": "pack-1", "productName": "Alpha Booster Pack", "setName": "Alpha",
        "productFamilyLabel": "Loose Booster Pack", "productImageUrl": None,
        "setCanonicalKey": "alphaSet", "familyRank": 1, "familySize": 1,
        "chaseAccessibility": {"value": 0.02, "percent": 2.0, "setRank": 3, "setCohortSize": 10},
    }]}}}

    result = service.read_public_overall_product_rankings(
        product_family_rankings=family_payload, client=object()
    )

    assert result["available"] is True
    assert result["rows"][0]["setCanonicalKey"] == "alphaSet"
    assert result["rows"][0]["productFamily"] == "loose_booster_pack"


# The budget/"All Products" overall projection must carry the SAME set-level
# Chase Accessibility authority block as the per-family projection
# (product_family_rankings_service.py), lifted verbatim off the identity index
# this function already builds from `product_family_rankings` — no new query.
def test_overall_projection_carries_chase_accessibility_authority_block(monkeypatch):
    monkeypatch.setattr(service, "load_latest_snapshot", lambda _client: {"full_market_budget": 150.0})
    monkeypatch.setattr(service, "load_full_market_ranking", lambda _client, **_kwargs: {
        "rows": [{
            "sealed_product_id": "pack-1", "set_id": "set-1", "product_family": "loose_booster_pack",
            "budget_rank": 1, "budget_cohort_size": 1, "quantity": 1,
            "actual_committed_capital": 10, "unused_capital": 140,
            "overall_rip_v10_score": 50, "financial_rip_v4_score": 40,
            "collector_appeal_score": 30, "product_market_price": 10,
            "expected_value": 8, "chance_to_recover_capital": .25,
        }],
        "authority": {},
    })
    monkeypatch.setattr(service, "public_budget_cohort_presentation", lambda _rows, _snapshot: {"pack-1": {
        "publicTier": "S", "overallRipLeaderScore": 100, "financialRipLeaderScore": 100,
        "overallRipScore": 50, "budgetRank": 1, "budgetCohortSize": 1,
    }})
    chase_block = {"value": 0.02, "percent": 2.0, "setRank": 3, "setCohortSize": 10}
    family_payload = {"families": {"loose_booster_pack": {"products": [{
        "sealedProductId": "pack-1", "productName": "Alpha Booster Pack", "setName": "Alpha",
        "productFamilyLabel": "Loose Booster Pack", "productImageUrl": None,
        "setCanonicalKey": "alphaSet", "familyRank": 1, "familySize": 1,
        "chaseAccessibility": chase_block,
    }]}}}

    result = service.read_public_overall_product_rankings(
        product_family_rankings=family_payload, client=object()
    )

    assert result["rows"][0]["chaseAccessibility"] == chase_block


def _authority_case(monkeypatch, *, v12_authority, v12_score, v12_rank, v12_size):
    snapshot = {
        "full_market_budget": 150.0,
        "ranked_under_v12_authority": v12_authority,
    }
    row = {
        "sealed_product_id": "pack-1", "set_id": "set-1",
        "product_family": "loose_booster_pack", "quantity": 1,
        "actual_committed_capital": 10, "unused_capital": 140,
        "overall_rip_v10_score": 10, "budget_rank": 9, "budget_cohort_size": 10,
        "overall_rip_v12_score": v12_score, "budget_rank_v12": v12_rank,
        "budget_cohort_size_v12": v12_size, "financial_rip_v4_score": 40,
        "collector_appeal_score": 30, "product_market_price": 10,
        "expected_value": 8, "chance_to_recover_capital": .25,
    }
    monkeypatch.setattr(service, "load_latest_snapshot", lambda _client: snapshot)
    monkeypatch.setattr(service, "load_full_market_ranking", lambda _client, **_kwargs: {
        "rows": [row], "authority": {"rankedUnderV12Authority": v12_authority},
    })
    return service.read_public_overall_product_rankings(
        product_family_rankings={"families": {"loose_booster_pack": {"products": [{
            "sealedProductId": "pack-1", "productName": "Alpha Booster Pack",
            "setName": "Alpha", "productFamilyLabel": "Loose Booster Pack",
        }]}}},
        client=object(),
    )


def test_live_v12_budget_read_uses_v12_generic_score_rank_and_cohort(monkeypatch):
    result = _authority_case(
        monkeypatch, v12_authority=True, v12_score=90, v12_rank=1, v12_size=7,
    )
    assert result["available"] is True
    assert result["rows"][0]["overallRipScore"] == 90
    assert result["rows"][0]["overallRipAbsoluteScore"] == 90
    assert result["rows"][0]["budgetRank"] == 1
    assert result["rows"][0]["budgetCohortSize"] == 7
    assert "O_budget" not in result["rows"][0]
    assert "ECE" not in result["rows"][0]


def test_live_historical_v10_budget_read_remains_readable(monkeypatch):
    result = _authority_case(
        monkeypatch, v12_authority=False, v12_score=90, v12_rank=1, v12_size=7,
    )
    assert result["available"] is True
    assert result["rows"][0]["overallRipScore"] == 10
    assert result["rows"][0]["budgetRank"] == 9
    assert result["rows"][0]["budgetCohortSize"] == 10


def test_live_malformed_v12_budget_read_fails_closed_without_mixing_authority(monkeypatch):
    result = _authority_case(
        monkeypatch, v12_authority=True, v12_score=90, v12_rank=None, v12_size=7,
    )
    assert result == {"available": False, "reason": "public_projection_incomplete", "rows": []}


def test_live_v12_budget_read_missing_score_fails_closed(monkeypatch):
    result = _authority_case(
        monkeypatch, v12_authority=True, v12_score=None, v12_rank=1, v12_size=7,
    )
    assert result == {"available": False, "reason": "public_projection_incomplete", "rows": []}


# --- Prepared Budget Product Rankings DB contract: median_value /
# top1_outcome_value_share / averageReturn (source-side bridge) ----------


def _prepared_row(**overrides):
    row = {
        "sealed_product_id": "pack-1", "set_id": "set-1", "product_family": "loose_booster_pack",
        "budget_rank": 1, "budget_cohort_size": 1, "quantity": 1,
        "actual_committed_capital": 20.0, "unused_capital": 5.0,
        "overall_rip_v10_score": 50, "financial_rip_v4_score": 40,
        "collector_appeal_score": 30, "product_market_price": 10,
        "expected_value": 30.0, "chance_to_recover_capital": .25,
        "median_value": 28.0, "top1_outcome_value_share": 0.12,
    }
    row.update(overrides)
    return row


def _prepared_read(monkeypatch, row):
    monkeypatch.setattr(service, "load_latest_snapshot", lambda _client: {"full_market_budget": 150.0})
    monkeypatch.setattr(service, "load_full_market_ranking", lambda _client, **_kwargs: {
        "rows": [row], "authority": {},
    })
    monkeypatch.setattr(service, "public_budget_cohort_presentation", lambda _rows, _snapshot: {"pack-1": {
        "publicTier": "S", "overallRipLeaderScore": 100, "financialRipLeaderScore": 100,
        "overallRipScore": 50, "budgetRank": 1, "budgetCohortSize": 1,
    }})
    family_payload = {"families": {"loose_booster_pack": {"products": [{
        "sealedProductId": "pack-1", "productName": "Alpha Booster Pack", "setName": "Alpha",
        "productFamilyLabel": "Loose Booster Pack", "productImageUrl": None,
        "setCanonicalKey": "alphaSet", "familyRank": 1, "familySize": 1,
    }]}}}
    return service.read_public_overall_product_rankings(product_family_rankings=family_payload, client=object())


def test_prepared_read_exposes_persisted_median_and_top1_outcome_value_share_round_trip(monkeypatch):
    """Requirement 4: the reader exposes exactly the persisted values, not a
    recomputation — round-trip proof."""
    row = _prepared_row(median_value=27.5, top1_outcome_value_share=0.137)
    result = _prepared_read(monkeypatch, row)
    assert result["rows"][0]["medianValue"] == 27.5
    assert result["rows"][0]["topOneOutcomeValueShare"] == 0.137


def test_prepared_read_average_return_denominator_is_actual_committed_capital(monkeypatch):
    """Requirement 3: Average Return = expected_value / actual_committed_capital,
    never the target budget band or a one-unit price."""
    row = _prepared_row(expected_value=30.0, actual_committed_capital=20.0, product_market_price=10.0)
    result = _prepared_read(monkeypatch, row)
    assert result["rows"][0]["averageReturn"] == 30.0 / 20.0
    assert result["rows"][0]["averageReturn"] != 30.0 / 10.0  # not one-unit price
    assert result["rows"][0]["averageReturn"] != 30.0 / 25.0  # not a target-budget band


def test_prepared_read_never_calls_score_budget_strategy(monkeypatch):
    """Requirement 6: no request-time strategy scoring on the read path."""
    def _forbidden(*_args, **_kwargs):
        raise AssertionError("score_budget_strategy must never be called from the read path")

    monkeypatch.setattr(bnpr, "score_budget_strategy", _forbidden)
    row = _prepared_row()
    result = _prepared_read(monkeypatch, row)
    assert result["available"] is True
    assert result["rows"][0]["medianValue"] == row["median_value"]


def test_prepared_read_legacy_row_missing_new_fields_degrades_soft(monkeypatch):
    """Requirement 7: a legacy/latest snapshot row published before this
    contract (median_value/top1_outcome_value_share/actual_committed_capital
    NULL/missing) must NOT crash and must NOT drop the row from the table —
    only these three fields degrade to unavailable/null."""
    row = _prepared_row(median_value=None, top1_outcome_value_share=None)
    del row["median_value"]
    del row["top1_outcome_value_share"]
    result = _prepared_read(monkeypatch, row)

    assert result["available"] is True
    assert len(result["rows"]) == 1
    assert result["rows"][0]["medianValue"] is None
    assert result["rows"][0]["topOneOutcomeValueShare"] is None
    # Every other pre-existing field on the row keeps working.
    assert result["rows"][0]["expectedValue"] == 30.0
    assert result["rows"][0]["overallRipScore"] == 50


def test_prepared_read_legacy_row_missing_committed_capital_makes_average_return_unavailable(monkeypatch):
    """Transitional safety: a legacy row missing actual_committed_capital must
    not throw and must not silently report a computed-looking zero — Average
    Return degrades to unavailable (None), the rest of the row still works."""
    row = _prepared_row()
    del row["actual_committed_capital"]
    result = _prepared_read(monkeypatch, row)

    assert result["available"] is True
    assert result["rows"][0]["averageReturn"] is None
    assert result["rows"][0]["medianValue"] == row["median_value"]
