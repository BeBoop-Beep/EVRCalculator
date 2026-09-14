from backend.db.services.collector_appeal_current_service import (
    build_public_collector_appeal_contract_from_v5,
)
from backend.desirability.collector_appeal import COLLECTOR_APPEAL_V5_VERSION


def test_canonical_v5_adapter_is_truthful_and_has_no_model_run_uuid():
    contract = build_public_collector_appeal_contract_from_v5({
        "status": "ready", "asOf": "2026-09-08",
        "collectorAppeal": {"score": 91.25, "version": COLLECTOR_APPEAL_V5_VERSION},
        "rosterDesirability": {"score": 80},
        "desirableOutcomeFrequency": {"rawValue": .1},
    })
    appeal = contract["collectorAppeal"]
    assert appeal["version"] == COLLECTOR_APPEAL_V5_VERSION
    assert appeal["modelVersion"] == COLLECTOR_APPEAL_V5_VERSION
    assert appeal["modelRunId"] is None
    assert appeal["score"] == 91.25


def test_v6_cannot_masquerade_through_v5_adapter():
    import pytest
    with pytest.raises(RuntimeError, match="non-V5"):
        build_public_collector_appeal_contract_from_v5({
            "status": "ready",
            "collectorAppeal": {"score": 99, "version": "pokemon_collector_appeal_v6_generalized_roster_frequency"},
        })
