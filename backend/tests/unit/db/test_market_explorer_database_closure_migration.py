from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MIGRATIONS = (
    "20260927234437_market_explorer_database_closure_sealed_screens_movement_v1.sql",
    "20260928003045_market_explorer_sealed_type_truthfulness_v1.sql",
    "20260928003715_market_explorer_sealed_parent_freshness_parity_v1.sql",
    "20260928031513_market_explorer_sealed_registry_current_pricing_v1.sql",
    "20260928031746_market_explorer_surface_health_and_sealed_parity_v1.sql",
    "20260928032222_market_explorer_sealed_authority_function_sync_v1.sql",
    "20260928032613_market_explorer_v2_bounded_roster_convergence_v1.sql",
    "20260930180000_market_explorer_sealed_constituent_movement_v2.sql",
)


def _sql(name: str) -> str:
    return (ROOT / "supabase" / "migrations" / name).read_text(encoding="utf-8")


def test_market_explorer_database_closure_migrations_are_mirrored():
    for name in MIGRATIONS:
        supabase = ROOT / "supabase" / "migrations" / name
        backend = ROOT / "backend" / "db" / "migrations" / name
        assert supabase.read_text(encoding="utf-8") == backend.read_text(encoding="utf-8")


def test_consumer_parent_policy_excludes_only_bulk_container_families():
    sql = _sql(MIGRATIONS[0])
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
    sql = _sql(MIGRATIONS[0])
    assert "least(coalesce(p_limit,10),10)" in sql
    assert "p_asset is null or d.asset=p_asset" in sql
    assert "'cards','sealed','graded'" in sql


def test_sealed_movement_contract_is_bounded_and_null_preserving():
    sql = _sql(MIGRATIONS[0])
    assert "cardinality(p_sealed_product_ids)>100" in sql
    assert "get_pokemon_market_explorer_sealed_constituent_movement_v1" in sql
    movement = sql.split(
        "create or replace function public.get_pokemon_market_explorer_sealed_constituent_movement_v1",
        1,
    )[1]
    assert "case when e.end_price>0 and b7.p>0" in movement
    assert "coalesce((e.end_price/b7.p-1.0)*100.0,0)" not in movement


def test_sealed_type_truthfulness_uses_current_priced_registry_and_v5_metadata():
    sql = _sql(MIGRATIONS[1])
    assert "rr.current_priced_count>0" in sql
    assert "consumer_retail_nonbulk_only" in sql
    assert "sealed-product-classification-v5-consumer-retail-taxonomy" in sql
    assert "Consumer-retail sealed products; only true bulk/container packaging is excluded" in sql


def test_sealed_parent_history_respects_set_page_30_day_freshness():
    sql = _sql(MIGRATIONS[2])
    assert "i.market_date+30" in sql
    assert "stage_pokemon_market_explorer_sealed_lattice_v2" in sql


def test_type_registry_current_pricing_is_30_day_bounded():
    sql = _sql(MIGRATIONS[3])
    assert "latest_market_date>=v_market_date-30" in sql
    assert "'freshnessDays',30" in sql


def test_surface_health_and_full_cohort_parity_audit_are_persisted():
    sql = _sql(MIGRATIONS[4])
    assert "get_pokemon_market_explorer_surface_freshness_v2" in sql
    assert "canonicalAcceptedDate" in sql
    assert "audit_pokemon_market_explorer_sealed_set_parity_v1" in sql
    assert "'freshnessDays',30" in sql
    assert "'missingFromExplorer',v_missing" in sql
    assert "'extraInExplorer',v_extra" in sql
    assert "'setValueOrCountMismatches',v_value_mismatches" in sql


def test_v5_sealed_refresh_functions_are_replayable_and_bounded():
    sql = _sql(MIGRATIONS[5])
    assert "market_explorer_sealed_is_bulk_container_v2" in sql
    assert "market_explorer_sealed_parent_member_for_product_v1" in sql
    assert "refresh_pokemon_market_explorer_sealed_daily_v1" in sql
    assert "p_through-p_from > 31" in sql
    assert "sealed-product-classification-v5-consumer-retail-taxonomy" in sql
    assert "market-explorer-consumer-sealed-v3-nonbulk-retail" in sql
    assert "refresh_pokemon_market_explorer_sealed_current_metadata_v1" in sql


def test_v2_publisher_converges_frozen_rosters_in_bounded_ticks():
    sql = _sql(MIGRATIONS[6])
    assert "freeze_pokemon_market_legacy_set_value_rosters_v1" in sql
    assert "v_target,20" in sql
    assert "raw_frozen_rosters_converging" in sql
    assert "'readyRoots',coalesce(v_ready_roots,0)" in sql
    assert "'expectedRoots',coalesce(v_expected_roots,0)" in sql
    assert "CURRENT_V2_RAW_ROOT_COUNT_MISMATCH" in sql


def test_sealed_movement_v2_is_additive_bounded_and_canonical():
    sql = _sql(MIGRATIONS[7])
    assert "get_pokemon_market_explorer_sealed_constituent_movement_v2" in sql
    assert "cardinality(p_sealed_product_ids)>100" in sql
    assert "p_as_of-180+1" in sql
    assert "p_as_of-365+1" in sql
    assert "baseline_since_tracking_date" in sql
    assert "order by o.captured_at::date asc,o.captured_at desc,o.id desc" in sql
    assert "coalesce((e.end_price/" not in sql
    assert "o.market_price>0" in sql
    assert "upper(pg_catalog.btrim(coalesce(o.currency,'USD')))='USD'" in sql
    assert "o.captured_at<(p_as_of+1)::timestamptz" in sql
