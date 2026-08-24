from pathlib import Path

BACKEND = Path("backend/db/migrations/20260824004604_strengthen_budget_product_ranking_publication.sql")
MIRROR = Path("supabase/migrations/20260824004604_strengthen_budget_product_ranking_publication.sql")
SQL = BACKEND.read_text(encoding="utf-8").lower()


def test_migration_mirrors_are_identical(): assert BACKEND.read_bytes() == MIRROR.read_bytes()
def test_replaces_only_rpc_and_is_atomic():
    assert "create or replace function public.publish_budget_product_ranking_snapshot" in SQL
    executable = "\n".join(line.split("--", 1)[0] for line in SQL.splitlines() if line.split("--", 1)[0].strip())
    assert "create table" not in executable and executable.strip().startswith("begin;") and executable.strip().endswith("commit;")
def test_security_contract_is_preserved():
    assert "security definer set search_path = public" in SQL
    assert "from public, anon, authenticated" in SQL
    assert "to service_role" in SQL
def test_persisted_validations_precede_latest_pointer():
    latest=SQL.index("insert into public.budget_product_ranking_latest")
    for token in ("count(distinct budget_rank)", "count(distinct financial_only_rank)", "pinned price authority", "full market count", "required value", "capital reconciliation"):
        assert 0 <= SQL.index(token) < latest
