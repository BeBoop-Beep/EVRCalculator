from pathlib import Path


SQL = (Path(__file__).parents[3] / ".." / "supabase" / "migrations" / "20260827090000_create_pokemon_card_chase_efficiency_publication.sql").resolve().read_text()


def test_normalized_atomic_private_publication_surface():
    for name in ("pokemon_card_chase_efficiency_snapshots", "pokemon_card_chase_efficiency_rows", "pokemon_card_chase_efficiency_latest"):
        assert f"CREATE TABLE IF NOT EXISTS public.{name}" in SQL
        assert f"ALTER TABLE public.{name} ENABLE ROW LEVEL SECURITY" in SQL
    assert "publish_pokemon_card_chase_efficiency_snapshot" in SQL
    assert "SECURITY DEFINER SET search_path = public" in SQL
    assert "REVOKE ALL ON FUNCTION" in SQL
    assert "card_variant_id UUID NOT NULL" in SQL
    assert "best_verified_pack_equivalent_cost" in SQL
    assert "loose_booster_pack_price" in SQL


def test_publication_rpc_promotes_latest_only_after_rows_and_integrity_checks():
    assert SQL.strip().startswith("-- Canonical exact-printing Chase Efficiency publication surface.\nBEGIN;")
    assert SQL.strip().endswith("COMMIT;")
    row_insert = SQL.index("INSERT INTO public.pokemon_card_chase_efficiency_rows")
    row_count_check = SQL.index("persisted Chase Efficiency count mismatch")
    rank_check = SQL.index("persisted Chase Efficiency set ranks invalid")
    latest_promotion = SQL.index("INSERT INTO public.pokemon_card_chase_efficiency_latest")
    assert row_insert < row_count_check < rank_check < latest_promotion
