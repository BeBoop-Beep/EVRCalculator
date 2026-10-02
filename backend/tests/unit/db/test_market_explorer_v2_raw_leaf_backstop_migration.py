from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
NAME = "20261002221000_market_explorer_v2_raw_leaf_backstop_v1.sql"


def _read(base: str) -> str:
    return (ROOT / base / "migrations" / NAME).read_text()


def test_raw_leaf_backstop_migration_is_mirrored():
    assert (ROOT / "supabase" / "migrations" / NAME).read_bytes() == (
        ROOT / "backend" / "db" / "migrations" / NAME
    ).read_bytes()


def test_v2_wrapper_repairs_and_reconciles_raw_leaf_sidecar_before_build():
    sql = _read("supabase")
    leaf_check = sql.index("pokemon_market_raw_edition_stable_leaf_history_v1")
    refresh = sql.index("refresh_pokemon_market_raw_edition_stable_leaves_v1")
    ready = sql.index("raw_leaf_sidecar_ready_for_build")
    core = sql.index("publish_pokemon_market_explorer_surface_current_core_v2")
    assert leaf_check < refresh < ready < core
    assert "v_leaf_count<>v_stable_card_count" in sql
    assert "round(v_leaf_value,2)<>round(v_stable_basket_value,2)" in sql
    assert "raw_source_generation_fingerprint=v_stable_fingerprint" in sql
    assert "raw_leaf_sidecar_reconciliation_failed" in sql


def test_v2_wrapper_preserves_publisher_role_security_contract():
    sql = _read("supabase")
    assert "SECURITY DEFINER" in sql
    assert "SET search_path = ''" in sql
    assert (
        "ALTER FUNCTION public.publish_pokemon_market_explorer_surface_current_v2()"
        in sql
    )
    assert "OWNER TO postgres" in sql
    assert "FROM PUBLIC, anon, authenticated" in sql
    assert "TO market_explorer_publisher, service_role" in sql
