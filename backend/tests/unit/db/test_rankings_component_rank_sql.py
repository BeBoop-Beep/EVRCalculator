from pathlib import Path


SQL = (Path(__file__).parents[4] / "supabase" / "migrations" /
       "20260928183000_rankings_collector_component_ranks_v1.sql").read_text(encoding="utf-8").lower()


def test_component_rank_is_windowed_before_result_filters_and_rpc_is_service_only():
    assert SQL.index("rank() over") < SQL.index("), filtered as")
    assert "count(*) over () as component_cohort_size" in SQL
    assert "security invoker" in SQL
    assert "from public, anon, authenticated" in SQL
    assert "to service_role" in SQL
