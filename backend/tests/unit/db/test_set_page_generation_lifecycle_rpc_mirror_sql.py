"""Structural contract tests for the set-page generation lifecycle RPC mirror.

Migration 20260908224500_mirror_set_page_generation_lifecycle_rpcs.sql is a
repo-source transcription of three functions that are ALREADY LIVE in
production (applied out-of-band by a party with DB access, not by this repo).
This test file is STATIC TEXT VERIFICATION ONLY: it parses the migration's SQL
source and asserts on token order/presence. It does NOT execute against any
database and cannot prove the transcription is byte-identical to the running
prod function bodies (no MD5/pg_get_functiondef comparison is possible without
live DB access, which this effort does not have).
"""

from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[3] / "db" / "migrations"
MIRROR_SQL = MIGRATIONS / "20260908224500_mirror_set_page_generation_lifecycle_rpcs.sql"


def _sql():
    return MIRROR_SQL.read_text(encoding="utf-8")


def test_mirror_migration_file_exists():
    assert MIRROR_SQL.exists()


# --------------------------------------------------------------------------- #
# validate_pokemon_set_page_snapshot_generation
# --------------------------------------------------------------------------- #
def test_validate_function_signature_and_security():
    sql = _sql()
    assert (
        "CREATE OR REPLACE FUNCTION public.validate_pokemon_set_page_snapshot_generation"
        "(p_generation_id uuid)" in sql
    )
    validate_start = sql.index("CREATE OR REPLACE FUNCTION public.validate_pokemon_set_page_snapshot_generation")
    activate_start = sql.index("CREATE OR REPLACE FUNCTION public.activate_pokemon_set_page_snapshot_generation")
    validate_body = sql[validate_start:activate_start]
    assert "RETURNS jsonb" in validate_body
    assert "LANGUAGE plpgsql" in validate_body
    assert "SECURITY DEFINER" in validate_body
    assert "SET search_path TO ''" in validate_body
    # validate has NO statement_timeout override in the supplied body.
    assert "statement_timeout" not in validate_body


def test_validate_only_runs_against_building_status():
    sql = _sql()
    assert "if not found or g.status<>'building' then" in sql
    assert "generation % is not building" in sql


def test_validate_bad_count_requires_the_contract_key_present_and_mismatched():
    """Confirms Phase 3's precise claim: a row lacking
    'publicCollectorAppealContractV1' can never contribute to `bad`, because
    the `bad` filter's WHERE clause only evaluates the mismatch branch when
    `payload_json?'publicCollectorAppealContractV1'` is true (it is the first
    operand of the `and`, short-circuiting the mismatch checks for rows
    without the key). Carried-forward rows without the key are excluded from
    `bad` by construction, not merely by accident of data.
    """
    sql = _sql()
    bad_filter_start = sql.index("count(*) filter(\n      where payload_json is null")
    bad_filter_end = sql.index(")\n  into collector_count,bad")
    bad_filter = sql[bad_filter_start:bad_filter_end]
    assert "payload_json?'publicCollectorAppealContractV1'\n           and (" in bad_filter
    # The null/non-object branches are unconditional (correctly -- a null or
    # non-object payload is always invalid), but the version/modelRunId
    # mismatch checks are gated behind the key-presence check via `and`.
    assert bad_filter.count("or\n") + bad_filter.count(" or ") >= 1


def test_validate_passed_requires_all_four_conditions():
    sql = _sql()
    assert "actual_count=g.expected_set_count" in sql
    assert "actual_ids=g.expected_set_ids" in sql
    assert "collector_count=g.expected_collector_row_count" in sql
    assert "and bad=0;" in sql


def test_validate_writes_status_and_validation_json_back():
    sql = _sql()
    assert "status=case when passed then 'validated' else 'failed' end" in sql
    assert "validation_passed=passed" in sql
    assert "validation_json=report" in sql


# --------------------------------------------------------------------------- #
# activate_pokemon_set_page_snapshot_generation (live-membership-loss guard)
# --------------------------------------------------------------------------- #
def test_activate_function_signature_and_security():
    sql = _sql()
    activate_start = sql.index("CREATE OR REPLACE FUNCTION public.activate_pokemon_set_page_snapshot_generation")
    wrapper_start = sql.index(
        "CREATE OR REPLACE FUNCTION public.publish_pokemon_public_rip_leaderboard_with_set_pages"
    )
    activate_body = sql[activate_start:wrapper_start]
    assert "RETURNS uuid" in activate_body
    assert "SECURITY DEFINER" in activate_body
    assert "SET search_path TO ''" in activate_body
    assert "SET statement_timeout TO '180s'" in activate_body


def test_activate_requires_validated_or_published_with_passed_validation():
    sql = _sql()
    assert "g.status not in ('validated','published')" in sql
    assert "not g.validation_passed" in sql
    assert "coalesce((g.validation_json->>'passed')::boolean,false)=false" in sql
    assert "generation % is not validated" in sql


