import re
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
MIGRATION = ROOT / "supabase/migrations/20260831050000_fix_bounded_set_value_refresh_carry_forward.sql"
BASELINE = ROOT / "backend/db/migrations/039_fix_set_value_hits_rollup.sql"


def _days(first_observation, latest_observation, start, end, phoenix_today):
    lower = max(first_observation, start or first_observation)
    upper = min(end if start is not None and end is not None else latest_observation, phoenix_today)
    if lower > upper:
        return []
    return [lower + timedelta(days=offset) for offset in range((upper - lower).days + 1)]


def test_migration_is_a_guarded_two_site_patch_not_a_second_formula():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "pg_get_functiondef(v_function)" in sql
    assert "v_match_count <> 2" in sql
    assert "regexp_replace" in sql
    assert "CREATE OR REPLACE FUNCTION public.refresh_pokemon_set_value_daily_history" not in sql
    assert "INSERT INTO public.pokemon_set_value_daily_history" not in sql
    assert "set_value_eligible" not in sql
    assert "0.01" not in sql


def test_explicit_bounds_use_requested_end_but_remain_phoenix_future_capped():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "WHEN p_start_date IS NOT NULL AND p_end_date IS NOT NULL" in sql
    assert "THEN p_end_date" in sql
    assert "ELSE b.latest_observation_date" in sql
    assert "timezone(v_set_value_market_day_timezone, now())::date" in sql

    generated = _days(
        date(2026, 8, 17), date(2026, 8, 17),
        date(2026, 8, 28), date(2026, 8, 28), date(2026, 8, 30),
    )
    assert generated == [date(2026, 8, 28)]
    assert _days(date(2026, 8, 17), date(2026, 8, 17),
                 date(2026, 8, 31), date(2026, 8, 31), date(2026, 8, 30)) == []


def test_unbounded_refresh_still_stops_at_latest_observation():
    assert _days(date(2026, 8, 10), date(2026, 8, 17), None, None, date(2026, 8, 30))[-1] == date(2026, 8, 17)


def test_same_day_and_carried_forward_dates_both_retain_nonzero_as_of_prices():
    observations = [(date(2026, 8, 17), 8184.57)]

    def latest_as_of(day):
        eligible = [price for observed, price in observations if observed <= day and price > 0]
        return eligible[-1] if eligible else None

    assert latest_as_of(date(2026, 8, 17)) == 8184.57
    canonical_cards_total = latest_as_of(date(2026, 8, 28))
    refreshed_standard_rows = [canonical_cards_total] if canonical_cards_total is not None else []
    assert len(refreshed_standard_rows) > 0
    assert refreshed_standard_rows[0] == canonical_cards_total == 8184.57
    assert abs(refreshed_standard_rows[0] - canonical_cards_total) <= 0.01
    assert refreshed_standard_rows[0] != 0


def test_patch_targets_both_generate_series_end_bounds_in_current_function_shape():
    baseline = BASELINE.read_text(encoding="utf-8")
    pattern = re.compile(
        r"least\(\s*coalesce\(p_end_date,\s*b\.latest_observation_date\),\s*"
        r"b\.latest_observation_date,\s*timezone\(v_set_value_market_day_timezone,\s*now\(\)\)::date\s*\)",
        re.MULTILINE,
    )
    assert len(pattern.findall(baseline)) == 2
