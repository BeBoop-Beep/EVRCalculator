from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MIGRATION = ROOT / "supabase" / "migrations" / "20260929211200_market_standard_performance_stage_single_pass_v2.sql"


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8").lower()


def test_standard_performance_stage_materializes_view_once():
    sql = _sql()
    assert "create temp table _mx_standard_perf" in sql
    assert "pokemon_market_standard_performance_daily_v1" in sql
    assert "stageMaterialization".lower() in sql
    assert "single_pass_temp_v2" in sql


def test_standard_performance_stage_requires_adjustment_convergence():
    sql = _sql()
    assert "standard_set_performance_adjustments_not_converged" in sql
    assert "refresh_pokemon_market_standard_performance_adjustments_v1" in sql


def test_standard_performance_stage_has_bounded_timeout():
    sql = _sql()
    assert "statement_timeout to '180s'" in sql
    assert "lock_timeout to '2s'" in sql
