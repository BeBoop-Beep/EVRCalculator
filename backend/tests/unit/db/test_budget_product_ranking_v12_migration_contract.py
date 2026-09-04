"""Migration contract test for the budget-ranking V12 authority columns
(Gate F, Phase 5). Static text assertions against the .sql file only - this
repository's migrations are manually applied and this test must NOT apply it
to any database.
"""

from __future__ import annotations

import os

MIGRATION_FILE = "20260902010000_add_budget_product_ranking_v12_authority_columns.sql"


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
    same_prefix = [name for name in all_files if name.startswith("20260902010000")]
    assert same_prefix == [MIGRATION_FILE]


def test_new_row_columns_are_present():
    sql = _read_migration()
    for column in (
        "overall_rip_v12_score",
        "overall_rip_v12_rankable",
        "overall_rip_v12_status",
        "chase_accessibility_raw",
        "budget_rank_v12",
        "budget_cohort_size_v12",
    ):
        assert ("ADD COLUMN IF NOT EXISTS %s" % column) in sql, column


def test_new_snapshot_columns_are_present():
    sql = _read_migration()
    for column in (
        "overall_rip_v12_version",
        "chase_accessibility_version",
        "chase_accessibility_transform_version",
        "ranked_under_v12_authority",
    ):
        assert ("ADD COLUMN IF NOT EXISTS %s" % column) in sql, column


def test_columns_are_nullable_with_no_default():
    sql = _read_migration()
    assert "overall_rip_v12_score NUMERIC" in sql
    assert "overall_rip_v12_score NUMERIC NOT NULL" not in sql
    assert "DEFAULT" not in sql


def test_migration_is_additive_only_no_destructive_ddl():
    sql = _read_migration()
    assert "CREATE TABLE" not in sql
    assert "DROP TABLE" not in sql
    assert "DROP COLUMN" not in sql
    assert "TRUNCATE" not in sql
    assert "ALTER COLUMN" not in sql


def test_migration_does_not_touch_v10_columns():
    sql = _read_migration()
    # V10's own columns are only ever referenced in prose comments explaining
    # why this migration does not touch them - never in an ADD/ALTER/DROP.
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        assert "overall_rip_v10_score" not in stripped
        assert "budget_rank INTEGER" not in stripped
        assert "budget_tier TEXT" not in stripped


def test_migration_touches_only_the_two_budget_ranking_tables():
    sql = _read_migration()
    assert "ALTER TABLE public.budget_product_ranking_snapshots" in sql
    assert "ALTER TABLE public.budget_product_ranking_rows" in sql
    alter_lines = [l for l in sql.splitlines() if l.strip().startswith("ALTER TABLE")]
    tables = {l.split("ALTER TABLE")[1].strip() for l in alter_lines}
    assert tables == {"public.budget_product_ranking_snapshots", "public.budget_product_ranking_rows"}


def test_migration_is_wrapped_in_a_transaction():
    sql = _read_migration()
    assert "\nBEGIN;" in sql
    assert "\nCOMMIT;" in sql


def test_migration_declares_itself_not_applied():
    sql = _read_migration()
    assert "not been applied" in sql or "NOT been applied" in sql or "not applied" in sql.lower()
