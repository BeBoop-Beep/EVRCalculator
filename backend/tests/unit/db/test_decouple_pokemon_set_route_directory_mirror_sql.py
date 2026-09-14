"""Structural contract tests for the 20260909030411 route-directory decouple.

Migration 20260909030411_decouple_pokemon_set_route_directory_from_rip_
publication.sql documents a live production repair (get_pokemon_set_route_
directory now driven by canonical public.sets root-set membership instead of
Rankings publication membership) applied out-of-band by a party with DB
access, not by this repo. This test file is STATIC TEXT VERIFICATION ONLY: it
does not execute against any database, and the SQL text here is a
reconstruction of the described live semantics (see the migration file's own
provenance note), not a verified byte-for-byte transcription.

CATALOG/ROUTE MEMBERSHIP != RIP ELIGIBILITY != MARKET ELIGIBILITY: these
tests exist specifically to prevent this RPC from ever again gating base
route membership on RIP simulation support or Rankings publication cohort
membership.
"""

from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[3] / "db" / "migrations"
DECOUPLE_SQL = MIGRATIONS / "20260909030411_decouple_pokemon_set_route_directory_from_rip_publication.sql"
ORIGINAL_SQL = MIGRATIONS / "20260828014500_create_pokemon_set_route_directory_rpc.sql"


def _sql():
    return DECOUPLE_SQL.read_text(encoding="utf-8")


def test_mirror_migration_file_exists():
    assert DECOUPLE_SQL.exists()


def test_original_migration_is_not_edited():
    """20260828014500 stays the historical (Rankings-membership) record;
    this is a forward-only CREATE OR REPLACE, never a rewrite of it."""
    assert ORIGINAL_SQL.exists()
    original_sql = ORIGINAL_SQL.read_text(encoding="utf-8")
    assert "from authority," in original_sql or "FROM authority," in original_sql.replace(
        "from authority,", "FROM authority,"
    )


def test_membership_driven_by_canonical_sets_not_rankings_authority():
    sql = _sql()
    # The base row source (root_sets) must come from public.sets, filtered
    # to root (non-subset) membership -- the SAME predicate the Pokemon Sets
    # catalog uses.
    assert "FROM public.sets s" in sql
    assert "COALESCE(s.is_subset, false) = false" in sql

    # The Rankings authority/published CTE must be present ONLY as an
    # optional LEFT JOIN supplement for display fields, never as the driving
    # FROM of the final SELECT.
    assert "LEFT JOIN published p ON p.target_id = r.id::text" in sql
    final_select_start = sql.rindex("SELECT\n    r.ordinal")
    final_select_body = sql[final_select_start:]
    assert "FROM root_sets r" in final_select_body


def test_a_root_set_absent_from_rankings_publication_still_resolves():
    """A canonical root set with no row in the Rankings `published` CTE
    (unsupported RIP simulation, or simply not (re)published yet) must still
    appear in root_sets and therefore still get an ordinal/route -- it is
    only the pack_score/pack_rank/pack_tier/relative_pack_score/
    ranked_set_count columns that come back null for it, via LEFT JOIN.
    """
    sql = _sql()
    assert "LEFT JOIN published p" in sql
    # A plain (inner) join to `published` would silently drop unsupported
    # sets from the directory -- that is exactly the bug being fixed.
    assert "JOIN published p ON" not in sql.replace("LEFT JOIN published p ON", "")


def test_security_invoker_and_service_role_only_grants():
    sql = _sql()
    assert "SECURITY INVOKER" in sql
    assert "REVOKE ALL ON FUNCTION public.get_pokemon_set_route_directory(integer) FROM public" in sql
    assert "REVOKE EXECUTE ON FUNCTION public.get_pokemon_set_route_directory(integer) FROM anon, authenticated" in sql
    assert "GRANT EXECUTE ON FUNCTION public.get_pokemon_set_route_directory(integer) TO service_role" in sql


def test_ceiling_raised_to_200():
    sql = _sql()
    assert "p_limit integer default 200" in sql
    assert "least(coalesce(p_limit, 200), 200)" in sql


def test_not_intended_to_be_applied_by_this_effort():
    sql = _sql()
    assert "DO NOT RUN THIS AGAINST ANY DATABASE FROM THIS BRANCH" in sql
    assert "no verbatim" in sql.lower() or "NOT a byte-for-byte" in sql
