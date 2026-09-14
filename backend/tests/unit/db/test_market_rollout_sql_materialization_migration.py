from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
NAME = "20260913230641_optimize_market_rollout_daily_materialization.sql"
BACKEND = ROOT / "backend" / "db" / "migrations" / NAME
SUPABASE = ROOT / "supabase" / "migrations" / NAME


def _sql() -> str:
    return SUPABASE.read_text(encoding="utf-8").lower()


def _body(sql: str, function_name: str) -> str:
    start = sql.index(f"create or replace function public.{function_name}")
    body_start = sql.index("as $function$", start)
    return sql[body_start : sql.index("$function$;", body_start)]


def test_migration_mirrors_are_byte_identical() -> None:
    assert BACKEND.read_bytes() == SUPABASE.read_bytes()


def test_both_write_paths_use_one_explicit_root_materialization() -> None:
    sql = _sql()
    for name in (
        "prepare_pokemon_market_candidate_rollout_set_values_v1",
        "refresh_pokemon_market_public_rollout_daily_snapshots_v1",
    ):
        body = _body(sql, name)
        assert body.count("get_pokemon_market_root_set_card_prices_latest_v1(s.id)") == 1
        assert "cross join lateral" in body
        assert "pokemon_market_rollout_prices_work_v1" in body
        assert "pokemon_market_root_set_value_latest_v1" not in body
        assert "pokemon_market_root_set_top10_latest_v1" not in body
        assert "get_pokemon_market_root_set_card_prices_latest_v1(null" not in body


def test_structural_rollout_root_contract_is_preserved() -> None:
    sql = _sql()
    for name in (
        "prepare_pokemon_market_candidate_rollout_set_values_v1",
        "refresh_pokemon_market_public_rollout_daily_snapshots_v1",
    ):
        body = _body(sql, name)
        assert "public.pokemon_market_public_era_rollout_v1" in body
        assert "s.parent_opening_set_id is null" in body
        assert "coalesce(s.catalog_only, false) = false" in body
        assert "coalesce(s.ready_for_daily_scrape, false) = true" in body
        assert "rollout.activated_market_date <=" in body
        assert "s.release_date is null or s.release_date <=" in body


def test_guards_sources_and_economic_contract_are_preserved() -> None:
    sql = _sql()
    candidate = _body(sql, "prepare_pokemon_market_candidate_rollout_set_values_v1")
    finalizer = _body(sql, "refresh_pokemon_market_public_rollout_daily_snapshots_v1")

    assert "candidate rollout set value preparation is current-date only" in candidate
    assert "canonical_root_set_public_rollout_candidate_v1" in candidate
    assert "canonical_root_top10_public_rollout_candidate_v1" in candidate
    assert "public rollout snapshot refresh is current-date only" in finalizer
    assert "status in ('ready','legacy_verified')" in finalizer
    assert "canonical_root_set_public_rollout_v1" in finalizer
    assert "canonical_root_top10_public_rollout_v1" in finalizer
    assert "round(coalesce(sum(p.market_price), 0::numeric), 2)" in sql
    assert "count(p.card_variant_id) = count(*)" in sql
    assert "count(p.market_price) = count(*)" in sql
    assert "order by p.market_price desc nulls last, p.canonical_card_id" in sql
    assert "having count(*) = 10" in sql


def test_finalizer_still_replaces_top_chase_history_from_ranked_rows() -> None:
    body = _body(_sql(), "refresh_pokemon_market_public_rollout_daily_snapshots_v1")
    assert "delete from public.pokemon_set_top_chase_card_daily_history" in body
    assert "insert into public.pokemon_set_top_chase_card_daily_history" in body
    assert "join public.pokemon_canonical_cards pcc" in body
    assert "coalesce(pcc.image_small_url, pcc.image_large_url)" in body
    assert "r.captured_at" in body


def test_candidate_execution_remains_service_role_only() -> None:
    sql = _sql()
    signature = "public.prepare_pokemon_market_candidate_rollout_set_values_v1(date)"
    assert f"revoke all on function {signature}\n  from public, anon, authenticated" in sql
    assert f"grant execute on function {signature}\n  to service_role" in sql
    assert sql.count("security invoker") == 2
    assert sql.count("set search_path = ''") == 2
