import copy

from backend.scripts.research_treatment_direct_preference_analyzer_v1 import (
    DOUBLE,
    SIR,
    ULTRA,
    analyze,
)


def _manifest():
    pairs = []
    triads = []
    for i in range(45):
        era = "Mega Evolution" if i < 21 else "Scarlet and Violet"
        set_name = f"Set {i%19}"
        subject = f"subject:{i}"
        triad = []
        for a, b in ((SIR, DOUBLE), (SIR, ULTRA), (ULTRA, DOUBLE)):
            pid = f"pair-{i}-{a[:2]}-{b[:2]}"
            row = {
                "study_version": "treatment_direct_preference_v1",
                "underlying_pair_id": pid,
                "set_id": f"set-{i}",
                "set_name": set_name,
                "era_name": era,
                "subject_key": subject,
                "treatment_a": a,
                "treatment_b": b,
                "card_a_id": f"a-{pid}",
                "card_b_id": f"b-{pid}",
            }
            pairs.append(row)
            triad.append(row)
        triads.append(triad)
    return {
        "study_subset": {
            "triad_count": 45,
            "pair_count": 135,
            "subject_concentration_gate_le_10pct": True,
            "pairs": pairs,
        }
    }, triads


def _responses(manifest, wins_a=30, wins_b=10, ties=0):
    out = []
    for pair in manifest["study_subset"]["pairs"]:
        n = wins_a + wins_b + ties
        for j in range(n):
            a_left = j % 2 == 0
            if j < wins_a:
                winner = "A"
            elif j < wins_a + wins_b:
                winner = "B"
            else:
                winner = None
            if winner is None:
                response = "TIE"
            elif (winner == "A" and a_left) or (winner == "B" and not a_left):
                response = "LEFT"
            else:
                response = "RIGHT"
            out.append({
                "study_version": "treatment_direct_preference_v1",
                "anonymous_session_id": f"s-{pair['underlying_pair_id']}-{j}",
                "underlying_pair_id": pair["underlying_pair_id"],
                "left_card_id": pair["card_a_id"] if a_left else pair["card_b_id"],
                "right_card_id": pair["card_b_id"] if a_left else pair["card_a_id"],
                "randomized_orientation_receipt": "A_LEFT" if a_left else "B_LEFT",
                "response": response,
                "submitted_at": f"2026-10-03T00:{j%60:02d}:00Z",
            })
    return out


def test_supported_synthetic_preference():
    manifest, _ = _manifest()
    result = analyze(manifest, _responses(manifest, wins_a=30, wins_b=10))
    assert result["decision_token"] == "TREATMENT_DIRECT_PREFERENCE_V1_SUPPORTED"
    assert result["coverage"]["pass"] is True
    assert result["orientation"]["pass"] is True
    assert result["edges"][f"{SIR}__{DOUBLE}"]["supported"] is True
    assert result["production_writes"] == 0


def test_insufficient_collection_coverage():
    manifest, _ = _manifest()
    responses = _responses(manifest, wins_a=30, wins_b=10)
    keep = {
        p["underlying_pair_id"]
        for p in manifest["study_subset"]["pairs"][:30]
    }
    responses = [r for r in responses if r["underlying_pair_id"] in keep]
    result = analyze(manifest, responses)
    assert result["decision_token"] == "TREATMENT_DIRECT_PREFERENCE_V1_INSUFFICIENT_COLLECTION_COVERAGE"
    assert result["coverage"]["pass"] is False


def test_duplicate_session_pair_is_deduped():
    manifest, _ = _manifest()
    responses = _responses(manifest, wins_a=30, wins_b=10)
    duplicate = copy.deepcopy(responses[0])
    duplicate["submitted_at"] = "2026-10-03T23:59:59Z"
    responses.append(duplicate)
    result = analyze(manifest, responses)
    assert result["validation"]["duplicate_rows_removed"] == 1


def test_orientation_receipt_mismatch_is_invalid():
    manifest, _ = _manifest()
    responses = _responses(manifest, wins_a=30, wins_b=10)
    responses[0]["randomized_orientation_receipt"] = "B_LEFT"
    result = analyze(manifest, responses)
    assert result["validation"]["invalid_rows"] == 1
