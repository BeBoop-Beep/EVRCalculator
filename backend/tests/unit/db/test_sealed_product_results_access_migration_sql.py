"""Contract: the raw Stage 1 product results table is backend-private.

Migration 064 is already applied to production, so the lockdown is a FOLLOW-ON
migration rather than an edit to 064. These tests pin the end state both
migrations produce together.
"""

from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[3] / "db" / "migrations"

def _statements(path: Path) -> str:
    """Executable SQL only. Comments explain intent; they are not the contract."""
    lines = [line.split("--", 1)[0] for line in path.read_text(encoding="utf-8").lower().splitlines()]
    return "\n".join(line for line in lines if line.strip())


CREATE_SQL = _statements(MIGRATIONS / "064_create_simulation_sealed_product_results.sql")
ACCESS_SQL = _statements(MIGRATIONS / "065_restrict_simulation_sealed_product_results_to_backend.sql")


def test_public_read_policy_is_dropped():
    assert "drop policy if exists simulation_sealed_product_results_read_policy" in ACCESS_SQL
    # And the follow-on migration must not re-create any permissive policy.
    assert "create policy" not in ACCESS_SQL
    assert "using (true)" not in ACCESS_SQL


def test_anon_and_authenticated_lose_direct_raw_select():
    assert "revoke all on public.simulation_sealed_product_results from anon;" in ACCESS_SQL
    assert "revoke all on public.simulation_sealed_product_results from authenticated;" in ACCESS_SQL
    assert "revoke all on public.simulation_sealed_product_results from public;" in ACCESS_SQL
    # No grant in the access migration may hand read access back to a public role.
    grant_lines = [line for line in ACCESS_SQL.splitlines() if line.strip().startswith("grant")]
    joined = " ".join(grant_lines)
    assert "anon" not in joined
    assert "authenticated" not in joined


def test_rls_remains_enabled_and_service_role_keeps_full_access():
    assert "enable row level security" in ACCESS_SQL
    assert "disable row level security" not in ACCESS_SQL
    assert "grant select, insert, update, delete" in ACCESS_SQL
    assert "to service_role" in ACCESS_SQL


def test_applied_migration_064_is_not_rewritten():
    # 064 shipped to production with the permissive grant; it must still read as
    # what was actually applied, with the correction living in 065.
    assert "grant select on public.simulation_sealed_product_results to anon, authenticated, service_role" in CREATE_SQL
    assert "create policy simulation_sealed_product_results_read_policy" in CREATE_SQL


def test_no_public_product_api_is_created_yet():
    assert "create view" not in ACCESS_SQL
    assert "create or replace view" not in ACCESS_SQL
    assert "create function" not in ACCESS_SQL
