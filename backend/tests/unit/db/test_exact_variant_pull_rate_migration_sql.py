from pathlib import Path


SQL = Path("supabase/migrations/20260827230636_create_simulation_card_variant_pull_rates.sql").read_text()


def test_exact_variant_publication_has_run_variant_uniqueness_and_lookup_indexes():
    lowered = SQL.lower()
    assert "unique (calculation_run_id, card_variant_id)" in lowered
    assert "simulation_card_variant_pull_rates_variant_run_idx" in lowered
    assert "pack_presence_count" in lowered
    assert "insufficient_observed_pulls" in lowered


def test_exact_variant_publication_is_service_only_under_rls():
    lowered = SQL.lower()
    assert "enable row level security" in lowered
    assert "revoke all on table public.simulation_card_variant_pull_rates from anon, authenticated" in lowered
    assert "grant all on table public.simulation_card_variant_pull_rates to service_role" in lowered
