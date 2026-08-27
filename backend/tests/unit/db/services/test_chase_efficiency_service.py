from backend.db.services.chase_efficiency_service import build_snapshot_from_inputs, validate_candidate


def test_candidate_keeps_exclusions_and_passes_audit():
    product = {"sealed_product_id":"p", "product_name":"Box", "product_family":"booster_box", "product_price":100,
               "random_pack_count":36, "composition_verified":True, "price_source":"x", "price_as_of":"2026-08-27"}
    base = {"set_id":"s", "source_calculation_run_id":"r", "effective_pull_rate":100, "canonical_card_id":"c",
            "era_id":"e", "canonical_rarity":"Illustration Rare", "card_name":"A", "current_market_price":50,
            "price_is_fresh":True, "card_price_as_of":"2026-08-27"}
    candidate = build_snapshot_from_inputs(
        market_date="2026-08-27", cards=[dict(base, card_variant_id="v1"), dict(base, card_variant_id="v2", price_is_fresh=False)],
        products_by_set={"s":[product]}, authoritative_run_ids={"s":"r"}, supported_set_count=1,
    )
    assert candidate["snapshot"]["eligible_cohort_count"] == 1
    assert candidate["snapshot"]["excluded_cohort_count"] == 1
    assert candidate["excluded"][0]["reason"] == "stale_near_mint_price"
    assert validate_candidate(candidate) == []
