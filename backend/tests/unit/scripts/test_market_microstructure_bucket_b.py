from datetime import date

import pytest

from backend.scripts.run_market_microstructure_bucket_b import (
    PANEL_FINGERPRINT, combined_stream_semantics, load_panel, preflight,
    select_smoke_rows, summarize,
)


def test_preflight_is_zero_credit_and_preserves_frozen_panel():
    result = preflight(card_limit=10, credit_cap=1000, max_items_per_card=80)
    assert result["status"] == "PREFLIGHT_OK"
    assert result["panel_fingerprint"] == PANEL_FINGERPRINT
    assert result["panel_card_count"] == 207
    assert result["selected_card_count"] == 10
    assert result["provider_requests"] == result["provider_credits_used"] == 0
    assert result["database_writes"] == 0
    assert result["combined_stream_graded_parameter"] is None
    assert result["set_value_authority_unchanged"] is True


def test_smoke_caps_cannot_exceed_issue_bounds():
    with pytest.raises(ValueError):
        preflight(card_limit=11, credit_cap=1000, max_items_per_card=1)
    with pytest.raises(ValueError):
        preflight(card_limit=10, credit_cap=1001, max_items_per_card=1)


def test_smoke_selection_is_deterministic_and_stratified():
    rows = load_panel()["rows"]
    first = select_smoke_rows(rows, 10)
    assert first == select_smoke_rows(rows, 10)
    assert len({row["price_band"] for row in first}) == 7
    assert len({row["era"] for row in first}) == 2
    second = select_smoke_rows(rows, 10, 10)
    assert not {row["canonical_card_id"] for row in first} & {
        row["canonical_card_id"] for row in second
    }


class FakeProvider:
    def ebay_sold_collection(self, provider_card_id, *, graded, max_items):
        raw = {"id": 1, "grader": None, "grade": None, "grade_qualifier": None}
        slab = {"id": 2, "grader": "CGC", "grade": "10", "grade_qualifier": "Pristine"}
        values = [raw, slab] if graded is None else ([slab] if graded else [raw])
        return {"rows": values, "has_more": False, "next_cursor": None}


def test_combined_stream_proves_raw_and_graded_with_qualifier():
    result = combined_stream_semantics(FakeProvider(), 7)
    assert result["safe_for_single_cursor"] is True
    assert result["qualifier_field_preserved"] is True
    assert result["control_union_overlap_count"] == 2


def test_summary_contains_required_zero_credit_statistics():
    rows = [
        {"sold_at": "2026-09-20", "price": "10", "graded": False,
         "grader": None, "grade": None, "grade_qualifier": None},
        {"sold_at": "2026-09-25", "price": "20", "graded": True,
         "grader": "PSA", "grade": "10", "grade_qualifier": None},
    ]
    out = summarize(rows, today=date(2026, 9, 29))
    assert out["transaction_count"] == 2 and out["transaction_days"] == 2
    assert out["count_7d"] == 1 and out["count_30d"] == 2
    assert out["median_days_between_sales"] == 5
    assert out["median_price"] == "15"
    assert out["mad_price"] == "5"
    assert out["raw_count"] == out["graded_count"] == 1
