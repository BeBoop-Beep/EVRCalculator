import pytest

from backend.db.services import pokemon_card_detail_service as service
from backend.domain.pokemon.target_chase_economics import target_chase_for_product


class Result:
    def __init__(self, data): self.data = data


class Query:
    def __init__(self, rows): self.rows = list(rows)
    def select(self, *_args): return self
    def eq(self, key, value):
        self.rows = [row for row in self.rows if str(row.get(key)) == str(value)]
        return self
    def in_(self, key, values):
        wanted = {str(value) for value in values}
        self.rows = [row for row in self.rows if str(row.get(key)) in wanted]
        return self
    def limit(self, value): self.rows = self.rows[:value]; return self
    def execute(self): return Result(self.rows)


class Client:
    def __init__(self, tables): self.tables = tables; self.reads = []
    def table(self, name): self.reads.append(name); return Query(self.tables.get(name, []))


def fixture(*, variants=("v1",), canonical_selected=None, price=True):
    tables = {
        "pokemon_canonical_cards": [{
            "id": "canonical", "set_id": "set-1", "pokemon_tcg_api_card_id": "api-1",
            "name": "Pikachu", "number": "25", "printed_number": "025/100",
            "rarity": "Rare", "supertype": "Pokemon", "subtypes": ["Basic"],
            "image_small_url": "small", "image_large_url": "large",
        }],
        "cards": [{"id": "legacy", "set_id": "set-1", "pokemon_tcg_api_id": "api-1"}],
        "card_variants": [
            {"id": variant, "card_id": "legacy", "printing_type": "holo" if i else "non-holo",
             "special_type": "master ball" if i else None}
            for i, variant in enumerate(variants)
        ],
        "conditions": [{"id": "nm", "name": "Near Mint"}],
        "pokemon_set_page_snapshot_latest": [{
            "set_id": "set-1", "payload_json": {"ripDecision": {"sourceCalculationRunId": "run-1"}}
        }],
        "simulation_input_cards": [
            {"calculation_run_id": "run-1", "card_id": "legacy", "card_variant_id": variant,
             "condition_id": "nm", "card_name": "Pikachu", "rarity_bucket": "Rare",
             "price_used": 10 + i, "captured_at": "2026-08-17T00:00:00Z",
             "effective_pull_rate": 480 + i * 480}
            for i, variant in enumerate(variants)
        ],
        "simulation_input_cards_with_near_mint_price": [
            {"calculation_run_id": "run-1", "card_id": "legacy", "card_variant_id": variant,
             "condition_id": "nm", "card_name": "Pikachu", "rarity_bucket": "Rare",
             "current_near_mint_price": (20 + i) if price else None,
             "current_near_mint_price_captured_at": "2026-08-18T01:02:03Z" if price else None,
             "current_near_mint_price_source": "TCGPlayer" if price else None}
            for i, variant in enumerate(variants)
        ],
        "pokemon_canonical_card_market_prices_latest": ([{
            "canonical_card_id": "canonical", "set_id": "set-1",
            "card_variant_id": canonical_selected, "market_price": 20,
            "captured_at": "2026-08-18T01:02:03Z", "source": "TCGPlayer",
            "price_selection_reason": "preferred_printing",
        }] if canonical_selected else []),
    }
    return Client(tables)


@pytest.fixture(autouse=True)
def patch_dependencies(monkeypatch):
    monkeypatch.setattr(service, "resolve_pokemon_set_identifier", lambda _value, client=None: {
        "id": "set-1", "name": "Example Set", "canonical_key": "example-set"
    })
    monkeypatch.setattr(service, "_load_current_run_product_rows", lambda **_kwargs: [])


def build(client, variant_id=None):
    return service.get_pokemon_card_detail_payload(
        set_id="example-set", card_id="canonical", variant_id=variant_id, client=client
    )


def test_one_modeled_variant_is_selected_and_provenance_is_actual_observation():
    payload = build(fixture())
    assert payload["selectedVariantId"] == "v1"
    assert payload["variantSelection"] == {"state": "selected", "source": "only_modeled_variant"}
    assert payload["market"]["observedAt"] == "2026-08-18T01:02:03Z"
    assert payload["chase"]["expectedPacksToHit"] == 480
    assert "pokemon_set_chase_economics_snapshot_latest" not in payload["meta"]["sources"]


