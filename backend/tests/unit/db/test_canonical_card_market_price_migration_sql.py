from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "db"
    / "migrations"
    / "040_add_refreshable_canonical_card_market_prices.sql"
)
OPTIMIZATION_MIGRATION = MIGRATION.with_name(
    "041_optimize_canonical_card_market_price_identity_resolution.sql"
)
MATERIALIZED_REFRESH_MIGRATION = MIGRATION.with_name(
    "042_materialize_canonical_card_price_refresh.sql"
)
INDEX_MIGRATION = MIGRATION.with_name(
    "043_index_canonical_card_market_price_foreign_keys.sql"
)


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def test_canonical_price_resolver_uses_stable_identity_and_valid_nm_usd_observations():
    sql = _sql()

    assert "c.pokemon_tcg_api_id = pcc.pokemon_tcg_api_card_id" in sql
    assert "cv.pokemon_tcg_api_id = pcc.pokemon_tcg_api_card_id" in sql
    assert "lower(regexp_replace(trim(c.name)" in sql
    assert "public.card_variant_price_observations" in sql
    assert "po.condition_id = nmc.id" in sql
    assert "po.market_price > 0" in sql
    assert "= 'USD'" in sql


def test_canonical_price_all_refresh_targets_every_canonical_set():
    sql = _sql()

    all_refresh = sql.split(
        "CREATE OR REPLACE FUNCTION public.refresh_pokemon_canonical_card_market_prices_latest_all()",
        1,
    )[1]
    assert "SELECT DISTINCT pcc.set_id" in all_refresh
    assert "FROM public.pokemon_canonical_cards pcc" in all_refresh
    assert "simulation" not in all_refresh.lower()
    assert "hit_eligible" not in all_refresh.lower()


def test_canonical_price_refresh_does_not_replace_a_populated_set_with_zero_rows():
    sql = _sql()

    assert "IF existing_count > 0 AND resolved_count = 0 THEN" in sql
    assert "Refusing to replace % canonical price rows with zero rows" in sql


def test_canonical_price_write_functions_are_service_role_only():
    sql = _sql()

    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "REVOKE ALL ON FUNCTION public.refresh_pokemon_canonical_card_market_prices_latest_all()" in sql
    assert "GRANT EXECUTE ON FUNCTION public.refresh_pokemon_canonical_card_market_prices_latest_all() TO service_role" in sql


def test_identity_fallbacks_are_resolved_in_order_without_set_wide_or_join():
    sql = OPTIMIZATION_MIGRATION.read_text(encoding="utf-8")

    assert "parent_api_identity AS" in sql
    assert "variant_api_identity AS" in sql
    assert "name_number_identity AS" in sql
    assert "SELECT * FROM parent_api_identity" in sql
    assert "UNION ALL" in sql
    assert "c.pokemon_tcg_api_id = pcc.pokemon_tcg_api_card_id\n          OR" not in sql


def test_set_refresh_materializes_resolver_once_before_safe_replacement():
    sql = MATERIALIZED_REFRESH_MIGRATION.read_text(encoding="utf-8")

    assert sql.count("get_pokemon_canonical_card_market_prices_latest_for_set(target_set_id)") == 1
    assert "jsonb_agg(to_jsonb(resolved))" in sql
    assert "jsonb_to_recordset(resolved_rows)" in sql
    assert "IF existing_count > 0 AND resolved_count = 0 THEN" in sql


def test_selected_price_foreign_keys_have_covering_indexes():
    sql = INDEX_MIGRATION.read_text(encoding="utf-8")

    assert "(card_variant_id)" in sql
    assert "(condition_id)" in sql
    assert "(legacy_card_id)" in sql
