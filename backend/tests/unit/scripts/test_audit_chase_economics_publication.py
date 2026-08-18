from backend.scripts.audit_chase_economics_publication import run_audit


class Result:
    def __init__(self, data): self.data = data


class Query:
    def __init__(self, rows): self.rows = list(rows)
    def select(self, *_a): return self
    def eq(self, key, value): self.rows = [r for r in self.rows if str(r.get(key)) == str(value)]; return self
    def range(self, start, end): self.rows = self.rows[start:end + 1]; return self
    def execute(self): return Result(self.rows)


class Client:
    def __init__(self, tables): self.tables = tables
    def table(self, name): return Query(self.tables.get(name, []))


def fixtures(snapshot_updated="2026-08-18T01:00:00+00:00", product_updated="2026-08-18T00:00:00+00:00"):
    product = {"sealed_product_id": "p1", "product_market_cost": 88.23,
               "price_as_of": "2026-08-18", "price_source": "TCGPlayer",
               "updated_at": product_updated, "calculation_run_id": "run-1"}
    payload = {"sourceCalculationRunId": "run-1", "eligibleCardCount": 1,
               "cards": [{"cardVariantId": "v1", "currentTargetMarketPrice": 100,
                          "currentPriceAsOf": "2026-08-18",
                          "products": [{"sealedProductId": "p1", "productPrice": 88.23,
                                        "productPriceAsOf": "2026-08-18"}]}]}
    return {
        "explore_rip_statistics_latest": [{"set_id": "s1", "calculation_run_id": "run-1"}],
        "pokemon_set_page_snapshot_latest": [{"set_id": "s1", "payload_json": {"ripDecision": {"sourceCalculationRunId": "run-1"}}}],
        "pokemon_set_chase_economics_snapshot_latest": [{"set_id": "s1", "calculation_run_id": "run-1",
            "payload_json": payload, "card_count": 1, "updated_at": snapshot_updated}],
        "simulation_sealed_product_results": [product],
    }


def test_current_snapshot_passes():
    assert run_audit(Client(fixtures()), market_date="2026-08-18").passed


def test_product_update_after_snapshot_is_detected():
    report = run_audit(Client(fixtures(product_updated="2026-08-18T02:00:00+00:00")), market_date="2026-08-18")
    assert not report.passed
    assert any("updated after" in failure for failure in report.failures)


def test_missing_current_card_price_provenance_cannot_be_certified():
    data = fixtures()
    data["pokemon_set_chase_economics_snapshot_latest"][0]["payload_json"]["cards"][0]["currentPriceAsOf"] = None
    report = run_audit(Client(data), market_date="2026-08-18")
    assert any("missing current-price provenance" in failure for failure in report.failures)
