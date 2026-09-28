from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SUPABASE = ROOT / "supabase" / "migrations" / "20260927234437_market_explorer_database_closure_sealed_screens_movement_v1.sql"
BACKEND = ROOT / "backend" / "db" / "migrations" / "20260927234437_market_explorer_database_closure_sealed_screens_movement_v1.sql"


def test_market_explorer_database_closure_migration_is_mirrored():
    assert SUPABASE.read_text(encoding="utf-8") == BACKEND.read_text(encoding="utf-8")


def test_consumer_parent_policy_excludes_only_bulk_container_families():
    sql = SUPABASE.read_text(encoding="utf-8")
    assert "not in ('case','display','master_carton')" in sql
    for family in (
        "collection_product",
        "multi_product_bundle",
        "single_pack_blister",
        "three_pack_blister",
        "ultra_premium_collection",
        "super_premium_collection",
        "premium_collection",
        "tin",
        "mini_tin",
        "chest",
    ):
        assert family in sql


def test_screen_contract_is_global_and_hard_capped_at_ten():
    sql = SUPABASE.read_text(encoding="utf-8")
    assert "least(coalesce(p_limit,10),10)" in sql
    assert "p_asset is null or d.asset=p_asset" in sql
    assert "'cards','sealed','graded'" in sql


def test_sealed_movement_contract_is_bounded_and_null_preserving():
    sql = SUPABASE.read_text(encoding="utf-8")
    assert "cardinality(p_sealed_product_ids)>100" in sql
    assert "get_pokemon_market_explorer_sealed_constituent_movement_v1" in sql
    assert "case when e.end_price>0 and b7.p>0" in sql
    movement = sql.split("create or replace function public.get_pokemon_market_explorer_sealed_constituent_movement_v1", 1)[1]\n    assert "coalesce((e.end_price/b7.p-1.0)*100.0,0)" not in movement
