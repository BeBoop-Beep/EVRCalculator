from __future__ import annotations

import pytest

from backend.db.services import pokemon_sealed_product_detail_service as service


class Result:
    def __init__(self, data): self.data = data


class Query:
    def __init__(self, client, table):
        self.client, self.table, self.filters, self.in_filters, self.maximum = client, table, [], [], None
    def select(self, *_args): return self
    def eq(self, key, value): self.filters.append((key, str(value))); return self
    def in_(self, key, values): self.in_filters.append((key, {str(v) for v in values})); return self
    def limit(self, value): self.maximum = value; return self
    def execute(self):
        self.client.executed.append((self.table, list(self.filters), list(self.in_filters)))
        rows = [dict(row) for row in self.client.data.get(self.table, [])]
        for key, value in self.filters: rows = [row for row in rows if str(row.get(key)) == value]
        for key, values in self.in_filters: rows = [row for row in rows if str(row.get(key)) in values]
        return Result(rows[: self.maximum] if self.maximum is not None else rows)


class Client:
    def __init__(self, data): self.data, self.queries, self.executed = data, [], []
    def table(self, name): self.queries.append(name); return Query(self, name)


def ranking(product_id="p1", run_id="run-current", rank=2, family="booster_box", set_ev_representativeness=None):
    return {
        "sealedProductId": product_id, "productName": product_id, "productFamily": family,
        "calculationRunId": run_id, "familyRank": rank, "familySize": 4,
        "publicTier": "A", "overallRipLeaderScore": 88, "financialRipLeaderScore": 77,
        "collectorAppealScore": 80, "collectorAppealTier": "A", "overallRipVersion": "overall-rip-v10",
        "financialRipVersion": "financial-rip-v4", "collectorAppealVersion": "collector-v4",
        "setEvRepresentativeness": set_ev_representativeness,
    }


def ev_representativeness(run_id="run-current", pack_count=420):
    return {
        "contractVersion": "ev_representativeness_public_v1",
        "methodVersion": "ev_representativeness_v1",
        "calculationRunId": run_id,
        "realizationHorizon": {"targetEvRatio": .80, "openerProbability": .80, "packCount": pack_count, "status": "confirmed"},
    }


def fixture_data(modeled=True, image="large.png", p1_set_ev_representativeness=None):
    rankings = [ranking("leader", rank=1), ranking(set_ev_representativeness=p1_set_ev_representativeness), ranking("lower", rank=3), ranking("other", rank=4)] if modeled else []
    return {
        "sealed_products": [
            {"id": "p1", "set_id": "s1", "name": "Alpha Booster Box", "product_type": "box", "image_small_url": None, "image_large_url": image},
            {"id": "p2", "set_id": "s1", "name": "Alpha Elite Trainer Box", "product_type": "box", "image_small_url": None, "image_large_url": None},
        ],
        "sets": [{"id": "s1", "name": "Alpha Set", "canonical_key": "alpha-set", "hero_image_url": "hero", "logo_image_url": "logo", "symbol_image_url": "symbol"}],
        "sealed_product_price_observations": [
            {"id": "2", "sealed_product_id": "p1", "market_price": 120, "currency": "USD", "source": "tcgplayer", "captured_at": "2026-08-28T10:00:00Z"},
            {"id": "1", "sealed_product_id": "p1", "market_price": 100, "currency": "USD", "source": "tcgplayer", "captured_at": "2026-08-01T10:00:00Z"},
            {"id": "3", "sealed_product_id": "p2", "market_price": 50, "currency": "USD", "source": "tcgplayer", "captured_at": "2026-08-28T10:00:00Z"},
        ],
        "pokemon_explore_rankings_snapshot_latest": [{"tcg": "pokemon", "scope": service.DEFAULT_RANKINGS_SCOPE, "updated_at": "now", "ranking_payload_json": {"productFamilyRankings": {"families": {"booster_box": {"products": rankings}}}}}],
        "simulation_sealed_product_results": ([{
            "sealed_product_id": "p1", "calculation_run_id": "run-current", "product_family": "booster_box",
            "product_market_cost": 120, "expected_value": 80, "median_value": 70, "p05_value": 5,
            "p95_value": 200, "p99_value": 350, "chance_to_recover_cost": .25,
            "expected_loss_when_losing": 60, "median_loss_when_losing": 55, "total_value_to_cost_ratio": .666,
            "pack_count": 36, "random_pack_count": 36, "guaranteed_component_count": 1,
            "guaranteed_component_market_value": 20, "accessory_value_included": False,
            "composition_version": "stage2", "composition_id": "composition", "distribution_model_version": "model",
        }, {"sealed_product_id": "p1", "calculation_run_id": "run-stale", "expected_value": 999}] if modeled else []),
    }


