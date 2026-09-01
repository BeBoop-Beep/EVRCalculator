from collections import defaultdict
from datetime import date
from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[4]
    / "supabase"
    / "migrations"
    / "20260830201143_optimize_market_explorer_cohort_execution.sql"
)
SQL = MIGRATION.read_text(encoding="utf-8")
NORMALIZED = " ".join(SQL.lower().split())
DATE_CONTRACT_SQL = " ".join((
    Path(__file__).resolve().parents[4]
    / "supabase"
    / "migrations"
    / "20260830201610_preserve_market_explorer_observed_date_contract.sql"
).read_text(encoding="utf-8").lower().split())
FAST_PATH_SQL = " ".join((
    Path(__file__).resolve().parents[4]
    / "supabase"
    / "migrations"
    / "20260831021617_add_market_explorer_interval_range_fast_path.sql"
).read_text(encoding="utf-8").lower().split())


def _series(dates, rows, top_n=None):
    """Small executable oracle for filter-first selected-state semantics."""
    eligible = defaultdict(list)
    for market_date, variant_id, price, included in rows:
        if included:
            eligible[market_date].append((variant_id, price))

    selected = {}
    ranks = {}
    for market_date in dates:
        ordered = sorted(eligible[market_date], key=lambda row: (-row[1], row[0]))
        chosen = ordered if top_n is None else ordered[:top_n]
        selected[market_date] = dict(chosen)
        ranks[market_date] = {variant_id: rank for rank, (variant_id, _) in enumerate(chosen, 1)}

    result = []
    for index, market_date in enumerate(dates):
        previous_date = dates[index - 1] if index else None
        current = selected[market_date]
        previous = selected.get(previous_date, {})
        common = set(current) & set(previous)
        latest_rank = ranks[market_date] if top_n is not None else {
            variant_id: rank
            for rank, (variant_id, _) in enumerate(
                sorted(current.items(), key=lambda row: (-row[1], row[0])), 1
            )
        }
        result.append({
            "date": market_date,
            "eligible": len(eligible[market_date]),
            "constituents": len(current),
            "common": len(common),
            "common_current": sum(current[key] for key in common),
            "common_previous": sum(previous[key] for key in common),
            "rank": latest_rank,
        })
    return result


def _half_open_contains(valid_from, valid_to, market_date):
    return valid_from <= market_date and (valid_to is None or market_date < valid_to)


def test_function_contract_signature_and_security_are_unchanged():
    signature = (
        "public.get_pokemon_market_explorer_filtered_cohort"
        "(uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer)"
    )
    assert signature in NORMALIZED
    assert "returns table(market_date date, constituent_count bigint" in NORMALIZED
    assert "security invoker" in NORMALIZED
    assert f"revoke all on function {signature} from public, anon, authenticated" in NORMALIZED
    assert f"grant execute on function {signature} to service_role" in NORMALIZED
    assert "security definer" not in NORMALIZED


def test_common_cohort_uses_previous_selected_window_not_selected_self_join():
    assert "join selected prev" not in NORMALIZED
    assert "left join selected cur" not in NORMALIZED
    assert "partition by selected.card_variant_id" in NORMALIZED
    assert "lag(selected.market_date)" in NORMALIZED
    assert "lag(selected.market_price)" in NORMALIZED
    assert "state.prev_seen_date = dates.previous_market_date" in NORMALIZED


def test_canonical_date_filter_first_and_top_n_contracts_are_preserved():
    assert "quality.status in ('ready', 'legacy_verified')" in NORMALIZED
    assert "date_context as materialized" in NORMALIZED
    assert NORMALIZED.index("panel as materialized") < NORMALIZED.index("top_n_ranked as materialized")
    assert "where p_top_n is not null" in NORMALIZED
    assert "order by panel.market_price desc, panel.card_variant_id" in NORMALIZED
    assert "where p_top_n is null" in NORMALIZED
    unranked = NORMALIZED[NORMALIZED.index("unranked_selected as materialized"):NORMALIZED.index("top_n_ranked as materialized")]
    assert "row_number() over" not in unranked


def test_eligible_count_precedes_top_n_and_metadata_is_latest_only():
    assert "eligible as materialized" in NORMALIZED
    assert NORMALIZED.index("eligible as materialized") < NORMALIZED.index("top_n_ranked as materialized")
    assert "count(*)::bigint eligible_universe_count" in NORMALIZED
    assert "latest_selected as materialized" in NORMALIZED
    assert "dates.market_date = dates.latest_market_date" in NORMALIZED
    assert "case when series.market_date = dates.latest_market_date" in NORMALIZED
    panel = NORMALIZED[NORMALIZED.index("panel as materialized"):NORMALIZED.index("eligible as materialized")]
    for wide_field in ("card_name", "card_number", "image_url", "edition", "printing_type", "special_type"):
        assert wide_field not in panel


def test_forward_fix_preserves_observed_rows_but_uses_canonical_previous_date():
    assert "observed_dates as materialized" in DATE_CONTRACT_SQL
    assert "from date_context dates join (select distinct panel.market_date from panel) observed" in DATE_CONTRACT_SQL
    assert "from observed_dates dates left join eligible" in DATE_CONTRACT_SQL
    assert "state.prev_seen_date = dates.previous_market_date" in DATE_CONTRACT_SQL


