from pathlib import Path


SQL = (Path(__file__).parents[4] / "supabase" / "migrations" /
       "20260907055306_market_explorer_v2_daily_advance_and_cache_lease_heartbeat.sql").read_text()


def test_v2_advance_is_incremental_bounded_and_idempotent():
    lowered = SQL.lower()
    assert "advance_pokemon_market_explorer_daily_v2_shadow_for_set" in lowered
    assert "return public.rebuild_pokemon_market_explorer_daily_v2_shadow_for_set" in lowered
    assert "p_through_date < v_coverage.computed_through" in lowered
    assert "market_date < v_from" in lowered
    assert "v_coverage.computed_through + 1" in lowered
    assert "on conflict (market_date, card_variant_id) do update" in lowered
    assert "select count(*) into v_rows" in lowered


def test_lease_renewal_cannot_resurrect_or_steal():
    lowered = SQL.lower()
    assert "renew_pokemon_market_explorer_query_cache_build" in lowered
    assert "status = 'building'" in lowered
    assert "build_token = p_build_token" in lowered
    assert "build_expires_at > clock_timestamp()" in lowered
    assert "build_expires_at = clock_timestamp() + make_interval" in lowered
    assert "grant execute" in lowered and "to service_role" in lowered
    assert "from public, anon, authenticated" in lowered
