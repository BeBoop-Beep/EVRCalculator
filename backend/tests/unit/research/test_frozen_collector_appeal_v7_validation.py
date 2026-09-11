import pytest

from backend.scripts.validate_frozen_collector_appeal_v7 import (
    CARD_FINGERPRINT, MODEL_FINGERPRINT, MODEL_VERSION, SET_FINGERPRINT,
    matched_analysis, raw_within_set, verify_frozen_artifact,
)


def frozen_payload():
    return {"manifest": {"modelVersion": MODEL_VERSION, "modelFingerprint": MODEL_FINGERPRINT,
            "cardFingerprint": CARD_FINGERPRINT, "setFingerprint": SET_FINGERPRINT,
            "config": {"marketValueInput": "excluded"}},
            "cards": [{"canonical_card_id": str(i)} for i in range(18293)], "sets": []}


def test_freeze_verification_rejects_changed_fingerprint():
    payload = frozen_payload(); payload["manifest"]["cardFingerprint"] = "changed"
    with pytest.raises(RuntimeError, match="V7_VALIDATION_MODEL_MUTATION_BLOCKER"):
        verify_frozen_artifact(payload)


def test_within_set_and_matching_are_set_scoped():
    rows = [{"set_id": "s", "set_name": "S", "era": "E", "card_appeal_v7": i*10,
             "market_price": i+1, "log_price": i, "rarity_key": "r", "slot_group": "x",
             "is_secret": 0, "is_promo": 0, "is_mechanic_card": 0, "pull_scarcity": 1.0}
            for i in range(1, 9)]
    assert raw_within_set(rows, "card_appeal_v7")["summary"]["medianRho"] == pytest.approx(1.0)
    assert matched_analysis(rows)["pairCount"] == 1
