from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MIGRATION = ROOT / "supabase" / "migrations" / "20260929232200_market_global_7d_baseline_reversion_guard_v1.sql"


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8").lower()


def test_baseline_reversion_guard_is_retrospective_and_exact_variant():
    sql = _sql()
    assert "target_baseline_reversion_guard_v1" in sql
    assert "card_variant_price_observations" in sql
    assert "card_variant_id=m.card_variant_id" in sql
    assert "condition_id=m.condition_id" in sql
    assert "m.baseline_date+3" in sql


def test_guard_only_rejects_large_baseline_shocks_that_revert():
    sql = _sql()
    assert ">=0.15" in sql
    assert "<=0.10" in sql
    assert "and q.reverted_to_prebaseline" in sql
    assert "where not c.baseline_transient" in sql
