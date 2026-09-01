from pathlib import Path
SQL=" ".join((Path(__file__).resolve().parents[4]/"supabase/migrations/20260831233000_add_market_explorer_card_daily_serving_projection.sql").read_text(encoding="utf-8").lower().split())
def test_projection_is_narrow_derived_and_coverage_gated():
 assert "primary key(market_date,card_variant_id)" in SQL
 assert "include(market_price)" in SQL
 assert "interval authority remains source of truth" in SQL
 assert "pokemon_market_explorer_card_daily_coverage" in SQL
def test_candidate_security_and_approved_dates():
 assert "security definer" not in SQL
 assert "revoke all on function public.get_pokemon_market_explorer_filtered_cohort_daily_candidate" in SQL
 assert "grant execute on function public.get_pokemon_market_explorer_filtered_cohort_daily_candidate" in SQL
 assert "to service_role" in SQL
 assert "status in('ready','legacy_verified')" in SQL
 assert "set enable_nestloop to 'off'" in SQL
 assert "set work_mem to '16mb'" in SQL
