"""Contract: PRIVATE Best-Open Price persistence store (Bucket 3A).

Comments are stripped: executable SQL is the contract, prose is not.
"""

from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3]
MIGRATIONS = BACKEND / "db" / "migrations"
MIGRATION = MIGRATIONS / "20260913220000_create_budget_product_best_open_price_store.sql"
SUPABASE_MIRROR = BACKEND.parent / "supabase" / "migrations" / MIGRATION.name


def _statements(path: Path) -> str:
    lines = [line.split("--", 1)[0] for line in path.read_text(encoding="utf-8").lower().splitlines()]
    return "\n".join(line for line in lines if line.strip())


SQL = _statements(MIGRATION)
FULL_TEXT = MIGRATION.read_text(encoding="utf-8").lower()


def test_migration_is_mirrored_into_supabase_directory():
    assert SUPABASE_MIRROR.exists()
    assert MIGRATION.read_text(encoding="utf-8") == SUPABASE_MIRROR.read_text(encoding="utf-8")


def test_three_tables_exist_as_a_separate_authority():
    assert "create table public.budget_product_best_open_price_snapshots" in SQL
    assert "create table public.budget_product_best_open_price_rows" in SQL
    assert "create table public.budget_product_best_open_price_latest" in SQL
    # separate authority from budget_product_ranking_rows: no shared PK/FK naming collision
    assert "budget_product_ranking_rows" not in SQL.split("create table")[1]  # first new table body


def test_snapshot_source_identity_binding_fields_present():
    for field in (
        "source_budget_snapshot_id uuid not null",
        "source_budget_published_at timestamptz not null",
        "source_market_date date not null",
        "source_cohort_fingerprint text not null",
        "source_full_market_row_fingerprint text not null",
        "source_full_market_budget numeric not null",
        "source_eligible_cohort_count integer not null",
    ):
        assert field in SQL, field


def test_snapshot_model_authority_version_fields_present():
    for field in (
        "ranking_method_version text not null",
        "allocation_method_version text not null",
        "comparison_scope_version text not null",
        "financial_rip_version text not null",
        "overall_rip_v12_version text not null",
        "collector_appeal_version text not null",
        "chase_accessibility_version text not null",
        "chase_accessibility_transform_version text not null",
        "best_open_price_method_version text not null",
    ):
        assert field in SQL, field


def test_snapshot_diagnostics_fields_present():
    assert "resolved_count integer not null" in SQL
    assert "unresolved_count integer not null" in SQL
    assert "runtime_seconds numeric not null" in SQL
    assert "diagnostics_json jsonb not null" in SQL
    assert "check (resolved_count + unresolved_count = source_eligible_cohort_count)" in SQL


def test_row_money_fields_are_cent_precision_constrained():
    assert "current_market_price numeric not null check (current_market_price >= 0" in SQL
    assert "current_market_price = round(current_market_price, 2)" in SQL
    assert "best_open_price numeric not null check (best_open_price >= 0" in SQL
    assert "best_open_price = round(best_open_price, 2)" in SQL


def test_status_taxonomy_locked_to_engine_supported_values():
    assert "status text not null check (status in (" in SQL
    assert "'resolved_below_market', 'current_number_one_with_headroom', 'resolved_at_market'" in SQL
    for stale in ("resolved_above_market", "unresolved_extreme_quantity", "unresolved_search_invariant"):
        assert stale not in SQL


def test_status_invariants_enforced_by_check_constraint():
    assert "status = 'resolved_below_market'" in SQL
    assert "best_open_price < current_market_price and price_gap_dollars > 0" in SQL
    assert "status = 'current_number_one_with_headroom'" in SQL
    assert "best_open_price >= current_market_price and price_gap_dollars <= 0" in SQL
    assert "status = 'resolved_at_market'" in SQL
    assert "best_open_price = current_market_price and price_gap_dollars = 0" in SQL


def test_row_unique_identity_and_light_diagnostics_only():
    assert "unique (snapshot_id, sealed_product_id)" in SQL
    # Light search diagnostics, not full candidate-probe dumps.
    assert "candidate_price_evaluations integer not null" in SQL
    assert "bracket_expansions integer not null" in SQL
    assert "bracket_refinements integer not null" in SQL
    assert "monotonicity_fallback_count integer not null" in SQL
    for stale in ("candidate_probe", "probe_dump", "full_candidate_log"):
        assert stale not in SQL


def test_latest_pointer_keyed_by_method_version():
    assert "best_open_price_method_version text primary key" in SQL


def test_rls_enabled_on_all_three_tables():
    assert "alter table public.budget_product_best_open_price_snapshots enable row level security" in SQL
    assert "alter table public.budget_product_best_open_price_rows enable row level security" in SQL
    assert "alter table public.budget_product_best_open_price_latest enable row level security" in SQL
    # No permissive policies at all.
    assert "create policy" not in SQL


def test_explicit_revoke_from_public_anon_authenticated_on_tables():
    assert "revoke all on public.budget_product_best_open_price_snapshots from public, anon, authenticated" in SQL
    assert "revoke all on public.budget_product_best_open_price_rows from public, anon, authenticated" in SQL
    assert "revoke all on public.budget_product_best_open_price_latest from public, anon, authenticated" in SQL


def test_rpc_is_security_definer_with_safe_search_path():
    assert "create or replace function public.publish_budget_product_best_open_price_snapshot" in SQL
    assert "language plpgsql security definer set search_path = public" in SQL


def test_rpc_grants_are_service_role_only():
    assert (
        "revoke all on function public.publish_budget_product_best_open_price_snapshot(jsonb, jsonb) "
        "from public, anon, authenticated"
    ) in SQL
    assert (
        "grant execute on function public.publish_budget_product_best_open_price_snapshot(jsonb, jsonb) "
        "to service_role"
    ) in SQL


def test_rpc_re_verifies_live_source_identity():
    assert "budget_product_ranking_latest" in SQL
    assert "budget_product_ranking_snapshots" in SQL
    assert "no live budget ranking source found" in SQL
    assert "stale or non-deterministic input" in SQL


def test_rpc_cross_checks_rows_against_live_ranking_rows():
    assert "budget_product_ranking_rows" in SQL
    assert "do not reconcile against the live full market ranking rows" in SQL


def test_rpc_rejects_duplicate_rows():
    assert "duplicate sealed_product_id rows in one best-open-price publication" in SQL


def test_rpc_rejects_row_count_mismatch_with_resolved_count():
    assert "does not equal resolved_count" in SQL


def test_rpc_rejects_cohort_membership_mismatch():
    assert "resolved_count + unresolved_count does not equal the live eligible cohort count" in SQL


def test_rpc_defends_cent_precision_at_publish_time():
    assert "is not exact-cent precision" in SQL


def test_rpc_is_idempotent_and_refuses_nondeterministic_content():
    assert "content_fingerprint" in SQL
    assert "refusing silent replace" in SQL


def test_rpc_moves_latest_pointer_only_after_all_validation():
    # The INSERT into *_latest must textually follow the row-count
    # reconciliation check inside the function body.
    body = SQL.split("create or replace function public.publish_budget_product_best_open_price_snapshot")[1]
    reconcile_idx = body.index("does not reconcile with the publication payload")
    latest_idx = body.index("insert into public.budget_product_best_open_price_latest")
    assert reconcile_idx < latest_idx


def test_no_frontend_or_public_api_terminology_leaked_into_migration():
    for stale in ("rankingsproductlensclient", "app/api", "public projection"):
        assert stale not in FULL_TEXT
