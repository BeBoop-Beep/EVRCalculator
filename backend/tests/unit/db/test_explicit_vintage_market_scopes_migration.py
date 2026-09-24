"""Contracts for explicit vintage Market-tab / Explorer edition scopes."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
NAME = "20260924160000_explicit_vintage_market_scopes_v1.sql"
BACK = ROOT / "backend" / "db" / "migrations" / NAME
SUPA = ROOT / "supabase" / "migrations" / NAME
SQL = BACK.read_text(encoding="utf-8")


def test_migration_trees_are_identical():
    assert SUPA.read_text(encoding="utf-8") == SQL


def test_scope_reader_filters_edition_before_selection():
    assert "get_pokemon_market_set_scope_constituents_v1" in SQL
    assert "meta.edition = rs.edition" in SQL
    assert "partition by ec.canonical_card_id" in SQL
    assert "pokemon_market_price_intervals_v2_shadow" in SQL
    assert "pokemon_market_explorer_card_current_metadata" in SQL


def test_scope_reader_is_least_privilege_and_fixed_path():
    assert "security invoker" in SQL
    assert "set search_path = ''" in SQL
    assert "from public, anon, authenticated" in SQL
    assert "to service_role" in SQL


def test_prepared_refresh_uses_snapshot_market_key_and_scope_history():
    assert "coalesce(nullif(e->>'marketKey','')" in SQL
    assert "'marketScope', coalesce(nullif(e->>'marketScope',''), 'standard')" in SQL
    assert "pokemon_market_root_set_value_daily_history_v2_shadow" in SQL
    assert "Edition-scoped vintage Set markets" in SQL
    assert "100.0 * set_value / nullif(base_value,0)" in SQL


def test_prepared_constituents_dispatch_scoped_markets_to_scope_reader():
    assert "get_pokemon_market_set_scope_constituents_v1(" in SQL
    assert "coalesce(d.metadata->>'marketScope','standard') <> 'standard'" in SQL
    assert "No certified Set market value exists for this explicit market scope" in SQL
