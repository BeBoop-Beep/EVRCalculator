from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BASE = ROOT / "supabase" / "migrations" / "20260929201345_market_standard_performance_continuity_v1.sql"
DEDUP = ROOT / "supabase" / "migrations" / "20260929201934_market_standard_performance_quality_dedup_v1.sql"


def _sql(path: Path) -> str:
    return path.read_text(encoding="utf-8").lower()


def test_standard_performance_authority_separates_value_from_performance():
    sql = _sql(BASE)
    assert "pokemon_market_standard_performance_adjustments_v1" in sql
    assert "pokemon_market_standard_performance_daily_v1" in sql
    assert "standard_common_cohort_stale_reprice_v1" in sql
    assert "full join current_prices c using(canonical_card_id)" in sql
    assert "previous_price is null and current_price is not null" in sql
    assert "previous_price is not null and current_price is null" in sql
    assert "(r.previous_market_date-p.observed_date)>30" in sql
    assert "pg_catalog.abs(a.set_value/nullif(a.previous_set_value,0)-1)>=0.05" in sql
    assert "set_value as tracked_value" in sql
    assert "x.adjusted_return" in sql


def test_standard_performance_excludes_explicit_edition_split_roots():
    sql = _sql(BASE)
    assert "pokemon_edition_split_root_sets_v2" in sql
    assert "d.market_key='set:'||d.set_id::text" in sql
    scoped = sql.index("stage_pokemon_market_explorer_scoped_set_overlays_v2")
    standard = sql.index("stage_pokemon_market_explorer_standard_set_performance_v1", scoped)
    raw = sql.index("stage_pokemon_market_explorer_raw_surface_v2", standard)
    assert scoped < standard < raw


def test_quality_gate_is_existential_not_row_multiplying():
    sql = _sql(DEDUP)
    assert "exists (" in sql
    assert "from public.pokemon_market_date_quality q" in sql
    assert "q.market_date=h.market_date" in sql
    assert "q.status in ('ready','legacy_verified')" in sql
    assert "join public.pokemon_market_date_quality q" not in sql


def test_standard_stage_deduplicates_market_identity_before_history_insert():
    sql = _sql(DEDUP)
    assert "select distinct d.market_key,d.set_id" in sql
    assert "create unique index on _mx_standard_markets(market_key)" in sql
    assert "standard_set_performance_adjustments_incomplete" in sql
