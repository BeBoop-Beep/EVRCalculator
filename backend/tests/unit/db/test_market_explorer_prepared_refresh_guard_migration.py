from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
NAME = "20260918183000_fix_market_explorer_prepared_refresh_guard.sql"
SUPABASE = ROOT / ".." / "supabase" / "migrations" / NAME
BACKEND = ROOT / "db" / "migrations" / NAME


def test_prepared_refresh_guard_migration_is_mirrored_byte_for_byte():
    assert SUPABASE.read_bytes() == BACKEND.read_bytes()


def test_full_refresh_delete_is_guard_compatible():
    sql = SUPABASE.read_text(encoding="utf-8").lower()
    assert "delete from public.pokemon_market_explorer_prepared_directory_v1\n  where market_key is not null;" in sql
    assert "delete from public.pokemon_market_explorer_prepared_directory_v1;" not in sql


def test_exact_date_wrapper_fails_closed_after_transactional_refresh():
    sql = SUPABASE.read_text(encoding="utf-8")
    assert "refresh_pokemon_market_explorer_prepared_directory_if_current_v1" in sql
    assert "v_result := public.refresh_pokemon_market_explorer_prepared_directory_v1();" in sql
    assert "v_comparison_asof is distinct from p_required_market_date" in sql
    assert "Market Explorer prepared generation not current" in sql
