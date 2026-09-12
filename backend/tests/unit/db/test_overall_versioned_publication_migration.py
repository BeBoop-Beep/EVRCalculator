from pathlib import Path

SQL=(Path(__file__).resolve().parents[4]/"supabase/migrations/20260911223000_overall_rip_versioned_publication.sql").read_text(encoding="utf-8").lower()
ROLLBACK_SQL=(Path(__file__).resolve().parents[4]/"supabase/migrations/20260912003000_overall_rip_publication_rollback_fix.sql").read_text(encoding="utf-8").lower()


def test_generic_ledger_pointer_and_generations_exist():
    for name in ("pokemon_overall_rip_publication_runs","pokemon_overall_rip_publication_rows","pokemon_overall_rip_publication_generations","pokemon_overall_rip_current_publication"):
        assert f"create table if not exists public.{name}" in SQL
    assert "overall_rip_v13_score" not in SQL


def test_promotion_is_atomic_and_service_role_only():
    assert "promote_pokemon_overall_rip_publication" in SQL
    assert "auth.role() <> 'service_role'" in SQL
    assert "revoke all on function public.promote_pokemon_overall_rip_publication(uuid) from public,anon,authenticated" in SQL
    assert "rankings_generation_id=excluded.rankings_generation_id" in SQL
    assert "set_page_generation_id=excluded.set_page_generation_id" in SQL


def test_v12_is_seeded_current_and_v13_is_only_validated():
    assert "values('overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5'" in SQL
    assert "values('overall_rip_v13_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v7'" in SQL
    assert "'validated','financial_rip_v4" in SQL


def test_rollback_reuses_immutable_superseded_generations():
    assert "status in ('validated','superseded','published')" in ROLLBACK_SQL
    assert "set status='superseded' where publication_run_id=prior" in ROLLBACK_SQL
