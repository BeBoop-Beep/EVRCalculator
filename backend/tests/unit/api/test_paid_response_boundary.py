"""Direct HTTP tests for the backend entitlement/serialization boundary."""

from fastapi.testclient import TestClient

from backend.api import main


PLUS_VALUE = 987654.321
BREADTH_VALUE = 73.456
MILESTONE_VALUE = 98761
PREMIUM_VALUE = 555555.125


def _install_auth(monkeypatch):
    plans = {"base-token": None, "plus-token": "plus", "premium-token": "premium"}

    def decode(token):
        if token not in plans:
            return None, ({"message": "Not authenticated"}, 401)
        return {"id": f"user-{token}"}, None

    def me(token):
        if token not in plans:
            return {"message": "Not authenticated"}, 401
        return {"user": {"id": f"user-{token}", "index_plan": plans[token]}}, 200

    monkeypatch.setattr(main, "decode_token", decode)
    monkeypatch.setattr(main, "get_me", me)


def _headers(token=None, **spoofed):
    headers = {key: value for key, value in spoofed.items()}
    if token:
        headers["authorization"] = f"Bearer {token}"
    return headers


def _rankings_fixture():
    return {
        "targets": [{
            "id": "set-1", "name": "Safe Set", "canonical_key": "safe-set",
            "setRipV1": {"score": 73.1, "rank": 4, "tier": "B", "cohortSize": 22,
                         "rankable": True, "methodologyVersion": "set-rip-v1",
                         "participatingFamilyCount": 1,
                         "displayFamilyScores": [{"family": "booster_box", "score": 81,
                                                   "rank": 3, "tier": "A"}],
                         "privateRawInputs": PREMIUM_VALUE},
            "checklistSetValue": 123.45, "financialRipV4": {"score": PLUS_VALUE},
            "unknownFutureAnalyticalField": PLUS_VALUE,
        }],
        "default_target": {"id": "set-1", "financialRipV4": {"score": PLUS_VALUE}},
        "productFamilyRankings": {"families": {"booster_box": {"secret": PLUS_VALUE}}},
        "meta": {"updatedAt": "now", "unknownSecret": PLUS_VALUE},
        "unknownTopLevel": PLUS_VALUE,
    }


def test_rip_statistics_http_matrix_cache_isolation_and_spoof_resistance(monkeypatch):
    _install_auth(monkeypatch)
    monkeypatch.setattr(main, "get_pokemon_explore_rankings_snapshot_payload", lambda limit=None: _rankings_fixture())
    client = TestClient(main.app)

    premium = client.get("/explore/rip-statistics/targets", headers=_headers("premium-token"))
    anonymous = client.get(
        "/explore/rip-statistics/targets?plan=premium&index_plan=premium",
        headers=_headers(**{"x-plan": "premium", "x-index-plan": "premium"}),
    )
    base = client.get("/explore/rip-statistics/targets", headers=_headers("base-token", **{"x-plan": "premium"}))
    plus = client.get("/explore/rip-statistics/targets", headers=_headers("plus-token"))
    premium_after_base = client.get("/explore/rip-statistics/targets", headers=_headers("premium-token"))

    assert all(response.status_code == 200 for response in (premium, anonymous, base, plus))
    assert str(PLUS_VALUE) in premium.text and str(PLUS_VALUE) in plus.text
    assert str(PLUS_VALUE) not in anonymous.text and str(PLUS_VALUE) not in base.text
    assert "unknownFutureAnalyticalField" not in premium.text
    assert "unknownTopLevel" not in premium.text
    assert str(PLUS_VALUE) in premium_after_base.text
    assert premium.headers["cache-control"] == "no-store"
    assert "Authorization" in premium.headers["vary"]


def test_product_rankings_http_projection_plus_then_base(monkeypatch):
    _install_auth(monkeypatch)
    monkeypatch.setattr(main, "get_pokemon_explore_rankings_snapshot_payload", lambda limit=200: {"productFamilyRankings": {}})
    monkeypatch.setattr(main, "read_public_overall_product_rankings", lambda *args, **kwargs: {
        "available": True, "reason": None, "cohortSize": 1,
        "selectedBudget": {"value": 100}, "availableBudgets": [],
        "authority": {"snapshotId": "paid-authority"},
        "rows": [{
            "sealedProductId": "product-1", "productName": "Safe Product", "unitPrice": 99,
            "overallRipScore": PLUS_VALUE, "expectedValue": PLUS_VALUE,
            "unknownPremiumField": PREMIUM_VALUE,
        }],
    })
    client = TestClient(main.app)
    plus = client.get("/explore/product-rankings/overall", headers=_headers("plus-token"))
    base = client.get("/explore/product-rankings/overall?plan=premium", headers=_headers("base-token"))

    assert str(PLUS_VALUE) in plus.text
    assert str(PLUS_VALUE) not in base.text
    assert "unknownPremiumField" not in plus.text
    assert base.json()["rows"] == [{
        "sealedProductId": "product-1", "productName": "Safe Product", "unitPrice": 99
    }]


