import pytest

from backend.scripts.build_card_treatment_prestige_v2_round5 import design, mixed_group


def row(label, species, set_id="s1", mechanic="basic", odds=2.0, price=2.0):
    return {"rarity_designation":label,"subject_ids":[species],"set_id":set_id,
        "mechanic_or_card_form":mechanic,"log_odds":odds,"price":price}


def test_species_fixed_effect_identifies_within_species_treatment_change():
    rows=[row("a","p1",odds=1),row("b","p1",odds=2),row("a","p2",odds=2),row("b","p2",odds=4)]
    result=design(rows,"b","species_fe")
    assert result["treatment_estimable"] is True
    assert result["residual_treatment_variance"]>0


def test_species_fixed_effect_detects_treatment_nested_in_species():
    rows=[row("a","p1",odds=1),row("a","p1",odds=2),row("b","p2",odds=2),row("b","p2",odds=3)]
    result=design(rows,"b","species_fe")
    assert result["treatment_estimable"] is False
    assert result["residual_treatment_variance"]==pytest.approx(0,abs=1e-20)


def test_mixed_group_counts_actual_cross_treatment_cells():
    rows=[row("a","p1"),row("b","p1"),row("a","p2"),row("a","p2")]
    result=mixed_group(rows,("species",))
    assert result=={"mixed_groups":1,"observations_in_mixed_groups":2,"cohort_percentage":.5}
