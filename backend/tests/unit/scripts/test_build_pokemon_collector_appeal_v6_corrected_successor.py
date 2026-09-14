from backend.scripts.build_pokemon_collector_appeal_v6_corrected_successor import pokemon_d, trainer_d

def test_frozen_pokemon_d_neutral_and_duplicate_contract():
    base=pokemon_d([90,80,70])[0]
    assert pokemon_d([90,80,70,50])[0] == base
    assert pokemon_d([90,80,70])[0] == base

def test_trainer_headroom_is_positive_and_bounded():
    dp=80;dt=trainer_d([90,75]);lift=(100-dp)*.15*(dt/100)
    assert 0 <= lift <= (100-dp)*.15
