"""Contract: internal Budget-Constrained Whole-Unit Product Ranking storage.

Migration 20260822213027 has NOT been applied to production (verified: none of
its three tables exist there) and has never been pushed, so the V1 freeze
edits it in place rather than stacking a follow-on migration — matching the
repo's own discipline, where a follow-on is used precisely WHEN the original
is already applied (see `test_sealed_product_results_access_migration_sql.py`,
which stacks 065 onto 064 for exactly that reason).

Comments are stripped: executable SQL is the contract, prose is not.
"""

from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3]
MIGRATIONS = BACKEND / "db" / "migrations"
MIGRATION = MIGRATIONS / "20260822213027_create_budget_normalized_product_rankings.sql"
SUPABASE_MIRROR = BACKEND.parent / "supabase" / "migrations" / MIGRATION.name


def _statements(path: Path) -> str:
    lines = [line.split("--", 1)[0] for line in path.read_text(encoding="utf-8").lower().splitlines()]
    return "\n".join(line for line in lines if line.strip())


SQL = _statements(MIGRATION)

#: Full file INCLUDING comments. Structural contracts assert against `SQL`
#: (executable only), but terminology hygiene is deliberately asserted against
#: the whole file: a comment that still calls this "equal committed capital"
#: misleads the next reader just as effectively as a wrong column name.
FULL_TEXT = MIGRATION.read_text(encoding="utf-8").lower()


def test_migration_is_mirrored_into_supabase_directory():
    assert SUPABASE_MIRROR.exists()
    assert MIGRATION.read_text(encoding="utf-8") == SUPABASE_MIRROR.read_text(encoding="utf-8")


def test_scope_version_is_budget_constrained_not_equal_capital():
    """The frozen V1 scope name. The pre-freeze string described the method as
    equal-committed-capital while the implementation was floor-to-budget; the
    validation proved those produce materially different rankings."""
    for stale in (
        "equal_committed_capital_cross_format_v1",
        "equal committed capital",
        "equal spend",
        "matched capital",
    ):
        assert stale not in FULL_TEXT, "stale pre-freeze terminology in migration: %r" % stale
    assert "budget_constrained_whole_unit_cross_format_v1" in FULL_TEXT
    # The column exists; its VALUE is supplied by the engine constant rather
    # than pinned by a CHECK, so a future V2 scope can publish without a
    # schema change while still being explicit per row.
    assert "comparison_scope_version text not null" in SQL


def test_capital_fields_are_persisted_and_reconciled():
    assert "capital_utilization numeric not null" in SQL
    assert "unused_capital_percent numeric not null" in SQL
    # utilization and unused percent must be exact complements
    assert "check (abs((capital_utilization + unused_capital_percent) - 1) < 0.000001)" in SQL
    # committed + unused must reconcile to the budget within currency rounding
    assert "check (abs((actual_committed_capital + unused_capital) - target_budget) < 0.01)" in SQL


def test_financial_only_rank_is_persisted_and_bounded():
    assert "financial_only_rank integer not null check (financial_only_rank >= 1)" in SQL
    assert "check (financial_only_rank <= budget_cohort_size)" in SQL


def test_chance_to_recover_capital_is_a_bounded_probability():
    assert "chance_to_recover_capital numeric" in SQL
    assert "chance_to_recover_capital >= 0 and chance_to_recover_capital <= 1" in SQL


def test_snapshot_pins_one_price_authority():
    assert "pinned_price_as_of date not null" in SQL


def test_rpc_rejects_mixed_price_authority():
    """Storage-level guarantee against 'newest row wins per SKU', which yields
    a full-looking cohort silently blended across market states."""
    assert "mixed price authority" in SQL
    assert "is distinct from (p_snapshot->>'pinned_price_as_of')" in SQL


def test_rpc_rejects_rank_exceeding_cohort_size():
    assert "rank greater than its cohort size" in SQL


def test_full_market_publication_metadata_is_persisted():
    assert "full_market_budget numeric not null" in SQL
    assert "max_eligible_sku_price numeric not null" in SQL
    assert "full_market_rounding_increment numeric not null" in SQL
    assert "full_market_rounding_rule_version text not null" in SQL
    assert "check (full_market_budget >= max_eligible_sku_price)" in SQL


def test_full_market_row_provenance_is_all_or_nothing():
    """Full Market rows carry their anchor derivation; other budgets must not."""
    assert "full_market_rounding_increment is not null" in SQL
    assert "full_market_rounding_rule_version is not null" in SQL
    assert "full_market_rounding_increment is null" in SQL
    assert "full_market_rounding_rule_version is null" in SQL


def test_budget_identity_is_product_plus_budget():
    assert "primary key (snapshot_id, sealed_product_id, target_budget, budget_type)" in SQL


def test_internal_only_no_public_grants():
    """anon/authenticated receive NO grant on any object this migration creates."""
    assert "revoke all on public.budget_product_ranking_snapshots, public.budget_product_ranking_rows, public.budget_product_ranking_latest" in SQL
    assert "from public, anon, authenticated;" in SQL
    for table in (
        "budget_product_ranking_snapshots",
        "budget_product_ranking_rows",
        "budget_product_ranking_latest",
    ):
        assert "grant select, insert, update, delete on public.%s to service_role;" % table in SQL
    assert "to anon" not in SQL
    assert "to authenticated" not in SQL


def test_rls_enabled_on_every_table():
    for table in (
        "budget_product_ranking_snapshots",
        "budget_product_ranking_rows",
        "budget_product_ranking_latest",
    ):
        assert "alter table public.%s enable row level security;" % table in SQL


def test_publish_function_is_service_role_only():
    assert "revoke all on function public.publish_budget_product_ranking_snapshot(jsonb, jsonb) from public, anon, authenticated;" in SQL
    assert "grant execute on function public.publish_budget_product_ranking_snapshot(jsonb, jsonb) to service_role;" in SQL


def test_publication_is_atomic_and_reconciled():
    assert sql_has_all(
        "refusing to publish an empty budget ranking snapshot",
        "duplicate (sealed_product_id, target_budget, budget_type) rows in one publication",
        "persisted budget ranking row count does not reconcile",
    )
    assert SQL.strip().startswith("begin;")
    assert SQL.strip().endswith("commit;")


def sql_has_all(*needles: str) -> bool:
    return all(needle in SQL for needle in needles)
