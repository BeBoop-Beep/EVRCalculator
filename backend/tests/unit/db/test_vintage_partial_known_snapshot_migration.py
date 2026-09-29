from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
NAME = "20260929183500_vintage_partial_known_snapshots_v1.sql"
SUPABASE = ROOT / "supabase" / "migrations" / NAME
BACKEND = ROOT / "backend" / "db" / "migrations" / NAME


def test_partial_known_snapshot_migration_copies_are_identical():
    assert SUPABASE.read_text(encoding="utf-8") == BACKEND.read_text(encoding="utf-8")


def test_partial_known_snapshot_preserves_identity_and_unknown_prices():
    sql = SUPABASE.read_text(encoding="utf-8")
    assert "get_pokemon_edition_history_card_prices_as_of_v2" in sql
    assert "currentValueStatus" in sql
    assert "partial_known_only" in sql
    assert "unknownCardCount" in sql
    assert "priceStatus" in sql
    assert "no_qualified_exact_edition_price" in sql
    assert "genericOrCrossEditionFallbackUsed',false" in sql
    assert "c.expected_card_count-c.priced_card_count" in sql


def test_partial_known_snapshot_reconciles_known_subtotal_but_withholds_history():
    sql = SUPABASE.read_text(encoding="utf-8")
    assert "r.roster_count<>c.expected_card_count" in sql
    assert "r.priced_count<>c.priced_card_count" in sql
    assert "r.known_value<>round(c.set_value,2)" in sql
    assert "AND h.certified_on_date" in sql
    assert "WHERE c.history_publishable" in sql
    assert "withheld_incomplete_current" in sql
