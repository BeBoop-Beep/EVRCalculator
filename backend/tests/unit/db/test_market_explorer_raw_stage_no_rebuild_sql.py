from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MIGRATION = ROOT / "supabase" / "migrations" / "20260929212000_market_explorer_raw_stage_no_rebuild_v1.sql"


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8").lower()


def test_raw_surface_stage_does_not_rebuild_authority():
    sql = _sql()
    assert "refresh_pokemon_market_raw_edition_stable_history_v1(p_market_date)" not in sql
    assert "authorityrefreshinsidestage" in sql
    assert "'authorityrefreshinsidestage',false" in sql


def test_raw_surface_stage_fails_closed_without_current_authority():
    sql = _sql()
    assert "raw_edition_stable_current_date_missing" in sql
    assert "edition_stable_market_identity_chain_v1" in sql


def test_raw_surface_stage_still_reconciles_leaf_count_and_value():
    sql = _sql()
    assert "raw_edition_stable_leaf_count_mismatch" in sql
    assert "raw_edition_stable_leaf_value_mismatch" in sql
    assert "raw_edition_stable_duplicate_instruments" in sql
