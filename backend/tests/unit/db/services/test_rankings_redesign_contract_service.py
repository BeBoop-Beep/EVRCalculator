from datetime import date

from backend.db.services.rankings_redesign_contract_service import (
    benchmark_presentation, benchmark_reference, project_product_contract,
    read_card_facets, read_financial_history_page, read_overview_v2, read_pack_economics,
    read_product_best_open_map,
    read_public_headlines, read_public_pack_economics_preview, read_public_product_catalogue, read_scorecards,
)


class Response:
    def __init__(self, data): self.data = data


class Query:
    def __init__(self, rows): self.rows = list(rows)
    def select(self, *_args, **_kwargs): return self
    def eq(self, key, value): self.rows = [r for r in self.rows if str(r.get(key)) == str(value)]; return self
    def gte(self, key, value): self.rows = [r for r in self.rows if str(r.get(key)) >= str(value)]; return self
    def gt(self, key, value): self.rows = [r for r in self.rows if str(r.get(key)) > str(value)]; return self
    def lte(self, key, value): self.rows = [r for r in self.rows if str(r.get(key)) <= str(value)]; return self
    def in_(self, key, values): self.rows = [r for r in self.rows if str(r.get(key)) in {str(v) for v in values}]; return self
    def order(self, key, desc=False, **_kwargs): self.rows.sort(key=lambda r: str(r.get(key)), reverse=desc); return self
    def limit(self, value): self.rows = self.rows[:value]; return self
    def range(self, start, end): self.rows = self.rows[start:end + 1]; return self
    def or_(self, expression):
        # The service emits the fixed keyset form: date > D OR (date = D AND id > I).
        parts = expression.split(",")
        date_value = parts[0].split(".gt.", 1)[1]
        entity_value = parts[2].rsplit(".gt.", 1)[1].rstrip(")")
        self.rows = [r for r in self.rows if str(r.get("market_date")) > date_value or
                     (str(r.get("market_date")) == date_value and str(r.get("entity_id")) > entity_value)]
        return self
    def execute(self): return Response(self.rows)


class Client:
    def __init__(self, tables): self.tables = tables; self.calls = []
    def table(self, name): self.calls.append(name); return Query(self.tables.get(name, []))


def test_benchmark_presentation_proves_neutral_center_and_canonical_tiers():
    assert benchmark_reference() == {"label": "Pokémon Overall Average", "score": 5.0, "iconKey": "pokemon"}
    assert benchmark_presentation(7.25, rank=2, cohort_size=22) == {
        "score": 7.25, "rank": 2, "cohortSize": 22, "tier": "S",
        "benchmarkReferenceScore": 5.0, "deltaVsBenchmark": 2.25, "benchmarkPosition": "above",
    }
    assert benchmark_presentation(5)["benchmarkPosition"] == "at"
    assert benchmark_presentation(4.5)["benchmarkPosition"] == "below"


def test_financial_history_v2_reads_exact_dedicated_dates_without_lineage():
    dates = ["2026-08-22", "2026-08-24", "2026-08-25", "2026-08-26", "2026-09-08", "2026-09-12",
             "2026-09-13", "2026-09-14", "2026-09-15", "2026-09-25", "2026-09-27", "2026-09-28"]
    history = [{"market_date": day, "entity_type": "set", "entity_id": "set-1",
                "absolute_financial_rip_score": 31, "overall_financial_rip_reference": 30,
                "absolute_delta_vs_overall": 1, "rank": 1, "cohort_size": 22,
                "financial_model_version": "financial-v4", "source_snapshot_id": "private"} for day in dates]
    client = Client({"pokemon_financial_rip_history_rows_v1": history,
                     "pokemon_financial_rip_history_publications_v1": [{"market_date": d} for d in dates]})
    result = read_financial_history_page(client, entities=[{"entity_type": "set", "entity_id": "set-1"}],
                                         start_date=date(2026, 8, 1), end_date=date(2026, 9, 30), limit=100)
    observed = [row["marketDate"] for row in result["rows"]]
    assert result["contractVersion"] == "financial-rip-history-v2"
    assert result["historyAvailableFrom"] == "2026-08-22"
    assert result["historyAvailableThrough"] == "2026-09-28"
    assert len(observed) == 12 and "2026-09-17" not in observed and "2026-09-26" not in observed
    assert observed.count("2026-09-25") == 1
    assert all("source_snapshot_id" not in row and "fingerprint" not in str(row).lower() for row in result["rows"])
    assert client.calls.count("pokemon_financial_rip_history_rows_v1") == 1


