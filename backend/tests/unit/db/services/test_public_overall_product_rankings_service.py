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
    monkeypatch.setattr(service, "public_budget_cohort_presentation", lambda _rows: {"pack-1": {
        "publicTier": "S", "overallRipLeaderScore": 100, "financialRipLeaderScore": 100,
    }})
    family_payload = {"families": {"loose_booster_pack": {"products": [{
        "sealedProductId": "pack-1", "productName": "Alpha Booster Pack", "setName": "Alpha",
        "productFamilyLabel": "Loose Booster Pack", "productImageUrl": None,
        "setCanonicalKey": "alphaSet", "familyRank": 1, "familySize": 1,
    }]}}}

    result = service.read_public_overall_product_rankings(
        product_family_rankings=family_payload, client=object()
    )

    assert result["available"] is True
    assert result["rows"][0]["setCanonicalKey"] == "alphaSet"
    assert result["rows"][0]["productFamily"] == "loose_booster_pack"
