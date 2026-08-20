from pathlib import Path

MIGRATION = (Path(__file__).resolve().parents[3]
             / "db/migrations/20260820120000_create_pokemon_market_date_quality.sql")


def _statements(sql: str) -> str:
    """The executable SQL only. Comment prose must not satisfy a contract test."""
    return "\n".join(
        line for line in sql.splitlines() if not line.strip().startswith("--"))


def test_migration_defines_quality_table_and_status_domain():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS public.pokemon_market_date_quality" in sql
    for status in ("READY", "INCOMPLETE", "DEGRADED", "LEGACY_VERIFIED"):
        assert f"'{status}'" in sql
    # Idempotent upsert target used by persist_market_date_quality.
    assert "UNIQUE (tcg, market_date, contract_version)" in sql


def test_migration_is_additive_only():
    """It must create, never alter or drop, existing Market/RIP authority."""
    sql = _statements(MIGRATION.read_text(encoding="utf-8")).upper()
    assert "DROP TABLE" not in sql
    assert "DELETE FROM" not in sql
    assert "TRUNCATE" not in sql
    # Must not touch the 167-set batch authority or RIP publication.
    for foreign in ("POKEMON_SCRAPE_BATCHES", "POKEMON_RIP", "SCRAPE_JOBS"):
        assert foreign not in sql, foreign
    # The only table it may ALTER is its own (to enable RLS).
    for line in sql.splitlines():
        if line.strip().startswith("ALTER TABLE"):
            assert "POKEMON_MARKET_DATE_QUALITY" in line, line


def test_migration_locks_down_the_authority_table():
    """Backend-only, same posture as pokemon_scrape_batches (047/051)."""
    sql = _statements(MIGRATION.read_text(encoding="utf-8"))
    assert ("ALTER TABLE public.pokemon_market_date_quality "
            "ENABLE ROW LEVEL SECURITY") in sql
    for role in ("PUBLIC", "anon", "authenticated", "service_role"):
        assert (f"REVOKE ALL ON TABLE public.pokemon_market_date_quality "
                f"FROM {role};") in sql
    assert "GRANT SELECT, INSERT, UPDATE" in sql
    assert "TO service_role;" in sql
    # Quality rows are audit evidence: never deletable, never truncatable.
    assert "DELETE" not in sql.upper()
    # No policy is created: RLS enabled with no policy denies non-BYPASSRLS roles.
    assert "CREATE POLICY" not in sql.upper()


def test_sequence_is_locked_down_too():
    sql = MIGRATION.read_text(encoding="utf-8")
    for role in ("PUBLIC", "anon", "authenticated"):
        assert (f"REVOKE ALL ON SEQUENCE public.pokemon_market_date_quality_id_seq "
                f"FROM {role};") in sql
    assert ("GRANT USAGE, SELECT ON SEQUENCE "
            "public.pokemon_market_date_quality_id_seq TO service_role;") in sql


def test_migration_is_mirrored_to_supabase():
    mirror = (Path(__file__).resolve().parents[3].parent
              / "supabase/migrations/20260820120000_create_pokemon_market_date_quality.sql")
    assert mirror.read_text(encoding="utf-8") == MIGRATION.read_text(encoding="utf-8")
