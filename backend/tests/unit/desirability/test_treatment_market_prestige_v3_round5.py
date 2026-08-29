import json, math
from pathlib import Path
import numpy as np
from backend.desirability.treatment_market_prestige_v3 import stable_json_hash
from backend.scripts.build_treatment_market_prestige_v3_round5 import PREREG, random_effect, score
ROOT=Path("docs/research")

def test_practical_bands_and_gates_are_preregistered():
    assert PREREG["practical_log_bands"]["approximately_equivalent"]==math.log(1.25)
    assert PREREG["eligibility"]["maximum_loso_score_shift"]==1.0

def test_partial_pooling_shrinks_noisy_cells_more():
    r=random_effect(np.array([0.,2.,2.]),np.array([.01,.1,10.]))
    assert r["shrinkage_factors"][2] < r["shrinkage_factors"][1]
    assert abs(r["partially_pooled"][2]-r["population_effect"]) < abs(2-r["population_effect"])

def test_score_uses_frozen_anchor_semantics():
    assert score(0,0,1)==5 and score(1,0,1)>5

def test_round5_artifact_integrity_and_fail_closed_matrix():
    out=ROOT/"treatment_market_prestige_v3_round5_frozen";m=json.loads((out/"manifest.json").read_text());c=json.loads((out/"cohort.json").read_text());s=json.loads((ROOT/"treatment_market_prestige_v3_round5_study.json").read_text())
    assert stable_json_hash(c["rows"])==m["cohort_hash"]
    assert stable_json_hash(s)==m["study_hash"]
    assert len(s["support_matrix"])==17
    assert s["rows_persisted"]==0
    assert s["catalog_path_status"] in ("CATALOG_WIDE_PRODUCTION_RESEARCH_AUTHORIZED","ADDITIONAL_TARGETED_RESEARCH_REQUIRED","CURRENTLY_MODERN_ONLY")

def test_round4_structural_universes_are_preserved():
    s=json.loads((ROOT/"treatment_market_prestige_v3_round5_study.json").read_text())
    assert len(s["swsh_regimes"])==5 and len(s["sunmoon_regimes"])==3