def test_rankings_lenses_are_projected_and_never_cross_tier_cache(monkeypatch):
    _install_auth(monkeypatch)
    family = {"label": "Booster Box", "count": 1, "products": [{
        "sealedProductId": "product-1", "productName": "Safe Product", "marketPrice": 99,
        "financialRipLeaderScore": PLUS_VALUE, "unknownFutureField": PREMIUM_VALUE,
    }]}
    monkeypatch.setattr(main, "get_pokemon_explore_rankings_lens_payload", lambda lens, limit=None: {
        "targets": _rankings_fixture()["targets"],
        "productFamilyRankings": {"families": {"booster_box": family}},
        "eraSetStrengthV1": {"cohortSize": 1, "secret": PLUS_VALUE, "eras": [{
            "eraId": "safe-era", "eraName": "Safe Era", "rank": 1, "score": 73.1,
            "tier": "B", "cohortSize": 1, "modeledSetCount": 3,
            "strongestSet": {"setId": "set-1", "setName": "Safe Set", "score": 80,
                              "privateDetail": PREMIUM_VALUE},
            "constituentSets": [{"setId": "set-1", "setName": "Safe Set", "score": 80,
                                  "tier": "A", "privateDetail": PREMIUM_VALUE}],
            "privateEraDetail": PREMIUM_VALUE,
        }]}, "meta": {"updatedAt": "now"},
    })
    monkeypatch.setattr(main, "read_public_overall_product_rankings", lambda *args, **kwargs: {
        "available": True, "rows": [{"sealedProductId": "product-1", "productName": "Safe Product",
                                      "unitPrice": 99, "financialRipLeaderScore": PLUS_VALUE}],
    })
    client = TestClient(main.app)

    plus_products = client.get("/explore/rankings/lens/products", headers=_headers("plus-token"))
    base_products = client.get("/explore/rankings/lens/products", headers=_headers("base-token"))
    base_sets = client.get("/explore/rankings/lens/sets", headers=_headers("base-token"))
    plus_sets = client.get("/explore/rankings/lens/sets", headers=_headers("plus-token"))
    base_eras = client.get("/explore/rankings/lens/eras", headers=_headers("base-token"))

    assert str(PLUS_VALUE) in plus_products.text and str(PLUS_VALUE) in plus_sets.text
    assert str(PLUS_VALUE) not in base_products.text and str(PLUS_VALUE) not in base_sets.text
    assert base_sets.json()["targets"][0]["setRipV1"]["score"] == 73.1
    assert base_sets.json()["targets"][0]["setRipV1"]["rank"] == 4
    assert base_sets.json()["targets"][0]["setRipV1"]["tier"] == "B"
    assert base_sets.json()["targets"][0]["setRipV1"]["participatingFamilyCount"] == 1
    assert base_sets.json()["targets"][0]["setRipV1"]["displayFamilyScores"][0]["family"] == "booster_box"
    assert "privateRawInputs" not in base_sets.text
    assert base_eras.json()["eraSetStrengthV1"]["eras"][0]["rank"] == 1
    assert base_eras.json()["eraSetStrengthV1"]["eras"][0]["score"] == 73.1
    assert base_eras.json()["eraSetStrengthV1"]["eras"][0]["tier"] == "B"
    assert base_eras.json()["eraSetStrengthV1"]["eras"][0]["modeledSetCount"] == 3
    assert base_eras.json()["eraSetStrengthV1"]["eras"][0]["strongestSet"]["setName"] == "Safe Set"
    assert "privateEraDetail" not in base_eras.text and "privateDetail" not in base_eras.text
    assert base_eras.json()["access"] == {"rankingsIntelligence": False, "requiredPlan": "plus"}
    assert "unknownFutureField" not in plus_products.text
    assert all(response.headers["cache-control"] == "no-store" for response in (
        plus_products, base_products, base_sets, plus_sets, base_eras,
    ))


