from datetime import date
from pathlib import Path

import pytest

from backend.scripts.run_market_microstructure_bucket_b3 import (
    EXPECTED_PROVIDER_IDS,
    HORIZON_CUTOFF,
    HORIZON_DAYS,
    MAX_PASSES,
    MAX_ROWS_PER_CARD_PASS,
    PAGE_SIZE,
    REFERENCE_DATE,
    TOTAL_CREDIT_CAP,
    _days_to_reference,
    _is_horizon_ready,
)


def test_fixed_180_day_reference_contract():
    assert REFERENCE_DATE == date(2026, 9, 29)
    assert HORIZON_DAYS == 180
    assert HORIZON_CUTOFF == date(2026, 4, 2)


@pytest.mark.parametrize(
    "oldest,drained,ready",
    [
        ("2026-04-02", False, True),
        ("2026-04-01", False, True),
        ("2026-04-03", False, False),
        ("2026-08-01", True, True),
        (None, True, True),
        (None, False, False),
    ],
)
def test_horizon_ready_is_fail_closed(oldest, drained, ready):
    assert _is_horizon_ready(oldest_sold_at=oldest, drained=drained) is ready


def test_days_to_reference_is_reference_based_not_span_based():
    assert _days_to_reference("2026-07-11") == 80
    assert _days_to_reference("2026-04-02") == 180
    assert _days_to_reference(None) is None


def test_preregistered_six_provider_identities_are_frozen():
    assert EXPECTED_PROVIDER_IDS == {14359, 24546, 24626, 31828, 34083, 114847}


def test_b3_source_is_page_bounded_and_cannot_start_breadth_backfill():
    path = (
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "run_market_microstructure_bucket_b3.py"
    )
    text = path.read_text(encoding="utf-8")
    assert "ebay_sold_page(" in text
    assert "ebay_sold_collection(" not in text
    assert "graded=None" in text
    assert "PAGE_SIZE = 20" in text
    assert "MAX_ROWS_PER_CARD_PASS = 80" in text
    assert "MAX_PASSES = 5" in text
    assert "TOTAL_CREDIT_CAP = 3000" in text
    assert '"breadth_backfill_started": False' in text
    assert "cards_by_tcgplayer_id" not in text


def test_b3_caps_have_expected_absolute_maximum():
    assert PAGE_SIZE == 20
    assert MAX_ROWS_PER_CARD_PASS == 80
    assert MAX_PASSES == 5
    assert TOTAL_CREDIT_CAP == 3000
    # Six cards x 80 rows x five passes is still beneath the hard provider cap.
    assert len(EXPECTED_PROVIDER_IDS) * MAX_ROWS_PER_CARD_PASS * MAX_PASSES <= TOTAL_CREDIT_CAP
