from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NAME = "20261001201500_market_explorer_rarity_nested_timeout_v1.sql"
SUPABASE = ROOT.parent / "supabase" / "migrations" / NAME
BACKEND = ROOT / "db" / "migrations" / NAME


def test_migration_mirrors_match():
    assert SUPABASE.read_bytes() == BACKEND.read_bytes()


def test_nested_rarity_timeout_matches_candidate_publication_budget():
    sql = SUPABASE.read_text(encoding="utf-8").lower()
    assert "alter function public.stage_pokemon_market_explorer_rarity_candidates_v2(uuid,date)" in sql
    assert "set statement_timeout='300s'" in sql
    assert "drop function" not in sql
