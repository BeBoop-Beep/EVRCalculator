"""Static contract for concurrent prepared-constituent staging hardening."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
NAME = "20260924010000_serialize_prepared_constituent_staging.sql"
BACK = ROOT / "backend" / "db" / "migrations" / NAME
SUPA = ROOT / "supabase" / "migrations" / NAME
SQL = BACK.read_text(encoding="utf-8")


def test_both_migration_trees_are_identical():
    assert SUPA.read_text(encoding="utf-8") == SQL


def test_generation_scoped_advisory_lock_is_in_stage_and_publisher():
    assert SQL.count("pg_advisory_xact_lock(hashtext(p_generation_id::text), 17341)") >= 1
    assert SQL.count("pg_advisory_xact_lock(hashtext(v_generation::text), 17341)") >= 2


def test_publisher_rechecks_totals_under_lock_before_staging():
    wrapper = SQL.split("run_market_explorer_guarded_publisher_v1(p_required_market_date date)")[1]
    lock = wrapper.index("pg_advisory_xact_lock(hashtext(v_generation::text), 17341)")
    check = wrapper.index("if not exists (select 1 from public.pokemon_market_explorer_prepared_constituent_totals_v1", lock)
    stage = wrapper.index("stage_pokemon_market_explorer_prepared_constituents_v1(v_generation)", check)
    assert lock < check < stage


def test_forward_migration_preserves_existing_authority_contract():
    assert "create or replace function public.stage_pokemon_market_explorer_prepared_constituents_v1" in SQL
    assert "create or replace function public.run_market_explorer_guarded_publisher_v1" in SQL
    assert "get_pokemon_cards_daily_constituents(array[d.set_id]" in SQL
    assert "'already_current'" in SQL
    assert "PREPARED_CONSTITUENT_VALIDATION_FAILED" in SQL
