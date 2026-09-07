from backend.db.services import public_overall_product_rankings_service as service


def test_overall_projection_preserves_loose_pack_artwork_identity(monkeypatch):
    monkeypatch.setattr(service, "load_latest_snapshot", lambda _client: {"full_market_budget": 150.0})
    monkeypatch.setattr(service, "load_full_market_ranking", lambda _client: {
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
    monkeypatch.setattr(service, "load_full_market_ranking", lambda _client: {
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
    monkeypatch.setattr(service, "load_full_market_ranking", lambda _client: {
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
