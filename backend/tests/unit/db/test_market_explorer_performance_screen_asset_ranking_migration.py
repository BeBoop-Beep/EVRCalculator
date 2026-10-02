from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
STEM = "20261002044542_fix_market_explorer_performance_screen_asset_ranking_20261002.sql"


def _source(tree: str) -> str:
    return (ROOT / tree / "migrations" / STEM).read_text(encoding="utf-8")


def test_production_screen_fix_is_identical_in_both_migration_trees():
    assert _source("backend/db") == _source("supabase")


def test_asset_filter_is_inside_ranked_universe_before_limit():
    sql = " ".join(_source("backend/db").lower().split())
    ranked = sql[sql.index("with asset_ranked as"):sql.index("order by r.asset_rank")]
    assert "and (v_asset='all' or d.asset=v_asset)" in ranked
    assert ranked.index("and (v_asset='all' or d.asset=v_asset)") < ranked.index("where r.asset_rank<=p_limit")
    assert "where r.asset_rank<=p_limit and" not in ranked


def test_cards_sealed_all_graded_and_supported_limits_remain_accepted():
    sql = " ".join(_source("backend/db").lower().split())
    assert "v_asset not in ('cards','sealed','graded','all')" in sql
    assert "p_limit<1 or p_limit>25" in sql
    assert "p_screen_key not in ('top-performers','worst-performers')" in sql
    assert "row_number() over" in sql
