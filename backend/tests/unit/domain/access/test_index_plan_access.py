"""The server-side half of the Index plan hierarchy.

These exist because the frontend gate is presentation. If this module and
``frontend/lib/access/indexPlanAccess.mjs`` ever disagree, a feature is either
free on the API or unreachable in the UI, and neither failure announces itself.
"""

import pytest

from backend.domain.access.index_plan_access import (
    FEATURE_CARD_CHASE_EFFICIENCY,
    FEATURE_MARKET_EXPLORER_CUSTOM_MARKETS,
    evaluate_market_query_access,
    INDEX_PLAN_PLUS,
    INDEX_PLAN_PREMIUM,
    filter_set_market_signal_access,
    has_index_plus_access,
    has_index_premium_access,
    has_index_feature_access,
    normalize_index_plan,
    project_insights_critical_response,
    project_product_family_rankings_response,
    project_product_rankings_response,
    project_rankings_response,
    project_set_page_response,
    project_set_rip_simulation_evidence_response,
    project_sealed_product_detail_response,
    resolve_market_explorer_plan_access,
    _PLUS_FEATURES,
    _PREMIUM_FEATURES,
)


_SIM_EVIDENCE_SENTINEL = "SENTINEL_PAID_ONLY_VALUE"


def _sim_evidence_fixture():
    return {
        "contractVersion": "pokemon-set-rip-simulation-evidence-v1",
        "setId": "set-1", "calculationRunId": "run-1", "marketDate": "2026-08-30",
        "summary": {
            "simulation_count": 1000000, "pack_cost": 4.99,
            "median_value": 3.5, "mean_value": 5.25,
            "p95_value": _SIM_EVIDENCE_SENTINEL, "max_value": _SIM_EVIDENCE_SENTINEL,
        },
        "distributionBins": [{
            "bin_floor": 0, "bin_ceiling": 5, "occurrence_count": 400000,
            "probability": 0.4, "cumulative_probability": 0.4, "survival_probability": 1.0,
            "unknownBinField": _SIM_EVIDENCE_SENTINEL,
        }],
        "thresholdBins": [{
            "threshold_floor": 0, "threshold_ceiling": 5, "occurrence_count": 400000,
            "probability": 0.4, "cumulative_probability": 0.4, "survival_probability": 1.0,
            "bucket_order": 1, "bucket_label": "$0-$5",
            "unknownThresholdField": _SIM_EVIDENCE_SENTINEL,
        }],
        "meta": {"contractVersion": "pokemon-set-rip-simulation-evidence-v1",
                 "marketDate": "2026-08-30", "calculationRunId": "run-1",
                 "unknownFutureField": _SIM_EVIDENCE_SENTINEL},
        "openingOutcomeProfile": {"secret": _SIM_EVIDENCE_SENTINEL},
        "evRepresentativeness": {"detail": _SIM_EVIDENCE_SENTINEL},
        "advanced": {"anything": _SIM_EVIDENCE_SENTINEL},
        "unknownFutureField": _SIM_EVIDENCE_SENTINEL,
    }


def _assert_no_sentinel(value):
    import json
    assert _SIM_EVIDENCE_SENTINEL not in json.dumps(value)


@pytest.mark.parametrize("plan", [None, "unknown", "base"])
def test_set_rip_simulation_evidence_projector_strips_paid_fields_for_base(plan):
    projected = project_set_rip_simulation_evidence_response(_sim_evidence_fixture(), plan)
    _assert_no_sentinel(projected)
    assert projected["contractVersion"] == "pokemon-set-rip-simulation-evidence-v1"
    assert projected["setId"] == "set-1"
    assert projected["summary"] == {
        "simulation_count": 1000000, "pack_cost": 4.99,
        "median_value": 3.5, "mean_value": 5.25,
    }
    assert projected["distributionBins"] == [{
        "bin_floor": 0, "bin_ceiling": 5, "occurrence_count": 400000,
        "probability": 0.4, "cumulative_probability": 0.4, "survival_probability": 1.0,
    }]
    assert projected["thresholdBins"][0]["bucket_label"] == "$0-$5"
    assert "openingOutcomeProfile" not in projected
    assert "evRepresentativeness" not in projected
    assert "advanced" not in projected
    assert "unknownFutureField" not in projected


