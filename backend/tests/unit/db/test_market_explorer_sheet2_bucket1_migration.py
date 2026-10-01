from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
NAME = "20260930230000_market_explorer_surface_canonical_movement_v1.sql"


def _sql() -> str:
    primary = (ROOT / "supabase" / "migrations" / NAME).read_text()
    mirror = (ROOT / "backend" / "db" / "migrations" / NAME).read_text()
    assert primary == mirror
    return primary.lower()


def test_elapsed_targets_resolve_at_or_before_without_synthetic_history():
    sql = _sql()
    for days in (7, 30, 90, 365):
        assert f"h.market_date<=p_as_of-{days}" in sql
    assert "order by h.market_date desc limit 1" in sql
    assert "h.market_date=p_as_of" in sql
    assert "generate_series" not in sql


def test_finalizer_consumes_one_canonical_movement_contract():
    sql = _sql()
    assert "get_pokemon_market_explorer_surface_movement_v1" in sql
    assert "movement as materialized" in sql
    assert "return_30d_pct=m.return_30d_pct" in sql
    assert "to service_role" in sql
    assert "from public,anon,authenticated" in sql


def test_asset_filter_preserves_global_screen_ranks():
    sql = _sql()
    assert "globally_ranked as" in sql
    assert "r.global_rank<=p_limit" in sql
    assert "v_asset='all' or r.asset=v_asset" in sql
    assert "'cards','sealed','graded','all'" in sql
