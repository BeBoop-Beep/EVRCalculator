"""Contract: additive Best-Open Price V2 dual-threshold migration.

Comments are stripped: executable SQL is the contract, prose is not.
"""

from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3]
MIGRATIONS = BACKEND / "db" / "migrations"
MIGRATION = MIGRATIONS / "20260916120000_add_best_open_price_v2_dual_threshold.sql"
SUPABASE_MIRROR = BACKEND.parent / "supabase" / "migrations" / MIGRATION.name


def _statements(path: Path) -> str:
    lines = [line.split("--", 1)[0] for line in path.read_text(encoding="utf-8").lower().splitlines()]
    return "\n".join(line for line in lines if line.strip())


SQL = _statements(MIGRATION)
FULL_TEXT = MIGRATION.read_text(encoding="utf-8").lower()


def test_migration_is_mirrored_into_supabase_directory():
    assert SUPABASE_MIRROR.exists()
    assert MIGRATION.read_text(encoding="utf-8") == SUPABASE_MIRROR.read_text(encoding="utf-8")


def test_seventeen_new_nullable_columns_present():
    for column in (
        "current_financial_only_rank integer",
        "financial_status text",
        "financial_best_open_price numeric",
        "financial_threshold_quantity integer",
        "financial_price_gap_dollars numeric",
        "financial_price_gap_percent numeric",
        "financial_benchmark_sealed_product_id uuid",
        "financial_benchmark_financial_rip_v4_score numeric",
        "financial_benchmark_overall_rip_v12_score numeric",
        "threshold_financial_rip_v4_score numeric",
        "threshold_overall_rip_v12_score numeric",
        "threshold_chance_to_recover_capital numeric",
        "threshold_actual_committed_capital numeric",
        "financial_threshold_financial_rip_v4_score numeric",
        "financial_threshold_overall_rip_v12_score numeric",
        "financial_threshold_chance_to_recover_capital numeric",
        "financial_threshold_actual_committed_capital numeric",
    ):
        assert column in SQL, column
    # The brief's Step 2 SQL block enumerates 17 ADD COLUMN statements
    # (despite its prose header saying "18 new columns" -- the literal SQL
    # list is authoritative and is reproduced verbatim here).
    assert SQL.count("add column") == 17


def test_new_columns_are_nullable_no_not_null():
    body = SQL.split("alter table public.budget_product_best_open_price_rows")[1]
    add_columns_block = body.split("add constraint")[0]
    assert "not null" not in add_columns_block


def test_three_new_tolerant_check_constraints_present():
    assert "add constraint budget_best_open_v2_gap_arithmetic" in SQL
    assert "add constraint budget_best_open_v2_direction" in SQL
    assert "add constraint budget_best_open_v2_not_self_financial_benchmark" in SQL
    # All three tolerate NULL (additive, historical V1 rows keep every new
    # column NULL).
    assert "financial_best_open_price is null" in SQL
    assert "financial_benchmark_sealed_product_id is null or sealed_product_id <> financial_benchmark_sealed_product_id" in SQL


def test_direction_constraint_matches_v1_convention():
    # rank-1/leader can only improve or hold (>=), non-leader can only
    # improve or hold downward (<=) -- same convention as V1's
    # current_budget_rank direction check.
    assert "current_financial_only_rank = 1 and financial_best_open_price >= current_market_price" in SQL
    assert "current_financial_only_rank <> 1 and financial_best_open_price <= current_market_price" in SQL


def test_gap_arithmetic_constraint_uses_tolerance_not_exact_percent_equality():
    assert "financial_price_gap_dollars = current_market_price - financial_best_open_price" in SQL
    assert "abs(financial_price_gap_percent - financial_price_gap_dollars / nullif(current_market_price, 0)) <= 0.000000000001" in SQL


def test_rpc_dispatches_on_method_version_with_three_branches():
    assert "create or replace function public.publish_budget_product_best_open_price_snapshot" in SQL
    assert "v_method_version text := p_snapshot->>'best_open_price_method_version'" in SQL
    assert "if v_method_version = 'budget_product_best_open_price_full_market_v1' then" in SQL
    assert (
        "elsif v_method_version = "
        "'budget_product_best_open_price_full_market_v2_dual_financial_v4_overall_v12' then"
    ) in SQL
    assert "unsupported best-open price method version" in SQL