def test_financial_history_v2_supports_mixed_set_era_bounded_pagination():
    rows = [{"market_date": "2026-09-28", "entity_type": kind, "entity_id": entity,
             "absolute_financial_rip_score": 30, "overall_financial_rip_reference": 30,
             "absolute_delta_vs_overall": 0, "rank": 1, "cohort_size": size,
             "financial_model_version": "v4"} for kind, entity, size in (("set", "s1", 22), ("era", "e1", 2))]
    client = Client({"pokemon_financial_rip_history_rows_v1": rows,
                     "pokemon_financial_rip_history_publications_v1": [{"market_date": "2026-09-28"}]})
    result = read_financial_history_page(client, entities=[{"entity_type": "set", "entity_id": "s1"},
                                                            {"entity_type": "era", "entity_id": "e1"}],
                                         start_date=date(2026, 9, 1), end_date=date(2026, 9, 30), limit=1)
    assert result["hasMore"] is True and result["nextCursor"] is not None and len(result["rows"]) == 1
    assert client.calls.count("pokemon_financial_rip_history_rows_v1") == 2


def test_financial_history_keyset_pages_concatenate_without_gaps_or_duplicates():
    rows = [{"market_date": day, "entity_type": kind, "entity_id": entity,
             "absolute_financial_rip_score": 30, "overall_financial_rip_reference": 30,
             "absolute_delta_vs_overall": 0, "rank": 1, "cohort_size": 24,
             "financial_model_version": "v4"}
            for day in ("2026-09-27", "2026-09-28")
            for kind, entity in (("era", "e1"), ("era", "e2"), ("set", "s1"), ("set", "s2"), ("set", "s3"))]
    client = Client({"pokemon_financial_rip_history_rows_v1": rows,
                     "pokemon_financial_rip_history_publications_v1": [{"market_date": "2026-09-27"}, {"market_date": "2026-09-28"}]})
    entities = [{"entity_type": kind, "entity_id": entity} for kind, entity in
                (("era", "e1"), ("era", "e2"), ("set", "s1"), ("set", "s2"), ("set", "s3"))]
    observed, cursor = [], None
    while True:
        page = read_financial_history_page(client, entities=entities, start_date=date(2026, 9, 1),
                                           end_date=date(2026, 9, 30), limit=3, after=cursor)
        observed.extend((r["marketDate"], r["entityType"], r["entityId"]) for r in page["rows"])
        if not page["hasMore"]:
            break
        cursor = page["nextCursor"]
    expected = sorted((r["market_date"], r["entity_type"], r["entity_id"]) for r in rows)
    assert observed == expected and len(observed) == len(set(observed))


def test_card_facets_are_one_prepared_pointer_bound_read():
    rows = [
        {"lens": "collector", "source_authority_id": "run", "source_model_version": "v7", "as_of_date": "2026-09-11",
         "dimension_type": "era", "facet_key": "base", "display_name": "Base", "entity_id": "e1", "parent_entity_id": None},
        {"lens": "collector", "source_authority_id": "run", "source_model_version": "v7", "as_of_date": "2026-09-11",
         "dimension_type": "set", "facet_key": "base-set", "display_name": "Base Set", "entity_id": "s1", "parent_entity_id": "e1"},
        {"lens": "collector", "source_authority_id": "run", "source_model_version": "v7", "as_of_date": "2026-09-11",
         "dimension_type": "subject_type", "facet_key": "neutral_functional", "display_name": "Neutral", "entity_id": None, "parent_entity_id": None},
    ]
    client = Client({"pokemon_card_ranking_facets_current_v1": rows})
    result = read_card_facets(client, lens="collector")
    assert result["sourceAuthorityId"] == "run" and result["sourceModelVersion"] == "v7"
    assert result["sets"][0]["eraId"] == "e1"
    assert result["subjectTypes"] == ["neutral_functional"]
    assert client.calls == ["pokemon_card_ranking_facets_current_v1"]


