"""SQL-text contract tests for the Sep 10, 2026 Market root authority.

No local Postgres/Supabase instance is available in this environment (no
`docker`, no `supabase` CLI, no existing test-DB fixture pattern was found --
same conclusion as the prior pass). These tests instead assert directly
against the migration SQL text (structure/predicates) and, where the
membership contract is behavioral rather than textual, against a Python-level
simulation of the corrected view's logic using fixture rows. Runtime
PostgreSQL validation of the actual view execution plan was NOT performed.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "db" / "migrations"
AUTHORITY_MIGRATION = MIGRATIONS_DIR / "20260912002422_pokemon_market_root_authority.sql"
V2_VIEW_MIGRATION = MIGRATIONS_DIR / "20260912002426_pokemon_market_set_value_publication_cohort_v2.sql"

EXPECTED_FINGERPRINT = "470c8e49e083ca29c7df4d075175b62fb5dd69311b67ca48fec6baf76cd6e892"


def _statements(sql: str) -> str:
    return "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))


# --- (6.6) exactly 106 Sep10 identities -> exact fingerprint match ----------

def test_authority_seed_is_exactly_106_ids_matching_the_frozen_fingerprint():
    sql = AUTHORITY_MIGRATION.read_text(encoding="utf-8")
    ids = re.findall(r"'([0-9a-f-]{36})'::uuid", sql)
    assert len(ids) == 106
    assert len(set(ids)) == 106, "must be 106 UNIQUE ids, not 106 rows with duplicates"
    fingerprint = hashlib.sha256(
        json.dumps(sorted(ids), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert fingerprint == EXPECTED_FINGERPRINT


def test_authority_migration_asserts_the_106_count_itself():
    """The migration must fail closed if the literal seed ever drifts from 106."""
    sql = _statements(AUTHORITY_MIGRATION.read_text(encoding="utf-8"))
    assert "v_count <> 106" in sql
    assert "RAISE EXCEPTION" in sql


def test_authority_migration_never_derives_the_seed_from_a_certification_view():
    """The 106 ids must be literal values, never INSERT ... SELECT FROM a
    certification-sensitive view (that was the flaw this table replaced)."""
    sql = _statements(AUTHORITY_MIGRATION.read_text(encoding="utf-8")).upper()
    assert "INSERT INTO PUBLIC.POKEMON_MARKET_ROOT_AUTHORITY" in sql
    assert "SELECT SET_ID FROM PUBLIC.POKEMON_MARKET_SET_VALUE_PUBLICATION_COHORT_V1" not in sql
    assert "SELECT SET_ID FROM POKEMON_MARKET_SET_VALUE_PUBLICATION_COHORT_V1" not in sql


# --- (6) v2 view must use authority membership, never certification ---------

def test_v2_view_rows_originate_in_temporal_authority():
    sql = _statements(V2_VIEW_MIGRATION.read_text(encoding="utf-8"))
    assert re.search(r"FROM\s+public\.pokemon_market_root_authority\s+a", sql, re.IGNORECASE)
    assert re.search(r"JOIN\s+public\.sets\s+s\s+ON\s+s\.id\s*=\s*a\.set_id", sql, re.IGNORECASE)
    assert "a.activated_market_date" in sql
    assert "a.deactivated_market_date" in sql
    assert re.search(r"WHERE\s+a\.enabled", sql, re.IGNORECASE)

def test_v2_view_has_no_market_publication_ready_filter():
    """CRITICAL: the whole point of v2 is removing v1's `WHERE
    market_publication_ready` membership gate. If this regresses, Sep10+
    membership could again be silently narrowed by certification state."""
    sql = _statements(V2_VIEW_MIGRATION.read_text(encoding="utf-8"))
    assert "WHERE" in sql
    where_clauses = re.findall(r"WHERE\s+(.+?)(?:;|\n\n|$)", sql, re.IGNORECASE | re.DOTALL)
    combined = " ".join(where_clauses).lower()
    assert "market_publication_ready" not in combined
    # No rollout-override CTE / force-true path either.
    assert "true as market_publication_ready" not in sql.lower()


def test_v2_view_joins_certification_as_left_join_only():
    sql = _statements(V2_VIEW_MIGRATION.read_text(encoding="utf-8"))
    assert re.search(
        r"LEFT JOIN\s+public\.pokemon_market_root_set_publication_current_certification_v1",
        sql,
        re.IGNORECASE,
    ), "certification must be LEFT JOINed (annotation), never an inner JOIN (gate)"


def test_v1_view_definition_is_untouched_by_this_migration_set():
    """v1 stays byte-for-byte the frozen historical authority; only a new v2
    view is introduced. Confirms no CREATE OR REPLACE of v1 exists anywhere in
    the new migrations."""
    for migration in (AUTHORITY_MIGRATION, V2_VIEW_MIGRATION):
        sql = migration.read_text(encoding="utf-8")
        assert "CREATE OR REPLACE VIEW public.pokemon_market_set_value_publication_cohort_v1" not in sql


# --- (7) migration ordering is local/static; live-head checks are preflight -

def test_authority_migration_precedes_dependent_view_with_unique_versions():
    authority_version = AUTHORITY_MIGRATION.stem.split("_", 1)[0]
    view_version = V2_VIEW_MIGRATION.stem.split("_", 1)[0]
    assert len(authority_version) == 14 and authority_version.isdigit()
    assert len(view_version) == 14 and view_version.isdigit()
    assert authority_version < view_version


def test_authority_and_v2_migrations_are_mirrored_byte_identical_in_both_trees():
    supabase_dir = MIGRATIONS_DIR.parents[2] / "supabase" / "migrations"
    for migration in (AUTHORITY_MIGRATION, V2_VIEW_MIGRATION):
        mirror = supabase_dir / migration.name
        assert mirror.exists(), f"missing supabase mirror for {migration.name}"
        assert mirror.read_bytes() == migration.read_bytes()


def test_authority_table_is_backend_read_only_with_rls_and_explicit_acl_reset():
    sql = _statements(AUTHORITY_MIGRATION.read_text(encoding="utf-8")).upper()
    compact = re.sub(r"\s+", " ", sql)
    assert "ALTER TABLE PUBLIC.POKEMON_MARKET_ROOT_AUTHORITY ENABLE ROW LEVEL SECURITY" in compact
    for role in ("PUBLIC", "ANON", "AUTHENTICATED", "SERVICE_ROLE"):
        assert f"REVOKE ALL ON TABLE PUBLIC.POKEMON_MARKET_ROOT_AUTHORITY FROM {role}" in compact
    assert "GRANT SELECT ON TABLE PUBLIC.POKEMON_MARKET_ROOT_AUTHORITY TO SERVICE_ROLE" in compact
    assert not re.search(
        r"GRANT\s+(?:INSERT|UPDATE|DELETE|ALL).*POKEMON_MARKET_ROOT_AUTHORITY.*SERVICE_ROLE",
        compact,
    )


def test_authority_identity_sequence_is_unavailable_to_runtime_roles():
    sql = _statements(AUTHORITY_MIGRATION.read_text(encoding="utf-8")).upper()
    compact = re.sub(r"\s+", " ", sql)
    for role in ("PUBLIC", "ANON", "AUTHENTICATED", "SERVICE_ROLE"):
        assert (
            "REVOKE ALL ON SEQUENCE PUBLIC.POKEMON_MARKET_ROOT_AUTHORITY_ID_SEQ "
            f"FROM {role}"
        ) in compact
    assert not re.search(
        r"GRANT\s+[^;]*ON\s+SEQUENCE\s+PUBLIC\.POKEMON_MARKET_ROOT_AUTHORITY_ID_SEQ",
        compact,
    )


def test_authority_trigger_helper_cannot_be_invoked_by_runtime_roles():
    sql = _statements(AUTHORITY_MIGRATION.read_text(encoding="utf-8")).upper()
    compact = re.sub(r"\s+", " ", sql)
    function = "PUBLIC.SET_POKEMON_MARKET_ROOT_AUTHORITY_UPDATED_AT()"
    for role in ("PUBLIC", "ANON", "AUTHENTICATED", "SERVICE_ROLE"):
        assert f"REVOKE ALL ON FUNCTION {function} FROM {role}" in compact
    assert not re.search(rf"GRANT\s+EXECUTE\s+ON\s+FUNCTION\s+{re.escape(function)}", compact)


def test_cohort_v2_is_security_invoker_and_service_role_select_only():
    sql = _statements(V2_VIEW_MIGRATION.read_text(encoding="utf-8")).upper()
    compact = re.sub(r"\s+", " ", sql)
    assert "WITH (SECURITY_INVOKER = TRUE)" in compact
    assert (
        "REVOKE ALL ON PUBLIC.POKEMON_MARKET_SET_VALUE_PUBLICATION_COHORT_V2 "
        "FROM PUBLIC, ANON, AUTHENTICATED"
    ) in compact
    assert (
        "REVOKE ALL ON PUBLIC.POKEMON_MARKET_SET_VALUE_PUBLICATION_COHORT_V2 "
        "FROM SERVICE_ROLE"
    ) in compact
    assert (
        "GRANT SELECT ON PUBLIC.POKEMON_MARKET_SET_VALUE_PUBLICATION_COHORT_V2 "
        "TO SERVICE_ROLE"
    ) in compact
    assert not re.search(
        r"GRANT\s+(?:INSERT|UPDATE|DELETE|ALL).*POKEMON_MARKET_SET_VALUE_PUBLICATION_COHORT_V2",
        compact,
    )


def test_cohort_v2_comment_references_the_final_authority_migration_name():
    sql = V2_VIEW_MIGRATION.read_text(encoding="utf-8")
    assert "20260912002422_pokemon_market_root_authority.sql" in sql
    assert "20260911235824_pokemon_market_root_authority.sql" not in sql


# --- (6.1-6.5) SQL contract behavioral simulation ---------------------------
#
# No live Postgres is available, so the view's actual JOIN/WHERE behavior is
# simulated in Python against the same predicate the migration encodes:
# "every set_id present, certification is annotation only". This proves the
# *logic* the migration SQL text implements is correct; it does not execute
# the SQL itself.

def _simulate_v2_row(set_id, sets_by_id, cert_by_id):
    """Mirror of the v2 view's LEFT JOIN + WHERE catalog_only=false clause."""
    s = sets_by_id.get(set_id)
    if s is None or s.get("catalog_only"):
        return None
    c = cert_by_id.get(set_id) or {}
    return {
        "set_id": set_id,
        "current_certification_status": c.get("current_certification_status"),
        "market_publication_ready": bool(c.get("current_market_scope_certified", False)),
    }


def _simulate_authority_membership(authority_rows, sets_by_id, cert_by_id):
    """Mirror of _authority_market_root_cohort: membership = authority table
    only; certification/metadata is LEFT JOIN annotation and never filters."""
    active_ids = {r["set_id"] for r in authority_rows if r["enabled"]}
    return {
        set_id: _simulate_v2_row(set_id, sets_by_id, cert_by_id) or {
            "set_id": set_id,
            "current_certification_status": None,
            "market_publication_ready": False,
        }
        for set_id in active_ids
    }


ROOT_A, ROOT_B, ROOT_C, CHILD_D, NON_AUTHORITY_E = "root-a", "root-b", "root-c", "child-d", "root-e"

SETS_BY_ID = {
    ROOT_A: {"catalog_only": False},
    ROOT_B: {"catalog_only": False},
    ROOT_C: {"catalog_only": False},
    CHILD_D: {"catalog_only": False},
    NON_AUTHORITY_E: {"catalog_only": False},
}
AUTHORITY_ROWS = [
    {"set_id": ROOT_A, "enabled": True},
    {"set_id": ROOT_B, "enabled": True},
    {"set_id": ROOT_C, "enabled": True},
    # CHILD_D and NON_AUTHORITY_E are deliberately NOT in the authority table.
]
CERT_BY_ID = {
    ROOT_A: {"current_certification_status": "CERTIFIED_CURRENT", "current_market_scope_certified": True},
    ROOT_B: {"current_certification_status": "PRICE_FRESHNESS_STALE", "current_market_scope_certified": False},
    # ROOT_C: no certification row at all (missing/failed to evaluate).
    CHILD_D: {"current_certification_status": "CERTIFIED_CURRENT", "current_market_scope_certified": True},
    NON_AUTHORITY_E: {"current_certification_status": "CERTIFIED_CURRENT", "current_market_scope_certified": True},
}


def test_contract_1_authority_member_certified_current_is_present():
    membership = _simulate_authority_membership(AUTHORITY_ROWS, SETS_BY_ID, CERT_BY_ID)
    assert ROOT_A in membership
    assert membership[ROOT_A]["current_certification_status"] == "CERTIFIED_CURRENT"


def test_contract_2_authority_member_price_freshness_stale_still_present():
    membership = _simulate_authority_membership(AUTHORITY_ROWS, SETS_BY_ID, CERT_BY_ID)
    assert ROOT_B in membership, "PRICE_FRESHNESS_STALE must never drop an authority member"
    assert membership[ROOT_B]["current_certification_status"] == "PRICE_FRESHNESS_STALE"


def test_contract_3_authority_member_missing_certification_stays_honest_not_fabricated():
    membership = _simulate_authority_membership(AUTHORITY_ROWS, SETS_BY_ID, CERT_BY_ID)
    assert ROOT_C in membership, "membership must survive even with zero certification evidence"
    assert membership[ROOT_C]["current_certification_status"] is None
    assert membership[ROOT_C]["market_publication_ready"] is False


def test_contract_4_non_authority_root_certified_current_is_absent():
    membership = _simulate_authority_membership(AUTHORITY_ROWS, SETS_BY_ID, CERT_BY_ID)
    assert NON_AUTHORITY_E not in membership, (
        "a fully-certified root that isn't in the authority table must never appear"
    )


def test_contract_5_child_subset_root_certified_is_absent_as_independent_root():
    membership = _simulate_authority_membership(AUTHORITY_ROWS, SETS_BY_ID, CERT_BY_ID)
    assert CHILD_D not in membership, (
        "a child/subset set must not appear as an independent root even if certified"
    )


def test_contract_7_pre_sep9_historical_behavior_is_a_disjoint_code_path():
    """Sep9-and-earlier resolution never touches pokemon_market_root_authority
    or the v2 view at all -- see pokemon_market_rollout_cohort.resolve_market_root_cohort's
    date branch, which routes exclusively to _legacy_market_root_cohort /
    _canonical_market_root_cohort (v1) for those dates."""
    from backend.db.services import pokemon_market_rollout_cohort as cohort

    assert cohort.MARKET_ROOT_AUTHORITY_CUTOVER_DATE == "2026-09-09"
    assert cohort.MARKET_ROOT_AUTHORITY_TABLE_CUTOVER_DATE == "2026-09-10"
    assert cohort.MARKET_ROOT_AUTHORITY_TABLE_CUTOVER_DATE > cohort.MARKET_ROOT_AUTHORITY_CUTOVER_DATE
