from pathlib import Path
SQL=Path("supabase/migrations/20260830020000_create_treatment_market_prestige_v3_publication.sql").read_text().lower()

def test_schema_is_additive_rls_protected_and_indexed():
    for table in ("treatment_market_prestige_publication_runs","treatment_market_prestige_publication_universes","treatment_market_prestige_results","treatment_market_prestige_regime_sets"):
        assert f"create table public.{table}" in SQL
        assert f"alter table public.{table} enable row level security" in SQL
    assert "where approval_status = 'approved'" in SQL
    assert "security_invoker=true" in SQL
    assert "references public.eras" in SQL and "references public.sets" in SQL

def test_candidate_is_not_approval_and_approval_is_separate_atomic_rpc():
    stage=SQL[SQL.index("function public.stage_treatment"):SQL.index("function public.approve_treatment")]
    approve=SQL[SQL.index("function public.approve_treatment"):SQL.index("revoke all on function")]
    assert "approval_status='approved'" not in stage.replace(" ","")
    assert "for update" in approve and "candidate is not approvable" in approve
    assert "treatment bypasses failed universe" in approve

def test_candidates_and_unavailable_scores_cannot_leak():
    view=SQL[SQL.index("create view public.latest_approved_treatment_market_prestige"):]
    assert "approval_status='approved'" in view.replace(" ","")
    assert "revoke all" in view and "from public, anon, authenticated" in view
    assert "final_availability_status <> 'available'" in SQL
    assert "magnitude_score is null" in SQL

def test_rpcs_are_service_role_only():
    assert SQL.count("from public, anon, authenticated")>=3
    assert "grant execute on function public.stage_treatment_market_prestige_v3_candidate" in SQL
    assert "grant execute on function public.approve_treatment_market_prestige_v3_candidate" in SQL