def test_products_split_keeps_rank_scope_and_separates_units():
    payload = {"available": True, "marketDate": "2026-09-28", "authority": {"overallRipVersion": "overall-rip-v12"},
               "bestOpenPrice": {"sourceMarketDate": "2026-09-08"},
               "rows": [{"sealedProductId": "p1", "productName": "Pack", "budgetRank": 1, "budgetCohortSize": 138,
                         "overallRipScore": 8, "publicTier": "A", "financialRipScore": 31,
                         "unitPrice": 10, "bestOpenPrice": 8, "expectedValue": 4, "chanceToRecoverCost": .1}]}
    scores = project_product_contract(payload, view="scores")["rows"][0]
    economics = project_product_contract(payload, view="economics")["rows"][0]
    assert scores["rank"] == 1 and scores["rankScope"] == "full_market"
    assert scores["ripScore"]["scoreValue"] == 8
    assert scores["ripScore"]["scoreKind"] == "absolute" and scores["ripScore"]["scoreScale"] == "0-100"
    assert scores["ripScore"]["benchmarkReference"] is None
    assert economics["modeledReturnOnSpend"] == .4
    assert economics["bestOpenFreshnessStatus"] == "older"
    assert "unitPrice" not in scores and "ripScore" not in economics


def test_product_score_contract_never_converts_absolute_and_activates_only_explicit_benchmark():
    payload = {"available": True, "marketDate": "2026-09-29",
               "authority": {"overallRipVersion": "overall-rip-v12"},
               "rows": [{"sealedProductId": "p1", "overallRipScore": 53.073,
                         "budgetRank": 1, "budgetCohortSize": 138}]}
    absolute = project_product_contract(payload, view="scores")
    assert absolute["rows"][0]["ripScore"]["scoreValue"] == 53.073
    assert absolute["scoreContract"] == {
        "scoreKind": "absolute", "scoreScale": "0-100", "metricVersion": "overall-rip-v12",
        "benchmarkAvailable": False, "publicationId": None, "calibrationVersion": None,
        "overallReference": {"status": "unavailable", "value": None,
                             "reason": "product_benchmark_publication_pending"},
    }
    benchmark = project_product_contract(payload, view="scores", product_benchmark={
        "status": "available", "metricVersion": "product-benchmark-v1", "publicationId": "pub1",
        "calibrationVersion": "cal1", "overallReference": {"status": "available", "value": 5.0},
        "rows": [{"sealedProductId": "p1", "benchmarkScore": 7.25, "rank": 2, "cohortSize": 10}],
    })
    score = benchmark["rows"][0]["ripScore"]
    assert (score["scoreKind"], score["scoreScale"], score["scoreValue"]) == ("benchmark", "0-10", 7.25)
    assert score["benchmarkReference"]["value"] == 5.0 and score["publicationId"] == "pub1"


def test_product_best_open_reads_direct_rows_without_pack_hierarchy():
    client = Client({
        "budget_product_best_open_price_latest": [{"snapshot_id": "snap", "source_market_date": "2026-09-08"}],
        "budget_product_best_open_price_rows": [{"snapshot_id": "snap", "sealed_product_id": "p1",
            "current_market_price": 45, "status": "available", "best_open_price": 42,
            "price_gap_dollars": 3, "price_gap_percent": .07}],
    })
    result = read_product_best_open_map(client, reference_date="2026-09-28")
    assert result["p1"]["bestOpenPrice"] == 42
    assert result["p1"]["bestOpenMarketPrice"] == 45
    assert result["p1"]["bestOpenMarketSourceDate"] == "2026-09-08"
    assert result["p1"]["bestOpenFreshnessStatus"] == "older"
    assert client.calls == ["budget_product_best_open_price_latest", "budget_product_best_open_price_rows"]


def test_overview_v2_contains_absolute_financial_and_clean_economics_headlines():
    payload = {"openingEconomics": {"population": {"setCount": 22, "productSkuCount": 138, "productFamilyCount": 8},
        "global": {"averageModelBreakEvenPerPack": 6.7, "averageCostPerPack": 17.4,
                   "modeledReturnOnSpend": .38, "chanceToRecoverCost": .04,
                   "averageEntertainmentCostPerPack": 10.7},
        "sets": [{"setId": "s1", "setName": "Cheap", "setCanonicalKey": "cheap", "eraId": "e1", "averageCostPerPack": 7.1}]}}
    client = Client({"pokemon_rip_stats_snapshot_latest": [{"market_date": "2026-09-28", "payload_json": payload}],
        "sets": [{"id": "s1", "logo_image_url": "logo.png", "symbol_image_url": "symbol.png"}],
        "pokemon_financial_rip_history_publications_v1": [{"market_date": "2026-09-28",
            "overall_financial_rip_reference": 30.36, "financial_model_version": "financial-v4"}]})
    result = read_overview_v2(client, legacy_headlines={"status": "available", "marketDate": "2026-09-28",
        "topSet": {"entityId": "s1", "name": "Cheap", "canonicalKey": "cheap", "benchmarkScore": 7, "rank": 1, "cohortSize": 22},
        "topEra": {"entityId": "e1", "name": "Era", "benchmarkScore": 6, "rank": 1, "cohortSize": 2}})
    assert result["overallFinancialRip"]["absoluteScore"] == 30.36
    assert result["lowestAveragePackCost"]["averagePackCost"] == 7.1
    assert result["modeledCoverage"] == {"setCount": 22, "productCount": 138, "productFamilyCount": 8}
    assert result["openingEconomics"]["overallExpectedValuePerPack"] == 6.7
    assert result["topSet"]["logoImageUrl"] == "logo.png"
    assert "typicalRetention" not in result["openingEconomics"] and "typicalOpening" not in result["openingEconomics"]


