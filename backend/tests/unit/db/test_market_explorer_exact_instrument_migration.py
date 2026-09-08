from pathlib import Path


SQL = (Path(__file__).parents[4] / "backend/db/migrations" /
       "20260908052614_20260907200000_add_market_explorer_exact_instrument_foundation.sql").read_text().lower()


def test_generic_cache_identity_is_backfilled_written_and_finalized():
    assert "add column if not exists instrument_id uuid" in SQL
    assert "item->>'sealedproductid'" in SQL
    assert "item->>'gradedcardvariantid'" in SQL
    assert "count(distinct instrument_id)" in SQL
    assert "query_fingerprint, instrument_id" in SQL


def test_exact_variant_predicate_and_indexes_cover_v1_v2_paths():
    assert SQL.count("p_card_variant_ids") >= 10
    assert "m.card_variant_id = any(p_card_variant_ids)" in SQL
    assert "o.card_variant_id = any(p_card_variant_ids)" in SQL
    assert "card_variant_id, market_date" in SQL
    assert "include (market_price, set_id)" in SQL


def test_existing_canonical_card_parameter_is_not_reinterpreted():
    assert "m.canonical_card_id = any(p_card_ids)" in SQL
    assert "o.canonical_card_id = any(p_card_ids)" in SQL
