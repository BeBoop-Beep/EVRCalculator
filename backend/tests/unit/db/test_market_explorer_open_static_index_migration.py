from pathlib import Path

SQL = " ".join((Path(__file__).resolve().parents[4] /
    "supabase/migrations/20260831223000_add_market_explorer_open_static_index.sql"
).read_text(encoding="utf-8").lower().split())


def test_index_is_small_static_open_row_shape():
    assert "(set_id, card_variant_id)" in SQL
    assert "include (canonical_card_id, rarity)" in SQL
    assert "where valid_to is null" in SQL


def test_migration_has_no_function_or_business_data_mutation():
    assert "create or replace function" not in SQL
    assert "insert into" not in SQL
    assert "update " not in SQL
    assert "delete from" not in SQL
