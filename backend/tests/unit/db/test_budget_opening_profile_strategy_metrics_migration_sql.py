from pathlib import Path

BACKEND = Path("backend/db/migrations/20260915233000_add_budget_opening_profile_strategy_metrics.sql")
MIRROR = Path("supabase/migrations/20260915233000_add_budget_opening_profile_strategy_metrics.sql")
SQL = BACKEND.read_text(encoding="utf-8").lower()
EXECUTABLE = "\n".join(
    line.split("--", 1)[0]
    for line in SQL.splitlines()
    if line.split("--", 1)[0].strip()
)


def test_migration_mirrors_are_identical():
    assert BACKEND.read_bytes() == MIRROR.read_bytes()


def test_adds_only_the_two_exact_strategy_summary_columns():
    assert "add column median_value numeric" in SQL
    assert "add column top1_outcome_value_share numeric" in SQL
    assert "add column average_return" not in SQL


def test_constraints_are_bounded_and_finite():
    assert "median_value >= 0" in SQL
    assert "top1_outcome_value_share >= 0" in SQL
    assert "top1_outcome_value_share <= 1" in SQL
    assert "'nan', 'infinity', '-infinity'" in SQL


def test_rpc_requires_exact_strategy_evidence_for_new_publications():
    for key in ("expected_value", "median_value", "top1_outcome_value_share"):
        assert f"nullif(row->>'{key}', '') is null" in SQL
    assert "missing or has invalid exact strategy opening-profile evidence" in SQL


def test_rpc_persists_all_three_strategy_summaries_atomically():
    update = """set expected_value = (row->>'expected_value')::numeric,
        median_value = (row->>'median_value')::numeric,
        top1_outcome_value_share = (row->>'top1_outcome_value_share')::numeric"""
    assert update in SQL
    assert "and expected_value is not null" in SQL
    assert "and median_value is not null" in SQL
    assert "and top1_outcome_value_share is not null" in SQL
    assert "persisted strategy opening-profile values do not reconcile" in SQL


def test_no_card_attribution_top1_metric_can_enter_executable_sql():
    assert "top1evshare" not in EXECUTABLE


def test_historical_rows_are_not_backfilled_or_inferred():
    # Columns are nullable by design until a fresh canonical publication replaces
    # the old snapshot. There must be no table-wide historical inference update.
    assert "update public.budget_product_ranking_rows set median_value" not in EXECUTABLE
    assert "coalesce(median_value" not in EXECUTABLE
    assert "coalesce(top1_outcome_value_share" not in EXECUTABLE


def test_existing_v12_atomic_publication_guards_are_preserved():
    for token in (
        "overall_rip_v12_score",
        "overall_rip_v12_rankable",
        "chase_accessibility_raw",
        "budget_rank_v12",
        "budget_cohort_size_v12",
        "persisted v12 budget fields do not reconcile",
        "persisted v12 budget cohort size or rank contiguity validation failed",
    ):
        assert token in SQL


def test_function_remains_security_definer_and_transactional():
    assert "security definer" in SQL
    assert "set search_path to 'public'" in SQL
    assert EXECUTABLE.startswith("begin;")
    assert EXECUTABLE.endswith("commit;")
