from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NAME = "20261001211500_market_explorer_rarity_runtime_budget_v2.sql"
SUPABASE = ROOT.parent / "supabase" / "migrations" / NAME
BACKEND = ROOT / "db" / "migrations" / NAME

def test_migration_mirrors_match():
    assert SUPABASE.read_bytes() == BACKEND.read_bytes()

def test_only_rarity_writer_budget_changes():
    sql = SUPABASE.read_text(encoding="utf-8").lower()
    assert "alter function public.stage_pokemon_market_explorer_rarity_candidates_v2(uuid,date)" in sql
    assert "set statement_timeout='600s'" in sql
    assert "build_pokemon_market_explorer_surface_candidate_v2" not in sql
    assert "alter role" not in sql
    assert "alter database" not in sql