def test_native_range_fast_path_has_no_extension_or_business_data_write():
    assert "using gist (daterange(valid_from, valid_to, '[)'))" in FAST_PATH_SQL
    assert "create extension" not in FAST_PATH_SQL
    assert "insert into" not in FAST_PATH_SQL
    assert "update " not in FAST_PATH_SQL
    assert "delete from" not in FAST_PATH_SQL
    assert "set_value_eligible" not in FAST_PATH_SQL
    assert "opening_eligible" not in FAST_PATH_SQL
    assert "duplicate_alias" not in FAST_PATH_SQL
    assert "abstract_identity" not in FAST_PATH_SQL


def test_half_open_range_semantics_cover_bounded_open_and_boundaries():
    start, end = date(2026, 1, 10), date(2026, 1, 20)
    assert _half_open_contains(start, end, start)
    assert _half_open_contains(start, end, date(2026, 1, 19))
    assert not _half_open_contains(start, end, end)
    assert not _half_open_contains(start, end, date(2026, 1, 9))
    assert not _half_open_contains(start, end, date(2026, 1, 21))
    assert _half_open_contains(start, None, start)
    assert _half_open_contains(start, None, date(2099, 1, 1))


def test_dimension_free_panel_is_separate_from_custom_filter_authorities():
    fast = FAST_PATH_SQL[
        FAST_PATH_SQL.index("fast_panel as materialized"):
        FAST_PATH_SQL.index("filtered_panel as materialized")
    ]
    filtered_start = FAST_PATH_SQL.index("filtered_panel as materialized")
    filtered = FAST_PATH_SQL[
        filtered_start:
        FAST_PATH_SQL.index("), panel as materialized", filtered_start)
    ]
    assert "join public.sets" not in fast
    assert "pokemon_card_desirability_links" not in fast
    assert "market_explorer_rarity_segment" not in fast
    assert "join public.sets" in filtered
    assert "pokemon_card_desirability_links" in filtered
    assert "market_explorer_rarity_segment" in filtered


def test_range_panel_and_latest_primary_key_lookup_preserve_identity():
    assert "daterange(fact.valid_from, fact.valid_to, '[)') @> dates.market_date" in FAST_PATH_SQL
    assert "panel.observation_id" in FAST_PATH_SQL
    assert "fact.observation_id = latest.observation_id" in FAST_PATH_SQL
    assert "partition by selected.card_variant_id" in FAST_PATH_SQL
    assert "state.prev_seen_date = dates.previous_market_date" in FAST_PATH_SQL
    assert "fact.observation_id = latest.observation_id" in FAST_PATH_SQL


def test_fast_path_signature_acl_and_top_n_contract_are_unchanged():
    signature = (
        "public.get_pokemon_market_explorer_filtered_cohort"
        "(uuid[],date,date,uuid[],text[],bigint[],text[],text[],integer)"
    )
    assert signature in FAST_PATH_SQL
    assert "security invoker" in FAST_PATH_SQL
    assert f"revoke all on function {signature} from public, anon, authenticated" in FAST_PATH_SQL
    assert f"grant execute on function {signature} to service_role" in FAST_PATH_SQL
    assert "order by panel.market_price desc, panel.card_variant_id" in FAST_PATH_SQL
    assert FAST_PATH_SQL.index("filtered_panel as materialized") < FAST_PATH_SQL.index("top_n_ranked as materialized")


def test_consecutive_presence_and_missing_prior_date():
    rows = [("d1", "a", 10, True), ("d2", "a", 11, True), ("d2", "b", 4, True)]
    result = _series(["d1", "d2"], rows)
    assert result[1]["common"] == 1
    assert result[1]["common_current"] == 11
    assert result[1]["common_previous"] == 10


def test_d1_present_d2_absent_d3_present_is_not_common():
    rows = [("d1", "a", 10, True), ("d3", "a", 12, True)]
    result = _series(["d1", "d2", "d3"], rows)
    assert result[2]["common"] == 0


def test_top_n_entry_exit_and_reentry_respect_immediate_previous_date():
    rows = [
        ("d1", "a", 10, True), ("d1", "b", 9, True),
        ("d2", "a", 8, True), ("d2", "b", 11, True),
        ("d3", "a", 12, True), ("d3", "b", 10, True),
    ]
    result = _series(["d1", "d2", "d3"], rows, top_n=1)
    assert [row["common"] for row in result] == [0, 0, 0]
    assert [next(iter(row["rank"])) for row in result] == ["a", "b", "a"]
    assert all(row["eligible"] == 2 and row["constituents"] == 1 for row in result)


def test_point_in_time_price_segment_entry_and_exit_break_common_membership():
    # `included` represents the point-in-time price filter already applied by panel.
    rows = [("d1", "a", 9, True), ("d2", "a", 11, False), ("d3", "a", 8, True)]
    result = _series(["d1", "d2", "d3"], rows)
    assert [row["constituents"] for row in result] == [1, 0, 1]
    assert result[2]["common"] == 0


def test_release_age_transition_breaks_common_membership_when_filter_excludes_date():
    rows = [("d1", "a", 5, True), ("d2", "a", 5, False), ("d3", "a", 5, False)]
    result = _series(["d1", "d2", "d3"], rows)
    assert [row["common"] for row in result] == [0, 0, 0]


def test_unranked_parity_and_latest_rank_use_variant_id_tie_break():
    rows = [("d1", "b", 10, True), ("d1", "a", 10, True), ("d1", "c", 4, True)]
    result = _series(["d1"], rows)
    assert result[0]["eligible"] == result[0]["constituents"] == 3
    assert result[0]["rank"] == {"a": 1, "b": 2, "c": 3}
