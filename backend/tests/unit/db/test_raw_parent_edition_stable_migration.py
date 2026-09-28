from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SUPABASE = ROOT / "supabase" / "migrations" / "20260928043000_raw_parent_edition_stable_v1.sql"
BACKEND = ROOT / "backend" / "db" / "migrations" / "20260928043000_raw_parent_edition_stable_v1.sql"
SERVICE_ROLE_GRANT_SUPABASE = ROOT / "supabase" / "migrations" / "20260928052000_grant_edition_history_binding_validator_service_role.sql"
SERVICE_ROLE_GRANT_BACKEND = ROOT / "backend" / "db" / "migrations" / "20260928052000_grant_edition_history_binding_validator_service_role.sql"
SCOPED_LEAF_AUTHORITY_SUPABASE = ROOT / "supabase" / "migrations" / "20260928054500_raw_parent_scoped_leaf_authority_v2.sql"
SCOPED_LEAF_AUTHORITY_BACKEND = ROOT / "backend" / "db" / "migrations" / "20260928054500_raw_parent_scoped_leaf_authority_v2.sql"


def test_migration_copies_are_identical():
    assert SUPABASE.read_text(encoding="utf-8") == BACKEND.read_text(encoding="utf-8")


def test_raw_parent_uses_explicit_market_identities_and_preserves_legacy_rows():
    sql = SUPABASE.read_text(encoding="utf-8")
    assert "pokemon_market_raw_edition_stable_daily_history_v1" in sql
    assert "edition_stable_market_identity_chain_v1" in sql
    assert "pokemon_edition_split_root_sets_v2" in sql
    assert "market_scope IN ('first_edition','unlimited','shadowless')" in sql
    assert "RAW_EDITION_STABLE_GENERIC_VINTAGE_FORBIDDEN" in sql
    assert "legacyGenericVintageExcluded" in sql
    # The migration is additive: it does not rewrite or delete legacy Raw
    # history, which remains available for audit/rollback.
    assert "DELETE FROM public.pokemon_market_index_daily_history" not in sql
    assert "UPDATE public.pokemon_market_index_daily_history" not in sql


def test_raw_parent_surface_reconciles_exact_current_leaves():
    sql = SUPABASE.read_text(encoding="utf-8")
    assert "pokemon_market_set_value_constituents_v1" in sql
    assert "pokemon_market_explorer_surface_constituents_v2" in sql
    assert "RAW_EDITION_STABLE_DUPLICATE_INSTRUMENTS" in sql
    assert "RAW_EDITION_STABLE_LEAF_COUNT_MISMATCH" in sql
    assert "RAW_EDITION_STABLE_LEAF_VALUE_MISMATCH" in sql
    assert "SURFACE_RAW_GENERIC_VINTAGE_LEAF_FORBIDDEN" in sql


def test_raw_parent_history_is_quality_gated_and_history_certified():
    sql = SUPABASE.read_text(encoding="utf-8")
    assert "q.status IN ('READY','LEGACY_VERIFIED')" in sql
    assert "c.history_publishable" in sql
    assert "h.certified_on_date" in sql
    assert "2026-04-23" in sql


def test_edition_history_binding_validator_service_role_grant_is_narrow():
    sql = SERVICE_ROLE_GRANT_SUPABASE.read_text(encoding="utf-8")
    assert sql == SERVICE_ROLE_GRANT_BACKEND.read_text(encoding="utf-8")
    assert "pokemon_market_binding_is_valid_v3" in sql
    assert "TO service_role" in sql
    assert "FROM PUBLIC, anon, authenticated" in sql
    assert "TO anon" not in sql
    assert "TO authenticated" not in sql


def test_raw_parent_scoped_leaves_use_edition_history_v2_directly():
    sql = SCOPED_LEAF_AUTHORITY_SUPABASE.read_text(encoding="utf-8")
    assert sql == SCOPED_LEAF_AUTHORITY_BACKEND.read_text(encoding="utf-8")
    assert "get_pokemon_edition_history_card_prices_as_of_v2" in sql
    assert "identitySource','edition_history_card_prices_as_of_v2'" in sql
    assert "JOIN scoped_market_keys k ON k.market_key=c.market_key" not in sql
    assert "RAW_EDITION_STABLE_LEAF_COUNT_MISMATCH" in sql
    assert "RAW_EDITION_STABLE_LEAF_VALUE_MISMATCH" in sql
