from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NAME = "20261001211000_market_explorer_candidate_runtime_budget_v1.sql"
SUPABASE = ROOT.parent / "supabase" / "migrations" / NAME
BACKEND = ROOT / "db" / "migrations" / NAME

def test_migration_mirrors_match():
    assert SUPABASE.read_bytes() == BACKEND.read_bytes()

def test_only_candidate_builder_budget_is_changed():
    sql = SUPABASE.read_text(encoding="utf-8").lower()
    assert "alter function public.build_pokemon_market_explorer_surface_candidate_v2(uuid,date,text)" in sql
    assert "set statement_timeout='600s'" in sql
    assert "alter role" not in sql
    assert "alter database" not in sql
    assert "get_pokemon_market_explorer" not in sql
