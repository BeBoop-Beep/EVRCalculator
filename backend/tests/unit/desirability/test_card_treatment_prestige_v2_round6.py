import numpy as np
import pytest

from backend.scripts.build_card_treatment_prestige_v2_round6 import holm, reparameterize


def row(label,species,set_id="s1",mechanic="basic",odds=1.0,price=2.0):
    return {"rarity_designation":label,"subject_ids":[species],"set_id":set_id,
        "mechanic_or_card_form":mechanic,"log_odds":odds,"price":price}


def test_reparameterization_removes_only_redundant_nuisance_columns():
    rows=[row("a","p1",mechanic="basic",odds=1),row("b","p1",mechanic="stage_1",odds=2),
          row("a","p2",mechanic="stage_1",odds=2),row("b","p2",mechanic="basic",odds=4),
          row("a","p3",mechanic="basic",odds=3),row("b","p3",mechanic="basic",odds=6)]
    fit=reparameterize(rows,"b")
    assert fit["rank"]==fit["columns"]
    assert fit["column_space_proof"]["nuisance_rank_before"]==fit["column_space_proof"]["nuisance_rank_after"]
    assert fit["column_space_proof"]["max_projection_error"]<1e-10
    assert all(x["classification"]=="NUISANCE_REDUNDANCY_REMOVED" for x in fit["removed_columns"])


def test_reparameterization_does_not_rescue_treatment_nested_in_mechanics():
    rows=[row("a","p1",mechanic="basic",odds=1),row("a","p2",mechanic="basic",odds=2),
          row("b","p1",mechanic="stage_1",odds=2),row("b","p2",mechanic="stage_1",odds=4)]
    fit=reparameterize(rows,"b")
    assert fit["treatment_estimable"] is False
    assert fit["coefficient"] is None


def test_holm_adjustment_controls_six_test_family():
    results=[{"permutation_placebo":{"raw_p_value":p},"status_pre_multiplicity":"CANDIDATE_VALIDATED"}
             for p in (.005,.005,.03,.10,.20,.30)]
    holm(results)
    assert results[0]["permutation_placebo"]["holm_adjusted_p_value"]==pytest.approx(.03)
    assert sum(x["status"]=="LOCALLY_VALIDATED" for x in results)==2
