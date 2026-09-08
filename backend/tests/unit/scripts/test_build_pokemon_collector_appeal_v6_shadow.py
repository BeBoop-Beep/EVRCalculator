from backend.scripts.build_pokemon_collector_appeal_v6_shadow import FPS, payloads


def test_frozen_payload_shape_and_formula_contract():
    cards, d_rows, appeal_rows = payloads("00000000-0000-0000-0000-000000000001")
    assert (len(cards), len(d_rows), len(appeal_rows)) == (18293, 128, 128)
    assert sum(row["score_status"] == "scored" for row in appeal_rows) == 22
    assert sum(row["score_status"] == "unavailable" for row in appeal_rows) == 106
    assert all(row["collector_appeal_score"] is None for row in appeal_rows if row["score_status"] == "unavailable")
    assert all(abs(row["collector_appeal_score"] - max(0, min(100, row["collector_roster_desirability_score"] + row["frequency_modifier_points"]))) < 1e-9 for row in appeal_rows if row["score_status"] == "scored")
    assert all(row["lineage_json"]["c5Fingerprint"] == FPS["c5Fingerprint"] for row in appeal_rows)


def test_artist_treatment_energy_and_market_inputs_are_disabled():
    cards, _, appeal_rows = payloads("00000000-0000-0000-0000-000000000001")
    assert all(row["artist_recognition_score"] is None and row["artist_lift"] == 0 for row in cards)
    assert all(row["price_input_excluded"] and row["treatment_input_excluded"] and row["hit_eligibility_independent"] for row in cards)
    assert all("Dual-Path Depth" in row["component_inputs_json"]["excludedInputs"] for row in appeal_rows)