def test_multiple_variants_require_selection_without_provable_default():
    payload = build(fixture(variants=("v1", "v2")))
    assert payload["selectedVariantId"] is None
    assert payload["variantSelection"]["state"] == "selection_required"
    assert payload["chase"] == {
        "available": False, "reason": "variant_selection_required", "sourceCalculationRunId": "run-1"
    }


def test_valid_explicit_variant_preserves_variant_identity_and_math():
    payload = build(fixture(variants=("v1", "v2")), "v2")
    assert payload["selectedVariantId"] == "v2"
    assert payload["variantSelection"]["source"] == "query"
    assert payload["chase"]["impliedOddsOneInN"] == 960


def test_market_only_variant_is_selectable_without_reusing_modeled_pull_rate():
    client = fixture(variants=("v1", "v2"))
    client.tables["simulation_input_cards"] = client.tables["simulation_input_cards"][:1]
    client.tables["simulation_input_cards_with_near_mint_price"] = client.tables["simulation_input_cards_with_near_mint_price"][:1]
    client.tables["card_variant_price_observations"] = [{
        "card_variant_id": "v2", "condition_id": "nm", "market_price": 31,
        "source": "TCGPlayer", "captured_at": "2026-08-20T00:00:00Z",
    }]
    payload = build(client, "v2")
    assert payload["selectedVariantId"] == "v2"
    assert payload["market"]["currentPrice"] == 31
    assert payload["chase"]["available"] is False
    assert payload["chase"]["reason"] == "variant_not_modeled"
    assert "modeledProbability" not in payload["chase"]


def test_foreign_or_unknown_explicit_variant_is_never_used_and_falls_back_deterministically():
    payload = build(fixture(), "foreign-variant")
    assert payload["selectedVariantId"] == "v1"
    assert payload["variantSelection"]["source"] == "only_modeled_variant"
    assert payload["meta"]["requestedVariantValid"] is False


def test_canonical_market_selection_wins_when_it_is_modeled():
    payload = build(fixture(variants=("v1", "v2"), canonical_selected="v2"))
    assert payload["selectedVariantId"] == "v2"
    assert payload["variantSelection"]["source"] == "canonical_market_selection"


def test_canonical_card_without_usable_chase_still_returns_identity():
    client = fixture(variants=())
    payload = build(client)
    assert payload["card"]["canonicalCardId"] == "canonical"
    assert payload["variantSelection"]["state"] == "unavailable"
    assert payload["chase"]["reason"] == "modeled_chase_unavailable"


def test_wrong_card_set_combination_is_404():
    client = fixture()
    client.tables["pokemon_canonical_cards"] = []
    with pytest.raises(service.PokemonCardDetailError) as raised:
        build(client)
    assert raised.value.status_code == 404


def test_arbitrary_card_is_calculated_without_top_25_snapshot_dependency():
    client = fixture()
    payload = build(client)
    assert payload["chase"]["available"] is True
    assert "pokemon_set_chase_economics_snapshot_latest" not in client.reads


def test_product_economics_are_the_existing_chase_output(monkeypatch):
    product = {"sealed_product_id": "p1", "product_name": "Booster Box", "product_family": "box",
               "product_market_cost": 100, "pack_count": 36, "expected_value": 72,
               "price_as_of": "2026-08-18", "price_source": "TCGPlayer"}
    monkeypatch.setattr(service, "_load_current_run_product_rows", lambda **_kwargs: [product])
    payload = build(fixture())
    actual = payload["chase"]["products"][0]
    direct = target_chase_for_product(
        product_price=100,
        pack_groups=service.build_chase_economics_contract.__globals__["pack_groups_for_product"](
            product, target_probability_per_pack=1 / 480
        )[0],
        target_value_used_in_ev=10,
        current_target_market_price=20,
    )
    for key, value in direct.items():
        assert actual[key] == value
    assert payload["chase"]["recoveryModel"] == "gross_market_value"


def test_supported_products_keep_model_order_before_sorted_catalog_only_products(monkeypatch):
    supported = [
        {"sealed_product_id": "bundle", "product_name": "Bundle", "product_family": "booster_bundle",
         "product_market_cost": 30, "pack_count": 6, "expected_value": 20},
        {"sealed_product_id": "etb", "product_name": "ETB", "product_family": "elite_trainer_box",
         "product_market_cost": 55, "pack_count": 9, "expected_value": 30},
    ]
    monkeypatch.setattr(service, "_load_current_run_product_rows", lambda **_kwargs: supported)
    monkeypatch.setattr(service, "_load_sealed_product_catalog", lambda *_args: [
        {"sealedProductId": "z", "productName": "Zulu Blister", "available": False, "currentPrice": 19.99},
        {"sealedProductId": "etb", "productName": "Example ETB", "available": False, "currentPrice": 54.99},
        {"sealedProductId": "a", "productName": "Alpha Blister", "available": False, "currentPrice": 12.99},
        {"sealedProductId": "bundle", "productName": "Example Bundle", "available": False, "currentPrice": 29.99},
    ])
    products = build(fixture())["chase"]["products"]
    assert [item["sealedProductId"] for item in products] == ["bundle", "etb", "a", "z"]
    assert all(item["available"] for item in products[:2])
    assert all(not item["available"] for item in products[2:])


