from pathlib import Path


SQL = (Path(__file__).resolve().parents[4] / "supabase" / "migrations" /
       "20260829210512_market_explorer_filtered_card_cohorts.sql").read_text(encoding="utf-8")


def test_filtered_cohort_rpc_is_service_only_and_invoker_safe():
    normalized = " ".join(SQL.lower().split())
    assert "security invoker" in normalized
    assert "revoke all on function" in normalized
    assert "from public, anon, authenticated" in normalized
    assert "grant execute on function" in normalized
    assert "to service_role" in normalized
    assert "security definer" not in normalized


def test_filter_first_rank_second_and_point_in_time_authorities_are_in_sql():
    assert SQL.index("panel AS MATERIALIZED") < SQL.index("ranked AS") < SQL.index("selected AS MATERIALIZED")
    assert "c.market_price < 10" in SQL
    assert "c.market_price >= 100" in SQL
    assert "c.market_date - s.release_date" in SQL
    assert "PARTITION BY p.market_date" in SQL
    assert "ORDER BY p.market_price DESC, p.canonical_card_id" in SQL
    assert "prev.canonical_card_id = cur.canonical_card_id" in SQL


def test_rpc_returns_reduced_dates_and_only_latest_constituent_identity():
    assert "current_constituents jsonb" in SQL
    assert "d.market_date = d.latest_market_date" in SQL
    assert "eligible_universe_count" in SQL
    assert "common_previous_value" in SQL