@pytest.mark.parametrize("plan", ["plus", "premium"])
def test_set_rip_simulation_evidence_projector_passes_plus_through_unchanged(plan):
    fixture = _sim_evidence_fixture()
    projected = project_set_rip_simulation_evidence_response(fixture, plan)
    assert projected == fixture


@pytest.mark.parametrize("plan", [None, "base", "unknown"])
def test_basic_product_detail_cannot_receive_set_ev_realization_values(plan):
    payload = {
        "set": {"id": "set-1"}, "product": {"id": "product-1"},
        "market": {"currentPrice": 99}, "meta": {},
        "rip": {"setEvRepresentativeness": {"realizationHorizon": {
            "packCount": 420, "targetEvRatio": .8, "openerProbability": .8,
        }}},
    }
    projected = project_sealed_product_detail_response(payload, plan)
    assert "rip" not in projected
    assert "packCount" not in str(projected)
    assert "targetEvRatio" not in str(projected)
    assert "openerProbability" not in str(projected)


@pytest.mark.parametrize("plan", ["plus", "premium"])
def test_paid_product_detail_receives_existing_snapshot_contract(plan):
    payload = {"set": {}, "product": {}, "market": {}, "meta": {}, "rip": {
        "setEvRepresentativeness": {"realizationHorizon": {"packCount": 420}}
    }}
    assert project_sealed_product_detail_response(payload, plan)["rip"] == payload["rip"]


def test_locked_commercial_capability_sets_fail_closed_and_inherit():
    assert len(_PLUS_FEATURES) == 13  # includes server response-boundary aliases
    assert len(_PREMIUM_FEATURES) == 11
    for feature in _PLUS_FEATURES:
        assert not has_index_feature_access(None, feature)
        assert has_index_feature_access("plus", feature)
        assert has_index_feature_access("premium", feature)
    for feature in _PREMIUM_FEATURES:
        assert not has_index_feature_access(None, feature)
        assert not has_index_feature_access("plus", feature)
        assert has_index_feature_access("premium", feature)
    assert not has_index_feature_access("premium", "unknown")


@pytest.mark.parametrize(
    "plan,plus,premium",
    [
        ("premium", True, True),   # Premium inherits Plus.
        ("plus", True, False),
        ("PLUS", True, False),     # normalization is case/space insensitive
        ("  premium  ", True, True),
        (None, False, False),
        ("", False, False),
        ("free", False, False),
        ("pro", False, False),     # an unrecognised tier fails CLOSED
        (7, False, False),
        ({}, False, False),
    ],
)
def test_plan_hierarchy(plan, plus, premium):
    assert has_index_plus_access(plan) is plus
    assert has_index_premium_access(plan) is premium


def test_premium_satisfies_every_plus_check():
    assert has_index_plus_access(INDEX_PLAN_PREMIUM) is True
    assert has_index_premium_access(INDEX_PLAN_PLUS) is False


def test_card_chase_efficiency_maps_only_to_index_premium():
    assert FEATURE_CARD_CHASE_EFFICIENCY == "card_chase_efficiency"
    assert has_index_feature_access(None, FEATURE_CARD_CHASE_EFFICIENCY) is False
    assert has_index_feature_access("plus", FEATURE_CARD_CHASE_EFFICIENCY) is False
    assert has_index_feature_access("premium", FEATURE_CARD_CHASE_EFFICIENCY) is True


def test_unrecognised_plans_normalize_to_none_rather_than_to_a_tier():
    assert normalize_index_plan("enterprise") is None
    assert normalize_index_plan(None) is None


def test_market_explorer_ladder_has_three_levels():
    assert resolve_market_explorer_plan_access(None) == {
        "accessMode": "basic",
        "canBrowsePreparedMarkets": True,
        "canComparePreparedMarkets": False,
        "canUseAnalyticalScreens": False,
        "canUseAdvancedMarketRanking": False,
        "canUsePreparedMarketIntelligence": False,
        "canBuildCustomMarkets": False,
        "canBuildSingleAxisMarket": False,
        "canBuildCompoundMarket": False,
        "canUseCustomRankedComposition": False,
    }
    assert resolve_market_explorer_plan_access({"index_plan": "plus"}) == {
        "accessMode": "plus",
        "canBrowsePreparedMarkets": True,
        "canComparePreparedMarkets": True,
        "canUseAnalyticalScreens": True,
        "canUseAdvancedMarketRanking": True,
        "canUsePreparedMarketIntelligence": True,
        "canBuildCustomMarkets": False,
        "canBuildSingleAxisMarket": False,
        "canBuildCompoundMarket": False,
        "canUseCustomRankedComposition": False,
    }
    assert resolve_market_explorer_plan_access({"index_plan": "premium"}) == {
        "accessMode": "premium",
        "canBrowsePreparedMarkets": True,
        "canComparePreparedMarkets": True,
        "canUseAnalyticalScreens": True,
        "canUseAdvancedMarketRanking": True,
        "canUsePreparedMarketIntelligence": True,
        "canBuildCustomMarkets": True,
        "canBuildSingleAxisMarket": True,
        "canBuildCompoundMarket": True,
        "canUseCustomRankedComposition": True,
    }