def test_pack_economics_preserves_multi_sku_best_open_and_stale_date():
    opening = {"openingEconomics": {"sets": [{"setId": "s1", "setName": "Set", "setCanonicalKey": "set",
        "eraId": "e1", "eraName": "Era", "productSkuCount": 2, "productFamilyCount": 1,
        "averageCostPerPack": 10, "averageModelBreakEvenPerPack": 4, "modeledReturnOnSpend": .4,
        "chanceToRecoverCost": .1, "averageEntertainmentCostPerPack": 6,
        "familyEconomics": [{"family": "elite_trainer_box", "productSkuCount": 2, "averageCostPerPack": 10,
            "averageModelBreakEvenPerPack": 4, "modeledReturnOnSpend": .4,
            "chanceToRecoverCost": .1, "averageEntertainmentCostPerPack": 6}]}]}}
    best = [
        {"snapshot_id": "b1", "sealed_product_id": "p1", "set_id": "s1", "product_family": "elite_trainer_box",
         "source_calculation_run_id": "run1", "current_market_price": 100, "current_quantity": 2,
         "current_actual_committed_capital": 200, "status": "resolved", "best_open_price": 80,
         "price_gap_dollars": 20, "price_gap_percent": .2},
        {"snapshot_id": "b1", "sealed_product_id": "p2", "set_id": "s1", "product_family": "elite_trainer_box",
         "source_calculation_run_id": "run2", "current_market_price": 120, "current_quantity": 1,
         "current_actual_committed_capital": 120, "status": "resolved", "best_open_price": 91,
         "price_gap_dollars": 29, "price_gap_percent": .2417},
    ]
    exact = [
        {"calculation_run_id": "run1", "sealed_product_id": "p1", "set_id": "s1", "product_family": "elite_trainer_box",
         "pack_count": 8, "random_pack_count": 8, "product_market_cost": 100, "price_as_of": "2026-09-08",
         "expected_value": 40, "chance_to_recover_cost": .10},
        {"calculation_run_id": "run2", "sealed_product_id": "p2", "set_id": "s1", "product_family": "elite_trainer_box",
         "pack_count": 11, "random_pack_count": 11, "product_market_cost": 120, "price_as_of": "2026-09-09",
         "expected_value": 66, "chance_to_recover_cost": .22},
    ]
    client = Client({"pokemon_rip_stats_snapshot_latest": [{"market_date": "2026-09-28", "payload_json": opening}],
        "budget_product_best_open_price_latest": [{"snapshot_id": "b1", "source_budget_snapshot_id": "rank1", "source_market_date": "2026-09-08"}],
        "budget_product_best_open_price_rows": best,
        "simulation_sealed_product_results": exact,
        "sealed_products": [{"id": "p1", "set_id": "s1", "name": "Standard ETB"},
                            {"id": "p2", "set_id": "s1", "name": "Pokémon Center ETB"}],
        "sets": [{"id": "s1", "logo_image_url": "logo.png", "symbol_image_url": "symbol.png"}]})
    result = read_pack_economics(client)
    family = result["sets"][0]["families"][0]
    assert result["bestOpenFreshnessStatus"] == "older"
    assert family["bestOpenDisplayMode"] == "multiple" and len(family["products"]) == 2
    assert result["sets"][0]["logoImageUrl"] == "logo.png"
    assert client.calls.count("sets") == 1
    products = result["sets"][0]["products"]
    assert [row["sealedProductId"] for row in products] == ["p2", "p1"]
    by_id = {row["sealedProductId"]: row for row in products}
    assert by_id["p1"]["packCount"] == 8 and by_id["p2"]["packCount"] == 11
    assert by_id["p1"]["averagePackCostPerPack"] == 12.5
    assert by_id["p2"]["averagePackCostPerPack"] == 120 / 11
    assert by_id["p1"]["expectedValuePerPack"] == 5
    assert by_id["p2"]["expectedValuePerPack"] == 6
    assert by_id["p1"]["modeledReturnOnSpend"] == .4 and by_id["p2"]["modeledReturnOnSpend"] == .55
    assert by_id["p1"]["chanceToRecoverCost"] == .10 and by_id["p2"]["chanceToRecoverCost"] == .22
    assert by_id["p1"]["bestOpenPrice"] == 80 and by_id["p2"]["bestOpenPrice"] == 91
    assert by_id["p1"]["entertainmentCostPerPack"] == 7.5
    assert round(by_id["p2"]["entertainmentCostPerPack"], 12) == round((120 - 66) / 11, 12)
    assert by_id["p1"]["economicsSourceMarketDate"] == "2026-09-08"
    assert by_id["p2"]["economicsSourceMarketDate"] == "2026-09-09"
    assert result["sets"][0]["averagePackCostPerPack"] == 10
    assert result["sets"][0]["expectedValuePerPack"] == 4
    assert result["sets"][0]["modeledReturnOnSpend"] == .4
    assert result["sets"][0]["chanceToRecoverCost"] == .1
    assert result["sets"][0]["entertainmentCostPerPack"] == 6
    assert len(client.calls) == 6
    assert "typicalRetention" not in result["sets"][0] and "typicalOpening" not in family


