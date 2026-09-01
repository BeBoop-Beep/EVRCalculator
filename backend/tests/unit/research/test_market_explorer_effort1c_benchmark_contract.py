from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SQL = (ROOT / "backend" / "research" / "market_explorer" /
       "effort1c_interval_vs_fact_benchmark.sql").read_text(encoding="utf-8")
DOC = (ROOT / "docs" / "MARKET_EXPLORER_EFFORT1C_INSTANT_READ_ARCHITECTURE.md").read_text(
    encoding="utf-8"
)


def test_fixture_is_non_deploying_and_never_reads_raw_observations():
    normalized = " ".join(SQL.lower().split())
    assert "create temp table effort1c_variant_daily_fact" in normalized
    assert "create table public." not in normalized
    assert "card_variant_price_observations" not in normalized
    assert "pokemon_card_variant_market_price_intervals" in normalized


def test_daily_facts_are_variant_date_unique_and_point_in_time_correct():
    normalized = " ".join(SQL.lower().split())
    assert "unique index effort1c_fact_variant_date" in normalized
    assert "(card_variant_id, market_date)" in normalized
    assert "interval.valid_from <= quality.market_date" in normalized
    assert "quality.market_date < interval.valid_to" in normalized
    assert "interval.market_price < 10" in normalized
    assert "quality.market_date - set_row.release_date" in normalized


def test_pokemon_uses_canonical_reference_bridge_not_names():
    normalized = " ".join(SQL.lower().split())
    assert "pokemon_card_desirability_links" in normalized
    assert "pokemon_reference_id" in normalized
    assert "pokemon_reference_ids" not in normalized
    assert "pokemon name" not in normalized


def test_top_25_is_a_display_query_separate_from_full_aggregate():
    normalized = " ".join(SQL.lower().split())
    aggregate = normalized.index("select count(*) constituent_count, sum(market_price) current_value")
    top_25 = normalized.index("order by market_price desc, card_variant_id limit 25")
    assert aggregate < top_25


def test_decision_and_effort2_todo_are_explicitly_preserved():
    assert "decision deferred" in DOC.lower()
    assert "Clear Graph" in DOC
    assert "Builder Clear remains separate" in DOC
    assert "First Edition" in DOC and "Reverse Holo" in DOC
