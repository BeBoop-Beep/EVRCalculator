import json

from backend.scripts.pokemon_snapshot_builders import build_set_rip_read_models


def _payload():
    return {
        "target": {"id": "set-1", "name": "Ascended Heroes"},
        "summary": {"calculation_run_id": "run-1", "market_date": "2026-08-28", "pack_cost": 5.0,
                    "mean_value": 4.0, "private": "excluded"},
        "overallRipV9": {"score": 1},
        "publicRipContractV9": {"overallRip": {"score": 1}},
        "overallRipV10": {"score": 90, "rank": 1},
        "publicRipContractV10": {
            "overallRip": {"leaderNormalizedScore": 100, "relativeScore": 90, "rank": 1, "components": {"huge": True}},
            "financialRip": {"relativeScore": 80, "rank": 2, "components": {"jackpotUpside": {"score": 70}}},
            "collectorAppeal": {"relativeScore": 85, "rank": 3, "components": {"rosterDesirability": {"score": 90}},
                                "topSubjects": [{"name": "Pikachu"}]},
        },
        "ripDecision": {"sourceCalculationRunId": "run-1", "sealedProducts": {"products": [{"name": "ETB"}]}},
        "percentiles": [{"percentile": 95, "value": 20}],
        "distribution_bins": [{"bin_floor": 0}],
        "threshold_bins": [{"threshold_floor": 5}],
        "rankings": [{"rarity_bucket": "SIR", "total_sampled_value": 10}],
        "cardDesirabilityValidation": {"cards": list(range(100))},
        "meta": {"simulationAvailability": {"available": True}},
    }


def test_read_models_are_same_run_allowlisted_and_current_v10():
    models = build_set_rip_read_models(_payload(), set_id="set-1", built_at="2026-08-28T12:00:00Z")
    assert {value["calculationRunId"] for value in models.values()} == {"run-1"}
    assert {value["marketDate"] for value in models.values()} == {"2026-08-28"}
    bootstrap = models["bootstrap"]
    assert bootstrap["canonicalRip"]["overall"]["relativeScore"] == 90
    assert "components" not in bootstrap["canonicalRip"]["overall"]
    assert bootstrap["ripDecision"]["sourceCalculationRunId"] == "run-1"
    assert bootstrap["collectorSubjects"] == [{"name": "Pikachu"}]
    assert "private" not in bootstrap["summary"]
    assert "overallRipV9" not in json.dumps(bootstrap)
    assert models["simulation"]["distributionBins"] == [{"bin_floor": 0}]
    advanced = models["advanced"]
    assert advanced["financialRip"]["components"]["jackpotUpside"]["score"] == 70
    assert advanced["collectorAppeal"]["components"]["rosterDesirability"]["score"] == 90
    assert advanced["rarityContribution"][0]["rarity_bucket"] == "SIR"
    assert "distributionBins" not in advanced
    assert "cardDesirabilityValidation" not in advanced
    assert len(json.dumps(bootstrap).encode()) < 75_000

