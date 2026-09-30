from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MIGRATION = ROOT / "supabase" / "migrations" / "20260930003000_market_mixed_7d_movers_v1.sql"


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8").lower()


def test_mixed_movers_union_cards_and_sealed_before_top_50_ranking():
    sql = _sql()
    assert "get_pokemon_market_raw_card_movers_v1(p_market_date,100)" in sql
    assert "market_key='sealedmarket'" in sql
    assert "union all" in sql
    assert "mixed_rank<=p_limit" in sql
    assert "mixed_movers_limit_must_be_1_to_50" in sql


def test_sealed_movers_require_current_day_endpoint_and_exact_observation_baseline():
    sql = _sql()
    assert "sealed_product_price_observations" in sql
    assert "o.captured_at>=p_market_date::timestamptz" in sql
    assert "o.captured_at<(p_market_date+1)::timestamptz" in sql
    assert "between p_market_date-10 and p_market_date-6" in sql


def test_cards_and_sealed_share_ranking_and_baseline_quality_contracts():
    sql = _sql()
    assert "market_movement_score_v1" in sql
    assert "target_baseline_reversion_guard_v1" in sql
    assert "serving_cards_and_sealed_exact_instruments_v1" in sql
    assert "'asset','sealed'" in sql
    assert "'asset','cards'" in sql
