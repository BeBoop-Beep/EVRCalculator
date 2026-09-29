import pytest
from pathlib import Path

from backend.scripts.run_market_microstructure_bucket_b2 import (
    _cursor_hash, validate_limits,
)


def test_calibration_limits_enforce_issue_caps():
    validate_limits(slice_count=3, subrun_credit_cap=1000, items_per_card=80)
    for kwargs in (
        {"slice_count": 4, "subrun_credit_cap": 1000, "items_per_card": 80},
        {"slice_count": 3, "subrun_credit_cap": 1001, "items_per_card": 80},
        {"slice_count": 3, "subrun_credit_cap": 1000, "items_per_card": 81},
    ):
        with pytest.raises(ValueError):
            validate_limits(**kwargs)


def test_cursor_proof_is_stable_without_disclosing_cursor():
    assert _cursor_hash("opaque-cursor") == _cursor_hash("opaque-cursor")
    assert _cursor_hash("opaque-cursor") != _cursor_hash("different")
    assert _cursor_hash(None) is None


def test_calibration_source_cannot_restart_or_expand_to_breadth():
    text = (Path(__file__).resolve().parents[3] / "scripts" /
            "run_market_microstructure_bucket_b2.py").read_text(encoding="utf-8")
    assert 'initial_cursor=str(cursor)' in text
    assert 'SMOKE_RUN_ID = "5c951f67-135d-4665-bd5a-e8b733480aea"' in text
    assert "CARD_COUNT = 10" in text and "ITEMS_PER_CARD = 80" in text
    assert "TOTAL_CREDIT_CAP = 3000" in text and "MAX_SLICES = 3" in text
    assert "cards_by_tcgplayer_id" not in text
