"""Behavioural tests for the canonical simulation business date.

WHAT THIS FILE REPLACES
-----------------------
The previous version asserted that certain SQL substrings existed and then
"tested" the Phoenix rollover with ``{promoted for _ in instants} == {promoted}``
- a set comprehension that ignores its own loop variable and is therefore true
for every possible input. It could not have failed. It did not test partitioning
at all, which is precisely where the defect lived.

WHAT IS ACTUALLY PROVEN HERE
----------------------------
The ``ranked`` CTE is EXTRACTED FROM THE SHIPPED MIGRATION FILE, mechanically
translated to SQLite, and EXECUTED against fixture rows. If someone moves the
COALESCE out of the PARTITION BY, these tests fail, because the executed SQL is
the migration's SQL rather than a hand-copy of it.

SQLite is a semantic proxy, not PostgreSQL. The same four fixtures were also
executed read-only against the production PostgreSQL 17.6 instance (fixture
VALUES rows inside a CTE; no table read, no write, no DDL) and produced
identical results - the output is recorded in
docs/RELIABILITY_BOUNDARY_2a51e351.md.
"""

import re
import sqlite3
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
SUPABASE_SQL_PATH = (
    REPO_ROOT
    / "supabase"
    / "migrations"
    / "20260901020000_add_calculation_run_market_date.sql"
)
BACKEND_SQL_PATH = (
    REPO_ROOT / "backend" / "db" / "migrations" / "076_add_calculation_run_market_date.sql"
)

SQL = SUPABASE_SQL_PATH.read_text(encoding="utf-8")

BUSINESS_DATE = "COALESCE(cr_1.market_date, (cr_1.created_at)::date)"


def _executable_sql():
    """The migration text with comment lines removed.

    The header comment deliberately quotes the rejected design and names the
    roles the migration must NOT grant, so substring checks have to run against
    executable SQL only.
    """
    return "\n".join(
        line for line in SQL.splitlines() if not line.lstrip().startswith("--")
    )


# ---------------------------------------------------------------------------
# Extraction + translation of the SHIPPED ranked CTE
# ---------------------------------------------------------------------------

def _extract_ranked_cte(sql):
    """Return the body of ``WITH ranked AS ( ... )`` from the migration."""
    start = sql.index("WITH ranked AS (")
    cursor = sql.index("(", start)
    depth = 0
    for index in range(cursor, len(sql)):
        if sql[index] == "(":
            depth += 1
        elif sql[index] == ")":
            depth -= 1
            if depth == 0:
                return sql[cursor + 1 : index]
    raise AssertionError("unbalanced parentheses in the ranked CTE")


def _to_sqlite(pg_sql):
    """Mechanically rewrite the PostgreSQL ranked CTE for SQLite execution.

    Only dialect spelling is rewritten. The partition key, the ordering and the
    COALESCE are carried through untouched, which is the whole point.
    """
    sqlite_sql = re.sub(r"\((cr_1\.created_at)\)::date", r"date(\1)", pg_sql)
    sqlite_sql = re.sub(
        r"=\s*ANY\s*\(ARRAY\[(.*?)\]\)",
        lambda match: "IN (" + match.group(1).replace("::text", "") + ")",
        sqlite_sql,
        flags=re.DOTALL,
    )
    return sqlite_sql


RANKED_CTE_SQLITE = _to_sqlite(_extract_ranked_cte(SQL))


FIXTURES = [
    # (id, target_type, target_id, created_at UTC, market_date)
    ("A", "set", "s1", "2026-08-31T23:59:00", "2026-08-31"),
    ("B", "set", "s1", "2026-09-01T00:01:00", "2026-08-31"),
    ("C", "set", "s2", "2026-09-01T02:00:00", "2026-08-31"),
    ("D", "set", "s2", "2026-09-01T20:00:00", "2026-09-01"),
    ("E", "set", "s3", "2026-08-31T23:59:00", None),
    ("F", "set", "s3", "2026-09-01T00:01:00", None),
    ("G", "set", "s4", "2026-09-01T01:00:00", None),
    ("H", "set", "s4", "2026-09-01T05:00:00", "2026-09-01"),
    # Filtered out by the view's valuation_method predicate.
    ("X", "set", "s1", "2026-09-01T23:00:00", "2026-08-31"),
]


@pytest.fixture()
def daily_latest():
    """Execute the shipped ranked CTE over the fixtures; return rn=1 rows."""
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE calculation_runs ("
        " id TEXT, target_type TEXT, target_id TEXT, calculation_config_id TEXT,"
        " valuation_method TEXT, notes TEXT, engine_version TEXT,"
        " created_at TEXT, market_date TEXT)"
    )
    connection.executemany(
        "INSERT INTO calculation_runs"
        " (id, target_type, target_id, calculation_config_id, valuation_method,"
        "  notes, engine_version, created_at, market_date)"
        " VALUES (?,?,?,NULL,?,NULL,NULL,?,?)",
        [
            (
                run_id,
                target_type,
                target_id,
                "ignored_method" if run_id == "X" else "expected_value",
                created_at,
                market_date,
            )
            for run_id, target_type, target_id, created_at, market_date in FIXTURES
        ],
    )

    def query(target_id):
        rows = connection.execute(
            "WITH ranked AS (" + RANKED_CTE_SQLITE + ")"
            " SELECT snapshot_date, calculation_run_id FROM ranked"
            " WHERE rn = 1 AND target_id = ? ORDER BY snapshot_date",
            (target_id,),
        ).fetchall()
        return [(str(snapshot_date), run_id) for snapshot_date, run_id in rows]

    yield query
    connection.close()