def test_rankings_lens_resolves_canonical_profile_once(monkeypatch):
    calls = 0

    def me(_token):
        nonlocal calls
        calls += 1
        return {"user": {"id": "user-plus", "index_plan": "plus"}}, 200

    monkeypatch.setattr(main, "get_me", me)
    monkeypatch.setattr(main, "decode_token", lambda _token: ({"id": "user-plus"}, None))
    monkeypatch.setattr(main, "get_pokemon_explore_rankings_lens_payload", lambda lens, limit=None: {
        "eraSetStrengthV1": {"methodologyVersion": "era-v1", "eras": []}, "meta": {}
    })
    response = TestClient(main.app).get(
        "/explore/rankings/lens/eras", headers=_headers("plus-token")
    )
    assert response.status_code == 200
    assert calls == 1


def test_public_opening_economics_stays_public_but_detailed_pack_values_are_plus(monkeypatch):
    _install_auth(monkeypatch)
    fixture = {
        "status": "available", "contractVersion": "pokemon-rip-stats-v3",
        "basis": "all_modeled_products_per_pack_equivalent", "methodology": {},
        "global": {"typicalOpeningPerPack": 3.25, "modeledReturnOnSpend": 0.71},
        "eras": [{"eraName": "Safe Era", "setCount": 2, "averageCostPerPack": 5,
                  "modeledReturnOnSpend": PLUS_VALUE}],
        "sets": [{"setId": "set-1", "setName": "Safe Set", "averageCostPerPack": 5,
                  "chanceToRecoverCost": PLUS_VALUE,
                  "familyEconomics": [{"secret": PLUS_VALUE}]}],
        "familyBenchmarks": [{"secret": PLUS_VALUE}],
    }
    monkeypatch.setattr(main, "read_public_opening_economics", lambda _client: fixture)
    client = TestClient(main.app)
    base = client.get("/explore/opening-economics", headers=_headers("base-token"))
    plus = client.get("/explore/opening-economics", headers=_headers("plus-token"))

    assert base.json()["global"]["typicalOpeningPerPack"] == 3.25
    assert str(PLUS_VALUE) not in base.text
    assert str(PLUS_VALUE) in plus.text
    assert '"secret"' not in plus.text  # unknown nested fields fail closed


def test_market_breadth_and_acquisition_value_sentinels_never_cross_to_base(monkeypatch):
    _install_auth(monkeypatch)
    payload = {
        "cardsMarket": {
            "marketIndex": {"value": 101},
            "marketBreadth": {"advancingPercent": BREADTH_VALUE},
        },
        "publicRipContractV10": {"collectorAppeal": {"topSubjects": [{
            "subjectName": "Safe subject",
            "elitePath": {"canonicalCardId": "card-1", "modeledProbability": 0.01,
                          "packsFor50PercentChance": MILESTONE_VALUE},
        }] }},
    }
    monkeypatch.setattr(main, "get_pokemon_set_market_dashboard_snapshot_payload", lambda **kwargs: payload)
    client = TestClient(main.app)
    premium = client.get("/tcgs/pokemon/sets/set-1/market/dashboard", headers=_headers("premium-token"))
    base = client.get("/tcgs/pokemon/sets/set-1/market/dashboard", headers=_headers("base-token"))

    assert str(BREADTH_VALUE) in premium.text and str(MILESTONE_VALUE) in premium.text
    assert str(BREADTH_VALUE) not in base.text and str(MILESTONE_VALUE) not in base.text
    assert base.json()["cardsMarket"]["marketIndex"] == {"value": 101}


def test_chase_efficiency_is_premium_and_gate_precedes_reader(monkeypatch):
    _install_auth(monkeypatch)
    reads = []
    monkeypatch.setattr(main, "query_chase_efficiency", lambda *args, **kwargs: reads.append(True) or {"value": PREMIUM_VALUE})
    client = TestClient(main.app)

    assert client.get("/explore/card-chase-efficiency").status_code == 401
    assert client.get("/explore/card-chase-efficiency", headers=_headers("base-token")).status_code == 403
    assert client.get("/explore/card-chase-efficiency", headers=_headers("plus-token")).status_code == 403
    assert reads == []
    premium = client.get("/explore/card-chase-efficiency", headers=_headers("premium-token"))
    assert premium.status_code == 200 and PREMIUM_VALUE == premium.json()["value"]
    assert reads == [True]


SENTINEL_PAID_ONLY_VALUE = "SENTINEL_PAID_ONLY_VALUE"