def test_v1_branch_preserves_hardened_v1_body_markers():
    # Spot-check markers proving the V1 branch is the verbatim hardened body
    # (not the pre-hardening original), not a re-derivation.
    v1_branch = SQL.split("if v_method_version = 'budget_product_best_open_price_full_market_v1' then")[1]
    v1_branch = v1_branch.split("elsif v_method_version =")[0]
    for marker in (
        "source pointer advanced while acquiring publication locks",
        "complete full market source cohort is required",
        "missing or non-finite numeric source/threshold evidence",
        "non-integral count/rank/quantity",
        "invalid threshold money/allocation/direction arithmetic",
        "do not reconcile against the live full market ranking rows",
        "do not reconcile against the live benchmark ranking row",
        "resolved_count + unresolved_count does not equal the live eligible cohort count",
        "is not exact-cent precision",
        "non-deterministic content for identical source identity and method version",
    ):
        assert marker in v1_branch, marker


def test_v2_branch_requires_financial_only_rank_and_dual_thresholds():
    v2_branch = SQL.split(
        "elsif v_method_version = "
        "'budget_product_best_open_price_full_market_v2_dual_financial_v4_overall_v12' then"
    )[1]
    v2_branch = v2_branch.split("\n    else\n")[0]
    assert "current_financial_only_rank is required on every best-open price v2 row" in v2_branch
    assert "live.financial_only_rank is distinct from (row->>'current_financial_only_rank')::integer" in v2_branch
    assert "do not reconcile against the live financial benchmark ranking row" in v2_branch
    assert "invalid dual threshold-evidence range or economic reconciliation" in v2_branch


def test_v2_financial_benchmark_check_is_independent_of_rip_benchmark_check():
    v2_branch = SQL.split(
        "elsif v_method_version = "
        "'budget_product_best_open_price_full_market_v2_dual_financial_v4_overall_v12' then"
    )[1]
    # The Financial benchmark join/self-check is keyed on
    # financial_benchmark_sealed_product_id and only forbids self-benchmark
    # against the row's own sealed_product_id -- it never requires the
    # Financial benchmark to differ from (or match) the RIP benchmark.
    assert "fbench.sealed_product_id = (row->>'sealed_product_id')::uuid" in v2_branch
    assert "financial_benchmark_sealed_product_id = benchmark_sealed_product_id" not in v2_branch
    assert "financial_benchmark_sealed_product_id <> benchmark_sealed_product_id" not in v2_branch


def test_v2_threshold_reconciliation_uses_tolerance_not_exact_equality():
    v2_branch = SQL.split(
        "elsif v_method_version = "
        "'budget_product_best_open_price_full_market_v2_dual_financial_v4_overall_v12' then"
    )[1]
    assert "threshold_quantity')::numeric * (x->>'best_open_price')::numeric" in v2_branch
    assert "financial_threshold_quantity')::numeric * (x->>'financial_best_open_price')::numeric" in v2_branch
    assert "> 0.01" in v2_branch
    # Discipline: must NOT require exact NUMERIC equality between committed
    # capital and quantity*price.
    assert (
        "threshold_actual_committed_capital = threshold_quantity * best_open_price" not in SQL
    )


def test_v2_branch_has_no_rip_money_columns():
    import re

    v2_branch = SQL.split(
        "elsif v_method_version = "
        "'budget_product_best_open_price_full_market_v2_dual_financial_v4_overall_v12' then"
    )[1]
    # Guard against any "rip_*" column name (e.g. rip_best_open_price,
    # rip_threshold_quantity), not just the three literal substrings
    # originally spot-checked.
    assert re.search(r"add column\s+rip_", SQL) is None
    for stale in ("rip_price", "rip_money", "rip_dollars"):
        assert stale not in v2_branch


