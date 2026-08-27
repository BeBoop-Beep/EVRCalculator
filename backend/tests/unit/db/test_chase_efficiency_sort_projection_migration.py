from pathlib import Path

SQL = (Path(__file__).parents[3] / ".." / "supabase" / "migrations" / "20260827130000_add_chase_efficiency_sort_projections.sql").resolve().read_text()


def test_server_sort_projections_are_generated_from_persisted_primitives():
    assert "chase_spend_50 NUMERIC" in SQL
    assert "cost_multiple_50 NUMERIC" in SQL
    assert SQL.count("GENERATED ALWAYS AS") == 2
    assert "current_near_mint_market_price" in SQL
    assert "pokemon_card_chase_efficiency_rows_spend50_idx" in SQL
    assert "pokemon_card_chase_efficiency_rows_multiple50_idx" in SQL
