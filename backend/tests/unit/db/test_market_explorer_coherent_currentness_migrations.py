from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]

MIGRATIONS = [
    "20260926230000_market_explorer_coherent_watermark_and_leaf_search.sql",
    "20260926230500_market_explorer_sealed_quicks_and_screens.sql",
    "20260926231000_market_explorer_coherent_v2_promotion_gates.sql",
    "20260926231500_market_explorer_exact_legacy_roster_recovery_v2.sql",
]


def read(tree: str, name: str) -> str:
    return (ROOT / tree / "migrations" / name).read_text()


def test_new_migration_trees_are_byte_identical():
    for name in MIGRATIONS:
        assert (ROOT / "supabase" / "migrations" / name).read_bytes() == (
            ROOT / "backend" / "db" / "migrations" / name
        ).read_bytes()


def test_coherent_watermark_and_leaf_search_contract():
    sql = read("supabase", MIGRATIONS[0]).lower()
    assert "comparison_as_of date" in sql
    assert "get_pokemon_market_explorer_asset_as_of_v1" in sql
    assert "search_pokemon_market_explorer_leaves_v3" in sql
    assert "search_pokemon_market_explorer_instruments_v2" in sql
    assert "current_market_price" in sql
    assert "current_market_date" in sql
    assert "set statement_timeout = '1s'" in sql
    assert "exact_name" in sql and "name_prefix" in sql
    assert "contiguous_phrase" in sql and "all_tokens" in sql
    assert "from public,anon,authenticated" in sql
    assert "to service_role" in sql
    assert "security definer" not in sql


def test_six_sealed_quicks_and_screen_contract():
    sql = read("supabase", MIGRATIONS[1]).lower()
    for key in (
        "sealed-quick:obtainable",
        "sealed-quick:intermediate",
        "sealed-quick:premium",
        "sealed-quick:new-releases",
        "sealed-quick:established",
        "sealed-quick:global-top10",
    ):
        assert key in sql
    assert "d.market_price<100" in sql
    assert "d.market_price>=100 and d.market_price<500" in sql
    assert "d.market_price>=500" in sql
    assert "(d.market_date-d.release_date)<=180" in sql
    assert "(d.market_date-d.release_date)>730" in sql
    assert "(d.market_date-d.release_date)<=1825" in sql
    assert "m.is_bulk_container=false" in sql
    assert "partition by d.market_date" in sql
    assert "global_rank<=10" in sql
    assert "top-performers" in sql and "worst-performers" in sql
    assert "least(greatest(coalesce(p_limit,25),1),25)" in sql
    assert "market_explorer_generation_mismatch" in sql


def test_v2_build_and_promotion_fail_closed_on_source_currency():
    sql = read("supabase", MIGRATIONS[2]).lower()
    assert "preflight_pokemon_market_explorer_surface_v2" in sql
    assert "base_prepared_generation_not_coherent" in sql
    assert "card_daily_authority_not_current" in sql
    assert "sealed_authority_not_current" in sql
    assert "rarity_authority_not_certified" in sql
    assert "raw_frozen_rosters_incomplete" in sql
    assert "directory_comparison_watermark_mismatch" in sql
    assert "history_not_current" in sql
    assert "sealed_quick_markets_missing" in sql
    assert "sealed_global_top10_count" in sql
    assert "validate_pokemon_market_explorer_surface_candidate_v2" in sql
    assert "only_current_validated_surface_generations_may_be_promoted" in sql


def test_legacy_recovery_never_relaxes_exact_reconciliation():
    sql = read("supabase", MIGRATIONS[3]).lower()
    assert "snapshot_eligible_exact" in sql
    assert "physical_variant_dedup_exact" in sql
    assert "round(v_value,2)=round(v_expected_value,2)" in sql
    assert "v_unique_variants=v_expected_count" in sql
    assert "v_unique_canonical=v_expected_count" in sql
    assert "no_exact_strategy" in sql
    assert "raw_roster_recovery_failures_v1" in sql
    assert "p_limit>10" in sql
    assert "set statement_timeout = '90s'" in sql
