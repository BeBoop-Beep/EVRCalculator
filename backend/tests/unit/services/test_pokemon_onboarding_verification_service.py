from pathlib import Path

import pytest

from backend.services.pokemon_onboarding_verification_service import collect_final_verification


class Query:
    def __init__(self, rows): self.data = rows
    def select(self, *_a, **_k): return self
    def eq(self, *_a, **_k): return self
    def in_(self, *_a, **_k): return self
    def gt(self, *_a, **_k): return self
    def order(self, *_a, **_k): return self
    def limit(self, *_a, **_k): return self
    def execute(self): return self


class Client:
    def __init__(self, rows): self.rows = rows
    def table(self, name): return Query(self.rows.get(name, []))


def healthy():
    return {
        "sets": [{"id": "set", "canonical_key": "futureSet", "name": "Future",
                  "ready_for_daily_scrape": True, "source_config_path": "backend/x/futureSet.py"}],
        "cards": [{"id": "card", "image_small_url": "img"}],
        "card_variants": [{"id": "variant", "card_id": "card", "image_small_url": None, "image_large_url": None}],
        "card_variant_price_observations": [{"captured_at": "2026-08-01T12:00:00Z", "market_price": 2}],
        "pokemon_set_value_daily_history": [{"snapshot_date": "2026-08-01", "set_value": 100}],
        "calculation_runs": [{"id": "run", "target_id": "set", "created_at": "2026-08-01"}],
        "simulation_run_summary": [{"calculation_run_id": "run", "simulation_count": 1000}],
        "simulation_input_cards": [{"calculation_run_id": "run"}],
        "simulation_derived_metrics": [{"calculation_run_id": "run"}],
        "pokemon_set_desirability_component_scores": [{"formula_version": "v1"}],
        "calculation_history_trend": [{"snapshot_date": "2026-08-01", "calculation_run_id": "run", "simulated_mean_pack_value_vs_pack_cost": 0.8}],
        "pokemon_set_top_chase_card_daily_history": [{"snapshot_date": "2026-08-01", "rank": 1}],
        "pokemon_set_market_dashboard_snapshot_latest": [{"latest_market_date": "2026-08-01", "updated_at": "now"}],
        "pokemon_explore_rankings_snapshot_latest": [{"ranking_payload_json": {"sets": [{"canonical_key": "futureSet"}]}, "updated_at": "now"}],
        "pokemon_set_page_snapshot_latest": [{
            "payload_json": {"collectorAppeal": {"status": "available", "score": 75},
                             "rip": {"status": "available", "score": 70, "rankable": True}},
            "updated_at": "now",
        }],
    }


def config(tmp_path: Path) -> Path:
    path = tmp_path / "futureSet.py"
    path.write_text('PULL_MODEL_STATUS = "approved"\n')
    return path


def test_healthy_set_completes_automatically(tmp_path):
    result = collect_final_verification(
        Client(healthy()), canonical_key="futureSet", config_path=config(tmp_path), min_image_coverage=0.9,
    )
    assert result["complete"] is True
    assert result["image_coverage_ratio"] == 1


@pytest.mark.parametrize(
    "mutation,missing",
    [
        (lambda rows: rows["pokemon_set_page_snapshot_latest"][0]["payload_json"].update(
            collectorAppeal={"status": "unavailable", "score": None}), "canonical_ca7"),
        (lambda rows: rows["pokemon_set_page_snapshot_latest"][0]["payload_json"].update(
            rip={"status": "unavailable", "score": None}), "overall_rip"),
        (lambda rows: rows.update(calculation_history_trend=[]), "current_opvc"),
        (lambda rows: rows.update(pokemon_explore_rankings_snapshot_latest=[]), "explore_contains_set"),
        (lambda rows: rows.update(pokemon_set_page_snapshot_latest=[]), "set_page_snapshot"),
        (lambda rows: rows["pokemon_set_top_chase_card_daily_history"][0].update(snapshot_date="2026-07-31"), "source_dates_align"),
    ],
)
def test_missing_or_misaligned_input_blocks(tmp_path, mutation, missing):
    rows = healthy()
    mutation(rows)
    result = collect_final_verification(
        Client(rows), canonical_key="futureSet", config_path=config(tmp_path), min_image_coverage=0.9,
    )
    assert result["complete"] is False
    assert missing in result["missing"]
