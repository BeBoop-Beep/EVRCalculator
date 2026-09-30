from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

from backend.scripts.run_market_microstructure_bucket_b4 import (
    CALIBRATED_MEAN_READY_ROWS,
    DAILY_B_CREDIT_CAP,
    EXPECTED_PANEL_COUNT,
    HORIZON_CUTOFF,
    HORIZON_DAYS,
    FIRST_FULL_C_DATE,
    IDENTITY_LOOKUP_WORST_CASE,
    MAX_ROWS_PER_CARD_DAY,
    PAGE_SIZE,
    ACCOUNT_DAILY_CREDIT_LIMIT,
    ACCOUNT_RESERVE_CREDITS,
    REFERENCE_DATE,
    _breadth_order,
    _can_spend,
    operational_pause_reason,
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


def test_credit_guard_uses_daily_b4_budget_not_request_rate_header():
    assert _can_spend(local_remaining=20, requested=20)
    assert not _can_spend(local_remaining=19, requested=20)


def test_b4_absolute_caps_and_calibration_are_frozen():
    assert PAGE_SIZE == 20
    assert MAX_ROWS_PER_CARD_DAY == 80
    assert ACCOUNT_DAILY_CREDIT_LIMIT == 75000
    assert DAILY_B_CREDIT_CAP == 55000
    assert ACCOUNT_RESERVE_CREDITS == 20000
    assert IDENTITY_LOOKUP_WORST_CASE == 5
    assert CALIBRATED_MEAN_READY_ROWS == 419.8


def test_b4_never_collects_lifetime_phase2_and_observes_c_authority():
    path = (
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "run_market_microstructure_bucket_b4.py"
    )
    text = path.read_text(encoding="utf-8")
    assert '"full_panel_daily") is True' in text
    assert 'int(run.get("target_count") or 0) == EXPECTED_PANEL_COUNT' in text
    assert 'int(run.get("observed_target_count") or 0) == EXPECTED_PANEL_COUNT' in text
    assert "C_CONTINUITY_WINDOW" in text
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


def test_b4_vm_schedule_yields_to_c_and_uses_shared_locks():
    root = Path(__file__).resolve().parents[4]
    cron = (root / "infra/oracle/market-microstructure-b4.crontab").read_text(encoding="utf-8")
    runner = (root / "infra/oracle/run_market_microstructure_bucket_b4.sh").read_text(encoding="utf-8")
    installer = (root / "infra/oracle/install_market_microstructure_bucket_b4_cron.sh").read_text(encoding="utf-8")

    assert "CRON_TZ=America/Phoenix" in cron
    assert "*/15 * * * *" in cron
    assert "/bin/bash" in cron
    assert "/tmp/active-supply-panel.lock" in runner
    assert "/tmp/pokemon-scrape-dispatcher.lock" in runner
    assert "/tmp/pkmnprices-api.lock" in runner
    assert "/tmp/pokemon-post-scrape-publication.lock" in runner
    assert "/home/ubuntu/state/db-safety/hold.json" in runner
    assert "--credit-cap 55000" in runner
    assert "worktree add --detach" in installer
    assert "VERIFY ONLY" in installer


def test_b4_pause_windows_prioritize_c_and_daily_scraper(monkeypatch):
    assert FIRST_FULL_C_DATE == date(2026, 9, 30)

    import backend.scripts.run_market_microstructure_bucket_b4 as b4

    monkeypatch.setattr(
        b4,
        "_scrape_batch_state",
        lambda db, expected_date: {"id": 67, "status": "complete"},
    )
    assert operational_pause_reason(
        object(), now_local=datetime(2026, 9, 29, 21, 43)
    ) is None
    assert operational_pause_reason(
        object(), now_local=datetime(2026, 9, 30, 20, 55)
    )["reason"] == "C_CONTINUITY_WINDOW"

    # Before the scrape window begins, no batch is required.
    assert operational_pause_reason(
        object(), now_local=datetime(2026, 9, 30, 0, 54)
    ) is None

    monkeypatch.setattr(b4, "_scrape_batch_state", lambda db, expected_date: None)
    assert operational_pause_reason(
        object(), now_local=datetime(2026, 9, 30, 0, 55)
    )["reason"] == "SCRAPE_BATCH_NOT_READY"

    monkeypatch.setattr(
        b4,
        "_scrape_batch_state",
        lambda db, expected_date: {"id": 68, "status": "running"},
    )
    assert operational_pause_reason(
        object(), now_local=datetime(2026, 9, 30, 1, 30)
    )["reason"] == "SCRAPE_BATCH_ACTIVE"

    monkeypatch.setattr(
        b4,
        "_scrape_batch_state",
        lambda db, expected_date: {"id": 68, "status": "complete"},
    )
    assert operational_pause_reason(
        object(), now_local=datetime(2026, 9, 30, 2, 30)
    ) is None


def test_b4_credit_day_is_shared_across_retry_invocations():
    path = (
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "run_market_microstructure_bucket_b4.py"
    )
    text = path.read_text(encoding="utf-8")
    assert "def _daily_b4_credits_used" in text
    assert "prior_b4_credits_today" in text
    assert "invocation_credit_cap = max(0, credit_cap - prior_b4_credits)" in text
    assert "min_request_interval=0.55" in text
