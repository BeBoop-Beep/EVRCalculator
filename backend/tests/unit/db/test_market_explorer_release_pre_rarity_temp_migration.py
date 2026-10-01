from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NAME = "20261001202500_market_explorer_release_pre_rarity_temp_v1.sql"
SUPABASE = ROOT.parent / "supabase" / "migrations" / NAME
BACKEND = ROOT / "db" / "migrations" / NAME


def test_migration_mirrors_match():
    assert SUPABASE.read_bytes() == BACKEND.read_bytes()


def test_cleanup_drops_only_completed_pre_rarity_temp_tables():
    sql = SUPABASE.read_text(encoding="utf-8").lower()
    for name in (
        "_mx_scoped_current",
        "_mx_scoped_roster",
        "_mx_scoped_leaves",
        "_mx_standard_markets",
        "_mx_standard_perf",
        "_mx_raw_stable_leaves",
    ):
        assert f"drop table if exists pg_temp.{name}" in sql
    assert "_mx_rarity_members" not in sql.split("create or replace function public.release_pokemon_market_explorer_pre_rarity_temp_v1",1)[1].split("$function$;",1)[0]


def test_rarity_stage_invokes_cleanup_before_its_own_materialization():
    sql = SUPABASE.read_text(encoding="utf-8").lower()
    assert "perform public.release_pokemon_market_explorer_pre_rarity_temp_v1();" in sql
    assert "rarity_stage_cleanup_patch_target_not_found" in sql
    assert "drop function public.stage_pokemon_market_explorer_rarity_candidates_v2" not in sql
