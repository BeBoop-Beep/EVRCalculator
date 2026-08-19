from pathlib import Path


SQL = (
    Path(__file__).resolve().parents[3]
    / "db" / "migrations" / "071_add_current_nm_price_observation_provenance.sql"
).read_text(encoding="utf-8")


def test_current_price_and_provenance_come_from_one_lateral_row():
    assert "current_nm.market_price AS current_near_mint_price" in SQL
    assert "current_nm.captured_at AS current_near_mint_price_captured_at" in SQL
    assert "current_nm.source AS current_near_mint_price_source" in SQL
    assert "LEFT JOIN LATERAL" in SQL


def test_lateral_identity_and_latest_order_are_explicit():
    assert "observation.card_variant_id = sic.card_variant_id" in SQL
    assert "observation.condition_id = sic.condition_id" in SQL
    assert "observation.captured_at DESC NULLS LAST" in SQL
    assert "observation.created_at DESC NULLS LAST" in SQL
    assert "observation.id DESC" in SQL
