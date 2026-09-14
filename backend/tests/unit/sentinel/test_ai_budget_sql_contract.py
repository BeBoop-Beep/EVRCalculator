from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SQL = (ROOT / "backend/db/proposals/sentinel_ai_budget_v1.sql").read_text(
    encoding="utf-8"
)
LOWER = SQL.lower()


def test_ai_budget_sql_is_future_proposal_only_and_not_a_migration():
    assert "future proposal only" in LOWER
    assert "p8 does not apply this sql" in LOWER
    assert "does not create a migration" in LOWER


def test_ai_budget_table_enforces_absolute_ten_dollar_cap():
    assert "create table public.sentinel_ai_budget" in LOWER
    assert "configured_budget_cents <= 1000" in LOWER
    assert "reserved_cents <= configured_budget_cents" in LOWER


def test_ai_budget_table_enables_rls_and_is_service_role_only():
    assert "alter table public.sentinel_ai_budget enable row level security" in LOWER
    assert "from public, anon, authenticated, service_role" in LOWER
    assert "to service_role" in LOWER
    assert " to anon" not in LOWER
    assert " to authenticated" not in LOWER


def test_budget_reservation_function_is_security_invoker_not_definer():
    assert "create or replace function public.reserve_sentinel_ai_budget" in LOWER
    assert "security invoker" in LOWER
    assert "security definer" not in LOWER


def test_budget_reservation_is_atomic_and_checks_remaining_envelope():
    assert "reserved_cents = b.reserved_cents + p_reservation_cents" in LOWER
    assert "b.reserved_cents + p_reservation_cents <= b.configured_budget_cents" in LOWER
    assert "request_count = b.request_count + 1" in LOWER


def test_budget_reservation_rpc_is_service_role_only_and_has_no_provider_call():
    assert (
        "revoke all on function public.reserve_sentinel_ai_budget(date, integer, integer)"
        in LOWER
    )
    assert (
        "grant execute on function public.reserve_sentinel_ai_budget(date, integer, integer)"
        in LOWER
    )
    assert "openai" not in LOWER
    assert "anthropic" not in LOWER
