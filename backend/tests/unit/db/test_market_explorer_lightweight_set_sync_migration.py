from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
NAME = "20260914211525_lightweight_explorer_set_directory_sync.sql"
SUPABASE = ROOT / ".." / "supabase" / "migrations" / NAME
BACKEND = ROOT / "db" / "migrations" / NAME


def test_lightweight_set_sync_migration_is_mirrored_byte_for_byte():
    assert SUPABASE.read_bytes() == BACKEND.read_bytes()


def test_global_set_market_trigger_uses_lightweight_set_directory_sync():
    sql = SUPABASE.read_text(encoding="utf-8")
    assert "sync_pokemon_market_explorer_set_directory_v1" in sql
    assert "PERFORM public.sync_pokemon_market_explorer_set_directory_v1();" in sql
    assert "PERFORM public.refresh_pokemon_market_explorer_prepared_directory_v1();" not in sql
    assert "directorySetCount" in sql
    assert "snapshotSetCount" in sql
    assert "Prepared Explorer Set-directory count mismatch after sync" in sql
