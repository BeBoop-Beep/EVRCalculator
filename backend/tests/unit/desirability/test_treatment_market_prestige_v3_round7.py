import json
from pathlib import Path
from backend.desirability.treatment_market_prestige_v3 import stable_json_hash
from backend.scripts.build_treatment_market_prestige_v3_round7 import DATES,SOURCE,load_freeze,universe_defs
ROOT=Path("docs/research")

def test_authoritative_source_and_checkpoint_contract():
    assert SOURCE["relation"]=="public.card_variant_price_observations"
    assert "no interpolation" in SOURCE["checkpoint"]
    assert (DATES[-1]-DATES[0]).days>=85 and len(DATES)==4

def test_round4_universes_preserved():
    r4=json.loads((ROOT/"treatment_market_prestige_v3_round4_study.json").read_text());u=universe_defs(r4)
    assert sum(k.startswith("sword_and_shield") for k in u)==5
    assert sum(k.startswith("sun_and_moon") for k in u)==2
    assert u["XY"]["type"]=="ERA_RELATIVE"

def test_round7_freeze_hashes_and_zero_writes():
    r4=json.loads((ROOT/"treatment_market_prestige_v3_round4_study.json").read_text());m,data=load_freeze(r4);s=json.loads((ROOT/"treatment_market_prestige_v3_round7_study.json").read_text())
    assert stable_json_hash(s)==m["study_hash"]
    assert s["rows_persisted"]==0
    assert len(data)==10 and all(len(x)==4 for x in data.values())

def test_positive_control_must_reproduce():
    s=json.loads((ROOT/"treatment_market_prestige_v3_round7_study.json").read_text())
    assert s["positive_control"]["status"]=="REPRODUCED"

def test_round6_contract_is_unchanged():
    r6=json.loads((ROOT/"treatment_market_prestige_v3_round6_frozen/production_contract.json").read_text());m=json.loads((ROOT/"treatment_market_prestige_v3_round7_temporal/manifest.json").read_text())
    assert stable_json_hash(r6)==m["round6_contract_hash"]
