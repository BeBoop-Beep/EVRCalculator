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
