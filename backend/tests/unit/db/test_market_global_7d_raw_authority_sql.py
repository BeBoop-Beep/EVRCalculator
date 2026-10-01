from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MIGRATION = ROOT / "supabase" / "migrations" / "20260929231500_market_global_7d_raw_authority_v1.sql"


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8").lower()


def test_global_movers_use_serving_raw_exact_variant_universe():
    sql = _sql()
    assert "pokemon_market_explorer_surface_constituents_v2" in sql
    assert "market_key='raw'" in sql
    assert "serving_raw_exact_variant_v1" in sql
    assert "pokemon_market_explorer_surface_serving_v2" in sql


def test_global_movers_use_exact_nm_observations_for_7d_baseline():
    sql = _sql()
    assert "card_variant_price_observations" in sql
    assert "near mint" in sql
    assert "p_market_date-6" in sql
    assert "p_market_date-10" in sql
    assert "inclusive_calendar_dates_v1" in sql


def test_global_movers_preserve_vintage_scope_and_rank_by_market_significance():
    sql = _sql()
    assert "'marketscope',p.market_scope" in sql
    assert "'edition',p.item->>'edition'" in sql
    assert "market_movement_score_v1" in sql
    assert "order by c.movement_score desc" in sql
