from pathlib import Path

BACKEND = Path("backend/db/migrations/20260825154658_expose_budget_product_strategy_expected_value.sql")
SUPABASE = Path("supabase/migrations/20260825154658_expose_budget_product_strategy_expected_value.sql")
SQL = SUPABASE.read_text(encoding="utf-8").lower()


def test_strategy_ev_is_persisted_and_required_for_new_publications():
    assert "add column expected_value numeric" in SQL
    assert "missing its real strategy expected value" in SQL
    assert "set expected_value = (row->>'expected_value')::numeric" in SQL


def test_internal_tables_remain_private():
    assert "from public, anon, authenticated" in SQL
    assert "grant select" not in SQL
    assert "to anon" not in SQL and "to authenticated" not in SQL


def test_migration_exists_in_both_canonical_locations():
    assert BACKEND.exists() and SUPABASE.exists()
