from pathlib import Path
import re

from pglast import parse_sql

ROOT = Path(__file__).resolve().parents[2]
PROPOSAL = ROOT / "backend/db/proposals/price_storage_v2_retire_legacy_derived_storage.sql"
GATE = ROOT / "docs/price_storage_v2/FRESH_CYCLE_RETIREMENT_GATE.sql"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _without_line_comments(sql: str) -> str:
    return "\n".join(re.sub(r"--.*$", "", line) for line in sql.splitlines())


def test_retirement_sql_parses_as_postgresql():
    assert parse_sql(_text(PROPOSAL))
    assert parse_sql(_text(GATE))


def test_retirement_requires_a_real_post_sep8_fresh_cycle():
    sql = _text(PROPOSAL)
    assert "o.captured_at > DATE '2026-09-08'" in sql
    assert "no fresh scrape exists after 2026-09-08" in sql
    assert "v_current_exact<>v_raw" in sql
    assert "v_event_exact<>v_events" in sql
    assert "v_interval_expected<>v_interval_actual" in sql
    assert "v_coverage_through<>v_tracked_sets" in sql


def test_retirement_only_drops_derived_legacy_market_explorer_storage():
    sql = _text(PROPOSAL)
    executable = _without_line_comments(sql)
    assert "DROP TABLE public.pokemon_market_explorer_card_daily_states;" in executable
    assert "DROP TABLE public.pokemon_card_variant_market_price_intervals;" in executable
    assert "DROP TABLE public.card_variant_price_observations" not in executable
    assert "DROP TABLE public.card_variant_price_monthly_rollups" not in executable
    assert " CASCADE" not in executable.upper()


def test_old_rpc_signatures_are_rebound_to_v2_before_drop():
    sql = _text(PROPOSAL)
    daily = sql.index("CREATE OR REPLACE FUNCTION public.get_pokemon_market_explorer_filtered_cohort_daily_candidate")
    materialized = sql.index("CREATE OR REPLACE FUNCTION public.get_pokemon_market_explorer_filtered_cohort_materialized_series")
    refresh = sql.index("CREATE OR REPLACE FUNCTION public.refresh_pokemon_card_variant_market_price_intervals")
    first_drop = sql.index("DROP TABLE public.pokemon_market_explorer_card_daily_states")
    assert daily < first_drop
    assert materialized < first_drop
    assert refresh < first_drop
    assert sql.count("get_pokemon_market_explorer_filtered_cohort_v2_interval_shadow") >= 3
    assert "rebuild_pokemon_market_price_intervals_v2_shadow_for_sets" in sql


def test_primary_public_readers_are_asserted_v2_after_retirement():
    sql = _text(PROPOSAL)
    assert "get_pokemon_market_explorer_filtered_cohort_v2_hybrid_shadow" in sql
    assert "get_pokemon_cards_daily_constituents_v2_hybrid_shadow" in sql
    assert "pokemon_market_root_set_value_daily_history_v2_shadow" in sql


def test_monthly_rollup_destination_is_explicitly_preserved():
    sql = _text(PROPOSAL)
    assert "current monthly-rollup destination was unexpectedly removed" in sql
    assert "public.card_variant_price_monthly_rollups_v2_shadow" in sql


def test_read_only_gate_matches_the_destructive_gate_dimensions():
    gate = _text(GATE)
    assert "currentExact" in gate and "currentDiff" in gate
    assert "eventExact" in gate and "eventDiff" in gate
    assert "intervalExpected" in gate and "intervalDiff" in gate
    assert "coverageThroughFreshDate" in gate
    assert "THEN 'PASS'" in gate
    assert "ELSE 'BLOCKED'" in gate
