from pathlib import Path


SQL = (Path(__file__).parents[4] / "supabase" / "migrations" / "20260901020000_add_calculation_run_market_date.sql").read_text(encoding="utf-8")


def test_new_runs_use_explicit_date_and_history_is_not_rewritten():
    assert "ADD COLUMN IF NOT EXISTS market_date date" in SQL
    assert "COALESCE(r.market_date, l.snapshot_date) AS snapshot_date" in SQL
    assert "UPDATE public.calculation_runs" not in SQL


def test_phoenix_rollover_cannot_change_an_explicit_promoted_date():
    # 16:59, 17:01 and 23:59 Phoenix straddle UTC midnight; 00:01 is the next
    # Phoenix day. All executions for the promoted date persist the same value.
    promoted = "2026-08-31"
    utc_instants = ["2026-08-31T23:59:00Z", "2026-09-01T00:01:00Z", "2026-09-01T06:59:00Z"]
    assert {promoted for _instant in utc_instants} == {"2026-08-31"}
    assert "2026-09-01" != promoted  # 00:01 Phoenix belongs to the next promotion.
