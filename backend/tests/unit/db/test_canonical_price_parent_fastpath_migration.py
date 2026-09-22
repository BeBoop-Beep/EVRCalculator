from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
NAME = "20260921193000_optimize_canonical_price_parent_identity.sql"


def _sql(path: str) -> str:
    return (ROOT / path / NAME).read_text(encoding="utf-8")


def test_parent_identity_fastpath_migration_mirrors_are_identical():
    assert _sql("backend/db/migrations") == _sql("supabase/migrations")


def test_fastpath_is_narrow_and_keeps_vintage_fallback():
    sql = _sql("backend/db/migrations").lower()
    assert "pokemon_market_explorer_card_current_metadata" in sql
    assert "identity_basis is distinct from 'parent_pokemon_tcg_api_id'" in sql
    assert "metadata.identity_basis = 'parent_pokemon_tcg_api_id'" in sql
    assert "get_pokemon_canonical_card_market_prices_latest_for_set_v2_shadow" in sql
    assert "public.is_pokemon_market_instrument_catalog_role(canonical.catalog_role)" in sql


def test_fastpath_preserves_canonical_variant_ranking_inputs():
    sql = _sql("backend/db/migrations").lower()
    assert "pokemon_canonical_card_variant_preferences_v2" in sql
    assert "card_variant_price_current_v2" in sql
    assert "last_observed_date desc nulls last" in sql
    assert "last_observation_created_at desc nulls last" in sql
    assert "metadata.special_type is null" in sql
    assert "metadata.printing_type='reverse-holo'" in sql
