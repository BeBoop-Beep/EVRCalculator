import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from backend.services.pokemon_set_onboarding_service import (
    OnboardingEngine, STEP_ORDER, validate_pull_rates_manifest,
)


def _job(step, metadata=None):
    return {
        "id": "job", "current_step": step, "canonical_key": "futureSet",
        "source_set_name": "Future Set", "metadata_json": metadata or {},
    }


def test_step_order_places_pre_and_post_desirability_around_simulation():
    assert STEP_ORDER.index("desirability_pre_sim") < STEP_ORDER.index("simulation")
    assert STEP_ORDER.index("simulation") < STEP_ORDER.index("desirability_post_sim")
    assert STEP_ORDER.index("explore_rankings") < STEP_ORDER.index("set_page_snapshot")


def test_pending_pull_model_blocks_simulation():
    outcome = OnboardingEngine(execute=True).run_step(_job("pull_model_validation"))
    assert outcome.kind == "wait"
    assert outcome.error_code == "awaiting_approved_pull_model"


def test_publication_gate_never_adds_force_publish():
    calls = []
    def runner(command, **kwargs):
        calls.append(command)
        return CompletedProcess(command, 0, stdout="", stderr="")
    job = _job("market_snapshots")
    outcome = OnboardingEngine(execute=True, command_runner=runner).run_step(job)
    assert outcome.kind == "advance"
    assert "--force-publish" not in calls[0]
    assert calls[0][-4:] == ["--days", "365", "--window", "365d"]


def test_pull_manifest_requires_provenance_and_positive_denominators(tmp_path: Path):
    path = tmp_path / "rates.json"
    path.write_text(json.dumps({
        "provenance": {"source_urls": ["https://source"]}, "captured_date": "2026-08-01",
        "rarity_denominators": {"rare": 10}, "slot_assumptions": {
            "rare_slot_probabilities": {"rare": 1.0},
        }, "product_type": "standard_booster", "validation": {
            "no_pack_odds_scaling_error": True, "valid_pack_state_override": True,
            "supported_product_collation": True, "all_required_rarities_classified": True,
        },
    }), encoding="utf-8")
    assert validate_pull_rates_manifest(path)["rarity_denominators"]["rare"] == 10
    payload = json.loads(path.read_text())
    payload["rarity_denominators"]["rare"] = 0
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid rarity denominator"):
        validate_pull_rates_manifest(path)
