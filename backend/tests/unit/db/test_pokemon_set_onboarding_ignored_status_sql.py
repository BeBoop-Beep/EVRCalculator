from pathlib import Path

SQL = Path(
    "backend/db/migrations/055_add_pokemon_set_onboarding_ignored_status.sql"
).read_text(encoding="utf-8")
MIGRATION_052 = Path(
    "backend/db/migrations/052_create_pokemon_set_onboarding_jobs.sql"
).read_text(encoding="utf-8")


def test_ignored_is_an_allowed_status():
    assert "'failed','ignored'" in SQL
    assert "pokemon_set_onboarding_jobs_status_check" in SQL


def test_already_applied_052_migration_is_not_edited():
    assert "'ignored'" not in MIGRATION_052


def test_claim_rpc_cannot_hand_out_ignored_baseline_rows():
    assert "WHERE status <> 'ignored'" in SQL
    # Baseline rows must not be reachable through the runnable set, the force-retry
    # escape hatch, or direct p_job_id targeting.
    assert "status IN ('detected','ready','retry')" in SQL
    assert "p_force_retry AND status IN ('waiting','manual_review')" in SQL


def test_claim_rpc_retains_lease_and_attempt_semantics():
    assert "FOR UPDATE SKIP LOCKED" in SQL
    assert "last_error_code = 'lease_expired'" in SQL
    assert "CASE WHEN status = 'retry' THEN 1 ELSE 0 END" in SQL
