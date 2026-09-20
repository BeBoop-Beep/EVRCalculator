from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
NAME = "20260920000523_retain_market_explorer_prepared_generations.sql"
SEALED_GUARD = "20260920001400_guard_prepared_sealed_constituent_source.sql"


def migration() -> str:
    supabase = (ROOT / "supabase" / "migrations" / NAME).read_text()
    backend = (ROOT / "backend" / "db" / "migrations" / NAME).read_text()
    assert supabase == backend
    return supabase


def test_existing_generation_is_registered_without_rewriting_serving_rows():
    sql = migration()
    assert "from public.pokemon_market_explorer_prepared_directory_v1 d;" in sql
    assert "from public.pokemon_market_explorer_prepared_history_v1 x" in sql
    assert "select generation_id into v_id" in sql
    assert "delete from public.pokemon_market_explorer_prepared_directory_v1\n" not in sql


def test_generation_qualified_storage_and_single_serving_pointer():
    sql = migration()
    assert "add primary key (generation_id, market_key);" in sql
    assert "add primary key (generation_id, market_key, market_date);" in sql
    assert "foreign key (generation_id, market_key)" in sql
    assert "singleton boolean primary key" in sql
    assert "join public.pokemon_market_explorer_prepared_serving_v1 p" in sql


def test_refresh_promotes_only_after_candidate_rows_and_metadata():
    sql = migration()
    candidate = sql.index("insert into public.pokemon_market_explorer_prepared_directory_generations_v1 select *")
    history = sql.index("insert into public.pokemon_market_explorer_prepared_history_generations_v1 select *")
    registry = sql.index("'  insert into public.pokemon_market_explorer_prepared_generations_v1'")
    promotion = sql.index("'  perform public.switch_pokemon_market_explorer_prepared_generation_v1")
    assert candidate < history < registry < promotion
    assert "prepared refresh definition changed; refusing unsafe rewrite" in sql


def test_switch_validates_retained_rows_and_contract_before_pointer_update():
    sql = migration()
    start = sql.index("create function public.switch_pokemon_market_explorer_prepared_generation_v1")
    end = sql.index("revoke all on function public.switch_pokemon_market_explorer_prepared_generation_v1", start)
    switch = sql[start:end]
    assert switch.index("v_target.contract_version <> 1") < switch.index("set generation_id=p_target where singleton")
    assert switch.index("v_history_fingerprint <> v_target.history_fingerprint") < switch.index("set generation_id=p_target where singleton")
    assert "UNKNOWN_GENERATION" in switch
    assert "INCOMPLETE_OR_INCOMPATIBLE_GENERATION" in switch
    assert "GENERATION_INTEGRITY_MISMATCH" in switch


def test_reader_rpc_signatures_are_preserved_and_d3_stays_on_serving_generation():
    sql = migration()
    for name in (
        "get_pokemon_market_explorer_prepared_directory_v1",
        "get_pokemon_market_explorer_prepared_comparison_v1",
        "get_pokemon_market_explorer_prepared_history_v1",
        "get_pokemon_market_explorer_prepared_screen_v1",
        "get_pokemon_market_explorer_prepared_constituents_v2",
    ):
        assert f"'{name}'" in sql
    assert "from public.pokemon_market_explorer_prepared_serving_directory_v1" in sql
    assert "from public.pokemon_market_explorer_prepared_serving_history_v1" in sql
    assert "if position(v_old in v_sql)=0" in sql


def test_rollback_and_cleanup_are_service_only_and_retention_is_delayed():
    sql = migration()
    assert "create function public.rollback_pokemon_market_explorer_prepared_generation_v1" in sql
    assert "p_target,'rollback',p_operator_path" in sql
    assert "from public, anon, authenticated" in sql
    assert "to service_role;" in sql
    assert "p_post_publication_verified is distinct from true" in sql
    assert "p_min_retention < interval '7 days'" in sql
    assert "order by coalesce(promoted_at,generated_at) desc limit 3" in sql


def test_sealed_candidate_requires_matching_complete_d3_source():
    supabase = (ROOT / "supabase" / "migrations" / SEALED_GUARD).read_text()
    backend = (ROOT / "backend" / "db" / "migrations" / SEALED_GUARD).read_text()
    assert supabase == backend
    assert "s.market_date=v_sealed_source_asof" in supabase
    assert "s.updated_at <= v_generated_at" in supabase
    assert "'PREPARED_SEALED_D3_SOURCE_MISMATCH" in supabase
    assert "prepared refresh definition changed; refusing unsafe sealed source guard" in supabase
