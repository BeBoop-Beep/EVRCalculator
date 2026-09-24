"""Static contract for the generation-pinned prepared-constituent authority migration."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
NAME = "20260924000000_prepared_constituent_authority_v1.sql"
BACK = ROOT / "backend" / "db" / "migrations" / NAME
SUPA = ROOT / "supabase" / "migrations" / NAME
SQL = BACK.read_text(encoding="utf-8")


def test_both_migration_trees_are_identical():
    assert SUPA.read_text(encoding="utf-8") == SQL


def test_authority_tables_carry_generation_invariants():
    assert "primary key (generation_id, market_key, rank)" in SQL
    assert "unique (generation_id, market_key, instrument_id)" in SQL
    assert "references public.pokemon_market_explorer_prepared_generations_v1(generation_id) on delete cascade" in SQL
    assert "foreign key (generation_id, market_key)" in SQL
    assert "enable row level security" in SQL
    assert "from public, anon, authenticated" in SQL
    assert "to service_role" in SQL


def test_functions_are_invoker_with_fixed_search_path_and_no_hardcoded_ids():
    assert SQL.count("set search_path = ''") >= 3
    assert "security invoker" in SQL
    import re
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", SQL)


def test_reader_is_bounded_generation_pinned_and_falls_back_to_v2():
    assert "p_limit > 100" in SQL
    assert "GENERATION_MISMATCH" in SQL
    assert "get_pokemon_market_explorer_prepared_constituents_v2(p_market_key" in SQL
    reader = SQL.split("constituents_v3(")[1].split("$function$;")[0]
    assert "payload_json" not in reader
    assert "get_pokemon_cards_daily_constituents" not in reader


def test_staging_is_atomic_with_publication_and_validated():
    wrapper = SQL.split("run_market_explorer_guarded_publisher_v1(p_required_market_date date)")[1]
    # Refreshed branch: refresh first, then stage the now-serving generation (same transaction).
    assert wrapper.index("refresh_pokemon_market_explorer_prepared_if_current_v1(") < wrapper.rindex(
        "stage_pokemon_market_explorer_prepared_constituents_v1(")
    # The production wrapper's already_current short-circuit and grantee ACL are preserved.
    assert "'already_current'" in wrapper
    assert "alter function public.run_market_explorer_guarded_publisher_v1" not in SQL
    assert "revoke all on function public.run_market_explorer_guarded_publisher_v1" not in SQL
    assert "PREPARED_CONSTITUENT_VALIDATION_FAILED" in SQL
    assert "mx <> t.total_count" in SQL


def test_set_staging_uses_accepted_membership_resolver_and_preserves_variants():
    assert "get_pokemon_cards_daily_constituents(array[d.set_id]" in SQL
    assert "'cardVariantId', r.card_variant_id" in SQL
    assert "cards.set_id = " not in SQL


def test_service_points_at_v3_reader():
    from backend.db.services import market_explorer_prepared_directory as service
    assert service.CONSTITUENTS_RPC.endswith("_v3")
