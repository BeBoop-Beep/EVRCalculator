from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
NAME = "20260918190500_add_top_chase_set_updated_at_index.sql"
SUPABASE = ROOT / ".." / "supabase" / "migrations" / NAME
BACKEND = ROOT / "db" / "migrations" / NAME


def test_top_chase_index_migration_is_mirrored_byte_for_byte():
    assert SUPABASE.read_bytes() == BACKEND.read_bytes()


def test_top_chase_index_matches_production_freshness_query():
    sql = SUPABASE.read_text(encoding="utf-8").lower()
    assert "create index concurrently if not exists" in sql
    assert "pokemon_set_top_chase_card_daily_history (set_id, updated_at desc)" in sql
    assert "begin;" not in sql
    assert "commit;" not in sql