@pytest.mark.parametrize("asset", ["cards", "sealed"])
def test_only_premium_can_build_one_axis_all_constituent_markets(asset):
    scope = {"asset": asset, "eraIds": ("sv",), "setIds": (), "segmentIds": (), "mode": "all"}
    segment = {"asset": asset, "eraIds": (), "setIds": (), "segmentIds": ("segment",), "mode": "all"}
    assert evaluate_market_query_access("plus", scope)["allowed"] is False
    assert evaluate_market_query_access("plus", segment)["allowed"] is False
    assert evaluate_market_query_access("premium", scope)["allowed"] is True


def test_plus_cannot_build_compound_or_ranked_markets_but_premium_can():
    compound = {"eraIds": ("sv",), "setIds": (), "segmentIds": ("sir",), "mode": "all"}
    ranked = {"eraIds": (), "setIds": (), "segmentIds": ("sir",), "mode": "chase"}
    assert evaluate_market_query_access("plus", compound)["capability"] == "market_explorer_compound"
    assert evaluate_market_query_access("plus", compound)["allowed"] is False
    assert evaluate_market_query_access("plus", ranked)["capability"] == "market_explorer_custom_ranked"
    assert evaluate_market_query_access("plus", ranked)["allowed"] is False
    assert evaluate_market_query_access("premium", compound)["allowed"] is True
    assert evaluate_market_query_access("premium", ranked)["allowed"] is True


def test_pass3_axis_packaging_is_centralized_and_fail_closed():
    price = {"priceSegmentIds": ("premium",), "mode": "all"}
    release = {"releaseAgeCohortIds": ("new",), "mode": "all"}
    pokemon = {"pokemonIds": ("149",), "mode": "all"}
    scope_price = {"setIds": ("sv8",), "priceSegmentIds": ("premium",), "mode": "all"}
    segment_pokemon = {"segmentIds": ("sir",), "pokemonIds": ("149",), "mode": "all"}

    assert evaluate_market_query_access("plus", price)["allowed"] is False
    assert evaluate_market_query_access("plus", release)["allowed"] is False
    pokemon_access = evaluate_market_query_access("plus", pokemon)
    assert pokemon_access["allowed"] is False
    assert pokemon_access["requiredPlan"] == "premium"
    assert pokemon_access["capability"] == "market_explorer_pokemon"
    assert pokemon_access["activeFilterAxes"] == ["pokemon"]
    assert evaluate_market_query_access("plus", scope_price)["allowed"] is False
    assert evaluate_market_query_access("plus", segment_pokemon)["allowed"] is False
    assert evaluate_market_query_access("premium", segment_pokemon)["allowed"] is True


def test_basic_cannot_obtain_query_results():
    broad = {"eraIds": (), "setIds": (), "segmentIds": (), "mode": "all"}
    assert evaluate_market_query_access(None, broad)["allowed"] is False


def test_authentication_alone_grants_nothing():
    # The correction this encodes: PLAN entitlement decides access, not login.
    anonymous = resolve_market_explorer_plan_access(None)
    authenticated_basic = resolve_market_explorer_plan_access(
        {"id": "user-1", "email": "a@b.c", "index_plan": None}
    )
    assert authenticated_basic == anonymous


def test_basic_set_market_response_redacts_breadth_but_keeps_market_index():
    source = {
        "cardsMarket": {
            "marketIndex": {"currentValue": 112.4},
            "marketBreadth": {"7D": {"advancingCount": 138, "advancingPercent": 46.8}},
        },
        "setValueHistoriesByScope": {"standard": [{"setValue": 5874}]},
    }
    filtered = filter_set_market_signal_access(source, None)
    assert filtered["cardsMarket"]["marketIndex"] == {"currentValue": 112.4}
    assert "marketBreadth" not in filtered["cardsMarket"]
    assert filtered["setValueHistoriesByScope"] == source["setValueHistoriesByScope"]
    assert source["cardsMarket"]["marketBreadth"]  # no mutation of the snapshot


