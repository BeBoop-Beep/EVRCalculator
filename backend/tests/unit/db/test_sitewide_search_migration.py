from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
NAME = "20260912174957_sitewide_search_route_identity_v1.sql"


def test_sitewide_companion_rpc_is_additive_rank_equivalent_and_service_role_only():
    backend = (ROOT / "backend/db/migrations" / NAME).read_text(encoding="utf-8")
    supabase = (ROOT / "supabase/migrations" / NAME).read_text(encoding="utf-8")
    assert backend == supabase
    sql = " ".join(backend.lower().split())
    assert "from public.search_pokemon_market_explorer_instruments_v2(" in sql
    assert "left join public.pokemon_market_explorer_card_current_metadata" in sql
    assert "m.card_variant_id = r.instrument_id" in sql
    assert "r.relevance_score desc" in sql
    assert "r.name_similarity" in sql
    assert "security invoker" in sql
    assert "from public, anon, authenticated" in sql
    assert "to service_role" in sql
    assert "drop function" not in sql
