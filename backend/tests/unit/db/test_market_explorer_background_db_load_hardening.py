from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
NAME = "20260925001000_bound_market_explorer_background_db_load.sql"


def _sql(tree: str) -> str:
    return (ROOT / tree / NAME).read_text(encoding="utf-8")


def test_migration_mirrors_are_identical():
    assert _sql("backend/db/migrations") == _sql("supabase/migrations")


def test_price_storage_cycle_is_bounded_and_non_overlapping():
    sql = _sql("backend/db/migrations").lower()
    body = sql.split(
        "create or replace function public.run_price_storage_v2_shadow_cycle()", 1
    )[1]
    assert "set statement_timeout = '15s'" in body
    assert "set lock_timeout = '2s'" in body
    assert "pg_try_advisory_xact_lock" in body
    assert "monthly_sets_per_cycle',1" in body
    assert "process_price_storage_v2_shadow_queue(" not in body
    assert "delegated_to_application_staged_worker" in body


def test_monthly_rollup_advances_one_set_per_cycle():
    sql = _sql("backend/db/migrations").lower()
    body = sql.split(
        "create or replace function public.sync_price_storage_v2_previous_monthly_rollup()", 1
    )[1].split(
        "create or replace function public.run_price_storage_v2_shadow_cycle()", 1
    )[0]
    assert "sync_price_storage_v2_monthly_rollup_month(v_month, 1, true)" in body
    assert "sync_price_storage_v2_monthly_rollup_month(v_month, 10, true)" not in body


def test_hot_background_predicates_have_targeted_indexes():
    sql = _sql("backend/db/migrations").lower()
    assert "idx_scrape_jobs_completed_market_set_v2" in sql
    assert "where status = 'completed'" in sql
    assert "idx_price_storage_v2_shadow_queue_market_status_set_v2" in sql
    assert "idx_price_storage_v2_monthly_rollup_claim_v2" in sql


def test_legacy_coverage_rpc_is_fail_fast():
    sql = _sql("backend/db/migrations").lower()
    assert (
        "alter function public.get_pokemon_market_explorer_set_history_coverage_v1(uuid[])"
        in sql
    )
    assert "set statement_timeout = '5s'" in sql
    assert "set lock_timeout = '1s'" in sql
    assert "set jit = 'off'" in sql


def test_presence_rpc_is_bounded_private_and_methodology_equivalent():
    sql = _sql("backend/db/migrations").lower()
    assert "has_pokemon_market_explorer_set_history_v1" in sql
    assert "returns boolean" in sql
    assert "h.value_scope = 'standard'" in sql
    assert "coalesce(s.catalog_only, false) = false" in sql
    assert "select exists" in sql
    assert "set statement_timeout = '1s'" in sql
    assert "from public, anon, authenticated" in sql
    assert "to service_role" in sql


def test_no_index_or_market_methodology_change_is_hidden_here():
    sql = _sql("backend/db/migrations").lower()
    forbidden = (
        "pokemon_market_index_daily_history",
        "normalized_index_value",
        "market_scope_contract",
        "update public.pokemon_market_explorer_surface_serving_v2",
        "cron.schedule(",
    )
    for fragment in forbidden:
        assert fragment not in sql
