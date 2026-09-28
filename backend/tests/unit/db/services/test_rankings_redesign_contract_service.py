from datetime import date

from backend.db.services.rankings_redesign_contract_service import (
    benchmark_presentation, benchmark_reference, project_product_contract,
    read_card_facets, read_financial_history_page, read_overview_v2, read_pack_economics,
)


class Response:
    def __init__(self, data): self.data = data


class Query:
    def __init__(self, rows): self.rows = list(rows)
    def select(self, *_args, **_kwargs): return self
    def eq(self, key, value): self.rows = [r for r in self.rows if str(r.get(key)) == str(value)]; return self
    def gte(self, key, value): self.rows = [r for r in self.rows if str(r.get(key)) >= str(value)]; return self
    def lte(self, key, value): self.rows = [r for r in self.rows if str(r.get(key)) <= str(value)]; return self
    def in_(self, key, values): self.rows = [r for r in self.rows if str(r.get(key)) in {str(v) for v in values}]; return self
    def order(self, key, desc=False, **_kwargs): self.rows.sort(key=lambda r: str(r.get(key)), reverse=desc); return self
    def limit(self, value): self.rows = self.rows[:value]; return self
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
    payload = {"available": True, "marketDate": "2026-09-28", "bestOpenPrice": {"sourceMarketDate": "2026-09-08"},
               "rows": [{"sealedProductId": "p1", "productName": "Pack", "budgetRank": 1, "budgetCohortSize": 138,
                         "overallRipScore": 8, "publicTier": "A", "financialRipScore": 31,
                         "unitPrice": 10, "bestOpenPrice": 8, "expectedValue": 4, "chanceToRecoverCost": .1}]}
    scores = project_product_contract(payload, view="scores")["rows"][0]
    economics = project_product_contract(payload, view="economics")["rows"][0]
    assert scores["rank"] == 1 and scores["rankScope"] == "full_market"
    assert economics["modeledReturnOnSpend"] == .4
    assert economics["bestOpenFreshnessStatus"] == "older"
    assert "unitPrice" not in scores and "ripScore" not in economics


def test_overview_v2_contains_absolute_financial_and_clean_economics_headlines():
    payload = {"openingEconomics": {"population": {"setCount": 22, "productSkuCount": 138, "productFamilyCount": 8},
        "global": {"averageModelBreakEvenPerPack": 6.7, "averageCostPerPack": 17.4,
                   "modeledReturnOnSpend": .38, "chanceToRecoverCost": .04,
                   "averageEntertainmentCostPerPack": 10.7},
        "sets": [{"setId": "s1", "setName": "Cheap", "setCanonicalKey": "cheap", "eraId": "e1", "averageCostPerPack": 7.1}]}}
    client = Client({"pokemon_rip_stats_snapshot_latest": [{"market_date": "2026-09-28", "payload_json": payload}],
        "pokemon_financial_rip_history_publications_v1": [{"market_date": "2026-09-28",
            "overall_financial_rip_reference": 30.36, "financial_model_version": "financial-v4"}]})
    result = read_overview_v2(client, legacy_headlines={"status": "available", "marketDate": "2026-09-28",
        "topSet": {"entityId": "s1", "name": "Cheap", "canonicalKey": "cheap", "benchmarkScore": 7, "rank": 1, "cohortSize": 22},
        "topEra": {"entityId": "e1", "name": "Era", "benchmarkScore": 6, "rank": 1, "cohortSize": 2}})
    assert result["overallFinancialRip"]["absoluteScore"] == 30.36
    assert result["lowestAveragePackCost"]["averagePackCost"] == 7.1
    assert result["modeledCoverage"] == {"setCount": 22, "productCount": 138, "productFamilyCount": 8}
    assert result["openingEconomics"]["overallExpectedValuePerPack"] == 6.7
    assert "typicalRetention" not in result["openingEconomics"] and "typicalOpening" not in result["openingEconomics"]


def test_pack_economics_preserves_multi_sku_best_open_and_stale_date():
    opening = {"openingEconomics": {"sets": [{"setId": "s1", "setName": "Set", "setCanonicalKey": "set",
        "eraId": "e1", "eraName": "Era", "productSkuCount": 2, "productFamilyCount": 1,
        "averageCostPerPack": 10, "averageModelBreakEvenPerPack": 4, "modeledReturnOnSpend": .4,
        "chanceToRecoverCost": .1, "averageEntertainmentCostPerPack": 6,
        "familyEconomics": [{"family": "box", "productSkuCount": 2, "averageCostPerPack": 10,
            "averageModelBreakEvenPerPack": 4, "modeledReturnOnSpend": .4,
            "chanceToRecoverCost": .1, "averageEntertainmentCostPerPack": 6}]}]}}
    best = [{"snapshot_id": "b1", "sealed_product_id": key, "set_id": "s1", "product_family": "box",
             "current_market_price": 100, "status": "resolved", "best_open_price": 80,
             "price_gap_dollars": 20, "price_gap_percent": .2} for key in ("p1", "p2")]
    client = Client({"pokemon_rip_stats_snapshot_latest": [{"market_date": "2026-09-28", "payload_json": opening}],
        "budget_product_best_open_price_latest": [{"snapshot_id": "b1", "source_market_date": "2026-09-08"}],
        "budget_product_best_open_price_rows": best,
        "sealed_products": [{"id": "p1", "name": "Box A"}, {"id": "p2", "name": "Box B"}]})
    result = read_pack_economics(client)
    family = result["sets"][0]["families"][0]
    assert result["bestOpenFreshnessStatus"] == "older"
    assert family["bestOpenDisplayMode"] == "multiple" and len(family["products"]) == 2
    assert "typicalRetention" not in result["sets"][0] and "typicalOpening" not in family
