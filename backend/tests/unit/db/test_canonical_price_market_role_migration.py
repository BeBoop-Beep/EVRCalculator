from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
NAME = "20260917194000_filter_canonical_price_resolver_market_roles.sql"


def _sql(path: str) -> str:
    return (ROOT / path / NAME).read_text(encoding="utf-8")


def test_migration_mirrors_are_identical():
    assert _sql("backend/db/migrations") == _sql("supabase/migrations")


def test_canonical_price_public_resolver_filters_by_market_instrument_authority():
    sql = _sql("backend/db/migrations").lower()
    assert "create or replace function public.get_pokemon_canonical_card_market_prices_latest_for_set(" in sql
    assert "get_pokemon_canonical_card_market_prices_latest_for_set_v2_shadow" in sql
    assert "join public.pokemon_canonical_cards" in sql
    assert "public.is_pokemon_market_instrument_catalog_role(canonical.catalog_role)" in sql


def test_price_selection_logic_stays_in_v2_shadow_resolver():
    sql = _sql("backend/db/migrations").lower()
    assert "card_variant_price_current_v2" not in sql
    assert "row_number() over" not in sql
    assert "delete from public.pokemon_canonical_cards" not in sql
    assert "update public.pokemon_canonical_cards" not in sql
