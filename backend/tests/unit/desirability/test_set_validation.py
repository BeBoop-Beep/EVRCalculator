from backend.desirability.set_validation import (
    alignment_band,
    alignment_score,
    build_opening_set_audit,
    build_validation_rows,
    build_desirability_validation_payload,
    impact_band,
)


def test_alignment_score_uses_rank_gap_over_total_ranked_sets():
    assert alignment_score(2, 7, 20) == 75.0
    assert alignment_score(1, 1, 20) == 100.0
    assert alignment_band(75) == "strong"
    assert alignment_band(60) == "moderate"
    assert alignment_band(40) == "weak"


def test_impact_band_classification():
    assert impact_band(3, 5) == "lift"
    assert impact_band(-3, -5) == "drag"
    assert impact_band(0.2, 0) == "neutral"


def test_desirability_validation_excludes_missing_alignment_fields():
    payload = build_desirability_validation_payload(
        set_id="set-1",
        target_rows=[
            {
                "id": "set-1",
                "name": "Alpha",
                "desirability_score": 90,
                "pack_score": 80,
                "profit_score": 70,
                "safety_score": 60,
                "stability_score": 50,
                "checklistSetValue": 300,
                "top_chase_value": 100,
            },
            {
                "id": "set-2",
                "name": "Beta",
                "desirability_score": 60,
                "pack_score": 85,
                "profit_score": 95,
                "safety_score": 80,
                "stability_score": 75,
                "checklistSetValue": 100,
                "top_chase_value": 20,
            },
        ],
    )

    assert payload["desirability_alignment_score"] is not None
    assert "expected_value" in payload["missing_data_flags"]
    assert payload["strongest_supporting_signal"] in {"Set Value", "Top Chase Value"}
    assert payload["card_appeal_summary"] == "Card appeal validation is not available for this set yet."


def test_card_appeal_validation_uses_card_aliases_when_available():
    payload = build_desirability_validation_payload(
        set_id="set-1",
        set_payload={
            "summary": {
                "desirability_score": 90,
                "pack_score": 80,
                "profit_score": 70,
                "safety_score": 60,
                "stability_score": 50,
            }
        },
        cards_payload={
            "cards": [
                {"cardAppealScore": 88, "currentPrice": 25},
                {"adjusted_card_appeal_score": 78, "market_price": 12},
                {"cardAppealScore": 50, "marketPrice": 0},
            ]
        },
        target_rows=[
            {"id": "set-1", "desirability_score": 90, "pack_score": 80, "profit_score": 70, "safety_score": 60, "stability_score": 50, "top_chase_value": 80},
            {"id": "set-2", "desirability_score": 60, "pack_score": 70, "profit_score": 65, "safety_score": 60, "stability_score": 55, "top_chase_value": 20, "card_appeal_score": 40},
        ],
    )

    assert payload["card_appeal_score"] == 83.0
    assert payload["card_appeal_rank"] == 1
    assert payload["card_appeal_summary"] != "Card appeal validation is not available for this set yet."


def test_validation_preserves_explicit_rip_comparison_fields_for_delta():
    payload = build_desirability_validation_payload(
        set_id="phantasmal-flames",
        set_payload={
            "summary": {
                "rip_score_without_desirability": 10.97,
                "rip_score_with_desirability": 21.13,
                "rip_rank_without_desirability": 27,
                "rip_rank_with_desirability": 20,
                "rip_score_delta": 10.16,
                "rip_rank_delta": 7,
            }
        },
        target_rows=[
            {
                "id": "phantasmal-flames",
                "name": "Phantasmal Flames",
                "rip_score_without_desirability": 10.97,
                "rip_score_with_desirability": 21.13,
                "rip_rank_without_desirability": 27,
                "rip_rank_with_desirability": 20,
                "rip_score_delta": 10.16,
                "rip_rank_delta": 7,
            },
            {
                "id": "other-set",
                "name": "Other Set",
                "profit_score": 80,
                "safety_score": 80,
                "stability_score": 80,
                "pack_score": 80,
            },
        ],
    )

    assert payload["rip_core_score_without_desirability"] == 10.97
    assert payload["final_rip_score_with_desirability"] == 21.13
    assert payload["rip_core_rank_without_desirability"] == 27
    assert payload["final_rip_rank_with_desirability"] == 20
    assert payload["desirability_score_delta"] == 10.16
    assert payload["desirability_rank_delta"] == 7


