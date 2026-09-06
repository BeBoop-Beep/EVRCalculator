from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
MIGRATION = (
    ROOT
    / "backend/db/migrations/20260906003840_harden_market_explorer_reproject_authority_boundary.sql"
)
SQL = " ".join(MIGRATION.read_text(encoding="utf-8").lower().split())


def test_reproject_joins_through_canonical_variant_authority():
    assert "get_pokemon_canonical_card_variant_authority(p_set_ids)" in SQL


def test_authority_join_is_keyed_by_card_variant_id_and_set_id():
    assert "on a.card_variant_id = i.card_variant_id" in SQL
    assert "and a.set_id = i.set_id" in SQL


def test_insert_does_not_read_intervals_without_the_authority_join():
    insert_start = SQL.index("insert into public.pokemon_market_explorer_card_daily_states")
    insert_end = SQL.index("get diagnostics v_inserted", insert_start)
    insert_block = SQL[insert_start:insert_end]
    assert "join authority a" in insert_block
    assert "join public.pokemon_card_variant_market_price_intervals i" in insert_block
    # The authority CTE join must appear, not merely be defined earlier and
    # ignored by the INSERT's own FROM/JOIN chain.
    assert insert_block.index("join public.pokemon_card_variant_market_price_intervals i") < (
        insert_block.index("join authority a")
    )


def test_coverage_preconditions_preserved():
    assert "repair projection requires existing coverage for every set" in SQL
    assert "repair end date % exceeds computed_through for % sets" in SQL
    assert "computed_through < p_end_date" in SQL


def test_coverage_row_count_recomputed_from_actual_states():
    assert "count(*) row_count" in SQL
    assert "from public.pokemon_market_explorer_card_daily_states" in SQL
    assert "update public.pokemon_market_explorer_card_daily_coverage c" in SQL


def test_remains_service_role_only():
    signature = "public.reproject_pokemon_market_explorer_card_daily_states(uuid[],date,date)"
    assert f"revoke all on function {signature} from public, anon, authenticated" in SQL
    assert f"grant execute on function {signature} to service_role" in SQL


def test_statement_timeout_and_work_mem_preserved():
    assert "set statement_timeout to '300s'" in SQL
    assert "set work_mem to '64mb'" in SQL


def test_returns_authority_filtered_true():
    assert "'authorityfiltered',true" in SQL
