import pytest

from backend.db.services.rip_desirability_comparison import (
    build_rip_desirability_comparison_payload,
    calculate_rip_score_with_desirability,
    calculate_rip_score_without_desirability,
)


def test_score_with_desirability_uses_current_four_pillar_formula():
    row = {
        "profit_score": 90.0,
        "safety_score": 80.0,
        "desirability_score": 20.0,
        "stability_score": 70.0,
    }

    assert calculate_rip_score_with_desirability(row) == pytest.approx(71.5)


def test_score_without_desirability_renormalizes_financial_pillars():
    row = {
        "profit_score": 90.0,
        "safety_score": 80.0,
        "desirability_score": 0.0,
        "stability_score": 70.0,
    }

    assert calculate_rip_score_without_desirability(row) == pytest.approx(84.38)


def test_rank_delta_identifies_lift_drag_and_minimal_impact():
    payload = build_rip_desirability_comparison_payload(
        [
            {
                "target_id": "financial-leader",
                "profit_score": 90.0,
                "safety_score": 80.0,
                "stability_score": 70.0,
                "desirability_score": 20.0,
            },
            {
                "target_id": "desirability-leader",
                "profit_score": 70.0,
                "safety_score": 70.0,
                "stability_score": 70.0,
                "desirability_score": 100.0,
            },
            {
                "target_id": "balanced",
                "profit_score": 75.0,
                "safety_score": 75.0,
                "stability_score": 75.0,
                "desirability_score": 75.0,
            },
        ]
    )

    rows = {row["target_id"]: row for row in payload["rows"]}
    assert rows["desirability-leader"]["rip_rank_without_desirability"] == 3
    assert rows["desirability-leader"]["rip_rank_with_desirability"] == 1
    assert rows["desirability-leader"]["rip_rank_delta"] == 2
    assert rows["desirability-leader"]["rip_desirability_impact_label"] == "Rank lift"
    assert rows["financial-leader"]["rip_rank_delta"] == -2
    assert rows["financial-leader"]["rip_desirability_impact_label"] == "Rank drag"
    assert rows["balanced"]["rip_rank_delta"] == 0
    assert rows["balanced"]["rip_desirability_impact_label"] == "Minimal impact"
    assert payload["diagnostics"]["raises_rank_count"] == 1
    assert payload["diagnostics"]["lowers_rank_count"] == 1
    assert payload["diagnostics"]["minimal_impact_count"] == 1


def test_missing_desirability_keeps_financial_score_but_no_with_score_or_delta():
    payload = build_rip_desirability_comparison_payload(
        [
            {
                "target_id": "missing",
                "profit_score": 80.0,
                "safety_score": 70.0,
                "stability_score": 60.0,
                "desirability_score": None,
            },
            {
                "target_id": "valid",
                "profit_score": 70.0,
                "safety_score": 70.0,
                "stability_score": 70.0,
                "desirability_score": 70.0,
            },
        ]
    )

    missing = {row["target_id"]: row for row in payload["rows"]}["missing"]
    assert missing["rip_score_without_desirability"] == pytest.approx(74.38)
    assert missing["rip_score_with_desirability"] is None
    assert missing["rip_score_delta"] is None
    assert missing["rip_rank_with_desirability"] is None
    assert missing["rip_rank_delta"] is None
    assert missing["desirability_component_score"] is None
    assert missing["rip_desirability_impact_label"] == "Missing desirability"
    assert payload["diagnostics"]["missing_desirability_count"] == 1


def test_existing_rip_score_fields_are_not_mutated():
    rows = [
        {
            "target_id": "set-1",
            "pack_score": 88.8,
            "relative_pack_score": 91.2,
            "pack_rank": 4,
            "profit_score": 80.0,
            "safety_score": 75.0,
            "stability_score": 70.0,
            "desirability_score": 65.0,
        }
    ]

    payload = build_rip_desirability_comparison_payload(rows)

    assert rows[0]["pack_score"] == 88.8
    assert rows[0]["relative_pack_score"] == 91.2
    assert rows[0]["pack_rank"] == 4
    enriched = payload["rows"][0]
    assert enriched["pack_score"] == 88.8
    assert enriched["relative_pack_score"] == 91.2
    assert enriched["pack_rank"] == 4
