from pathlib import Path


def test_artifact_migration_is_private_and_run_scoped():
    sql = Path("backend/db/migrations/070_create_simulation_pack_outcome_artifacts.sql").read_text().lower()
    assert "calculation_run_id uuid primary key" in sql
    assert "on delete cascade" in sql
    assert "payload bytea not null" in sql
    assert "enable row level security" in sql
    assert "revoke all" in sql
    assert "anon, authenticated" in sql
    assert "service_role" in sql
