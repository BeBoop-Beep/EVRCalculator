from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SUPABASE_MIGRATION = "20260830014500_harden_operational_alert_permissions.sql"
BACKEND_MIGRATION = "076_harden_operational_alert_permissions.sql"
FUNCTIONS = (
    "queue_scrape_failure_alert",
    "queue_scrape_run_alert",
    "queue_scrape_run_ratio_alerts",
    "queue_stuck_scrape_run_alerts",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_operational_alert_migrations_are_mirrored():
    supabase = _read(ROOT / "supabase" / "migrations" / SUPABASE_MIGRATION)
    backend = _read(ROOT / "backend" / "db" / "migrations" / BACKEND_MIGRATION)
    backend_without_mirror_comment = "\n".join(backend.splitlines()[1:]).lstrip()
    assert supabase.rstrip() == backend_without_mirror_comment.rstrip()


def test_alert_table_is_private_and_rls_stays_enabled():
    sql = _read(ROOT / "supabase" / "migrations" / SUPABASE_MIGRATION)
    assert "ALTER TABLE public.alert_events ENABLE ROW LEVEL SECURITY;" in sql
    assert "DROP POLICY IF EXISTS alert_events_public_access" in sql
    for role in ("PUBLIC", "anon", "authenticated"):
        assert f"REVOKE ALL ON TABLE public.alert_events FROM {role};" in sql
    assert (
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.alert_events "
        "TO service_role;"
    ) in sql


def test_alert_queue_functions_are_service_role_only_with_safe_search_path():
    sql = _read(ROOT / "supabase" / "migrations" / SUPABASE_MIGRATION)
    for function in FUNCTIONS:
        signature = f"public.{function}()"
        assert (
            f"ALTER FUNCTION {signature}\n  SET search_path = pg_catalog, public;"
        ) in sql
        assert (
            f"REVOKE EXECUTE ON FUNCTION {signature}\n"
            "  FROM PUBLIC, anon, authenticated;"
        ) in sql
        assert f"GRANT EXECUTE ON FUNCTION {signature} TO service_role;" in sql
    assert "SECURITY DEFINER" not in sql


def test_legacy_alert_setup_cannot_recreate_public_access():
    sql = _read(ROOT / "backend" / "docs" / "sqlSetUps" / "SQL_ALERT_SETUP.sql")
    assert "CREATE POLICY alert_events_public_access" not in sql
    for role in ("PUBLIC", "anon", "authenticated"):
        assert f"REVOKE ALL ON TABLE public.alert_events FROM {role};" in sql
    assert (
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.alert_events "
        "TO service_role;"
    ) in sql
