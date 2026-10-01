from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MIGRATION = ROOT / "supabase" / "migrations" / "20260929223000_market_standard_variant_identity_continuity_v1.sql"


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8").lower()


def test_print_identity_precedes_freshness_in_asof_and_fast_history():
    sql = _sql()
    assert sql.count("canonical_price_events_v2_root_standard_print_identity_v3") >= 3
    # Both selectors must rank physical-print semantics before observation recency.
    assert sql.count("obs.latest_observed_date desc nulls last") >= 2
    assert "when v.rarity in ('common','uncommon') and v.printing_type='non-holo' then 0" in sql


def test_variant_change_is_structural_not_performance():
    sql = _sql()
    assert "variant_identity_change" in sql
    assert "variant_change_count" in sql
    assert "not variant_changed and not stale_to_fresh_reprice" in sql


def test_rebuild_is_bounded_and_excludes_explicit_vintage_roots():
    sql = _sql()
    assert "standard_identity_rebuild_limit_must_be_1_to_5" in sql
    assert "pokemon_edition_split_root_sets_v2" in sql
    assert "limit p_limit" in sql
