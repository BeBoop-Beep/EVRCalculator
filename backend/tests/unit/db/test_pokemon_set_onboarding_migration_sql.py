from pathlib import Path


SQL = Path("backend/db/migrations/052_create_pokemon_set_onboarding_jobs.sql").read_text(encoding="utf-8")


def test_onboarding_identity_and_internal_permissions():
    assert "UNIQUE (source_system, source_set_id)" in SQL
    assert "REVOKE ALL ON public.pokemon_set_onboarding_jobs FROM anon, authenticated" in SQL
    assert "GRANT SELECT, INSERT, UPDATE ON public.pokemon_set_onboarding_jobs TO service_role" in SQL


def test_claim_is_lease_based_and_concurrency_safe():
    assert "FOR UPDATE SKIP LOCKED" in SQL
    assert "lease_expires_at < now()" in SQL
    assert "attempt_count < max_attempts" in SQL


def test_waiting_claims_do_not_consume_execution_attempts():
    assert "CASE WHEN status IN ('detected','retry') THEN 1 ELSE 0 END" in SQL
    assert "p_force_retry AND status IN ('waiting','manual_review','failed')" in SQL