def test_v2_branch_inserts_all_new_columns():
    v2_branch = SQL.split(
        "elsif v_method_version = "
        "'budget_product_best_open_price_full_market_v2_dual_financial_v4_overall_v12' then"
    )[1]
    for column in (
        "current_financial_only_rank",
        "financial_status, financial_best_open_price, financial_threshold_quantity",
        "financial_benchmark_sealed_product_id, financial_benchmark_financial_rip_v4_score",
        "threshold_financial_rip_v4_score, threshold_overall_rip_v12_score",
        "financial_threshold_financial_rip_v4_score, financial_threshold_overall_rip_v12_score",
    ):
        assert column in v2_branch, column


def test_idempotency_scoped_by_method_version_so_v1_and_v2_coexist():
    assert SQL.count("best_open_price_method_version = p_snapshot->>'best_open_price_method_version'") >= 2
    assert "on conflict (best_open_price_method_version) do update set" in SQL


def test_rpc_grants_are_service_role_only():
    assert (
        "revoke all on function public.publish_budget_product_best_open_price_snapshot(jsonb, jsonb) "
        "from public, anon, authenticated"
    ) in SQL
    assert (
        "grant execute on function public.publish_budget_product_best_open_price_snapshot(jsonb, jsonb) "
        "to service_role"
    ) in SQL


def test_rpc_is_security_definer_with_safe_search_path():
    assert "language plpgsql security definer set search_path = pg_catalog, public, extensions, pg_temp" in SQL


def test_financial_status_invariant_constraint_mirrors_v1_status_invariant():
    # Same three-branch OR, same strict comparisons per status value as
    # V1's status-invariant CHECK, but for financial_status/
    # financial_best_open_price/financial_price_gap_dollars, tolerant of
    # NULL for historical/non-financial rows.
    assert "add constraint budget_best_open_v2_financial_status_invariant" in SQL
    assert "financial_status is null" in SQL
    assert (
        "financial_status = 'resolved_below_market'\n"
        "          and financial_best_open_price < current_market_price and financial_price_gap_dollars > 0"
    ) in SQL
    assert (
        "financial_status = 'current_number_one_with_headroom'\n"
        "          and financial_best_open_price >= current_market_price and financial_price_gap_dollars <= 0"
    ) in SQL
    assert (
        "financial_status = 'resolved_at_market'\n"
        "          and financial_best_open_price = current_market_price and financial_price_gap_dollars = 0"
    ) in SQL


def test_v2_branch_requires_financial_status_non_null():
    v2_branch = SQL.split(
        "elsif v_method_version = "
        "'budget_product_best_open_price_full_market_v2_dual_financial_v4_overall_v12' then"
    )[1]
    assert "financial_status is required on every best-open price v2 row" in v2_branch
    assert "x->>'financial_status' is null" in v2_branch


def test_v2_branch_requires_both_overall_rip_v12_threshold_scores_non_null():
    v2_branch = SQL.split(
        "elsif v_method_version = "
        "'budget_product_best_open_price_full_market_v2_dual_financial_v4_overall_v12' then"
    )[1]
    # Both threshold_overall_rip_v12_score and
    # financial_threshold_overall_rip_v12_score must be in the
    # required-non-null/finite numeric field array, matching the brief's
    # Step 4.7 "non-null, finite" requirement for all four fields per set.
    required_block = v2_branch.split("missing or non-finite numeric source/threshold evidence")[0]
    assert "'threshold_overall_rip_v12_score'" in required_block
    assert "'financial_threshold_overall_rip_v12_score'" in required_block


def test_does_not_touch_the_already_applied_v1_migration_files():
    v1_store = MIGRATIONS / "20260914184759_create_budget_product_best_open_price_store.sql"
    v1_harden = MIGRATIONS / "20260914225000_harden_best_open_publication_review.sql"
    assert v1_store.exists()
    assert v1_harden.exists()
    # This migration is purely additive: it never DROPs or ALTERs away any
    # existing column/constraint from the earlier migrations.
    assert "drop column" not in SQL
    assert "drop constraint" not in SQL
    assert "drop table" not in SQL
    assert "drop function" not in SQL
