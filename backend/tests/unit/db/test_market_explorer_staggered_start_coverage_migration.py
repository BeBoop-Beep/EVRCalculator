from pathlib import Path


MIGRATION = Path(__file__).resolve().parents[4] / "supabase/migrations/20260901030000_fix_market_explorer_staggered_start_coverage.sql"
SQL = " ".join(MIGRATION.read_text(encoding="utf-8").lower().split())
TIMEOUT_MIGRATION = Path(__file__).resolve().parents[4] / "supabase/migrations/20260901031000_bound_market_explorer_daily_candidate_build_timeout.sql"
TIMEOUT_SQL = " ".join(TIMEOUT_MIGRATION.read_text(encoding="utf-8").lower().split())


def test_forward_migration_removes_only_the_invalid_start_gate():
    assert "pg_get_functiondef" in SQL
    assert "expected staggered-start coverage predicate was not found" in SQL
    assert "and first_market_date<=p_start_date and computed_through>=p_end_date" in SQL
    assert "new_predicate constant text := ' and computed_through>=p_end_date'" in SQL


def test_public_rpc_signature_and_security_model_are_unchanged():
    assert "security definer" not in SQL
    assert "get_pokemon_market_explorer_filtered_cohort_daily_candidate" in SQL
    assert "uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer" in SQL


def test_cache_builder_timeout_is_function_local_and_lease_bounded():
    assert "alter function public.get_pokemon_market_explorer_filtered_cohort_daily_candidate" in TIMEOUT_SQL
    assert "set statement_timeout = '300s'" in TIMEOUT_SQL
    assert "alter role" not in TIMEOUT_SQL
    assert "alter database" not in TIMEOUT_SQL
