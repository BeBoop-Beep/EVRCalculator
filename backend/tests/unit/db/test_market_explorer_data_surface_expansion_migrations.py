from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[4]
MIGRATIONS = (
    "20260924213000_market_explorer_data_surface_authorities_v1.sql",
    "20260924214500_market_explorer_generation_surface_v2.sql",
    "20260924220000_market_explorer_catalog_search_v1.sql",
    "20260925061000_market_explorer_raw_frozen_set_value_constituents_v1.sql",
)


def read(name: str) -> str:
    return (ROOT / "supabase" / "migrations" / name).read_text(encoding="utf-8")


def test_migration_trees_are_byte_identical():
    for name in MIGRATIONS:
        assert (ROOT / "supabase" / "migrations" / name).read_bytes() == (
            ROOT / "backend" / "db" / "migrations" / name
        ).read_bytes()


def test_full_rarity_taxonomy_and_truthful_states_are_seeded():
    sql = read(MIGRATIONS[0])
    keys = re.findall(
        r"\('([A-Za-z0-9]+)','[^']+','pokemon-card-rarity-filter-taxonomy-v1'",
        sql,
    )
    assert len(keys) == 39
    assert len(set(keys)) == 39
    assert "('rareHoloGx','Rare Holo GX'" in sql
    for state in (
        "PREPARED",
        "CUSTOM_BUILD_AVAILABLE",
        "INSUFFICIENT_COHORT",
        "INSUFFICIENT_HISTORY",
        "UNAVAILABLE",
    ):
        assert state in sql
    assert "25-card / 3-set" in sql


def test_sealed_registry_is_complete_and_total_parent_excludes_bulk():
    sql = read(MIGRATIONS[0])
    families = re.findall(
        r"\('([a-z_]+)','[^']+','[^']*','sealed-product-classification-v3-loose-pack-family'",
        sql,
    )
    assert set(families) == {
        "booster_box",
        "half_booster_box",
        "enhanced_booster_box",
        "elite_trainer_box",
        "pokemon_center_elite_trainer_box",
        "booster_bundle",
        "loose_booster_pack",
        "sleeved_booster_pack",
        "build_and_battle_box",
        "build_and_battle_stadium",
        "three_pack_blister",
        "single_pack_blister",
        "collection_product",
        "case",
        "display",
        "multi_product_bundle",
        "fun_pack",
        "other",
    }
    parent_fn = sql.split("market_explorer_sealed_parent_member_v1", 1)[1].split("$function$;", 1)[0]
    assert "'case'" not in parent_fn
    assert "'display'" not in parent_fn
    assert "'booster_box'" in parent_fn
    assert "'half_booster_box'" in parent_fn
    assert "'enhanced_booster_box'" in parent_fn


def test_raw_parent_is_composition_only_and_must_reconcile():
    sql = read(MIGRATIONS[0])
    assert "pokemon_market_index_daily_history" in sql
    assert "FAILED_RECONCILIATION" in sql
    assert "round(v_value,2)=round(v_raw.basket_value,2)" in sql
    assert "v_count=v_raw.card_count" in sql
    assert "pokemon_market_explorer_raw_composition_v1" in sql
    # The new work never overwrites the persisted Raw index.
    assert not re.search(
        r"(insert\s+into|update|delete\s+from)\s+public\.pokemon_market_index_daily_history",
        sql,
        flags=re.I,
    )


def test_image_precedence_is_variant_then_canonical_then_metadata():
    sql = read(MIGRATIONS[0])
    expected = (
        "cv.image_small_url,cc.image_small_url,"
        "cv.image_large_url,cc.image_large_url,cm.image_url"
    )
    assert expected in sql.replace("\n", "").replace(" ", "")
    assert "'imageUrl'" in sql
    assert "'imageSmallUrl'" in sql
    assert "'imageLargeUrl'" in sql


def test_surface_is_shadow_first_and_page_reads_are_pk_bounded():
    sql = read(MIGRATIONS[1])
    assert "surface_serving_v2" in sql
    assert "promote_pokemon_market_explorer_surface_v2" in sql
    assert "rollback_pokemon_market_explorer_surface_v2" in sql
    assert "ONLY_VALIDATED_SURFACE_GENERATIONS_MAY_BE_PROMOTED" in sql
    assert "p_limit<1 or p_limit>100" in sql
    reader = sql.split(
        "get_pokemon_market_explorer_surface_constituents_v2(", 1
    )[1].split("$function$;", 1)[0]
    assert "pokemon_market_explorer_surface_constituents_v2" in reader
    assert "pokemon_market_explorer_card_daily_states" not in reader
    assert "sealed_product_price_observations" not in reader
    assert "payload_json" not in reader
    assert "rank>coalesce(p_after_rank,0)" in reader