def prepared_product(product_id, name, price, family, history=None):
    history = history or [
        {"date": "2026-07-14", "marketPrice": price - 10, "source": "market"},
        {"date": "2026-08-28", "marketPrice": price, "source": "market"},
    ]
    return {
        "sealedProductId": product_id,
        "name": name,
        "productFamily": family,
        "productFamilyLabel": family.replace("_", " ").title(),
        "currentPrice": price,
        "priceAsOf": "2026-08-28",
        "source": "market",
        "history": history,
        "movements": {"30D": {"comparisonStatus": "available"}},
    }


@pytest.fixture(autouse=True)
def current_publication(monkeypatch):
    monkeypatch.setattr(service, "_rankings_publication_identity_mismatches", lambda _payload: [])


def test_known_product_resolves_real_identity_market_family_and_parent_set():
    payload = service.get_pokemon_sealed_product_detail_payload("p1", Client(fixture_data()))
    assert payload["product"]["name"] == "Alpha Booster Box"
    assert payload["product"]["productFamily"] == "booster_box"
    assert payload["set"] == {"id": "s1", "slug": "alpha-set", "canonicalKey": "alpha-set", "name": "Alpha Set", "heroImageUrl": "hero", "logoImageUrl": "logo", "symbolImageUrl": "symbol"}
    assert [row["date"] for row in payload["market"]["history"]] == ["2026-08-01", "2026-08-28"]
    assert payload["market"]["currentPrice"] == 120
    assert payload["market"]["marketDate"] == "2026-08-28"
    assert payload["market"]["movements"]["30D"]["comparisonStatus"] == "since_first_available"


def test_published_run_is_exact_and_canonical_v10_v4_fields_win():
    payload = service.get_pokemon_sealed_product_detail_payload("p1", Client(fixture_data()))
    rip = payload["rip"]
    assert rip["available"] is True
    assert rip["calculationRunId"] == "run-current"
    assert rip["expectedValue"] == 80  # never the stale run's 999
    assert rip["overallRipVersion"] == "overall-rip-v10"
    assert rip["financialRipVersion"] == "financial-rip-v4"
    assert rip["collectorAppealScore"] == 80
    assert rip["collectorAppealTier"] == "A"
    assert rip["entertainmentCost"]["expectedValue"] == 80
    assert rip["entertainmentCost"]["entertainmentCost"] == 40  # guaranteed value was not added twice


def test_set_ev_representativeness_inherits_from_the_same_run_published_ranking_row():
    """The product page shows the SET's confirmed EV realization headline,
    sourced from the exact same published ranking row/query already used for
    everything else in the RIP contract - no second table read."""
    data = fixture_data(p1_set_ev_representativeness=ev_representativeness())
    client = Client(data)
    payload = service.get_pokemon_sealed_product_detail_payload("p1", client)
    rip = payload["rip"]
    assert rip["setEvRepresentativeness"]["calculationRunId"] == "run-current"
    assert rip["setEvRepresentativeness"]["realizationHorizon"]["packCount"] == 420
    # No additional table beyond the ones the RIP contract already reads.
    tables_read = {name for name, *_ in client.executed}
    assert tables_read <= {
        "sealed_products", "sets", "sealed_product_price_observations",
        "pokemon_explore_rankings_snapshot_latest", "simulation_sealed_product_results",
        "pokemon_set_sealed_market_snapshot_latest",
    }


def test_set_ev_representativeness_omitted_when_run_id_does_not_match():
    """A different-run set-level headline never survives - it is dropped,
    never shown as though it belonged to this product's validated run."""
    data = fixture_data(p1_set_ev_representativeness=ev_representativeness(run_id="run-DIFFERENT"))
    payload = service.get_pokemon_sealed_product_detail_payload("p1", Client(data))
    assert payload["rip"]["setEvRepresentativeness"] is None


def test_set_ev_representativeness_missing_does_not_break_the_product_rip_contract():
    payload = service.get_pokemon_sealed_product_detail_payload("p1", Client(fixture_data()))
    assert payload["rip"]["available"] is True
    assert payload["rip"]["setEvRepresentativeness"] is None


