from backend.services.pokemon_onboarding_publication_service import evaluate_onboarding_publication_readiness


class Query:
    def __init__(self, rows):
        self.data = rows
    def select(self, *_a, **_k): return self
    def eq(self, *_a, **_k): return self
    def in_(self, *_a, **_k): return self
    def gt(self, *_a, **_k): return self
    def gte(self, *_a, **_k): return self
    def lt(self, *_a, **_k): return self
    def order(self, *_a, **_k): return self
    def limit(self, *_a, **_k): return self
    def execute(self): return self


class Client:
    def __init__(self, rows, failure=None):
        self.rows, self.failure = rows, failure
    def table(self, name):
        if self.failure == name:
            raise RuntimeError("authority unavailable")
        return Query(self.rows.get(name, []))


def healthy():
    return {
        "pokemon_scrape_batches": [{
            "id": "batch", "market_date": "2026-08-01", "status": "complete",
            "promoted_at": "2026-08-02T00:00:00Z", "missing_set_count": 0,
            "expected_set_count": 1, "succeeded_set_count": 1, "failed_set_count": 0,
        }],
        "cards": [{"id": "card"}], "card_variants": [{"id": "variant"}],
        "card_variant_price_observations": [{"captured_at": "2026-08-01T12:00:00-07:00", "market_price": 1}],
        "sets": [{"id": "set", "name": "Future", "canonical_key": "futureSet"}],
        "calculation_history_trend": [{
            "snapshot_date": "2026-08-01", "target_id": "set", "calculation_run_id": "run",
            "simulated_mean_pack_value_vs_pack_cost": 0.8,
            "simulated_median_pack_value_vs_pack_cost": 0.7,
        }],
        "simulation_run_summary": [{"calculation_run_id": "run"}],
    }


def test_complete_promoted_aligned_batch_advances():
    rows = healthy()
    # Execution time is deliberately next-day and ignored; snapshot_date is authoritative.
    rows["calculation_runs"] = [{"id": "run", "created_at": "2026-08-02T01:00:00Z"}]
    result = evaluate_onboarding_publication_readiness(
        Client(rows), set_id="set", canonical_key="futureSet", market_date="2026-08-01",
    )
    assert result["complete"] is True
    assert result["reason_code"] == "allowed_complete"
    assert result["force_publish"] is False
    assert result["simulation_snapshot_date"] == "2026-08-01"
    assert result["calculation_run_id"] == "run"


def test_missing_and_incomplete_batch_wait():
    assert evaluate_onboarding_publication_readiness(
        Client({}), set_id="set", canonical_key="futureSet", market_date="2026-08-01",
    )["reason_code"] == "batch_missing"
    rows = healthy()
    rows["pokemon_scrape_batches"][0]["status"] = "incomplete"
    assert evaluate_onboarding_publication_readiness(
        Client(rows), set_id="set", canonical_key="futureSet", market_date="2026-08-01",
    )["reason_code"] == "batch_incomplete"


def test_authority_error_waits_safely():
    result = evaluate_onboarding_publication_readiness(
        Client(healthy(), failure="pokemon_scrape_batches"), set_id="set",
        canonical_key="futureSet", market_date="2026-08-01",
    )
    assert result["complete"] is False
    assert result["reason_code"] == "batch_authority_unavailable"


def test_missing_observation_and_simulation_mismatch_wait():
    rows = healthy()
    rows["card_variant_price_observations"] = []
    assert evaluate_onboarding_publication_readiness(
        Client(rows), set_id="set", canonical_key="futureSet", market_date="2026-08-01",
    )["reason_code"] == "set_observation_missing"
    rows = healthy()
    rows["calculation_history_trend"][0]["snapshot_date"] = "2026-08-03"
    assert evaluate_onboarding_publication_readiness(
        Client(rows), set_id="set", canonical_key="futureSet", market_date="2026-08-01",
    )["reason_code"] == "simulation_market_date_mismatch"


def test_missing_or_invalid_authoritative_simulation_history_waits():
    cases = []
    rows = healthy()
    rows["calculation_history_trend"] = []
    cases.append((rows, "simulation_history_missing"))
    rows = healthy()
    rows["calculation_history_trend"][0]["calculation_run_id"] = None
    cases.append((rows, "simulation_history_invalid"))
    rows = healthy()
    rows["simulation_run_summary"] = []
    cases.append((rows, "simulation_history_invalid"))
    rows = healthy()
    rows["calculation_history_trend"][0]["simulated_mean_pack_value_vs_pack_cost"] = None
    cases.append((rows, "simulation_history_invalid"))

    for rows, reason in cases:
        result = evaluate_onboarding_publication_readiness(
            Client(rows), set_id="set", canonical_key="futureSet", market_date="2026-08-01",
        )
        assert result["complete"] is False
        assert result["reason_code"] == reason
        assert result["force_publish"] is False