def test_pack_economics_never_substitutes_family_means_when_exact_evidence_is_unavailable():
    opening = {"openingEconomics": {"sets": [{"setId": "s1", "setName": "Set", "productSkuCount": 1,
        "averageCostPerPack": 10, "averageModelBreakEvenPerPack": 4, "modeledReturnOnSpend": .4,
        "chanceToRecoverCost": .1, "averageEntertainmentCostPerPack": 6,
        "familyEconomics": [{"family": "elite_trainer_box", "productSkuCount": 1,
            "averageCostPerPack": 99, "averageModelBreakEvenPerPack": 88,
            "modeledReturnOnSpend": .89, "chanceToRecoverCost": .77,
            "averageEntertainmentCostPerPack": 11}]}]}}
    client = Client({
        "pokemon_rip_stats_snapshot_latest": [{"market_date": "2026-09-28", "payload_json": opening}],
        "sets": [{"id": "s1"}],
        "budget_product_best_open_price_latest": [{"snapshot_id": "b1", "source_market_date": "2026-09-08"}],
        "budget_product_best_open_price_rows": [{"snapshot_id": "b1", "sealed_product_id": "p1", "set_id": "s1",
            "product_family": "elite_trainer_box", "current_market_price": 100, "status": "resolved",
            "best_open_price": 80, "price_gap_dollars": 20, "price_gap_percent": .2}],
        "sealed_products": [{"id": "p1", "set_id": "s1", "name": "ETB"}],
    })
    product = read_pack_economics(client)["sets"][0]["products"][0]
    assert product["economicsAvailabilityStatus"] == "unavailable"
    assert product["unitPrice"] == 100
    assert all(product[key] is None for key in ("packCount", "averagePackCostPerPack",
        "expectedValuePerPack", "modeledReturnOnSpend", "chanceToRecoverCost", "entertainmentCostPerPack"))
    assert product["bestOpenPrice"] == 80


def test_paid_set_scorecards_project_artwork_in_one_bounded_identity_read():
    client = Client({
        "pokemon_rip_benchmark_publications_v1": [{"id": "pub", "market_date": "2026-09-28",
            "benchmark_key": "pokemon", "calibration_version": "v1", "overall_model_version": "overall-v12",
            "publication_status": "published"}],
        "pokemon_rip_benchmark_rows_v1": [{"publication_id": "pub", "entity_type": "set", "entity_id": "s1",
            "metric_key": "financial", "benchmark_score": 6.2, "rank": 1, "cohort_size": 1, "benchmark_status": "available"}],
        "sets": [{"id": "s1", "name": "Set", "canonical_key": "set", "era_id": "e1",
                  "logo_image_url": "logo.png", "symbol_image_url": "symbol.png"}],
        "eras": [{"id": "e1", "name": "Era", "canonical_key": "era"}],
    })
    result = read_scorecards(client, entity_type="set", benchmark_key="pokemon", calibration_version="v1")
    assert result["rows"][0]["logoImageUrl"] == "logo.png"
    assert result["rows"][0]["symbolImageUrl"] == "symbol.png"
    assert client.calls.count("sets") == 1


