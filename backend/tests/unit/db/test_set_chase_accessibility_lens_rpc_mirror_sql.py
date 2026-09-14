"""Structural contract tests for the 20260908223000 Set lens RPC mirror.

setRipV1.chaseAccessibility was dropped from the compact Set lens projection
(project_pokemon_rankings_set_target) when 20260906055315 added the V11/V12
fields, causing the Rankings -> Sets table's Chase Accessibility column to
render "Unavailable" for every set. This migration restores the block. This
test file is STATIC TEXT VERIFICATION ONLY: it does not execute against any
database.
"""

from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[3] / "db" / "migrations"
SUPABASE_MIGRATIONS = Path(__file__).resolve().parents[4] / "supabase" / "migrations"
MIRROR_SQL = MIGRATIONS / "20260908223000_add_set_chase_accessibility_to_rankings_sets_lens_rpc.sql"
SUPABASE_SQL = SUPABASE_MIGRATIONS / "20260908223000_add_set_chase_accessibility_to_rankings_sets_lens_rpc.sql"
PRIOR_SQL = MIGRATIONS / "20260906055315_add_v12_v11_to_rankings_sets_lens_rpc.sql"


def _sql():
    return MIRROR_SQL.read_text(encoding="utf-8")


def test_mirror_migration_file_exists():
    assert MIRROR_SQL.exists()


def test_backend_and_supabase_migrations_are_identical():
    assert SUPABASE_SQL.exists()
    assert MIRROR_SQL.read_text(encoding="utf-8") == SUPABASE_SQL.read_text(encoding="utf-8")


def test_prior_migration_is_not_edited():
    assert PRIOR_SQL.exists()
    prior_sql = PRIOR_SQL.read_text(encoding="utf-8")
    assert "chaseAccessibility" not in prior_sql


def test_projects_set_rip_chase_accessibility_block():
    sql = _sql()
    assert "p_target#>'{setRipV1,chaseAccessibility}'" in sql
    for field in [
        "value", "percent", "status", "version", "chaseDepth", "mappedHcMass",
        "modelScore", "publicScore", "setRank", "setCohortSize", "cohortId",
    ]:
        assert f"'{field}'" in sql


def test_preserves_existing_set_rip_and_v11_v12_fields():
    sql = _sql()
    assert "'score','tier','rank','cohortSize','rankable','methodologyVersion'" in sql
    assert "overallRipV12" in sql
    assert "financialRipV4" in sql
    assert "publicRipContractV11" in sql


def test_does_not_recompute_chase_accessibility():
    """This is a pure projection of the existing authoritative shape - no
    CASE/computed logic on chase accessibility belongs in this RPC, only key
    selection via project_rankings_json_keys."""
    sql = _sql()
    assert "CASE" not in sql
    assert "project_rankings_json_keys(p_target#>'{setRipV1,chaseAccessibility}'" in sql


def test_grants_unchanged():
    sql = _sql()
    assert "REVOKE ALL ON FUNCTION public.project_pokemon_rankings_set_target(JSONB) FROM PUBLIC, anon, authenticated;" in sql
    assert "GRANT EXECUTE ON FUNCTION public.project_pokemon_rankings_set_target(JSONB) TO service_role;" in sql
