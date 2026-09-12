from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SQL = (ROOT / "backend/db/proposals/sentinel_kernel_v1.sql").read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_proposal_defines_only_internal_sentinel_tables():
    for table in (
        "sentinel_incidents",
        "sentinel_check_state",
        "sentinel_recovery_attempts",
        "sentinel_component_heartbeats",
    ):
        assert f"create table public.{table}" in LOWER


def test_every_sentinel_table_enables_rls():
    for table in (
        "sentinel_incidents",
        "sentinel_check_state",
        "sentinel_recovery_attempts",
        "sentinel_component_heartbeats",
    ):
        assert f"alter table public.{table} enable row level security" in LOWER


def test_proposal_revokes_public_and_client_roles_then_grants_only_service_role():
    assert "from public, anon, authenticated, service_role" in LOWER
    assert "to service_role" in LOWER
    assert "grant select" in LOWER
    assert " to anon" not in LOWER
    assert " to authenticated" not in LOWER


def test_proposal_has_no_security_definer_or_public_function():
    assert "security definer" not in LOWER
    assert "create function" not in LOWER
    assert "create or replace function" not in LOWER


def test_active_incident_fingerprint_is_partial_unique():
    assert "create unique index sentinel_incidents_one_active_fingerprint_uq" in LOWER
    assert "where status in ('open','recovering','escalated')" in LOWER


def test_component_heartbeat_is_latest_state_not_append_only_history():
    assert "create table public.sentinel_component_heartbeats" in LOWER
    assert "primary key (component, host)" in LOWER
    assert "sentinel_component_heartbeats_at_idx" in LOWER


def test_recovery_attempt_contract_prevents_duplicate_incident_runbook_attempt_number():
    assert "create table public.sentinel_recovery_attempts" in LOWER
    assert "status text not null" in LOWER
    assert "check (status in ('started','succeeded','failed','blocked'))" in LOWER
    assert "attempt_number integer not null check (attempt_number >= 1)" in LOWER
    assert "cooldown_until timestamptz" in LOWER
    assert "unique (incident_id, runbook, attempt_number)" in LOWER


def test_recovery_attempts_are_service_role_only_like_other_sentinel_state():
    assert "revoke all on public.sentinel_recovery_attempts" in LOWER
    assert "grant select, insert, update, delete on public.sentinel_recovery_attempts" in LOWER


def test_proposal_is_explicitly_non_deployed():
    assert "proposal only" in LOWER
    assert "does not apply this sql to production" in LOWER
