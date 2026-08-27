from pathlib import Path


PATH = (Path(__file__).parents[3] / ".." / "supabase" / "migrations" / "20260827231500_bound_chase_efficiency_publication_timeout.sql").resolve()
SQL = PATH.read_text()


def test_timeout_override_is_finite_and_scoped_only_to_chase_publication_rpc():
    normalized = " ".join(SQL.lower().split())
    assert "alter function public.publish_pokemon_card_chase_efficiency_snapshot(jsonb, jsonb)" in normalized
    assert "set statement_timeout = '5min'" in normalized
    assert "statement_timeout = '0'" not in normalized
    assert "alter database" not in normalized
    assert "alter role" not in normalized
    assert "create or replace function" not in normalized
    assert normalized.count("alter function") == 1