@pytest.mark.parametrize("plan", ["plus", "premium"])
def test_plus_and_premium_set_market_response_keep_breadth(plan):
    source = {"cardsMarket": {"marketBreadth": {"7D": {"advancingCount": 138}}}}
    assert filter_set_market_signal_access(source, plan) == source


def _collector_payload():
    return {"publicRipContractV10": {"collectorAppeal": {"topSubjects": [{
        "subjectName": "Charizard",
        "elitePath": {"canonicalCardId": "charizard-elite", "modeledProbability": 0.001, "impliedOdds": 1000, "packsFor50PercentChance": 693, "packsFor90PercentChance": 2302},
        "accessiblePath": {"canonicalCardId": "charizard-accessible", "modeledProbability": 0.01, "impliedOdds": 100, "packsFor50PercentChance": 69, "packsFor90PercentChance": 230},
    }]}}}


def test_basic_payload_keeps_collector_identity_and_raw_odds_but_redacts_milestones():
    filtered = filter_set_market_signal_access(_collector_payload(), None)
    subject = filtered["publicRipContractV10"]["collectorAppeal"]["topSubjects"][0]
    for path in (subject["elitePath"], subject["accessiblePath"]):
        assert path["canonicalCardId"]
        assert path["modeledProbability"]
        assert path["impliedOdds"]
        assert "packsFor50PercentChance" not in path
        assert "packsFor90PercentChance" not in path


@pytest.mark.parametrize("plan", ["plus", "premium"])
def test_plus_and_premium_payloads_keep_collector_milestones(plan):
    filtered = filter_set_market_signal_access(_collector_payload(), plan)
    subject = filtered["publicRipContractV10"]["collectorAppeal"]["topSubjects"][0]
    assert subject["elitePath"]["packsFor50PercentChance"] == 693
    assert subject["accessiblePath"]["packsFor90PercentChance"] == 230


def test_the_gated_capability_is_named_as_a_feature_not_a_plan():
    # Commercial packaging is not final, so the API refuses by CAPABILITY.
    assert FEATURE_MARKET_EXPLORER_CUSTOM_MARKETS == "market_explorer_custom_markets"


def test_the_two_runtimes_agree_on_the_plan_strings():
    # A drift here is silent and expensive, so it is asserted rather than
    # trusted to review. Read as text: importing the ESM module is not
    # available to pytest.
    from pathlib import Path

    source = Path(__file__).resolve().parents[5] / "frontend" / "lib" / "access" / "indexPlanAccess.mjs"
    text = source.read_text(encoding="utf-8")
    assert f'INDEX_PLAN_PLUS = "{INDEX_PLAN_PLUS}"' in text
    assert f'INDEX_PLAN_PREMIUM = "{INDEX_PLAN_PREMIUM}"' in text
    assert FEATURE_MARKET_EXPLORER_CUSTOM_MARKETS in text
    # And on the rule that Premium satisfies Plus.
    assert "normalized === INDEX_PLAN_PLUS || normalized === INDEX_PLAN_PREMIUM" in text


def _rankings_target():
    return {
        "set_id": "set-1", "name": "Test Set",
        "overallRipV10": {"rank": 3, "relativeScore": 60.0},
        "publicRipContractV10": {"overallRip": {"rank": 3}},
        "overallRipV12": {"rank": 2, "relativeScore": 70.0},
        "publicRipContractV11": {"overallRip": {"rank": 2}},
        "chaseAccessibility": {"chaseAccessibility": 0.01},
    }


def test_base_rankings_projection_cannot_see_v12_or_v10_intelligence():
    result = project_rankings_response({"targets": [_rankings_target()]}, plan=None)
    target = result["targets"][0]
    assert "overallRipV12" not in target
    assert "publicRipContractV11" not in target
    assert "overallRipV10" not in target
    assert "publicRipContractV10" not in target
    assert "chaseAccessibility" not in target
    assert result["access"]["rankingsIntelligence"] is False


