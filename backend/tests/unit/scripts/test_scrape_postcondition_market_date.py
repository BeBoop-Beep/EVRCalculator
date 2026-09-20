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



def test_catalog_sealed_only_skips_empty_card_variant_postcondition(monkeypatch):
    monkeypatch.setattr(
        "backend.db.services.scrape_postcondition.verify_tcgplayer_source_variant_persistence",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("card postcondition must not run")),
    )

    class Scraper:
        enable_db_ingestion = True
        def scrape(self, *_):
            return {
                "data": {"cards": [], "sealed_products": [{}]},
                "_scrape_outcome": {
                    "setId": "set-sealed",
                    "sourceVariantKeys": [],
                    "marketDate": "2026-09-20",
                    "rawRows": 0,
                    "acceptedVariantGroups": 0,
                    "dropped_other_code_card": 0,
                },
            }

    class Config:
        PRINTED_TOTAL = 0
        CATALOG_ONLY = True

    result = _scrape_one_set(Scraper(), Config, "sealedOnly", 1, 1, "2026-09-20")
    assert result["status"] == "success"
    assert result["sealed_scraped"] == 1
    assert result["metadata"]["cardPostconditionStatus"] == (
        "not_applicable_catalog_empty_or_code_cards_only"
    )


def test_catalog_code_cards_only_skips_empty_card_variant_postcondition(monkeypatch):
    monkeypatch.setattr(
        "backend.db.services.scrape_postcondition.verify_tcgplayer_source_variant_persistence",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("card postcondition must not run")),
    )

    class Scraper:
        enable_db_ingestion = True
        def scrape(self, *_):
            return {
                "data": {"cards": [], "sealed_products": [{}]},
                "_scrape_outcome": {
                    "setId": "set-code",
                    "sourceVariantKeys": [],
                    "marketDate": "2026-09-20",
                    "rawRows": 3,
                    "acceptedVariantGroups": 0,
                    "dropped_other_code_card": 3,
                },
            }

    class Config:
        PRINTED_TOTAL = 0
        CATALOG_ONLY = True

    result = _scrape_one_set(Scraper(), Config, "codeCardsOnly", 1, 1, "2026-09-20")
    assert result["status"] == "success"


def test_catalog_missing_required_rows_do_not_get_sealed_only_exemption(monkeypatch):
    monkeypatch.setattr(
        "backend.scripts.run_pokemon_set_scrape._backoff_sleep",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "backend.db.services.scrape_postcondition.verify_tcgplayer_source_variant_persistence",
        lambda *_a, **_k: {
            "success": False,
            "acceptedVariantGroups": 0,
            "reconciledSourceVariantCount": 0,
        },
    )

    class Scraper:
        enable_db_ingestion = True
        def scrape(self, *_):
            return {
                "data": {"cards": [], "sealed_products": [{}]},
                "_scrape_outcome": {
                    "setId": "set-bad-card",
                    "sourceVariantKeys": [],
                    "marketDate": "2026-09-20",
                    "rawRows": 3,
                    "acceptedVariantGroups": 0,
                    "dropped_other_code_card": 0,
                    "dropped_other_missing_required": 3,
                },
            }

    class Config:
        PRINTED_TOTAL = 0
        CATALOG_ONLY = True

    result = _scrape_one_set(Scraper(), Config, "missingRequired", 1, 1, "2026-09-20")
    assert result["status"] == "failed"
    assert "incomplete_source_variant_persistence" in result["error"]
