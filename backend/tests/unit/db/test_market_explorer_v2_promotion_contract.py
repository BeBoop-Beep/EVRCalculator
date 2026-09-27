from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]

COHERENT = "20260927020409_market_explorer_coherent_generation_quicks_screens.sql"
FINAL_GAPS = "20260927042229_market_explorer_promotion_final_gaps_v2.sql"
LIVE_SYNC = "20260927043142_market_explorer_v2_live_contract_source_sync_v3.sql"
SEALED_INDEX = "20260927043901_index_sealed_product_observation_snapshot_reads.sql"
FINAL_AUTOMATION = "20260927044821_market_explorer_v2_final_cutover_automation.sql"


def _read(tree: str, name: str) -> str:
    return (ROOT / tree / "migrations" / name).read_text(encoding="utf-8")


def test_market_explorer_live_migrations_are_byte_identical_mirrors():
    for name in (COHERENT, FINAL_GAPS, LIVE_SYNC, SEALED_INDEX, FINAL_AUTOMATION):
        assert _read("backend/db", name) == _read("supabase", name)


def test_superseded_repo_only_migration_identities_are_retired():
    for tree in ("backend/db", "supabase"):
        root = ROOT / tree / "migrations"
        for old_name in (
            "20260927021000_market_explorer_coherent_generation_quicks_screens.sql",
            "20260927043000_market_explorer_promotion_final_gaps.sql",
            "20260927044500_market_explorer_v2_live_contract_source_sync.sql",
        ):
            assert not (root / old_name).exists()
    assert not (
        ROOT / "supabase/migrations/20260927023500_market_explorer_seed_from_retained_prepared_generation.sql"
    ).exists()


def test_coherent_migration_contains_seed_build_and_leaf_authorities():
    sql = _read("supabase", COHERENT).lower()
    for required in (
        "seed_pokemon_market_explorer_surface_from_prepared_v1",
        "build_pokemon_market_explorer_surface_candidate_v2",
        "search_pokemon_market_explorer_leaves_v1",
    ):
        assert required in sql


def test_bulk_parent_membership_is_product_aware():
    sql = _read("supabase", FINAL_GAPS).lower()
    assert "market_explorer_sealed_parent_member_for_product_v1" in sql
    assert "master[[:space:]]+)?carton" in sql
    assert "market_explorer_sealed_parent_member_v1(p_family)" in sql
    assert "sealed-product-classification-v4-product-bulk-aware" in sql


def test_mixed_search_no_longer_requires_global_market_date():
    sql = _read("supabase", FINAL_GAPS).lower()
    fn = sql.split(
        "create or replace function public.search_pokemon_market_explorer_instruments_v2(", 1
    )[1]
    assert "card_date as materialized" in fn
    assert "max(d.market_date)" in fn
    assert "pokemon_market_explorer_sealed_current_metadata_v1" in fn
    assert "pokemon_market_date_quality" not in fn
    assert "three[ -]+pack" in fn


def test_live_v2_contracts_are_source_synced():
    sql = _read("supabase", LIVE_SYNC).lower()
    for required in (
        "search_pokemon_market_explorer_leaves_v1",
        "stage_pokemon_market_explorer_sealed_quick_markets_v2",
        "get_pokemon_market_explorer_performance_screen_v1",
        "assert_pokemon_market_explorer_surface_coherent_v2",
        "promote_pokemon_market_explorer_surface_v2",
        "rollback_pokemon_market_explorer_surface_v2",
        "sealed-quick:obtainable",
        "sealed-quick:intermediate",
        "sealed-quick:premium",
        "sealed-quick:new-releases",
        "sealed-quick:established",
        "sealed-quick:global-top10",
        "top-performers",
        "worst-performers",
        "performance_screen_generation_mismatch",
        "surface_sealed_quick_contains_bulk",
    ):
        assert required in sql


def test_leaf_search_is_bounded_and_asset_specific():
    sql = _read("supabase", LIVE_SYNC).lower()
    fn = sql.split(
        "create or replace function public.search_pokemon_market_explorer_leaves_v1(", 1
    )[1].split("$function$;", 1)[0]
    assert "set statement_timeout to '1s'" in fn
    assert "p_limit>50" in fn
    assert "max(d.market_date)" in fn
    assert "max(m.latest_market_date)" in fn
    assert " three " in fn
    assert " 3 " in fn


def test_performance_screens_are_generation_pinned_and_capped():
    sql = _read("supabase", LIVE_SYNC).lower()
    fn = sql.split(
        "create or replace function public.get_pokemon_market_explorer_performance_screen_v1(", 1
    )[1].split("$function$;", 1)[0]
    assert "top-performers" in fn
    assert "worst-performers" in fn
    assert "p_limit>25" in fn
    assert "performance_screen_generation_mismatch" in fn
    assert "d.comparison_as_of" in fn


def test_final_automation_adds_current_publisher_and_screen_compatibility():
    sql = _read("supabase", FINAL_AUTOMATION).lower()
    assert "publish_pokemon_market_explorer_surface_current_v2" in sql
    assert "pg_try_advisory_xact_lock" in sql
    assert "candidate_validation_failed" in sql
    assert "assert_pokemon_market_explorer_surface_coherent_v2" in sql
    assert "promote_pokemon_market_explorer_surface_v2" in sql
    assert "get_pokemon_market_explorer_prepared_screen_v1" in sql
    assert "get_pokemon_market_explorer_performance_screen_v1" in sql
    assert "metric_7d_pct" in sql
    assert "performance_screen_v2_not_serving" in sql
    assert "grant execute on function public.publish_pokemon_market_explorer_surface_current_v2()" in sql
    assert "to service_role" in sql
