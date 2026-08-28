from pathlib import Path


PATH = (Path(__file__).parents[3] / ".." / "supabase" / "migrations" / "20260827233500_stage_chase_efficiency_publication.sql").resolve()
SQL = PATH.read_text()


def test_staging_is_private_and_final_visibility_is_atomic():
    normalized = " ".join(SQL.lower().split())
    assert "private.pokemon_card_chase_efficiency_publication_jobs" in normalized
    assert "private.pokemon_card_chase_efficiency_publication_rows" in normalized
    assert "revoke all on private.pokemon_card_chase_efficiency_publication_jobs from public,anon,authenticated,service_role" in normalized
    assert "revoke all on private.pokemon_card_chase_efficiency_publication_rows from public,anon,authenticated,service_role" in normalized
    finalizer = normalized.index("function public.finalize_pokemon_card_chase_efficiency_publication")
    published_rows = normalized.index("insert into public.pokemon_card_chase_efficiency_rows", finalizer)
    integrity = normalized.index("persisted chase efficiency set ranks invalid", published_rows)
    latest = normalized.index("insert into public.pokemon_card_chase_efficiency_latest", integrity)
    assert finalizer < published_rows < integrity < latest


def test_staging_rpcs_are_service_role_only_and_timeouts_are_bounded():
    normalized = " ".join(SQL.lower().split())
    for function in ("begin_", "append_", "finalize_", "abort_"):
        assert f"revoke all on function public.{function}pokemon_card_chase_efficiency_publication" in normalized
        assert f"grant execute on function public.{function}pokemon_card_chase_efficiency_publication" in normalized
    assert "statement_timeout = '5min'" in normalized
    assert "statement_timeout = '1min'" in normalized
    assert "statement_timeout = '0'" not in normalized
    assert "alter database" not in normalized
    assert "alter role" not in normalized