def test_market_history_is_variant_condition_scoped_sorted_and_deduplicated():
    client = fixture()
    client.tables["card_variant_price_observations"] = [
        {"card_variant_id": "v2", "condition_id": "nm", "market_price": 999, "captured_at": "2026-08-02T00:00:00Z"},
        {"card_variant_id": "v1", "condition_id": "lp", "market_price": 3, "captured_at": "2026-08-02T00:00:00Z"},
        {"card_variant_id": "v1", "condition_id": "nm", "market_price": 10, "source": "TCGPlayer", "captured_at": "2026-08-01T12:00:00Z"},
        {"card_variant_id": "v1", "condition_id": "nm", "market_price": 11, "source": "TCGPlayer", "captured_at": "2026-08-01T23:00:00Z"},
        {"card_variant_id": "v1", "condition_id": "nm", "market_price": 12, "source": "TCGPlayer", "captured_at": "2026-08-03T00:00:00Z"},
    ]
    payload = build(client)
    assert [row["date"] for row in payload["market"]["history"]] == ["2026-08-01", "2026-08-03"]
    assert [row["marketPrice"] for row in payload["market"]["history"]] == [11.0, 12.0]
    assert all(row["conditionId"] == "nm" and row["isObserved"] for row in payload["market"]["history"])


def test_long_requested_window_truthfully_reports_partial_coverage():
    history = [
        {"date": "2026-06-01", "marketPrice": 10},
        {"date": "2026-08-01", "marketPrice": 15},
    ]
    movement = service._market_movement(history, "1Y")
    assert movement["status"] == "partial_history"
    assert movement["fullCoverage"] is False
    assert movement["effectiveWindow"] == "lifetime"
    assert movement["deltaAmount"] == 5


def test_catalog_products_preserve_identity_media_latest_price_and_page_id():
    client = fixture()
    client.tables["sealed_products"] = [
        {"id": "p1", "set_id": "set-1", "name": "Example Set Booster Bundle", "product_type": "Sealed Products", "image_small_url": "small.jpg", "image_large_url": "large.jpg"},
        {"id": "p1", "set_id": "set-1", "name": "Duplicate", "product_type": "Sealed Products"},
    ]
    client.tables["sealed_product_price_observations"] = [
        {"sealed_product_id": "p1", "market_price": 80, "captured_at": "2026-08-20", "source": "TCGPlayer"},
        {"sealed_product_id": "p1", "market_price": 86.23, "captured_at": "2026-08-26", "source": "TCGPlayer"},
    ]
    products = service._load_sealed_product_catalog(client, "set-1")
    assert len(products) == 1
    assert products[0] == {
        "sealedProductId": "p1", "productName": "Example Set Booster Bundle", "catalogProductType": "Sealed Products",
        "productFamily": "booster_bundle", "productFamilyLabel": "Booster Bundle", "imageUrl": "small.jpg",
        "imageSmallUrl": "small.jpg", "imageLargeUrl": "large.jpg", "productPageId": "p1", "currentPrice": 86.23,
        "priceAsOf": "2026-08-26", "priceSource": "TCGPlayer", "available": False,
        "reason": "chase_economics_not_supported",
    }


def test_set_contract_separates_internal_target_id_from_canonical_route_slug():
    payload = build(fixture())
    assert payload["set"]["targetId"] == "example-set"
    assert payload["set"]["slug"] == "example-set"


def test_camel_case_internal_set_key_never_becomes_route_slug(monkeypatch):
    monkeypatch.setattr(service, "resolve_pokemon_set_identifier", lambda _value, client=None: {
        "id": "set-1", "name": "Ascended Heroes", "canonical_key": "ascendedHeroes"
    })
    payload = build(fixture())
    assert payload["set"]["targetId"] == "ascendedHeroes"
    assert payload["set"]["slug"] == "ascended-heroes"
