"""Structural contract tests for the 20260909030230 publish RPC timeout mirror.

Migration 20260909030230_repair_public_rip_publish_rpc_v12.sql documents a
live production repair (statement_timeout='60s' added to
publish_pokemon_public_rip_leaderboard) applied out-of-band by a party with
DB access, not by this repo. This test file is STATIC TEXT VERIFICATION
ONLY: it does not execute against any database.
"""

from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[3] / "db" / "migrations"
MIRROR_SQL = MIGRATIONS / "20260909030230_repair_public_rip_publish_rpc_v12.sql"
V12_SQL = MIGRATIONS / "078_update_public_rip_rpc_to_v12.sql"


def _sql():
    return MIRROR_SQL.read_text(encoding="utf-8")


def test_mirror_migration_file_exists():
    assert MIRROR_SQL.exists()


def test_078_is_not_edited():
    """078 stays the historical record; this is a forward-only CREATE OR
    REPLACE layered on top of it, never a rewrite of 078 itself."""
    assert V12_SQL.exists()
    v12_sql = V12_SQL.read_text(encoding="utf-8")
    assert "overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5" in v12_sql
    assert "statement_timeout" not in v12_sql


def test_adds_statement_timeout_without_touching_identity_constants():
    sql = _sql()
    assert "SET statement_timeout = '60s'" in sql
    # Every V12 identity constant from 078 must be preserved verbatim.
    assert "overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5" in sql
    assert "public_rip_contract_v11" in sql
    assert "financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5" in sql
    assert "collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2" in sql


def test_no_v10_fallback_introduced():
    sql = _sql()
    assert "overall_rip_v10" not in sql
    assert "public_rip_contract_v10" not in sql


def test_security_definer_and_grants_preserved():
    sql = _sql()
    assert "SECURITY DEFINER" in sql
    assert "SET search_path = public" in sql
    assert "REVOKE ALL ON FUNCTION public.publish_pokemon_public_rip_leaderboard" in sql
    assert "GRANT EXECUTE ON FUNCTION public.publish_pokemon_public_rip_leaderboard" in sql
    assert "TO service_role" in sql


def test_fail_closed_validation_preserved():
    sql = _sql()
    # Cohort completeness, rank contiguity, and bidirectional set parity
    # checks from 078 must all still be present.
    assert "incomplete RIP cohort" in sql
    assert "canonical V12 ranks are not contiguous 1..%" in sql
    assert "canonical V12 ranked target IDs are missing from the history rows" in sql
    assert "RIP history rows contain % set(s) that are not canonical V12 ranked targets" in sql


def test_not_intended_to_be_applied_by_this_effort():
    sql = _sql()
    assert "DO NOT RUN THIS AGAINST ANY DATABASE FROM THIS BRANCH" in sql
