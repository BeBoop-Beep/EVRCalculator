from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
NAME = "20261002215500_market_explorer_root_standard_roster_source_parity_v1.sql"


def _read(base: str) -> str:
    return (ROOT / base / "migrations" / NAME).read_text()


def test_root_standard_roster_source_parity_migration_is_mirrored():
    assert (ROOT / "supabase" / "migrations" / NAME).read_bytes() == (
        ROOT / "backend" / "db" / "migrations" / NAME
    ).read_bytes()


def test_current_snapshot_fallback_is_strictly_bounded_and_fail_closed():
    sql = _read("supabase")
    primary = sql.index("get_pokemon_market_root_standard_card_prices_as_of_v2")
    fallback = sql.index("get_pokemon_market_root_set_card_prices_latest_v1")
    assert primary < fallback
    assert "p_market_date = v_latest_approved_date" in sql
    assert "v_history_source = 'root_latest_v2_snapshot'" in sql
    assert "count(DISTINCT card_variant_id)" in sql
    assert "count(DISTINCT canonical_card_id)" in sql
    assert "round(v_value, 2) = round(v_expected_value, 2)" in sql
    assert "bool_and(captured_at IS NOT NULL AND captured_at <= p_market_date)" in sql
    assert "root_latest_v2_snapshot_frozen_fallback_v1" in sql


def test_roster_freezer_keeps_security_definer_constrained():
    sql = _read("supabase")
    assert "SECURITY DEFINER" in sql
    assert "SET search_path = ''" in sql
    assert (
        "REVOKE ALL ON FUNCTION "
        "public.freeze_pokemon_market_root_standard_roster_v2(uuid,date)"
    ) in sql
    assert "FROM PUBLIC, anon, authenticated" in sql
    assert "TO service_role" in sql
