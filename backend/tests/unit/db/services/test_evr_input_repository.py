from unittest.mock import MagicMock, patch

import pytest

from backend.db.services.evr_input_repository import EVRInputRepository


@patch("backend.db.services.evr_input_repository.get_set_by_name")
@patch("backend.db.services.evr_input_repository.get_set_by_pokemon_api_set_id")
@patch("backend.db.services.evr_input_repository.get_set_by_canonical_key")
def test_resolve_set_prefers_canonical_key(
    mock_get_by_canonical,
    mock_get_by_api_id,
    mock_get_by_name,
):
    mock_get_by_canonical.return_value = {"id": "set-1", "canonical_key": "base"}

    service = EVRInputRepository()
    set_row, path = service._resolve_set_row(
        {"canonical_key": "base", "set_id": "sv1", "set_name": "Base"}
    )

    assert set_row["id"] == "set-1"
    assert path == "canonical_key"
    mock_get_by_api_id.assert_not_called()
    mock_get_by_name.assert_not_called()


@patch("backend.db.services.evr_input_repository.get_set_by_name")
@patch("backend.db.services.evr_input_repository.get_set_by_pokemon_api_set_id")
@patch("backend.db.services.evr_input_repository.get_set_by_canonical_key")
def test_resolve_set_fallbacks_to_api_id_then_name(
    mock_get_by_canonical,
    mock_get_by_api_id,
    mock_get_by_name,
):
    mock_get_by_canonical.return_value = None
    mock_get_by_api_id.return_value = None
    by_name_response = MagicMock()
    by_name_response.data = {"id": "set-by-name", "name": "Base"}
    mock_get_by_name.return_value = by_name_response

    service = EVRInputRepository()
    set_row, path = service._resolve_set_row(
        {"canonical_key": "", "set_id": "", "set_name": "Base"}
    )

    assert set_row["id"] == "set-by-name"
    assert path == "set_name"


@patch("backend.db.services.evr_input_repository.get_latest_prices_for_sealed_product_ids")
@patch("backend.db.services.evr_input_repository.get_sealed_products_for_set")
@patch("backend.db.services.evr_input_repository.get_latest_prices_for_variants")
@patch("backend.db.services.evr_input_repository.get_card_variants_by_card_ids")
@patch("backend.db.services.evr_input_repository.get_all_cards_for_set")
@patch("backend.db.services.evr_input_repository.get_condition_by_name")
@patch("backend.db.services.evr_input_repository.get_set_by_name")
@patch("backend.db.services.evr_input_repository.get_set_by_pokemon_api_set_id")
@patch("backend.db.services.evr_input_repository.get_set_by_canonical_key")
def test_load_inputs_returns_structured_payload_with_diagnostics(
    mock_get_by_canonical,
    _mock_get_by_api_id,
    _mock_get_by_name,
    mock_get_condition,
    mock_get_cards,
    mock_get_variants,
    mock_get_latest_variant_prices,
    mock_get_sealed_products,
    mock_get_latest_sealed_prices,
):
    mock_get_by_canonical.return_value = {
        "id": "set-1",
        "name": "Base",
        "canonical_key": "base",
        "pokemon_api_set_id": "sv1",
    }
    mock_get_condition.return_value = {"id": 1, "name": "Near Mint"}

    mock_get_cards.return_value = [
        {"id": 10, "name": "Charizard", "card_number": "4", "rarity": "Rare"},
        {"id": 11, "name": "Charizard", "card_number": "4", "rarity": "Rare"},
        {"id": 12, "name": "Blastoise", "card_number": "2", "rarity": "Rare"},
    ]
    mock_get_variants.return_value = [
        {"id": 101, "card_id": 10, "pokemon_tcg_api_id": "sv1-4", "special_type": "ex"},
        {"id": 102, "card_id": 12, "pokemon_tcg_api_id": "sv1-2", "special_type": None},
    ]
    mock_get_latest_variant_prices.return_value = [
        {"variant_id": 101, "condition_id": 1, "market_price": 120.0}
    ]

    mock_get_sealed_products.return_value = [
        {"id": 201, "set_id": "set-1", "name": "Base Booster Pack", "product_type": "Pack"},
        {"id": 202, "set_id": "set-1", "name": "Base Elite Trainer Box", "product_type": "ETB"},
        {"id": 203, "set_id": "set-1", "name": "Base ETB Promo Card", "product_type": "Promo"},
        {
            "id": 204,
            "set_id": "set-1",
            "name": "Base Pokemon Center Elite Trainer Box",
            "product_type": "ETB",
        },
        {
            "id": 205,
            "set_id": "set-1",
            "name": "Base Pokemon Center ETB Promo Card",
            "product_type": "Promo",
        },
        {"id": 206, "set_id": "set-1", "name": "Base Booster Box", "product_type": "Booster Box"},
    ]
    mock_get_latest_sealed_prices.return_value = [
        {"sealed_product_id": 201, "market_price": 6.0},
        {"sealed_product_id": 202, "market_price": 55.0},
        {"sealed_product_id": 204, "market_price": 89.0},
        {"sealed_product_id": 205, "market_price": 11.5},
        {"sealed_product_id": 206, "market_price": 180.0},
    ]

    service = EVRInputRepository()
    result = service.load_inputs({"canonical_key": "base", "set_id": "sv1", "set_name": "Base"})

    assert result["set"]["id"] == "set-1"
    assert len(result["cards"]) == 3
    assert result["diagnostics"]["total_cards_loaded"] == 3
    assert result["diagnostics"]["cards_missing_prices"] == 2
    assert result["diagnostics"]["duplicate_card_mappings"] == 1
    assert result["diagnostics"]["pack_price_resolution_status"] == "priced"
    assert result["diagnostics"]["etb_price_resolution_status"] == "priced"
    assert result["diagnostics"]["promo_price_resolution_status"] == "missing_price"
    assert result["diagnostics"]["booster_box_price_resolution_status"] == "priced"

    assert result["sealed"]["pack"]["sealed_product"]["id"] == 201
    assert result["sealed"]["etb"]["sealed_product"]["id"] == 202
    assert result["sealed"]["promo"]["sealed_product"]["id"] == 203
    assert result["sealed"]["booster_box"]["sealed_product"]["id"] == 206

    assert result["sealed_variants"]["etb"]["standard"]["resolved"]["sealed_product"]["id"] == 202
    assert result["sealed_variants"]["etb"]["pokemon_center"]["resolved"]["sealed_product"]["id"] == 204
    assert result["sealed_variants"]["promo"]["standard"]["resolved"]["sealed_product"]["id"] == 203
    assert result["sealed_variants"]["promo"]["pokemon_center"]["resolved"]["sealed_product"]["id"] == 205
    assert result["sealed_variants"]["booster_box"]["standard"]["resolved"]["sealed_product"]["id"] == 206
    assert result["sealed_variants"]["booster_box"]["pokemon_center"]["resolved"] is None
    assert result["cards"][0]["variants"][0]["special_type"] == "ex"
    assert result["cards"][2]["variants"][0]["special_type"] is None