def test_top_level_v10_shape_lets_the_shared_explanation_hierarchy_render_the_canonical_split():
    """`rip.overallRipV10`/`rip.financialRipV4` are a pure relabeling of the
    same leader/rank/tier fields already on the RIP contract - the exact
    top-level shape `canonicalRipV7.mjs`'s `resolveCanonicalRipV7` already
    knows how to read (its "topLevelV10" branch), so
    `OverallRipExplanationHierarchy` can render the canonical 90/10
    explanation without a second frontend implementation."""
    payload = service.get_pokemon_sealed_product_detail_payload("p1", Client(fixture_data()))
    rip = payload["rip"]
    assert rip["overallRipV10"] == {
        "leaderNormalizedScore": rip["overallRipLeaderScore"],
        "rank": rip["familyRank"],
        "tier": rip["publicTier"],
        "cohortSize": rip["familySize"],
        "status": "ready",
    }
    assert rip["financialRipV4"] == {"leaderNormalizedScore": rip["financialRipLeaderScore"]}
    # No shadow V12 data on this fixture's ranking row - the contract must be
    # honestly None, never fabricated.
    assert rip["publicRipContractV11"] is None


def test_shadow_v12_ranking_payload_flows_through_as_publicRipContractV11():
    """When the product-family-rankings row (built from
    `simulation_sealed_product_results.overall_rip_v12_payload`) carries a
    SHADOW V12 result, the product detail contract exposes it under the same
    `publicRipContractV11` shape the shared frontend selector already knows
    how to read - a pure passthrough, no re-derivation of the score/weights."""
    v12_payload = {
        "score": 88.42, "version": "overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5",
        "status": "ready", "statusReason": None, "rankable": True,
        "components": {"financialRipV4": {"score": 91.2}}, "missingInputs": [],
        "weights": {"financial_rip": 0.86, "chase_accessibility": 0.04, "collector_appeal": 0.10},
        "effectiveWeights": {"chase_accessibility": 20.0},
    }
    data = fixture_data()
    families = data["pokemon_explore_rankings_snapshot_latest"][0]["ranking_payload_json"]["productFamilyRankings"]["families"]
    for row in families["booster_box"]["products"]:
        if row["sealedProductId"] == "p1":
            row["overallRipV12"] = v12_payload
    payload = service.get_pokemon_sealed_product_detail_payload("p1", Client(data))
    contract = payload["rip"]["publicRipContractV11"]
    assert contract["contractVersion"] == "public_rip_contract_v11"
    assert contract["overallRipV12"]["score"] == 88.42
    assert contract["overallRipV12"]["status"] == "ready"
    assert contract["overallRipV12"]["canonical"] is False
    assert contract["overallRipV12Composition"]["weights"] == v12_payload["weights"]
    assert contract["overallRipV12Composition"]["effectiveWeights"] == v12_payload["effectiveWeights"]


def test_shadow_v12_unavailable_status_never_fabricated_as_ready():
    """An unavailable/authority-mismatch V12 payload (as the finalizer writes
    it) must be reported honestly, never coerced to a ready score."""
    v12_payload = {
        "score": None, "version": "overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5",
        "status": "unavailable_authority_mismatch", "statusReason": "mismatch", "rankable": False,
        "components": {}, "missingInputs": ["chase_accessibility_v1"], "weights": {}, "effectiveWeights": {},
    }
    data = fixture_data()
    families = data["pokemon_explore_rankings_snapshot_latest"][0]["ranking_payload_json"]["productFamilyRankings"]["families"]
    for row in families["booster_box"]["products"]:
        if row["sealedProductId"] == "p1":
            row["overallRipV12"] = v12_payload
    payload = service.get_pokemon_sealed_product_detail_payload("p1", Client(data))
    contract = payload["rip"]["publicRipContractV11"]
    assert contract["overallRipV12"]["score"] is None
    assert contract["overallRipV12"]["status"] == "unavailable_authority_mismatch"
    assert contract["overallRipV12"]["rankable"] is False


def test_missing_exact_published_run_fails_only_rip_closed():
    data = fixture_data()
    data["simulation_sealed_product_results"] = [data["simulation_sealed_product_results"][1]]
    payload = service.get_pokemon_sealed_product_detail_payload("p1", Client(data))
    assert payload["product"]["id"] == "p1"
    assert payload["market"]["available"] is True
    assert payload["rip"]["available"] is False
    assert payload["rip"]["reason"] == "authoritative_result_unavailable"
    assert payload["rip"]["expectedValue"] is None


def test_unmodeled_and_missing_image_are_valid_without_fake_zeroes():
    payload = service.get_pokemon_sealed_product_detail_payload("p1", Client(fixture_data(modeled=False, image=None)))
    assert payload["product"]["imageUrl"] is None
    assert payload["market"]["currentPrice"] == 120
    assert payload["rip"]["available"] is False
    assert payload["rip"]["overallRipLeaderScore"] is None
    assert payload["comparisons"]["sameFamily"] == []