def test_public_headlines_are_overall_only_and_keep_set_artwork():
    client = Client({
        "pokemon_rip_benchmark_publications_v1": [{"id": "pub", "market_date": "2026-09-28",
            "benchmark_key": "pokemon", "calibration_version": "v1", "overall_model_version": "overall-v12",
            "publication_status": "published"}],
        "pokemon_rip_benchmark_rows_v1": [
            {"publication_id": "pub", "entity_type": "set", "entity_id": "s1", "metric_key": "overall",
             "benchmark_score": 7.2, "rank": 1, "cohort_size": 22, "benchmark_status": "available"},
            {"publication_id": "pub", "entity_type": "set", "entity_id": "s1", "metric_key": "financial",
             "benchmark_score": 9.9, "rank": 1, "cohort_size": 22, "benchmark_status": "available"}],
        "sets": [{"id": "s1", "name": "Set", "canonical_key": "set", "era_id": "e1",
                  "logo_image_url": "logo.png", "symbol_image_url": "symbol.png"}],
        "eras": [{"id": "e1", "name": "Era", "canonical_key": "era"}],
    })
    result = read_public_headlines(client, entity_type="set", benchmark_key="pokemon", calibration_version="v1")
    assert len(result["rows"]) == 1 and result["rows"][0]["overall"]["score"] == 7.2
    assert result["rows"][0]["logoImageUrl"] == "logo.png" and result["rows"][0]["symbolImageUrl"] == "symbol.png"
    text = str(result).lower()
    assert "financial" not in text and "collector" not in text and "chase" not in text and "lineage" not in text
    assert client.calls.count("pokemon_rip_benchmark_rows_v1") == 1


def test_public_pack_preview_allowlists_counts_cost_and_artwork():
    opening = {"openingEconomics": {"sets": [{"setId": "s1", "setName": "Set", "eraId": "e1",
        "productFamilyCount": 2, "productSkuCount": 3, "averageCostPerPack": 4.5,
        "averageModelBreakEvenPerPack": 99, "modeledReturnOnSpend": .9, "chanceToRecoverCost": .8,
        "entertainmentCostPerPack": 7, "familyEconomics": [{}, {}]}]}}
    client = Client({"pokemon_rip_stats_snapshot_latest": [{"market_date": "2026-09-28", "payload_json": opening}],
        "sets": [{"id": "s1", "name": "Set", "canonical_key": "set", "era_id": "e1",
                  "logo_image_url": "logo.png", "symbol_image_url": "symbol.png"}],
        "eras": [{"id": "e1", "name": "Era", "canonical_key": "era"}]})
    result = read_public_pack_economics_preview(client)
    row = result["sets"][0]
    assert (row["productFamilyCount"], row["productCount"], row["averagePackCostPerPack"]) == (2, 3, 4.5)
    assert row["logoImageUrl"] == "logo.png" and row["symbolImageUrl"] == "symbol.png"
    assert all(key not in row for key in ("expectedValuePerPack", "modeledReturnOnSpend", "chanceToRecoverCost", "entertainmentCostPerPack", "families"))


def test_public_product_catalogue_is_alphabetical_and_score_independent():
    client = Client({
        "sealed_products": [
            {"id": "p2", "set_id": "s1", "name": "Zulu Booster Box", "product_type": "Sealed", "image_small_url": "z.png"},
            {"id": "p1", "set_id": "s1", "name": "Alpha Elite Trainer Box", "product_type": "Sealed", "image_small_url": "a.png"}],
        "sets": [{"id": "s1", "name": "Set", "canonical_key": "set", "era_id": "e1"}],
        "eras": [{"id": "e1", "name": "Era", "canonical_key": "era"}],
        "pokemon_rip_benchmark_rows_v1": [{"entity_id": "p2", "benchmark_score": 10}],
    })
    result = read_public_product_catalogue(client)
    assert [row["sealedProductId"] for row in result["rows"]] == ["p1", "p2"]
    assert result["rows"][0]["familyKey"] == "elite_trainer_box"
    assert "pokemon_rip_benchmark_rows_v1" not in client.calls
    assert all(not any(key in row for key in ("rank", "ripScore", "unitPrice", "bestOpenPrice")) for row in result["rows"])
