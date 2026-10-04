from __future__ import annotations

from uuid import uuid4

import pytest

from backend.domain.pokemon import treatment_preference_v1 as tp


class _Exec:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self


class FakeDB:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def rpc(self, name, args):
        self.calls.append((name, args))
        return _Exec(self.responses.pop(0))


def _authority():
    questions = []
    pairs = {}
    for i in range(12):
        pair_id = f"{i:024d}"
        a_id = str(uuid4())
        b_id = str(uuid4())
        orientation = "A_LEFT" if i % 2 == 0 else "B_LEFT"
        questions.append(
            {
                "underlying_pair_id": pair_id,
                "set_id": str(uuid4()),
                "subject_key": f"pokemon:test:{i}",
                "left_card_id": a_id if orientation == "A_LEFT" else b_id,
                "right_card_id": b_id if orientation == "A_LEFT" else a_id,
                "left_image_url": f"https://images.example/{i}/left",
                "right_image_url": f"https://images.example/{i}/right",
                "randomized_orientation_receipt": orientation,
            }
        )
        pairs[pair_id] = {
            "underlying_pair_id": pair_id,
            "treatment_a": "Special Illustration Rare",
            "treatment_b": "Double Rare",
        }
    block = {"block_id": "a" * 24, "block_index": 0, "questions": questions}
    return {
        "schedule": {"blocks": [block]},
        "block_by_id": {block["block_id"]: block},
        "pair_by_id": pairs,
    }


def test_claim_payload_is_blinded(monkeypatch):
    authority = _authority()
    monkeypatch.setattr(tp, "runtime_authority", lambda db: authority)
    token = str(uuid4())
    db = FakeDB([[{"block_index": 0, "claim_token": token, "already_completed": False}]])

    result = tp.claim_block(db, str(uuid4()))

    assert result["status"] == "ready"
    assert result["claimToken"] == token
    assert result["questionCount"] == 12
    assert len(result["questions"]) == 12
    for question in result["questions"]:
        assert set(question) == {"pairId", "leftImageUrl", "rightImageUrl"}
        assert "treatment" not in str(question).lower()
        assert "card" not in str(question).lower()


def test_completed_session_does_not_receive_another_block(monkeypatch):
    monkeypatch.setattr(tp, "runtime_authority", lambda db: _authority())
    db = FakeDB([[{"block_index": 0, "claim_token": str(uuid4()), "already_completed": True}]])

    result = tp.claim_block(db, str(uuid4()))

    assert result["status"] == "submitted"
    assert "questions" not in result


def test_submit_reconstructs_hidden_fields_server_side(monkeypatch):
    authority = _authority()
    monkeypatch.setattr(tp, "runtime_authority", lambda db: authority)
    db = FakeDB([[{"accepted_responses": 12, "already_completed": False}]])
    answers = [
        {"pairId": q["underlying_pair_id"], "response": "LEFT" if i % 3 == 0 else "TIE"}
        for i, q in enumerate(authority["schedule"]["blocks"][0]["questions"])
    ]

    result = tp.submit_block(
        db,
        session_id=str(uuid4()),
        block_id="a" * 24,
        claim_token=str(uuid4()),
        answers=answers,
    )

    assert result["status"] == "submitted"
    assert result["acceptedResponses"] == 12
    name, payload = db.calls[-1]
    assert name == "submit_pokemon_treatment_preference_v1_block"
    rows = payload["p_responses"]
    assert len(rows) == 12
    assert {row["response"] for row in rows} <= {"LEFT", "RIGHT", "TIE"}
    assert all(row["randomized_orientation_receipt"] in {"A_LEFT", "B_LEFT"} for row in rows)
    assert all(row["left_treatment"] and row["right_treatment"] for row in rows)


def test_submit_rejects_pair_set_mismatch(monkeypatch):
    authority = _authority()
    monkeypatch.setattr(tp, "runtime_authority", lambda db: authority)
    answers = [
        {"pairId": q["underlying_pair_id"], "response": "LEFT"}
        for q in authority["schedule"]["blocks"][0]["questions"]
    ]
    answers[-1]["pairId"] = "z" * 24

    with pytest.raises(tp.TreatmentPreferenceV1Error) as exc:
        tp.submit_block(
            FakeDB([]),
            session_id=str(uuid4()),
            block_id="a" * 24,
            claim_token=str(uuid4()),
            answers=answers,
        )
    assert exc.value.code == "TREATMENT_PREFERENCE_PAIR_SET_MISMATCH"


def test_session_id_must_be_uuid(monkeypatch):
    monkeypatch.setattr(tp, "runtime_authority", lambda db: _authority())
    with pytest.raises(tp.TreatmentPreferenceV1Error) as exc:
        tp.claim_block(FakeDB([]), "not-a-session")
    assert exc.value.code == "TREATMENT_PREFERENCE_SESSION_INVALID"


def test_frozen_authority_constants():
    assert tp.EXPECTED_MANIFEST_FINGERPRINT == "c8777261004c08f011407019819e1a02c58ca5db0f54fd110d20186618cf8c55"
    assert tp.EXPECTED_SCHEDULE_FINGERPRINT == "4b08be6bd2fe4c3b1dde4627da0780f3832740c53ee411c7df81a2f976830055"
    assert tp.EXPECTED_TRIADS == 45
    assert tp.EXPECTED_PAIRS == 135
    assert tp.EXPECTED_BLOCKS == 450



def test_question_order_is_session_randomized_and_resumable():
    authority = _authority()
    block = authority["schedule"]["blocks"][0]
    hash_a = "a" * 64
    hash_b = "b" * 64

    first = tp._ordered_questions(block, hash_a)
    resumed = tp._ordered_questions(block, hash_a)
    other = tp._ordered_questions(block, hash_b)

    original_ids = {q["underlying_pair_id"] for q in block["questions"]}
    assert [q["underlying_pair_id"] for q in first] == [
        q["underlying_pair_id"] for q in resumed
    ]
    assert {q["underlying_pair_id"] for q in first} == original_ids
    assert {q["underlying_pair_id"] for q in other} == original_ids
    assert [q["underlying_pair_id"] for q in first] != [
        q["underlying_pair_id"] for q in other
    ]
    assert tp.QUESTION_ORDER_VERSION == "treatment_direct_preference_v1_question_order_v1"