def test_top_ten_multi_product_bundle_reuses_exact_prepared_market_without_rip():
    data = fixture_data(modeled=False)
    product = data["sealed_products"][0]
    product.update({"name": "Ascended Heroes Tin [Set of 3]", "product_type": "Sealed Products"})
    prepared = prepared_product("p1", product["name"], 224.64, "multi_product_bundle")
    data["pokemon_set_sealed_market_snapshot_latest"] = [{
        "set_id": "s1", "payload_json": {
            "products": [], "setPageConsumerTopProducts": [prepared], "meta": {},
        },
        "market_date": "2026-08-28", "product_count": 0, "updated_at": "now",
    }]
    data["sealed_product_price_observations"] = []

    payload = service.get_pokemon_sealed_product_detail_payload("p1", Client(data))

    assert payload["product"]["id"] == prepared["sealedProductId"]
    assert payload["market"]["available"] is True
    assert payload["market"]["currentPrice"] == prepared["currentPrice"]
    assert payload["market"]["marketDate"] == prepared["priceAsOf"]
    assert payload["market"]["history"] == prepared["history"]
    assert payload["market"]["movements"] == prepared["movements"]
    assert payload["rip"]["available"] is False
    assert payload["rip"]["reason"] == "unsupported_product_family"
    assert payload["meta"]["marketSource"] == "pokemon_set_sealed_market_snapshot_latest"


@pytest.mark.parametrize(
    ("name", "family"),
    [
        ("Alpha Booster Box", "booster_box"),
        ("Alpha Elite Trainer Box", "elite_trainer_box"),
        ("Alpha Collector Tin", "tin"),
        ("Alpha Collection Box", "collection_product"),
        ("Alpha Three Pack Blister", "blister"),
    ],
)
def test_prepared_market_is_independent_of_modeling_family(name, family):
    data = fixture_data(modeled=False)
    data["sealed_products"][0]["name"] = name
    prepared = prepared_product("p1", name, 75, family)
    data["pokemon_set_sealed_market_snapshot_latest"] = [{
        "set_id": "s1", "payload_json": {
            "products": [prepared] if family in {"booster_box", "elite_trainer_box"} else [],
            "setPageConsumerTopProducts": [prepared], "meta": {},
        },
        "market_date": "2026-08-28", "product_count": 1, "updated_at": "now",
    }]
    data["sealed_product_price_observations"] = []

    payload = service.get_pokemon_sealed_product_detail_payload("p1", Client(data))

    assert payload["market"]["available"] is True
    assert payload["market"]["history"] == prepared["history"]
    assert payload["rip"]["available"] is False


def test_absent_snapshot_product_uses_only_requested_identity_raw_fallback():
    data = fixture_data(modeled=False)
    data["pokemon_set_sealed_market_snapshot_latest"] = [{
        "set_id": "s1", "payload_json": {
            "products": [], "setPageConsumerTopProducts": [], "meta": {},
        },
        "market_date": None, "product_count": 0, "updated_at": "now",
    }]
    client = Client(data)

    payload = service.get_pokemon_sealed_product_detail_payload("p1", client)

    assert payload["market"]["currentPrice"] == 120
    assert payload["meta"]["marketSource"] == "sealed_product_price_observations"
    assert "sealed_product_price_observations" in client.queries
    observation_reads = [query for query in client.executed if query[0] == "sealed_product_price_observations"]
    assert observation_reads == [("sealed_product_price_observations", [("sealed_product_id", "p1")], [])]


def test_comparisons_are_bounded_exclude_current_and_same_family_never_crosses_format():
    payload = service.get_pokemon_sealed_product_detail_payload("p1", Client(fixture_data()))
    assert all(row["sealedProductId"] != "p1" for row in payload["comparisons"]["sameSet"])
    assert all(row["sealedProductId"] != "p1" for row in payload["comparisons"]["sameFamily"])
    assert len(payload["comparisons"]["sameFamily"]) <= 5
    assert {row["productFamily"] for row in payload["comparisons"]["sameFamily"]} <= {"booster_box"}
    assert payload["comparisons"]["sameSet"][0]["href"] == "/sealed-products/p2"


def test_unknown_product_is_404():
    with pytest.raises(service.PokemonSealedProductDetailError) as caught:
        service.get_pokemon_sealed_product_detail_payload("missing", Client(fixture_data()))
    assert caught.value.status_code == 404