# ---------------------------------------------------------------------------
# 1. Same promoted date, different UTC dates -> ONE daily row
# ---------------------------------------------------------------------------

def test_same_promoted_date_across_utc_rollover_yields_one_row(daily_latest):
    """Runs A (23:59Z 08-31) and B (00:01Z 09-01) both promote 2026-08-31.

    The rejected wrapper design produced two rows here, both relabelled
    2026-08-31: two 'daily latest' rows for one business day.
    """
    rows = daily_latest("s1")
    assert len(rows) == 1
    snapshot_date, winning_run = rows[0]
    assert snapshot_date == "2026-08-31"
    assert winning_run == "B", "the newest created_at must win the business day"


# ---------------------------------------------------------------------------
# 2. Distinct promoted dates sharing one UTC date -> TWO daily rows
# ---------------------------------------------------------------------------

def test_distinct_promoted_dates_on_one_utc_date_stay_separate(daily_latest):
    """C and D both land on UTC 2026-09-01 but promote different market dates.

    Legacy UTC partitioning collapses these to a single row and silently loses
    the 08-31 business day.
    """
    rows = daily_latest("s2")
    assert [row[0] for row in rows] == ["2026-08-31", "2026-09-01"]
    assert [row[1] for row in rows] == ["C", "D"]


# ---------------------------------------------------------------------------
# 3. Legacy fallback: NULL market_date partitions by created_at::date exactly
# ---------------------------------------------------------------------------

def test_null_market_date_preserves_historical_utc_partitioning(daily_latest):
    """E and F straddle UTC midnight with no promoted date.

    They must remain TWO rows on their historical UTC dates. Any change here
    would silently rewrite already-published history.
    """
    assert daily_latest("s3") == [("2026-08-31", "E"), ("2026-09-01", "F")]


def test_migration_never_backfills_historical_rows():
    assert re.search(r"\bUPDATE\b", SQL) is None


# ---------------------------------------------------------------------------
# 4. Mixed legacy and explicit rows stay deterministic
# ---------------------------------------------------------------------------

def test_mixed_legacy_and_explicit_rows_are_deterministic(daily_latest):
    """G is legacy (UTC 2026-09-01); H explicitly promotes 2026-09-01.

    Both resolve to the same business date, so they form one day and the newest
    run wins - not two competing rows for a single date.
    """
    assert daily_latest("s4") == [("2026-09-01", "H")]


def test_the_valuation_method_filter_is_still_applied(daily_latest):
    """Run X is the newest row for s1 but is not an expected_value/combined run.

    It must never win the day; the filter is part of the preserved contract.
    """
    assert "X" not in [run_id for _snapshot_date, run_id in daily_latest("s1")]


# ---------------------------------------------------------------------------
# 5. Structural guarantees that behaviour alone cannot express
# ---------------------------------------------------------------------------

def test_business_date_is_in_both_the_projection_and_the_partition_key():
    """The defect was a correct projection sitting over a wrong partition."""
    ranked = _extract_ranked_cte(SQL)
    partition = ranked[ranked.index("PARTITION BY") : ranked.index("ORDER BY")]
    assert BUSINESS_DATE in partition, "business date missing from the partition key"
    assert BUSINESS_DATE + " AS snapshot_date" in ranked


def test_the_rejected_wrapper_architecture_cannot_return():
    """The migration's header comment explains the rejected design by quoting
    it, so only executable lines may be checked here."""
    executable = _executable_sql()
    assert "COALESCE(r.market_date, l.snapshot_date)" not in executable
    assert "_legacy_timestamp_date" not in executable
    assert "RENAME TO" not in executable


def test_view_is_replaced_in_place_so_the_acl_and_trend_view_survive():
    assert "CREATE OR REPLACE VIEW public.calculation_history_daily_latest" in SQL
    assert "WITH (security_invoker = true)" in SQL
    assert "DROP VIEW" not in SQL


def test_migration_does_not_broaden_access_to_the_history_views():
    """Migration 075 revoked anon/authenticated from these views.

    A GRANT here would undo that, and would be useless anyway: the views are
    security_invoker and neither role holds SELECT on public.calculation_runs.
    """
    executable = _executable_sql()
    assert "GRANT" not in executable
    assert "REVOKE" not in executable
    assert "anon" not in executable
    assert "authenticated" not in executable


def test_the_trend_view_definition_is_not_recreated():
    """Rebuilding the daily view corrects the trend view's day identity too.

    calculation_history_trend selects FROM calculation_history_daily_latest, so
    its P95 carry-forward is preserved exactly by leaving it alone. CREATE OR
    REPLACE (rather than DROP) is what makes that possible.
    """
    assert "calculation_history_trend" not in _executable_sql()


def test_backend_mirror_is_identical_to_the_supabase_migration():
    assert BACKEND_SQL_PATH.read_text(encoding="utf-8") == SQL
