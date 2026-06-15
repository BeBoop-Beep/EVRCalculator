import json

from backend.desirability.opening_desirability_presenter import present_opening_desirability


def test_public_labels_map_to_internal_scores_and_ranks():
    public = present_opening_desirability(
        {
            "primary_rip_desirability_score": 79.5,
            "rip_desirability_rank_70_30": 2,
            "pure_desirability_score": 91.1,
            "pure_desirability_rank": 1,
            "monetary_chase_appeal_score": 52.6,
            "monetary_chase_appeal_rank": 7,
            "monetary_data_quality": "usable",
        }
    )

    assert public["opening_desirability_score"] == 79.5
    assert public["opening_desirability_rank"] == 2
    assert public["collector_appeal_score"] == 91.1
    assert public["collector_appeal_rank"] == 1
    assert public["chase_appeal_score"] == 52.6
    assert public["chase_appeal_rank"] == 7
    assert public["chase_appeal_data_quality"] == "usable"
    assert public["display_status"] == "scored"


def test_public_payload_does_not_expose_formula_weights_or_blend_name():
    public = present_opening_desirability(
        {
            "primary_rip_desirability_score": 79.5,
            "pure_desirability_score": 91.1,
            "monetary_chase_appeal_score": 52.6,
            "monetary_data_quality": "usable",
        }
    )
    serialized = json.dumps(public).lower()

    assert "formula" not in serialized
    assert "weight" not in serialized
    assert "70/30" not in serialized


def test_missing_chase_appeal_returns_collector_only_payload():
    public = present_opening_desirability(
        {
            "primary_rip_desirability_score": None,
            "pure_desirability_score": 79.2,
            "pure_desirability_rank": 4,
            "monetary_chase_appeal_score": None,
            "monetary_chase_appeal_rank": None,
            "monetary_data_quality": "missing",
        }
    )

    assert public["opening_desirability_score"] is None
    assert public["opening_desirability_rank"] is None
    assert public["collector_appeal_score"] == 79.2
    assert public["collector_appeal_rank"] == 4
    assert public["chase_appeal_score"] is None
    assert public["chase_appeal_rank"] is None
    assert public["chase_appeal_data_quality"] == "missing"
    assert public["display_status"] == "collector_only"
    assert "Collector Appeal is available" in public["summary"]


def test_usable_chase_appeal_produces_scored_payload_with_public_copy():
    public = present_opening_desirability(
        {
            "rip_desirability_score_70_30": 62.5,
            "rip_desirability_rank_70_30": 12,
            "pure_desirability_score": 70.0,
            "pure_desirability_rank": 20,
            "monetary_chase_appeal_score": 45.0,
            "monetary_chase_appeal_rank": 18,
            "monetary_data_quality": "partial",
        }
    )

    assert public["display_status"] == "scored"
    assert public["opening_desirability_score"] == 62.5
    assert public["chase_appeal_data_quality"] == "partial"
    assert "Opening Desirability estimates" in public["tooltip_copy"]["opening_desirability"]
    assert "independent of market price" in public["tooltip_copy"]["collector_appeal"]
    assert "meaningful chase cards" in public["tooltip_copy"]["chase_appeal"]


def test_public_copy_does_not_make_collector_appeal_price_driven():
    public = present_opening_desirability(
        {
            "pure_desirability_score": 80,
            "monetary_chase_appeal_score": None,
            "monetary_data_quality": "missing",
        }
    )

    collector_copy = public["tooltip_copy"]["collector_appeal"].lower()
    assert "independent of market price" in collector_copy
    assert "price-driven" not in collector_copy
