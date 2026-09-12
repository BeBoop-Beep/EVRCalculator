from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
MIGRATION = ROOT / "supabase" / "migrations" / "20260910203723_market_explorer_filtered_query_preflight.sql"
SQL = MIGRATION.read_text(encoding="utf-8").lower()


def test_preflight_is_bounded_read_only_and_private():
    assert "stable" in SQL
    assert "security invoker" in SQL
    assert "set search_path = ''" in SQL
    assert "set statement_timeout = '5s'" in SQL
    assert "revoke all" in SQL and "from public, anon, authenticated" in SQL
    assert "grant execute" in SQL and "to service_role" in SQL
    for mutation in ("insert into", "update public.", "delete from", "truncate "):
        assert mutation not in SQL


def test_preflight_reuses_canonical_filter_authorities_without_index_math():
    for authority in (
        "pokemon_market_explorer_card_daily_states_v2_shadow",
        "pokemon_market_explorer_card_current_metadata",
        "market_explorer_rarity_segment",
        "pokemon_card_desirability_links",
        "pokemon_market_date_quality",
    ):
        assert authority in SQL
    assert "p_card_variant_ids is not null" in SQL
    assert "explicit instrument membership is not supported" in SQL
    assert "chain" not in SQL and "normalizedindex" not in SQL


def test_empty_and_no_history_are_distinct_results():
    assert "'empty_now'" in SQL
    assert "'no_usable_history'" in SQL
    assert "matched_current_constituent_count" in SQL
    assert "has_usable_history" in SQL