def _set_rip_simulation_evidence_fixture():
    return {
        "contractVersion": "pokemon-set-rip-simulation-evidence-v1",
        "setId": "set-1",
        "calculationRunId": "run-1",
        "marketDate": "2026-08-30",
        "summary": {
            "simulation_count": 1000000,
            "pack_cost": 4.99,
            "median_value": 3.5,
            "mean_value": 5.25,
            "max_value": SENTINEL_PAID_ONLY_VALUE,
            "p95_value": SENTINEL_PAID_ONLY_VALUE,
            "p99_value": SENTINEL_PAID_ONLY_VALUE,
            "tail_value_p05": SENTINEL_PAID_ONLY_VALUE,
            "big_hit_threshold": SENTINEL_PAID_ONLY_VALUE,
        },
        "distributionBins": [{
            "bin_floor": 0, "bin_ceiling": 5, "occurrence_count": 400000,
            "probability": 0.4, "cumulative_probability": 0.4,
            "survival_probability": 1.0,
            "unknownBinField": SENTINEL_PAID_ONLY_VALUE,
        }],
        "thresholdBins": [{
            "threshold_floor": 0, "threshold_ceiling": 5, "occurrence_count": 400000,
            "probability": 0.4, "cumulative_probability": 0.4,
            "survival_probability": 1.0, "bucket_order": 1, "bucket_label": "$0-$5",
            "unknownThresholdField": SENTINEL_PAID_ONLY_VALUE,
        }],
        "meta": {
            "contractVersion": "pokemon-set-rip-simulation-evidence-v1",
            "builtAt": "2026-08-30T00:00:00Z", "marketDate": "2026-08-30",
            "calculationRunId": "run-1", "source": "snapshot", "available": True,
            "status": "ready", "unknownFutureField": SENTINEL_PAID_ONLY_VALUE,
        },
        "openingOutcomeProfile": {"secret": SENTINEL_PAID_ONLY_VALUE},
        "evRepresentativeness": {"detail": SENTINEL_PAID_ONLY_VALUE},
        "financialRip": {"score": SENTINEL_PAID_ONLY_VALUE},
        "collectorAppeal": {"score": SENTINEL_PAID_ONLY_VALUE},
        "advanced": {"anything": SENTINEL_PAID_ONLY_VALUE},
        "unknownFutureField": SENTINEL_PAID_ONLY_VALUE,
    }


def test_set_rip_simulation_evidence_is_public_and_projected(monkeypatch):
    _install_auth(monkeypatch)
    fixture = _set_rip_simulation_evidence_fixture()
    monkeypatch.setattr(main, "get_pokemon_set_rip_simulation_evidence_snapshot_payload",
                        lambda set_id=None: fixture)
    client = TestClient(main.app)
    route = "/tcgs/pokemon/sets/set-1/rip/simulation-evidence"

    anonymous = client.get(route)
    base = client.get(route, headers=_headers("base-token"))
    plus = client.get(route, headers=_headers("plus-token"))
    premium = client.get(route, headers=_headers("premium-token"))
    spoofed = client.get(
        route + "?plan=premium&index_plan=premium",
        headers=_headers("base-token", **{"x-plan": "premium", "x-index-plan": "premium"}),
    )

    for response in (anonymous, base, plus, premium, spoofed):
        assert response.status_code == 200

    for response in (anonymous, base, spoofed):
        body = response.json()
        assert SENTINEL_PAID_ONLY_VALUE not in response.text
        assert body["contractVersion"] == "pokemon-set-rip-simulation-evidence-v1"
        assert body["setId"] == "set-1"
        assert body["calculationRunId"] == "run-1"
        assert body["marketDate"] == "2026-08-30"
        assert body["summary"] == {
            "simulation_count": 1000000, "pack_cost": 4.99,
            "median_value": 3.5, "mean_value": 5.25,
        }
        assert body["distributionBins"] == [{
            "bin_floor": 0, "bin_ceiling": 5, "occurrence_count": 400000,
            "probability": 0.4, "cumulative_probability": 0.4, "survival_probability": 1.0,
        }]
        assert body["thresholdBins"] == [{
            "threshold_floor": 0, "threshold_ceiling": 5, "occurrence_count": 400000,
            "probability": 0.4, "cumulative_probability": 0.4, "survival_probability": 1.0,
            "bucket_order": 1, "bucket_label": "$0-$5",
        }]
        assert "openingOutcomeProfile" not in body
        assert "evRepresentativeness" not in body
        assert "financialRip" not in body
        assert "collectorAppeal" not in body
        assert "advanced" not in body
        assert "unknownFutureField" not in body

    # spoofed premium claim on an actually-Base token never changes the resolved plan
    assert spoofed.json() == base.json()

    for response in (plus, premium):
        assert SENTINEL_PAID_ONLY_VALUE in response.text
        assert response.json() == fixture

    assert anonymous.headers["cache-control"] == "no-store"
    assert "Authorization" in anonymous.headers["vary"]


