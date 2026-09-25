"""Contracts for explicit vintage Market identities.

The public Market surfaces must never collapse an edition-split vintage root
back to one generic Set identity. The forward migration patches only currently
deployed functions and fails closed if their expected sections drift.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
NAME = "20260924190000_explicit_vintage_market_scopes.sql"
BACK = ROOT / "backend" / "db" / "migrations" / NAME
SUPA = ROOT / "supabase" / "migrations" / NAME
SQL = BACK.read_text(encoding="utf-8")


def test_migration_trees_are_identical():
    assert SUPA.read_text(encoding="utf-8") == SQL


def test_prepared_set_market_key_includes_explicit_scope():
    assert "e->>'marketKey'" in SQL
    assert "'set:' || (e->>'setId') || ':' || (e->>'marketScope')" in SQL
    assert "'marketScope', coalesce(nullif(e->>'marketScope',''),'standard')" in SQL
    assert "'scopeContractVersion', 'pokemon-set-market-scope-v1'" in SQL


def test_scoped_prepared_history_uses_certified_root_scope_not_dashboard():
    assert "pokemon_market_root_set_value_daily_history_v2_shadow" in SQL
    assert "rv.market_scope=p.market_scope" in SQL
    assert "p.market_scope<>'standard'" in SQL
    assert "rv.certified_on_date=true" in SQL
    assert "100.0 * set_value / nullif(base_value,0)" in SQL


def test_standard_history_keeps_existing_dashboard_path():
    assert "pokemon_set_market_dashboard_snapshot_latest" in SQL
    assert "p.market_scope='standard'" in SQL
    assert "rv.market_scope='standard'" in SQL


def test_scoped_constituents_use_root_scope_authority():
    # DB agent's final contract: date-pinned scoped roster, never "latest".
    assert "get_pokemon_market_root_set_card_prices_as_of_v1" in SQL
    assert "get_pokemon_cards_daily_constituents(" in SQL
    assert "market_count" in SQL


def test_lightweight_sync_removes_superseded_generic_set_keys():
    assert "Remove superseded generic or retired scoped Set identities" in SQL
    assert "delete from public.pokemon_market_explorer_prepared_directory_v1" in SQL


def test_rewrites_are_shape_guarded():
    assert "refusing unsafe rewrite" in SQL
    assert "pg_get_functiondef('public.refresh_pokemon_market_explorer_prepared_directory_v1()'" in SQL
    assert "pg_get_functiondef('public.stage_pokemon_market_explorer_prepared_constituents_v1(uuid)'" in SQL
