from pathlib import Path

MIGRATION = Path("supabase/migrations/20260929191500_market_explorer_surface_dependency_backstop_v1.sql")


def test_surface_dependency_backstop_is_bounded_and_self_healing():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "rename to publish_pokemon_market_explorer_surface_current_core_v2" in sql
    assert "publish_pokemon_market_explorer_daily_v2_for_set" in sql
    assert "limit 8" in sql
    assert "card_daily_converging" in sql
    assert "refresh_pokemon_market_explorer_sealed_daily_v1" in sql
    assert "refresh_pokemon_market_explorer_sealed_current_metadata_v1" in sql
    assert "publish_pokemon_market_explorer_surface_current_core_v2()" in sql
