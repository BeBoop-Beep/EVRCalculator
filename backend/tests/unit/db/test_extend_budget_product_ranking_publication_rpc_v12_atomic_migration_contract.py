"""Migration contract test for the V12 budget-ranking publication RPC
extension (Gate F physical persistence closure). Static text assertions
against the .sql file only - this repository's migrations are manually
applied and this test must NOT apply it to any database.
"""

from __future__ import annotations

import os

MIGRATION_FILE = "20260903224637_extend_budget_product_ranking_publication_rpc_v12_atomic.sql"

V12_SNAPSHOT_FIELDS = (
    "overall_rip_v12_version",
    "chase_accessibility_version",
    "chase_accessibility_transform_version",
    "ranked_under_v12_authority",
)
V12_ROW_FIELDS = (
    "overall_rip_v12_score",
    "overall_rip_v12_rankable",
    "overall_rip_v12_status",
    "chase_accessibility_raw",
    "budget_rank_v12",
    "budget_cohort_size_v12",
)
LOCKED_IDENTITIES = (
    "overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5",
    "financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5",
    "collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2",
    "chase_accessibility_v1_hc_value_squared_modeled_probability",
    "chase_accessibility_overall_score_v1_saturating_k002",
)


def _migration_path() -> str:
    return os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "db", "migrations", MIGRATION_FILE
    )


def _read_migration() -> str:
    path = _migration_path()
    assert os.path.isfile(path), "migration file must exist at %s" % path
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def test_migration_file_exists_and_is_unique():
    migrations_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "db", "migrations")
    all_files = os.listdir(migrations_dir)
    matches = [name for name in all_files if name == MIGRATION_FILE]
    assert len(matches) == 1
    same_prefix = [name for name in all_files if name.startswith("20260903224637")]
    assert same_prefix == [MIGRATION_FILE]


def test_replaces_outer_wrapper_only():
    sql = _read_migration()
    create_lines = [l.strip() for l in sql.splitlines() if l.strip().startswith("CREATE OR REPLACE FUNCTION")]
    assert len(create_lines) == 1
    assert "public.publish_budget_product_ranking_snapshot(" in create_lines[0]
    assert "without_strategy_ev" not in create_lines[0]


def test_does_not_replace_or_drop_inner_helper():
    sql = _read_migration()
    assert "CREATE OR REPLACE FUNCTION public.publish_budget_product_ranking_snapshot_without_strategy_ev" not in sql
    assert "DROP FUNCTION" not in sql


def test_retains_call_to_inner_helper():
    sql = _read_migration()
    assert "public.publish_budget_product_ranking_snapshot_without_strategy_ev(p_snapshot, p_rows)" in sql


def test_retains_expected_value_handling():
    sql = _read_migration()
    assert "expected_value" in sql
    assert "a ranked budget row is missing its real strategy expected value" in sql
    assert "persisted strategy expected values do not reconcile with publication rows" in sql


def test_contains_all_ten_v12_persisted_fields():
    sql = _read_migration()
    for field in V12_SNAPSHOT_FIELDS + V12_ROW_FIELDS:
        assert field in sql, field


def test_v12_behavior_gated_on_ranked_under_v12_authority_flag():
    sql = _read_migration()
    assert "COALESCE((p_snapshot->>'ranked_under_v12_authority')::BOOLEAN, FALSE)" in sql


def test_v12_branch_requires_exact_locked_identities():
    sql = _read_migration()
    for identity in LOCKED_IDENTITIES:
        assert identity in sql, identity


def test_contains_v12_rank_contiguity_validation():
    sql = _read_migration()
    assert "persisted V12 budget ranking cohort size or rank contiguity validation failed" in sql
    assert "budget_rank_v12" in sql and "budget_cohort_size_v12" in sql


def test_v12_persistence_happens_after_inner_helper_and_before_return():
    sql = _read_migration()
    call_idx = sql.index("public.publish_budget_product_ranking_snapshot_without_strategy_ev(p_snapshot, p_rows)")
    v12_idx = sql.index("v_ranked_v12 := COALESCE")
    return_idx = sql.rindex("RETURN v_snapshot_id;")
    assert call_idx < v12_idx < return_idx


def test_migration_does_not_recreate_or_drop_any_table():
    sql = _read_migration()
    assert "CREATE TABLE" not in sql
    assert "DROP TABLE" not in sql
    assert "TRUNCATE" not in sql


def test_preserves_security_definer_and_service_role_execution_posture():
    sql = _read_migration()
    assert "SECURITY DEFINER" in sql
    assert "REVOKE ALL ON FUNCTION public.publish_budget_product_ranking_snapshot(JSONB, JSONB) FROM PUBLIC, anon, authenticated;" in sql
    assert "GRANT EXECUTE ON FUNCTION public.publish_budget_product_ranking_snapshot(JSONB, JSONB) TO service_role;" in sql


def test_migration_is_wrapped_in_a_transaction():
    sql = _read_migration()
    assert "\nBEGIN;" in sql
    assert "\nCOMMIT;" in sql


def test_migration_declares_itself_not_applied_here():
    sql = _read_migration()
    lowered = sql.lower()
    assert "must not be" in lowered or "not be (re)applied" in lowered
    assert "already been applied" in lowered
    assert "20260903224637" in sql
