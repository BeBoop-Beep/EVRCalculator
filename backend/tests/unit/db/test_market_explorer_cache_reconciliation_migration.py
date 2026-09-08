from pathlib import Path


SQL = (Path(__file__).resolve().parents[4] / "supabase" / "migrations" /
       "20260908192748_reconcile_market_explorer_cache_publication.sql").read_text(
           encoding="utf-8"
       ).lower()


def test_prepare_is_lease_guarded_and_preserves_instrument_uniqueness_rule():
    assert "prepare_pokemon_market_explorer_query_cache_constituents" in SQL
    assert "status = 'building'" in SQL
    assert "build_token = p_build_token" in SQL
    assert "build_expires_at > clock_timestamp()" in SQL
    assert "set instrument_id = null" in SQL
    assert "drop index" not in SQL


def test_build_base_metadata_is_bounded_and_service_role_only():
    assert "get_pokemon_market_explorer_query_cache_build_base_metadata" in SQL
    assert "count(distinct d.instrument_id)" in SQL
    assert "current_constituents" not in SQL
    assert "from public, anon, authenticated" in SQL
    assert "to service_role" in SQL