def test_set_rip_advanced_and_legacy_simulation_evidence_stay_gated(monkeypatch):
    _install_auth(monkeypatch)
    monkeypatch.setattr(main, "get_pokemon_set_rip_advanced_snapshot_payload",
                        lambda set_id=None: {"secret": SENTINEL_PAID_ONLY_VALUE})
    monkeypatch.setattr(main, "get_pokemon_set_simulation_evidence_snapshot_payload",
                        lambda set_id=None: {"secret": SENTINEL_PAID_ONLY_VALUE})
    client = TestClient(main.app)

    advanced_anon = client.get("/tcgs/pokemon/sets/set-1/rip/advanced")
    advanced_base = client.get("/tcgs/pokemon/sets/set-1/rip/advanced", headers=_headers("base-token"))
    advanced_plus = client.get("/tcgs/pokemon/sets/set-1/rip/advanced", headers=_headers("plus-token"))
    legacy_anon = client.get("/tcgs/pokemon/sets/set-1/simulation-evidence")
    legacy_base = client.get("/tcgs/pokemon/sets/set-1/simulation-evidence", headers=_headers("base-token"))
    legacy_plus = client.get("/tcgs/pokemon/sets/set-1/simulation-evidence", headers=_headers("plus-token"))

    assert advanced_anon.status_code == 401
    assert advanced_base.status_code == 403
    assert advanced_plus.status_code == 200 and SENTINEL_PAID_ONLY_VALUE in advanced_plus.text
    assert legacy_anon.status_code == 401
    assert legacy_base.status_code == 403
    assert legacy_plus.status_code == 200 and SENTINEL_PAID_ONLY_VALUE in legacy_plus.text


def test_custom_market_plus_normalizes_for_access_but_cannot_reach_planner(monkeypatch):
    _install_auth(monkeypatch)
    touched = []
    normalized = {
        "contractVersion": "test", "asset": "cards", "eraIds": (), "setIds": ("set",),
        "segmentIds": ("rarity",), "pokemonIds": (), "priceSegmentIds": (),
        "releaseAgeCohortIds": (), "mode": "all", "topN": None,
    }
    monkeypatch.setattr(main, "normalize_query_spec",
                        lambda *args, **kwargs: touched.append("normalize") or normalized)
    monkeypatch.setattr(main.GLOBAL_MARKET_EXPLORER_PLANNER, "execute",
                        lambda **kwargs: touched.append("planner"))
    client = TestClient(main.app)
    response = client.post(
        "/market/explorer/query?plan=premium", json={
            "asset": "cards", "plan": "premium", "index_plan": "premium",
            "user_id": "forged-premium-user",
        },
        headers=_headers("plus-token", **{"x-index-plan": "premium"}),
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "MARKET_EXPLORER_PLAN_REQUIRED"
    assert touched == ["normalize"]


def test_custom_market_premium_cache_cannot_be_replayed_to_plus(monkeypatch):
    _install_auth(monkeypatch)
    main._market_explorer_query_cache.clear()
    normalized = {
        "contractVersion": "test", "asset": "cards", "eraIds": (), "setIds": (),
        "segmentIds": (), "pokemonIds": (), "priceSegmentIds": (),
        "releaseAgeCohortIds": (), "mode": "chase", "topN": 10,
    }
    monkeypatch.setattr(main, "normalize_query_spec", lambda **kwargs: normalized)
    runs = []
    from types import SimpleNamespace
    monkeypatch.setattr(main.GLOBAL_MARKET_EXPLORER_PLANNER, "execute",
                        lambda **kwargs: runs.append(True) or SimpleNamespace(
                            payload={"premiumMetric": PREMIUM_VALUE}))
    monkeypatch.setattr(
        main, "build_market_explorer_filter_options",
        lambda _client: {"premiumOptions": PREMIUM_VALUE},
    )
    client = TestClient(main.app)

    premium = client.post(
        "/market/explorer/query", json={"asset": "cards"},
        headers=_headers("premium-token"),
    )
    plus = client.post(
        "/market/explorer/query", json={"asset": "cards"},
        headers=_headers("plus-token"),
    )
    options_plus = client.get(
        "/market/explorer/query/options", headers=_headers("plus-token")
    )
    options_premium = client.get(
        "/market/explorer/query/options", headers=_headers("premium-token")
    )

    assert premium.status_code == 200 and str(PREMIUM_VALUE) in premium.text
    assert plus.status_code == 403 and str(PREMIUM_VALUE) not in plus.text
    assert options_plus.status_code == 200
    assert options_premium.status_code == 200 and str(PREMIUM_VALUE) in options_premium.text
    assert runs == [True]
