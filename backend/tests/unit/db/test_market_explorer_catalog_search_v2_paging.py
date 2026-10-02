from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
NAME = "20261002090000_market_explorer_catalog_search_v2_paging.sql"


def test_catalog_v2_migration_is_mirrored_byte_for_byte():
    assert (ROOT / "supabase" / "migrations" / NAME).read_bytes() == (
        ROOT / "backend" / "db" / "migrations" / NAME
    ).read_bytes()


def test_catalog_v2_pages_set_context_by_current_price_without_client_recomputation():
    sql = (ROOT / "supabase" / "migrations" / NAME).read_text(encoding="utf-8").lower()
    assert "search_pokemon_market_explorer_catalog_v2" in sql
    assert "p_after integer default 0" in sql
    assert "offset v_after limit v_limit+1" in sql
    assert "order by d.market_price desc,m.card_variant_id" in sql
    assert "order by m.latest_market_price desc,m.sealed_product_id" in sql
    assert "search_pokemon_market_explorer_instruments_v2" in sql
    assert "'nextcursor'" in sql
    assert "set statement_timeout = '2s'" in sql
    assert "to service_role" in sql
    assert "from public,anon,authenticated" in sql
