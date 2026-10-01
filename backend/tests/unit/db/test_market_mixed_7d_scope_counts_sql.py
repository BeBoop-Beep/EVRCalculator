from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MIGRATION = ROOT / "supabase" / "migrations" / "20260930003500_market_mixed_7d_scope_counts_v1.sql"


def test_mixed_authority_exposes_card_sealed_and_union_set_counts():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "'cardrootcount'" in sql
    assert "'cardmarketcount'" in sql
    assert "'sealedsetcount'" in sql
    assert "'marketsetcount'" in sql
    assert "market_key in ('raw','sealedmarket')" in sql
