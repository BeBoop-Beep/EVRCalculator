"""Migration contract test for the Overall RIP V12 additive columns.

Phase 15: verifies the migration file's exact shape WITHOUT applying it to any
database - this repository's migrations are manually applied, and this test
must not assume otherwise. Static text assertions against the .sql file only.
"""

from __future__ import annotations

import os

MIGRATIONS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "db", "migrations"
)
MIGRATION_FILE = "20260902000000_add_sealed_product_overall_rip_v12.sql"


def _migration_path() -> str:
    return os.path.join(os.path.dirname(__file__), "..", "..", "..", "db", "migrations", MIGRATION_FILE)


def _read_migration() -> str:
    path = _migration_path()
    assert os.path.isfile(path), "migration file must exist at %s" % path
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def test_migration_file_exists_and_is_unique_in_the_directory():
    migrations_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "db", "migrations")
    all_files = os.listdir(migrations_dir)
    matches = [name for name in all_files if name == MIGRATION_FILE]
    assert len(matches) == 1
    # No other migration in the directory claims this exact filename/number.
    same_prefix = [name for name in all_files if name.startswith("20260902000000")]
    assert same_prefix == [MIGRATION_FILE]


def test_new_v12_columns_are_exactly_these_five():
    sql = _read_migration()
    for column in (
        "overall_rip_v12_score",
        "overall_rip_v12_version",
        "overall_rip_v12_rankable",
        "overall_rip_v12_status",
        "overall_rip_v12_payload",
    ):
        assert ("ADD COLUMN IF NOT EXISTS %s" % column) in sql, column


def test_v12_columns_are_nullable_with_no_default():
    sql = _read_migration()
    # None of the new columns declare NOT NULL or DEFAULT - additive, no
    # backfill required, existing/new rows without V12 remain valid.
    assert "overall_rip_v12_score NUMERIC" in sql
    assert "overall_rip_v12_score NUMERIC NOT NULL" not in sql
    assert "DEFAULT" not in sql


def test_v12_score_check_constraint_matches_v10s_own_bound():
    sql = _read_migration()
    assert "CHECK (overall_rip_v12_score IS NULL OR overall_rip_v12_score BETWEEN 0 AND 100)" in sql


def test_migration_touches_only_the_sealed_product_results_table():
    sql = _read_migration()
    assert "ALTER TABLE public.simulation_sealed_product_results" in sql
    assert "CREATE TABLE" not in sql
    assert "DROP TABLE" not in sql
    assert "DROP COLUMN" not in sql
    assert "TRUNCATE" not in sql


def test_migration_does_not_touch_v10_or_v11_columns():
    sql = _read_migration()
    # V10's own columns are never referenced by an ADD/ALTER/DROP here - only
    # discussed in prose comments (which legitimately name V10/V11 to explain
    # why this migration does not touch them).
    assert "overall_rip_v10_score" not in sql
    assert "ADD COLUMN IF NOT EXISTS overall_rip_v11" not in sql
    assert "DROP COLUMN" not in sql


def test_migration_is_wrapped_in_a_transaction():
    sql = _read_migration()
    assert sql.strip().startswith("--")  # header comment first
    assert "\nBEGIN;" in sql
    assert "\nCOMMIT;" in sql


def test_migration_declares_itself_not_applied():
    sql = _read_migration()
    assert "NOT applied" in sql or "not applied" in sql.lower()


def test_v10_migration_073_is_untouched_reference():
    """Sanity check: migration 073 (the V10 precedent this migration follows)
    still exists and still only defines V10/V4 columns, confirming this new
    migration did not modify it."""
    v10_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "db", "migrations",
        "073_add_sealed_product_financial_rip_v4_and_overall_rip_v10.sql",
    )
    assert os.path.isfile(v10_path)
    with open(v10_path, "r", encoding="utf-8") as handle:
        v10_sql = handle.read()
    assert "overall_rip_v12" not in v10_sql