def test_resolve_pack_target_selects_only_surging_sparks_booster_pack_for_pack_price():
    service = EVRInputRepository()
    sealed_rows = [
        {"id": 301, "name": "Surging Sparks Booster Pack", "product_type": "Pack"},
        {"id": 302, "name": "Surging Sparks 3 Pack Blisters", "product_type": "Pack"},
        {"id": 303, "name": "Surging Sparks Booster Bundle", "product_type": "Pack"},
        {"id": 304, "name": "Surging Sparks Booster Box", "product_type": "Pack"},
    ]
    latest = {
        301: {
            "sealed_product_id": 301,
            "market_price": 6.5,
            "source": "TCGPlayer",
            "captured_at": "2026-04-18T00:00:00+00:00",
        },
        302: {"sealed_product_id": 302, "market_price": 16.0},
        303: {"sealed_product_id": 303, "market_price": 29.0},
        304: {"sealed_product_id": 304, "market_price": 172.0},
    }

    resolved = service._resolve_single_sealed_target(sealed_rows, latest, "pack")

    assert resolved["status"] == "priced"
    assert resolved["resolved"]["sealed_product"]["id"] == 301
    assert resolved["resolved"]["sealed_product"]["name"] == "Surging Sparks Booster Pack"
    assert resolved["resolved"]["latest_price"]["sealed_product_id"] == 301


def test_resolve_pack_target_raises_when_multiple_canonical_single_pack_rows_exist():
    service = EVRInputRepository()
    sealed_rows = [
        {"id": 401, "name": "Base Booster Pack", "product_type": "Pack"},
        {"id": 402, "name": "Base Booster Pack (Alt Listing)", "product_type": "Booster Pack"},
    ]

    with pytest.raises(ValueError, match="PACK target ambiguous"):
        service._resolve_single_sealed_target(sealed_rows, {}, "pack")


def test_resolve_pack_target_raises_when_no_canonical_single_pack_row_exists():
    service = EVRInputRepository()
    sealed_rows = [
        {"id": 501, "name": "Base 3 Pack Blister", "product_type": "Pack"},
        {"id": 502, "name": "Base Sleeved Booster Pack", "product_type": "Pack"},
        {"id": 503, "name": "Base Booster Bundle", "product_type": "Bundle"},
    ]

    with pytest.raises(ValueError, match="PACK target missing canonical single booster pack row"):
        service._resolve_single_sealed_target(sealed_rows, {}, "pack")
