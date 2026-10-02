from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
MIGRATION = "20261002033311_rankings_trend_history_v1.sql"


def test_trend_rpc_is_mirrored_bounded_read_only_and_service_role_only():
    backend = (ROOT / "backend" / "db" / "migrations" / MIGRATION).read_text(encoding="utf-8")
    supabase = (ROOT / "supabase" / "migrations" / MIGRATION).read_text(encoding="utf-8")
    assert backend.strip() == supabase.strip()
    normalized = backend.lower()
    for token in ("security invoker", "set search_path = ''", "jsonb_array_length(coalesce(p_entities", "between 1 and 22",
                  "p_end_date - p_start_date <= 3660", "revoke execute", "grant execute", "service_role",
                  "distinct on (s.market_date)", "published_at desc", "s.id desc", "materialized"):
        assert token in normalized
    assert "simulation_run_summary" in normalized and "prob_profit" in normalized
    assert "pokemon_financial_rip_history_rows_v1" in normalized
    assert not any(statement in normalized for statement in ("insert into", "update ", "delete from"))


def test_trend_rpc_carries_four_metrics_and_equal_set_era_aggregation():
    sql = (ROOT / "supabase" / "migrations" / MIGRATION).read_text(encoding="utf-8").lower()
    for field in ("financial_rip", "expected_value_per_pack", "chance_to_beat_pack", "chance_to_recover_cost"):
        assert field in sql
    assert "avg(" in sql
    assert "st.era_id" in sql
    assert "pokemon-rip-stats-v3" in sql
    assert "hierarchical_product_per_pack_empirical_v1" in sql
    assert "equal-set_equal-family_equal-sku-v1" in sql