def test_validation_does_not_recompute_missing_canonical_deltas():
    payload = build_desirability_validation_payload(
        set_id="set-1",
        target_rows=[
            {
                "id": "set-1",
                "rip_score_without_desirability": 10.0,
                "rip_score_with_desirability": 99.0,
                "rip_rank_without_desirability": 1,
                "rip_rank_with_desirability": 9,
            }
        ],
    )

    assert payload["desirability_score_delta"] is None
    assert payload["desirability_rank_delta"] is None


def test_top_hits_do_not_populate_canonical_top_10_card_value():
    payload = build_desirability_validation_payload(
        set_id="set-1",
        set_payload={
            "summary": {"desirability_score": 90, "pack_score": 80},
            "top_hits": [
                {"card_name": "A", "current_near_mint_price": 12.34},
                {"card_name": "B", "current_near_mint_price": 5.66},
            ],
        },
    )

    assert payload["top_10_card_value"] is None
    assert "top_10_card_value" in payload["missing_data_flags"]


def test_subset_rows_are_excluded_unless_mapped_to_opening_set():
    rows = build_validation_rows(
        [
            {"id": "main", "name": "Crown Zenith", "desirability_score": 80, "set_value": 100},
            {"id": "gg", "name": "Crown Zenith Galarian Gallery", "desirability_score": 95, "set_value": 50},
        ]
    )

    assert [row["set_id"] for row in rows] == ["main"]


def test_mapped_subset_value_rolls_up_to_parent_opening_set():
    rows = build_validation_rows(
        [
            {"id": "main", "name": "Brilliant Stars", "desirability_score": 80, "set_value": 100, "top_chase_value": 25},
            {
                "id": "tg",
                "name": "Brilliant Stars Trainer Gallery",
                "is_subset": True,
                "parent_opening_set_id": "main",
                "set_value": 40,
                "top_chase_value": 60,
            },
        ]
    )

    assert len(rows) == 1
    assert rows[0]["set_value"] == 140
    assert rows[0]["top_chase_value"] == 60


def test_opening_set_audit_reports_subset_universe_counts():
    audit = build_opening_set_audit(
        [
            {"id": "main", "name": "Main Set"},
            {"id": "tg", "name": "Main Set Trainer Gallery", "parent_opening_set_id": "main"},
            {"id": "classic", "name": "Classic Collection"},
        ]
    )

    assert audit["total_raw_pokemon_set_rows"] == 3
    assert audit["total_opening_sets"] == 1
    assert audit["total_subset_rows"] == 2
    assert audit["subset_rows_mapped_to_parent_opening_sets"] == 1
    assert audit["subset_rows_missing_parent_mapping"] == 1
    assert audit["sets_whose_combined_card_count_or_value_changes_after_rollup"] == ["main"]


def test_metric_specific_sample_sizes_allow_value_without_simulation():
    payload = build_desirability_validation_payload(
        set_id="value-only",
        target_rows=[
            {"id": "value-only", "desirability_score": 80, "set_value": 100, "pack_cost": 7},
            {"id": "simulated", "desirability_score": 70, "set_value": 90, "mean_value": 5, "p95_value_to_cost_ratio": 2},
        ],
    )

    assert payload["set_value_sample_size"] == 2
    assert payload["pack_cost_sample_size"] == 1
    assert payload["expected_value_sample_size"] == 1
    assert payload["p95_sample_size"] == 1
