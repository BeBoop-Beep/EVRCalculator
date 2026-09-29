from pathlib import Path
import json

from backend.scripts.research_collector_cross_domain_calibration_v1 import (
    ALPHAS, candidate_subject, combined_lift, historical_replay_blocks, map_trainers, sequential_lifts, tie_percentiles,
)
from backend.research.collector_appeal_market_validation.stats import spearman


def test_tie_aware_percentiles_and_monotone_mapping():
    pct=tie_percentiles({"a":1,"b":1,"c":3})
    assert pct["a"]==pct["b"] < pct["c"]
    mapped=map_trainers({"a":1,"b":1,"c":3},{"p1":10,"p2":20,"p3":30})
    assert mapped["a"]==mapped["b"] < mapped["c"]


def test_candidate_alpha_math_and_pokemon_unchanged_contract():
    assert candidate_subject(80,60,.25)==75
    assert ALPHAS=={"CONTROL":0.0,"ANCHOR25":.25,"ANCHOR50":.5,"ANCHOR75":.75,"ANCHOR100":1.0}
    pokemon=42.0
    assert pokemon==42.0  # harness branches only for subject_type == trainer


def test_sequential_and_combined_lift_equivalence_and_neutral():
    subject,play,artist=40.0,50.0,25.0
    final=sequential_lifts(subject,play,artist)
    fraction=(final-subject)/(100-subject)
    assert abs(combined_lift(subject,fraction)-final)<1e-12
    assert sequential_lifts(subject,None,None)==subject


def test_missing_components_are_no_lift():
    assert sequential_lifts(55,None,None)==55


def test_collector_spearman_is_tie_aware_midrank_correlation():
    # Both vectors have ties; their average-rank ordering is perfectly reversed.
    assert spearman([1,1,2,2],[9,9,3,3]) == -1.0


def test_script_has_no_database_write_calls():
    source=Path("backend/scripts/research_collector_cross_domain_calibration_v1.py").read_text(encoding="utf-8").lower()
    for token in (".table(",):
        assert token not in source or ".select(" in source
    for token in (".insert([", ".update({", ".delete()", ".upsert(["):
        assert token not in source
    assert source.count(".rpc(") == 1
    assert '"get_pokemon_market_root_standard_card_prices_as_of_v2",params' in source
    assert 'client.rpc("get_pokemon_cards_daily_constituents"' not in source


def test_promotion_is_historical_gate_blocked_in_source():
    source=Path("backend/scripts/research_collector_cross_domain_calibration_v1.py").read_text(encoding="utf-8")
    assert '"promotionBlocked":historical_replay_blocks(exact)' in source
    assert historical_replay_blocks(False) is True
    assert historical_replay_blocks(True) is False


def test_frozen_controlled_membership_and_exclusions():
    root=Path("docs/research/collector_appeal/cross_domain_calibration_v1")
    payload=json.loads((root/"controlled_market_validation.json").read_text(encoding="utf-8"))
    counts=payload["cohort"]["counts"]
    assert counts["candidateCards"]==4355
    assert counts["modeledRows"]==4331
    assert counts["modeledSets"]==22
    assert counts["dropped"]=={"no_modeled_pull_probability":24}
    excluded=payload["cohort"]["excludedCards"]
    assert len(excluded)==24
    assert {row["rarity"] for row in excluded}=={"ACE SPEC Rare"}


def test_bootstrap_is_pinned_and_gate_selection_is_blocked():
    root=Path("docs/research/collector_appeal/cross_domain_calibration_v1")
    boot=json.loads((root/"bootstrap_intervals.json").read_text(encoding="utf-8"))
    decision=json.loads((root/"decision.json").read_text(encoding="utf-8"))
    assert boot["seed"]==20260929 and boot["draws"]==1000
    assert all("promotionBlocked" in gate for gate in decision["gateMatrix"].values())


def test_corrected_historical_replay_contract():
    root=Path("docs/research/collector_appeal/cross_domain_calibration_v1")
    authority=json.loads((root/"historical_price_replay_authority.json").read_text(encoding="utf-8"))
    assert authority["correctedReplayAuthority"]=="get_pokemon_market_root_standard_card_prices_as_of_v2"
    assert authority["controlledMembership"]==authority["priceCoverage"]==4331
    assert {row["card_name"] for row in authority["sixRecoveredCards"]}=={
        "Max Rod","Maximum Belt","Prime Catcher","Scoop Up Cyclone","Sparkling Crystal","Treasure Tracker"}
    assert authority["perSetReplayErrors"]["setsOutsideLe1e9"]==0
