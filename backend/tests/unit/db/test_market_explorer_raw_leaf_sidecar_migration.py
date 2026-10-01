from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NAME = "20261001214000_market_explorer_raw_leaf_sidecar_v1.sql"
SUPABASE = ROOT.parent / "supabase" / "migrations" / NAME
BACKEND = ROOT / "db" / "migrations" / NAME

def _sql():
    return SUPABASE.read_text(encoding="utf-8").lower()

def test_migration_mirrors_match():
    assert SUPABASE.read_bytes() == BACKEND.read_bytes()

def test_sidecar_is_frozen_and_service_role_only():
    sql=_sql()
    assert "pokemon_market_raw_edition_stable_leaf_history_v1" in sql
    assert "primary key (market_date,market_key,canonical_card_id)" in sql
    assert "unique index" in sql and "(market_date,card_variant_id)" in sql
    assert "enable row level security" in sql
    assert "from public,anon,authenticated" in sql

def test_reconstruction_fails_closed_and_uses_two_standard_authorities():
    sql=_sql()
    assert "timestamp_rewind_v1" in sql
    assert "standard_asof_v2" in sql
    assert "edition_asof_v2" in sql
    assert "get_pokemon_market_root_set_card_prices_latest_v1" in sql
    assert "card_variant_price_observations" in sql
    assert "get_pokemon_market_root_standard_card_prices_as_of_v2" in sql
    assert "get_pokemon_edition_history_card_prices_as_of_v2" in sql
    assert "raw_leaf_standard_reconstruction_unresolved" in sql
    assert "raw_leaf_market_reconciliation_failed" in sql
    assert "raw_leaf_total_count_mismatch" in sql
    assert "raw_leaf_total_value_mismatch" in sql

def test_raw_surface_consumes_sidecar_not_partial_set_value_constituents():
    sql=_sql()
    raw=sql.split("create or replace function public.stage_pokemon_market_explorer_raw_surface_v2",1)[1]
    assert "pokemon_market_raw_edition_stable_leaf_history_v1" in raw
    assert "pokemon_market_set_value_constituents_v1" not in raw
    assert "raw_edition_stable_leaf_sidecar_missing_or_stale" in raw
    assert "'leafauthority','pokemon_market_raw_edition_stable_leaf_history_v1'" in raw
