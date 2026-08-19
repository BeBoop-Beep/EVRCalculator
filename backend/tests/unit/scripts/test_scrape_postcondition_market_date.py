from backend.scripts.run_pokemon_set_scrape import _scrape_one_set

def test_write_target_and_postcondition_target_are_identical(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "backend.db.services.scrape_postcondition.verify_tcgplayer_source_variant_persistence",
        lambda set_id, market_date, keys: calls.append(market_date) or {
            "success": True, "acceptedVariantGroups": 1,
            "reconciledSourceVariantCount": 1})
    class Scraper:
        enable_db_ingestion = True
        def scrape(self, *_):
            return {"data": {"cards": [{}], "sealed_products": []},
                    "_scrape_outcome": {"setId": "set-1", "sourceVariantKeys": ["p|v"],
                                        "marketDate": "2026-08-18"}}
    class Config:
        PRINTED_TOTAL = 1
    result = _scrape_one_set(Scraper(), Config, "base", 1, 1, "2026-08-18")
    assert result["status"] == "success"
    assert calls == ["2026-08-18"]
