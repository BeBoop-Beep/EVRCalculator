"""Contract tests for Rankings redesign DB Bucket 1 final continuation migration."""

from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3]
MIGRATIONS = BACKEND / "db" / "migrations"
MIGRATION = MIGRATIONS / "20260928210657_rankings_db_bucket1_final_continuation_v1.sql"
SUPABASE_MIRROR = BACKEND.parent / "supabase" / "migrations" / MIGRATION.name


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8").lower()


SQL = _sql()


def _body(function_name: str, next_marker: str) -> str:
    return SQL.split(function_name, 1)[1].split(next_marker, 1)[0]


def test_migration_mirrors_match_byte_for_byte():
    assert SUPABASE_MIRROR.exists()
    assert MIGRATION.read_text(encoding="utf-8") == SUPABASE_MIRROR.read_text(encoding="utf-8")


def test_financial_incremental_function_has_no_collector_identity_dependency():
    body = _body(
        "create or replace function public.refresh_pokemon_financial_rip_history_snapshot_v1",
        "create or replace function public.refresh_pokemon_financial_rip_history_v1",
    )
    assert "join public.sets st on st.id = r.set_id" in body
    assert "st.era_id" in body
    assert "pokemon_card_collector_appeal_rankings_current_v" not in body
    assert "pokemon_collector_appeal_current" not in body


def test_full_financial_backfill_delegates_to_single_snapshot_function():
    body = _body(
        "create or replace function public.refresh_pokemon_financial_rip_history_v1",
        "create or replace function public.pokemon_financial_rip_history_snapshot_autorefresh_v2",
    )
    assert "refresh_pokemon_financial_rip_history_snapshot_v1(s.id)" in body


def test_financial_daily_triggers_are_incremental():
    assert "pokemon_financial_history_snapshot_refresh_v2" in SQL
    assert "pokemon_financial_history_rows_refresh_v2" in SQL
    assert "referencing new table as new_financial_history_rows" in SQL
    assert "refresh_pokemon_financial_rip_history_snapshot_v1(new.id)" in SQL
    assert "select distinct snapshot_id from new_financial_history_rows" in SQL
    assert "drop trigger if exists pokemon_financial_history_snapshot_refresh_v1" in SQL
    assert "drop trigger if exists pokemon_financial_history_rows_refresh_v1" in SQL


def test_financial_semantic_date_contract_is_preserved():
    body = _body(
        "create or replace function public.refresh_pokemon_financial_rip_history_snapshot_v1",
        "create or replace function public.refresh_pokemon_financial_rip_history_v1",
    )
    assert "market_date,source_snapshot_id,snapshot_market_date,source_market_date" in body
    assert "c.source_market_date,c.source_snapshot_id,c.snapshot_market_date,c.source_market_date" in body
    assert "exact duplicate semantic market date" in body


def test_collector_facets_are_run_scoped_and_canonical_identity_backed():
    body = _body(
        "create or replace function public.refresh_pokemon_collector_card_ranking_facets_v1",
        "create or replace function public.refresh_pokemon_chase_card_ranking_facets_v1",
    )
    assert "where model_run_id=p_model_run_id and status='scored'" in body
    assert "join public.sets st on st.id=r.set_id" in body
    assert "join public.eras e on e.id=st.era_id" in body
    assert "on conflict do nothing" in body


def test_chase_facets_require_published_snapshot_and_canonical_identity():
    body = _body(
        "create or replace function public.refresh_pokemon_chase_card_ranking_facets_v1",
        "create or replace function public.pokemon_collector_card_ranking_facets_pointer_v1",
    )
    assert "if v_status <> 'published'" in body
    assert "where snapshot_id=p_snapshot_id" in body
    assert "join public.sets st on st.id=r.set_id" in body
    assert "join public.eras e on e.id=st.era_id" in body


def test_collector_and_chase_pointer_tables_drive_automatic_refresh():
    assert "on public.pokemon_collector_appeal_current" in SQL
    assert "refresh_pokemon_collector_card_ranking_facets_v1(new.model_run_id)" in SQL
    assert "on public.pokemon_card_chase_efficiency_latest" in SQL
    assert "refresh_pokemon_chase_card_ranking_facets_v1(new.snapshot_id)" in SQL


def test_current_facet_view_binds_to_source_pointers_not_built_at():
    body = SQL.split("create or replace view public.pokemon_card_ranking_facets_current_v1", 1)[1]
    assert "from public.pokemon_collector_appeal_current c" in body
    assert "from public.pokemon_card_chase_efficiency_latest l" in body
    assert "g.source_authority_id=s.source_authority_id" in body
    assert "order by lens,built_at" not in body
    assert "distinct on (lens)" not in body


def test_canonical_chase_pointer_contract_is_explicit():
    body = SQL.split("create or replace view public.pokemon_card_ranking_facets_current_v1", 1)[1]
    assert "pokemon-chase-efficiency-v1" in body
    assert "value-times-hit-hazard-over-best-pack-cost-v1" in body
    assert "best-verified-pack-equivalent-cost-v1" in body


def test_new_functions_are_security_invoker():
    for name in (
        "refresh_pokemon_financial_rip_history_snapshot_v1",
        "refresh_pokemon_financial_rip_history_v1",
        "refresh_pokemon_collector_card_ranking_facets_v1",
        "refresh_pokemon_chase_card_ranking_facets_v1",
        "pokemon_collector_card_ranking_facets_pointer_v1",
        "pokemon_chase_card_ranking_facets_pointer_v1",
    ):
        body = SQL.split(f"create or replace function public.{name}", 1)[1].split("$$;", 1)[0]
        assert "security invoker" in body, name


def test_public_anon_authenticated_execute_remains_revoked():
    for signature in (
        "refresh_pokemon_financial_rip_history_snapshot_v1(uuid)",
        "refresh_pokemon_collector_card_ranking_facets_v1(uuid)",
        "refresh_pokemon_chase_card_ranking_facets_v1(uuid)",
        "pokemon_collector_card_ranking_facets_pointer_v1()",
        "pokemon_chase_card_ranking_facets_pointer_v1()",
    ):
        assert f"revoke all on function public.{signature}" in SQL
        revoke_tail = SQL.split(f"revoke all on function public.{signature}", 1)[1][:100]
        assert "public,anon,authenticated" in revoke_tail.replace(" ", "")
