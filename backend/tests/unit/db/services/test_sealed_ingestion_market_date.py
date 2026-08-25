from backend.db.services.sealed_products_service import SealedProductsService


def test_sealed_price_uses_immutable_market_date_not_wall_clock():
    _, price, _, errors = SealedProductsService()._prepare_sealed_product_data({
        "name": "Box", "product_type": "Booster Box",
        "prices": {"market": 99.5}, "source": "TCGPlayer",
        "_market_date": "2026-08-23",
    }, "set-1")
    assert errors == []
    assert price["captured_at"] == "2026-08-23"