def test_activate_completeness_check_precedes_membership_guard_precedes_delete():
    """Static/structural verification of the documented ordering invariant:

        (n <> expected_set_count) check  ---BEFORE--->  missing_live_count check  ---BEFORE--->  DELETE

    This is proven here by source-text offset comparison only. It is NOT a
    live-execution proof -- no database was run against this file.
    """
    sql = _sql()
    completeness_at = sql.index("if n<>g.expected_set_count then")
    membership_select_at = sql.index("select count(*) into missing_live_count")
    membership_check_at = sql.index("if missing_live_count > 0 then")
    delete_at = sql.index("delete from public.pokemon_set_page_snapshot_latest")

    assert completeness_at < membership_select_at < membership_check_at < delete_at


def test_activate_membership_guard_predicate_and_exception_message():
    sql = _sql()
    assert "from public.pokemon_set_page_snapshot_latest live" in sql
    assert "live.set_id is not null" in sql
    assert "not exists (" in sql
    assert "candidate.generation_id=p_generation_id" in sql
    assert "candidate.set_id=live.set_id" in sql
    assert (
        "'generation % omits % currently live set page(s); refusing destructive activation'"
        in sql
    )


def test_activate_a_superset_candidate_yields_zero_missing_live_count_by_construction():
    """Structural argument (not a live-DB run): `missing_live_count` counts
    live.set_id rows with NO matching generation_rows candidate for this
    generation_id. A candidate whose row set is a SUPERSET of (or equal to)
    the live set_id set can never leave a live row unmatched, so
    missing_live_count = 0 and the guard's `if missing_live_count > 0` branch
    is not taken -- activation proceeds past the guard. A SUBSET candidate
    (missing at least one live set_id) leaves that set_id unmatched by the
    `not exists` predicate, so missing_live_count > 0 and the RAISE fires.
    This test only confirms the guard's SQL shape matches that argument; it
    does not execute the predicate against real rows.
    """
    sql = _sql()
    guard = sql[sql.index("select count(*) into missing_live_count"):sql.index("if missing_live_count > 0 then")]
    assert "not exists" in guard
    assert "where candidate.generation_id=p_generation_id" in guard


def test_activate_delete_before_insert_and_pointer_swap():
    sql = _sql()
    delete_at = sql.index("delete from public.pokemon_set_page_snapshot_latest")
    insert_latest_at = sql.index("insert into public.pokemon_set_page_snapshot_latest\n  select set_id")
    pointer_swap_at = sql.index("insert into public.pokemon_set_page_snapshot_current_generation")
    status_update_at = sql.index("update public.pokemon_set_page_snapshot_generations\n  set status='published'")
    assert delete_at < insert_latest_at < pointer_swap_at < status_update_at


# --------------------------------------------------------------------------- #
# publish_pokemon_public_rip_leaderboard_with_set_pages (wrapper)
# --------------------------------------------------------------------------- #
def test_wrapper_function_signature_and_security():
    sql = _sql()
    wrapper_start = sql.index(
        "CREATE OR REPLACE FUNCTION public.publish_pokemon_public_rip_leaderboard_with_set_pages"
    )
    wrapper_body = sql[wrapper_start:]
    assert "p_snapshot jsonb" in wrapper_body
    assert "p_rows jsonb" in wrapper_body
    assert "p_latest jsonb" in wrapper_body
    assert "p_generation_id uuid" in wrapper_body
    assert "RETURNS uuid" in wrapper_body
    assert "SECURITY DEFINER" in wrapper_body
    assert "SET search_path TO ''" in wrapper_body
    assert "SET statement_timeout TO '240s'" in wrapper_body


def test_wrapper_calls_writer_then_activation_in_order():
    sql = _sql()
    writer_call_at = sql.index("public.publish_pokemon_public_rip_leaderboard(\n      p_snapshot,")
    activation_call_at = sql.index("public.activate_pokemon_set_page_snapshot_generation(\n      p_generation_id")
    assert writer_call_at < activation_call_at


def test_wrapper_asserts_activation_returned_the_requested_generation():
    sql = _sql()
    assert "if v_generation_id is distinct from p_generation_id then" in sql
    assert "'set-page activation returned unexpected generation %'" in sql


def test_no_exception_block_anywhere_in_the_mirrored_bodies():
    """No EXCEPTION handler and no dblink/autonomous-transaction extension use
    anywhere in the three mirrored bodies. This is the load-bearing fact for
    the atomicity argument documented in the migration header and restated in
    the final report: an unhandled RAISE EXCEPTION from either the writer RPC
    or the activation RPC propagates out of
    publish_pokemon_public_rip_leaderboard_with_set_pages uncaught, so
    Postgres rolls back the WHOLE implicit transaction -- there is no partial
    commit path.
    """
    executable = _sql().split("BEGIN;", 1)[1].lower()
    assert "exception when" not in executable
    assert "dblink" not in executable
    assert "autonomous" not in executable


def test_migration_is_forward_only_wrapped_in_a_single_transaction():
    sql = _sql()
    assert sql.strip().count("BEGIN;") == 1
    assert sql.strip().endswith("COMMIT;")
