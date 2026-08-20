from pathlib import Path

MIGRATION = (Path(__file__).resolve().parents[3]
             / "db/migrations/20260820120000_create_pokemon_market_date_quality.sql")


def test_migration_defines_quality_table_and_status_domain():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS public.pokemon_market_date_quality" in sql
    for status in ("READY", "INCOMPLETE", "DEGRADED", "LEGACY_VERIFIED"):
        assert f"'{status}'" in sql
    # Idempotent upsert target used by persist_market_date_quality.
    assert "UNIQUE (tcg, market_date, contract_version)" in sql


def test_migration_is_mirrored_to_supabase():
    mirror = (Path(__file__).resolve().parents[3].parent
              / "supabase/migrations/20260820120000_create_pokemon_market_date_quality.sql")
    assert mirror.read_text(encoding="utf-8") == MIGRATION.read_text(encoding="utf-8")
