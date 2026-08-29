from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MIGRATION_NAME = "20260829170127_harden_paid_analytics_data_boundary.sql"


def _migration_text(location: Path) -> str:
    return (location / MIGRATION_NAME).read_text(encoding="utf-8")


def test_mirrored_migrations_are_identical():
    supabase = _migration_text(ROOT / "supabase" / "migrations")
    backend = _migration_text(ROOT / "backend" / "db" / "migrations")
    assert supabase.rstrip() == backend.rstrip()


def test_raw_snapshots_and_roles_are_explicitly_hardened():
    sql = _migration_text(ROOT / "supabase" / "migrations")
    for relation in (
        "pokemon_set_page_snapshot_latest",
        "pokemon_set_market_dashboard_snapshot_latest",
        "pokemon_explore_rankings_snapshot_latest",
        "pokemon_rip_stats_snapshot_latest",
        "simulation_derived_metrics",
        "simulation_latest_by_target",
    ):
        assert f"'{relation}'" in sql

    assert "FROM PUBLIC, anon, authenticated" in sql
    assert "TO service_role" in sql
    assert "DROP POLICY IF EXISTS" in sql

    sealed_market_sql = (
        ROOT
        / "supabase"
        / "migrations"
        / "20260829170301_harden_sealed_market_breadth_snapshot.sql"
    ).read_text(encoding="utf-8")
    assert "pokemon_set_sealed_market_snapshot_latest" in sealed_market_sql


def test_no_public_payload_is_built_by_subtracting_paid_keys():
    sql = _migration_text(ROOT / "supabase" / "migrations").lower()
    assert "payload_json -" not in sql
    assert "ranking_payload_json -" not in sql
