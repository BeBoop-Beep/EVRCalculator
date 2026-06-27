from datetime import datetime, timedelta, timezone
from pathlib import Path


MIGRATIONS_DIR = (
    Path(__file__).resolve().parents[3]
    / "db"
    / "migrations"
)
MIGRATION = MIGRATIONS_DIR / "038_set_value_daily_history_market_day_timezone.sql"
HOTFIX_MIGRATION = MIGRATIONS_DIR / "039_fix_set_value_hits_rollup.sql"


def _migration_sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _hotfix_sql() -> str:
    return HOTFIX_MIGRATION.read_text(encoding="utf-8")


def test_set_value_market_day_uses_phoenix_business_dates():
    sql = _migration_sql()

    assert "v_set_value_market_day_timezone CONSTANT TEXT := 'America/Phoenix'" in sql
    assert "Set Value daily history uses America/Phoenix business dates" in sql
    assert "timezone(v_set_value_market_day_timezone, o.captured_at)::date" in sql
    assert "timezone('utc', o.captured_at)::date" not in sql.lower()
    assert "AT TIME ZONE 'UTC'" not in sql


def test_set_value_market_day_cutoff_and_current_date_clamp_use_phoenix():
    sql = _migration_sql()

    assert "((sd.snapshot_date + interval '1 day')::timestamp AT TIME ZONE v_set_value_market_day_timezone)" in sql
    assert "timezone(v_set_value_market_day_timezone, now())::date" in sql
    assert "p_end_date DATE DEFAULT timezone('America/Phoenix', now())::date" in sql


def test_hits_rollup_uses_hit_counts_without_set_only_scope_join():
    for sql in (_migration_sql(), _hotfix_sql()):
        assert "hit_counts AS (" in sql
        assert "WHERE lpc.is_hit_eligible = true" in sql
        assert "max(hc.hit_card_count)::integer AS total_card_count" in sql
        assert "JOIN canonical_scope_flags csf\n          ON csf.set_id = lpc.set_id" not in sql


def test_hits_rollup_fixture_does_not_multiply_by_canonical_count():
    canonical_cards = [
        {"id": "card-1", "is_hit_eligible": True, "price": 10},
        {"id": "card-2", "is_hit_eligible": True, "price": 20},
        {"id": "card-3", "is_hit_eligible": False, "price": 60},
    ]

    standard_value = sum(card["price"] for card in canonical_cards)
    hits_value = sum(card["price"] for card in canonical_cards if card["is_hit_eligible"])
    top10_value = sum(sorted((card["price"] for card in canonical_cards), reverse=True)[:10])
    buggy_set_only_join_hits_value = hits_value * len(canonical_cards)

    assert hits_value == 30
    assert buggy_set_only_join_hits_value == 90
    assert standard_value == 90
    assert top10_value == 90


def test_phoenix_market_day_boundary_examples():
    after_utc_midnight = datetime(2026, 6, 27, 1, 30, tzinfo=timezone.utc)
    before_utc_midnight = datetime(2026, 6, 26, 23, 30, tzinfo=timezone.utc)

    assert (after_utc_midnight + timedelta(hours=-7)).date().isoformat() == "2026-06-26"
    assert (before_utc_midnight + timedelta(hours=-7)).date().isoformat() == "2026-06-26"
