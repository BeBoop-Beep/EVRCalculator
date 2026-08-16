from pathlib import Path


SQL = (
    Path(__file__).resolve().parents[3]
    / "db"
    / "migrations"
    / "064_create_simulation_sealed_product_results.sql"
).read_text(encoding="utf-8").lower()


def test_stage1_results_hang_off_the_real_parent_run_with_one_row_per_sku():
    assert "create table if not exists public.simulation_sealed_product_results" in SQL
    assert "references public.calculation_runs(id) on delete cascade" in SQL
    assert "references public.sealed_products(id) on delete cascade" in SQL
    assert "references public.sets(id) on delete cascade" in SQL
    assert "unique (calculation_run_id, sealed_product_id)" in SQL


def test_financial_payload_is_jsonb_and_market_provenance_is_required():
    assert "financial_rip_v3_payload jsonb not null" in SQL
    assert "overall_rip_payload jsonb" in SQL
    assert "product_market_cost numeric not null check (product_market_cost > 0)" in SQL
    assert "price_as_of" in SQL and "price_source" in SQL


def test_modeling_disclosure_and_grants_follow_repo_convention():
    assert "composition_version text not null" in SQL
    assert "distribution_model_version text not null" in SQL
    assert "pack_independence_assumption" in SQL
    assert "grant select on public.simulation_sealed_product_results to anon, authenticated, service_role" in SQL
    assert "grant insert, update, delete on public.simulation_sealed_product_results to service_role" in SQL


def test_no_existing_simulation_table_is_altered():
    assert "alter table" not in SQL.replace(
        "alter table public.simulation_sealed_product_results enable row level security", ""
    )