def test_sealed_lattice_has_explicit_namespaced_keys_and_legacy_aliases():
    sql = read(MIGRATIONS[1])
    for fragment in (
        "'sealedMarket'",
        "'sealed-set:'||d.set_id::text",
        "'sealed-era:'||d.era_id::text",
        "'sealed-type:'||d.product_family",
        "'sealed-type:packs'",
    ):
        assert fragment in sql
    assert "pokemon_market_explorer_surface_aliases_v2" in sql
    assert "Legacy prepared sealed-format key" in sql


def test_no_sealed_quick_market_is_silently_approved():
    sql = read(MIGRATIONS[0])
    seed = sql.split(
        "insert into public.pokemon_market_explorer_sealed_quick_registry_v1", 1
    )[1].split("on conflict", 1)[0]
    assert "'APPROVED'" not in seed
    assert seed.count("'PROPOSED'") == 5


def test_focus_features_are_readiness_only_not_fake_metrics():
    sql = read(MIGRATIONS[0])
    assert "DEMAND_PRESSURE_NOT_READY" in sql
    assert "INDEX_FAIR_VALUE_NOT_READY_FOR_PRODUCTION" in sql
    assert "Active asks/listings are not completed sales" in sql
    assert "pokemon_market_demand_pressure_v1" not in sql
    assert "fair_value_index" not in sql


def test_contextual_search_is_asset_scoped_bounded_and_graded_fail_closed():
    sql = read(MIGRATIONS[2])
    assert "search_pokemon_market_explorer_catalog_v1" in sql
    assert "least(greatest(coalesce(p_limit,20),1),50)" in sql
    assert "set statement_timeout = '1s'" in sql
    assert "INSUFFICIENT_AUTHORITY" in sql
    assert "pokemon_market_explorer_sealed_current_metadata_v1" in sql
    assert "sealed_product_price_observations" not in sql
    assert "pokemon_set_sealed_market_snapshot_latest" not in sql


def test_new_db_objects_are_private_and_fixed_search_path():
    combined = "\n".join(read(x) for x in MIGRATIONS)
    assert "grant execute" in combined.lower()
    assert "to service_role" in combined.lower()
    assert "from public,anon,authenticated" in combined.lower() or "from public, anon, authenticated" in combined.lower()
    scrubbed = re.sub(
        r"grant\s+select\s*,\s*insert\s*,\s*update\s*,\s*delete\s+on[\s\S]*?to\s+service_role\s*;",
        "",
        combined.lower(),
    )
    assert not re.search(r"grant\s+select\b", scrubbed)
    # All authored functions deliberately pin search_path.  No SECURITY DEFINER
    # was introduced for these authorities.
    assert "security definer" not in combined.lower()
    assert combined.lower().count("set search_path = ''") >= 20


def test_no_commercial_comparison_quota_is_encoded():
    combined = "\n".join(read(x) for x in MIGRATIONS).lower()
    for forbidden in ("index+ limit", "premium limit", "comparison quota", "max_active_markets"):
        assert forbidden not in combined


def test_live_prepared_rarity_segment_id_is_supported():
    authority_sql = read(MIGRATIONS[0])
    surface_sql = read(MIGRATIONS[1])
    assert "nullif(d.metadata->>'segmentId','')" in authority_sql
    assert "nullif(d.metadata->>'segmentId','')" in surface_sql


def test_raw_composition_successor_uses_frozen_set_value_leaves():
    sql = read(MIGRATIONS[3])
    assert "pokemon_market_set_value_constituent_publications_v1" in sql
    assert "pokemon_market_set_value_constituents_v1" in sql
    assert "replace_pokemon_market_set_value_constituents_v1" in sql
    assert "Frozen Set Value leaf publications incomplete or mismatched" in sql
    stage = sql.split(
        "create or replace function public.stage_pokemon_market_explorer_raw_composition_v1(", 1
    )[1].split("$function$;", 1)[0]
    assert "pokemon_market_set_value_constituents_v1" in stage
    assert "pokemon_market_explorer_card_daily_states_v2_shadow" not in stage
    assert "get_pokemon_set_value_canonical_prices_as_of_v2_shadow" not in stage
    assert "'standard'::text as market_scope" in stage
    assert "round(v_value,2)=round(v_raw.basket_value,2)" in stage
    assert "v_count=v_raw.card_count" in stage


def test_frozen_set_value_leaf_publication_is_private_bounded_and_atomic():
    sql = read(MIGRATIONS[3]).lower()
    assert "p_expected_card_count > 2000" in sql
    assert "pg_advisory_xact_lock" in sql
    assert "set statement_timeout = '10s'" in sql
    assert "set lock_timeout = '2s'" in sql
    assert "enable row level security" in sql
    assert "from public,anon,authenticated" in sql
    assert "to service_role" in sql
    assert "security definer" not in sql
