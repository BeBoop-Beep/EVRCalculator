from datetime import date
from pathlib import Path
from types import SimpleNamespace

from backend.scripts.run_market_microstructure_bucket_b4 import (
    CALIBRATED_MEAN_READY_ROWS,
    DAILY_B_CREDIT_CAP,
    EXPECTED_PANEL_COUNT,
    HORIZON_CUTOFF,
    HORIZON_DAYS,
    IDENTITY_LOOKUP_WORST_CASE,
    MAX_ROWS_PER_CARD_DAY,
    PAGE_SIZE,
    PROVIDER_REMAINING_FLOOR,
    REFERENCE_DATE,
    _breadth_order,
    _can_spend,
    _horizon_ready,
)


def test_phase1_reference_contract_is_frozen():
    assert REFERENCE_DATE == date(2026, 9, 29)
    assert HORIZON_DAYS == 180
    assert HORIZON_CUTOFF == date(2026, 4, 2)
    assert EXPECTED_PANEL_COUNT == 207


def test_phase1_ready_stops_at_horizon_or_provider_drain():
    assert _horizon_ready("2026-04-02", drained=False) == (True, "HORIZON_180D")
    assert _horizon_ready("2026-03-31", drained=False) == (True, "HORIZON_180D")
    assert _horizon_ready("2026-04-03", drained=False) == (False, None)
    assert _horizon_ready("2026-08-01", drained=True) == (True, "PROVIDER_DRAINED")


def test_breadth_order_prioritizes_least_depth_then_panel_order():
    states = [
        {"phase1_ready": False, "rows_seen": 80, "panel_index": 0},
        {"phase1_ready": False, "rows_seen": 0, "panel_index": 2},
        {"phase1_ready": False, "rows_seen": 0, "panel_index": 1},
        {"phase1_ready": True, "rows_seen": 20, "panel_index": 3},
    ]
    ordered = _breadth_order(states)
    assert [(x["rows_seen"], x["panel_index"]) for x in ordered] == [
        (0, 1), (0, 2), (80, 0)
    ]


def test_credit_and_provider_reserve_guard_is_fail_closed():
    provider = SimpleNamespace(rate_remaining=None)
    assert _can_spend(provider, local_remaining=20, requested=20)
    assert not _can_spend(provider, local_remaining=19, requested=20)

    provider.rate_remaining = PROVIDER_REMAINING_FLOOR + 20
    assert _can_spend(provider, local_remaining=100, requested=20)
    provider.rate_remaining = PROVIDER_REMAINING_FLOOR + 19
    assert not _can_spend(provider, local_remaining=100, requested=20)


def test_b4_absolute_caps_and_calibration_are_frozen():
    assert PAGE_SIZE == 20
    assert MAX_ROWS_PER_CARD_DAY == 80
    assert DAILY_B_CREDIT_CAP == 8000
    assert IDENTITY_LOOKUP_WORST_CASE == 5
    assert CALIBRATED_MEAN_READY_ROWS == 419.8


def test_b4_source_requires_c_gate_and_never_collects_lifetime_phase2():
    path = (
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "run_market_microstructure_bucket_b4.py"
    )
    text = path.read_text(encoding="utf-8")
    assert '"full_panel_daily") is True' in text
    assert 'int(run.get("target_count") or 0) == EXPECTED_PANEL_COUNT' in text
    assert 'int(run.get("observed_target_count") or 0) == EXPECTED_PANEL_COUNT' in text
    assert 'if not gate["ready"]' in text
    assert '"provider_credits_used": 0' in text
    assert '"database_writes": 0' in text
    assert '"phase2_lifetime_archival": False' in text


def test_b4_uses_page_level_slices_and_exact_identity_reuse():
    path = (
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "run_market_microstructure_bucket_b4.py"
    )
    text = path.read_text(encoding="utf-8")
    assert "ebay_sold_page(" in text
    assert "ebay_sold_collection(" not in text
    assert "graded=None" in text
    assert "cards_by_tcgplayer_id" in text
    assert "PHASE1_CACHED_IDENTITY_MISMATCH" in text
    assert "MAX_ROWS_PER_CARD_DAY = 80" in text


def test_b4_batches_identity_and_sync_state_reads():
    path = (
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "run_market_microstructure_bucket_b4.py"
    )
    text = path.read_text(encoding="utf-8")
    assert 'def _paged_rows(' in text
    assert '"pkmnprices_card_identity_v1"' in text
    assert '"pkmnprices_sold_sync_state_v1"' in text
    assert "phase1_reference_date" in text
    assert "phase1_oldest_sold_at" in text
