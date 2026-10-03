from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MIGRATION = "20261002184600_market_explorer_v2_publisher_role_acl_fix.sql"


def _read(tree: str) -> str:
    return (ROOT / tree / "migrations" / MIGRATION).read_text(encoding="utf-8").lower()


def test_market_explorer_v2_publisher_acl_fix_is_mirrored():
    assert _read("backend/db") == _read("supabase")


def test_guarded_direct_publisher_can_execute_v2_handoff_without_broad_acl():
    sql = _read("supabase")
    fn = "public.publish_pokemon_market_explorer_surface_current_v2()"
    assert f"alter function {fn}\n  security definer" in sql
    assert "owner to postgres" in sql
    assert "to service_role, market_explorer_publisher" in sql
    assert "from public, anon, authenticated" in sql
    assert "publish_pokemon_market_explorer_surface_current_core_v2" not in sql