def test_plus_rankings_projection_receives_v12_and_v11():
    result = project_rankings_response({"targets": [_rankings_target()]}, plan=INDEX_PLAN_PLUS)
    target = result["targets"][0]
    assert target["overallRipV12"]["rank"] == 2
    assert target["publicRipContractV11"]["overallRip"]["rank"] == 2
    assert target["chaseAccessibility"]["chaseAccessibility"] == 0.01
    # Historical V10 data is preserved for existing Plus consumers.
    assert target["overallRipV10"]["rank"] == 3
    assert target["publicRipContractV10"]["overallRip"]["rank"] == 3


def _product_family_ranking_row():
    return {
        "sealedProductId": "prod-1", "setId": "set-1", "productName": "Test Booster Box",
        "setName": "Test Set", "productFamily": "booster_box", "productFamilyLabel": "Booster Box",
        "marketPrice": 100.0, "financialRipLeaderScore": 80.0, "collectorAppealScore": 60.0,
        "chaseAccessibility": {
            "value": 0.002, "percent": 0.2, "status": "ready",
            "version": "chase_accessibility_v1_hc_value_squared_modeled_probability",
            "chaseDepth": 3.1, "mappedHcMass": 1.0, "setRank": 1, "setCohortSize": 22,
        },
    }


def test_product_family_rankings_projection_carries_chase_accessibility_at_plus_and_strips_it_at_base():
    # UI-5 Phase 14 regression: `chaseAccessibility` was added to the raw
    # product-family-rankings builder by UI-4/UI-4B but was never added to
    # this response's tier allowlist, so it was silently stripped from the
    # LIVE `/explore/rankings/lens?lens=products` response
    # (RankingsProductLensClient.jsx) despite existing frontend/backend tests
    # for the raw builder and the component both passing.
    payload = {"families": {"booster_box": {"label": "Booster Box", "count": 1, "products": [_product_family_ranking_row()]}}}

    base = project_product_family_rankings_response(payload, plan=None)
    base_product = base["families"]["booster_box"]["products"][0]
    assert "chaseAccessibility" not in base_product

    plus = project_product_family_rankings_response(payload, plan=INDEX_PLAN_PLUS)
    plus_product = plus["families"]["booster_box"]["products"][0]
    assert plus_product["chaseAccessibility"]["value"] == 0.002
    assert plus_product["chaseAccessibility"]["setRank"] == 1
    assert plus_product["chaseAccessibility"]["setCohortSize"] == 22
    # No Premium Product Chase field ever rides along with it.
    for leaked in ("oBudget", "ece", "effectivePacks", "quantity"):
        assert leaked not in plus_product


def test_overall_product_rankings_projection_carries_chase_accessibility_at_plus():
    payload = {
        "available": True, "reason": None, "selectedBudget": None, "availableBudgets": [],
        "cohortSize": 1, "rows": [_product_family_ranking_row()],
    }
    base = project_product_rankings_response(payload, plan=None)
    assert "chaseAccessibility" not in base["rows"][0]

    plus = project_product_rankings_response(payload, plan=INDEX_PLAN_PLUS)
    assert plus["rows"][0]["chaseAccessibility"]["value"] == 0.002


def test_base_set_page_projection_cannot_see_v12_or_v10_intelligence():
    payload = {"target": {}, "set": {}, "meta": {}, **_rankings_target()}
    result = project_set_page_response(payload, plan=None)
    assert "overallRipV12" not in result
    assert "publicRipContractV11" not in result
    assert "overallRipV10" not in result


def test_plus_set_page_projection_receives_v12_and_v11():
    payload = {"target": {}, "set": {}, "meta": {}, **_rankings_target()}
    result = project_set_page_response(payload, plan=INDEX_PLAN_PLUS)
    assert result["overallRipV12"]["rank"] == 2
    assert result["publicRipContractV11"]["overallRip"]["rank"] == 2
    assert result["overallRipV10"]["rank"] == 3


def test_base_insights_critical_projection_cannot_see_v12_or_v10_intelligence():
    payload = {"set": {}, "meta": {}, **_rankings_target()}
    result = project_insights_critical_response(payload, plan=None)
    assert "overallRipV12" not in result
    assert "publicRipContractV11" not in result
    assert "overallRipV10" not in result


def test_plus_insights_critical_projection_receives_v12_and_v11():
    payload = {"set": {}, "meta": {}, **_rankings_target()}
    result = project_insights_critical_response(payload, plan=INDEX_PLAN_PLUS)
    assert result["overallRipV12"]["rank"] == 2
    assert result["publicRipContractV11"]["overallRip"]["rank"] == 2
    assert result["overallRipV10"]["rank"] == 3
