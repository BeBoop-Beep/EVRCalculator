from backend.scripts.build_treatment_market_prestige_v3_round3 import EVIDENCE_CONTRACT, TEMPORAL_GATES


def test_temporal_gates_are_preregistered_and_strict():
    assert TEMPORAL_GATES["minimum_adequate_checkpoints"] >= 3
    assert TEMPORAL_GATES["minimum_exact_order_preservation"] >= .75
    assert TEMPORAL_GATES["strong_ordering_probability"] >= .95


def test_low_sample_contract_is_composite_not_post_hoc_name_rule():
    rule=EVIDENCE_CONTRACT["composite_low_sample"]
    assert rule["minimum_cards"] < EVIDENCE_CONTRACT["standard"]["minimum_cards"]
    assert len(rule) >= 9
    assert "ultra" not in str(EVIDENCE_CONTRACT).lower()


def test_uncertainty_is_required_for_every_cell():
    common=EVIDENCE_CONTRACT["common_requirements"]
    assert common["bootstrap_interval_excludes_zero"] is True
    assert common["temporally_stable"] is True
