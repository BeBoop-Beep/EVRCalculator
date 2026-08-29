import json
from pathlib import Path

from backend.desirability.treatment_market_prestige_v3 import stable_json_hash
from backend.scripts.build_treatment_market_prestige_v3_round4 import PREREG, score

ROOT=Path("docs/research")

def test_score_is_monotonic_and_centered():
    assert score(-1,0,1) < score(0,0,1) < score(1,0,1)
    assert score(0,0,1) == 5

def test_stability_thresholds_were_preregistered():
    assert PREREG["acceptable_score_movement"] == {"unrelated_universe_change": .5, "set_or_sample_perturbation": 1.0}

def test_round4_freeze_and_study_hashes():
    out=ROOT/"treatment_market_prestige_v3_round4_frozen"
    defs=json.loads((out/"regime_definitions.json").read_text())
    core={k:v for k,v in defs.items() if k not in ("definition_id","definition_hash")}
    assert stable_json_hash(core)==defs["definition_hash"]
    study=json.loads((ROOT/"treatment_market_prestige_v3_round4_study.json").read_text())
    manifest=json.loads((out/"manifest.json").read_text())
    assert stable_json_hash(study)==manifest["study_hash"]
    assert study["rows_persisted"]==study["production_scores"]==0
    assert len(study["era_support_statuses"])==17

def test_boundaries_are_structural_and_have_multiset_support():
    defs=json.loads((ROOT/"treatment_market_prestige_v3_round4_frozen/regime_definitions.json").read_text())
    assert "price-blind" in defs["assurance"]
    for era in defs["era_regimes"].values():
        assert all(len(regime["set_ids"])>=3 for regime in era["regimes"])
