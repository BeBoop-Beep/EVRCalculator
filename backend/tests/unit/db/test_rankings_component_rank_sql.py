from pathlib import Path


ROOT = Path(__file__).parents[4]
NAME = "20260929001151_rankings_collector_component_ranks_v1.sql"
SUPABASE_MIGRATION = ROOT / "supabase" / "migrations" / NAME
BACKEND_MIGRATION = ROOT / "backend" / "db" / "migrations" / NAME
SQL = SUPABASE_MIGRATION.read_text(encoding="utf-8").lower()


def test_component_rank_is_windowed_before_result_filters_and_rpc_is_service_only():
    assert SQL.index("rank() over") < SQL.index("), filtered as")
    assert "count(*) over () as component_cohort_size" in SQL
    assert "security invoker" in SQL
    assert "from public, anon, authenticated" in SQL
    assert "to service_role" in SQL


def test_component_rank_migration_trees_are_byte_identical():
    assert SUPABASE_MIGRATION.read_bytes() == BACKEND_MIGRATION.read_bytes()
    assert not (ROOT / "supabase" / "migrations" /
                "20260928183000_rankings_collector_component_ranks_v1.sql").exists()
    assert not (ROOT / "backend" / "db" / "migrations" /
                "20260928183000_rankings_collector_component_ranks_v1.sql").exists()
