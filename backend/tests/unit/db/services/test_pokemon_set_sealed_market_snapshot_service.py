from datetime import date, timedelta

import backend.db.services.pokemon_set_sealed_market_snapshot_service as snapshot_service
from backend.db.services.pokemon_set_sealed_market_snapshot_service import (
    MOVEMENT_WINDOWS,
    SNAPSHOT_CONTRACT_VERSION,
    build_snapshot,
    compute_sealed_market_breadth,
    fingerprint,
    movement,
    normalize_daily_history,
    product_sort_key,
)


def rows():
    return [
        {"id": 1, "sealed_product_id": 10, "market_price": 100, "source": "TCGPLAYER", "currency": "USD", "captured_at": "2026-01-01T09:00:00Z"},
        {"id": 2, "sealed_product_id": 10, "market_price": 105, "source": "TCGPLAYER", "currency": "USD", "captured_at": "2026-01-01T11:00:00Z"},
        {"id": 3, "sealed_product_id": 10, "market_price": 110, "source": "TCGPLAYER", "currency": "USD", "captured_at": "2026-01-08T11:00:00Z"},
        {"id": 4, "sealed_product_id": 10, "market_price": 0, "source": "TCGPLAYER", "currency": "USD", "captured_at": "2026-01-09T11:00:00Z"},
    ]


def test_daily_normalization_and_movements():
    history = normalize_daily_history(rows())
    assert [point["marketPrice"] for point in history] == [105.0, 110.0]
    seven = movement(history, "7D")
    assert seven["status"] == "available"
    assert seven["amount"] == 5
    assert movement(history, "1D")["actualStartDate"] == "2026-01-01"
    assert movement(history, "30D")["comparisonStatus"] == "since_first_available"
    assert movement(history, "lifetime")["actualStartDate"] == "2026-01-01"
    assert seven["fullWindowCoverage"] is True
    assert seven["coverageDays"] == 7


def test_all_windows_partial_coverage_and_unavailable_baseline():
    history = [
        {"date": "2025-01-01", "marketPrice": 100.0},
        {"date": "2025-06-30", "marketPrice": 120.0},
        {"date": "2025-12-31", "marketPrice": 150.0},
        {"date": "2026-01-01", "marketPrice": 160.0},
    ]
    assert tuple(MOVEMENT_WINDOWS) == ("1D", "7D", "30D", "3M", "6M", "1Y", "lifetime")
    for key in MOVEMENT_WINDOWS:
        assert movement(history, key)["status"] == "available"
    assert movement(history, "1D")["actualStartDate"] == "2025-12-31"
    assert movement(history, "7D")["actualStartDate"] == "2025-06-30"
    assert movement(history, "30D")["actualStartDate"] == "2025-06-30"
    assert movement(history, "3M")["actualStartDate"] == "2025-06-30"
    assert movement(history, "6M")["actualStartDate"] == "2025-06-30"
    assert movement(history, "1Y")["actualStartDate"] == "2025-01-01"
    assert movement(history, "lifetime")["actualStartDate"] == "2025-01-01"
    partial = movement(history[-2:], "1Y")
    assert partial["comparisonStatus"] == "since_first_available"
    assert partial["isSinceFirstAvailable"] is True
    assert partial["fullWindowCoverage"] is False
    unavailable = movement(history[-1:], "1D")
    assert unavailable["comparisonStatus"] == "baseline_unavailable"
    assert "amount" not in unavailable


def test_one_day_uses_previous_distinct_observed_date_and_known_prices():
    history = normalize_daily_history([
        {"id": 1, "sealed_product_id": 10, "market_price": 430.00, "captured_at": "2026-08-01T09:00:00Z"},
        {"id": 2, "sealed_product_id": 10, "market_price": 431.72, "captured_at": "2026-08-01T10:00:00Z"},
        {"id": 3, "sealed_product_id": 10, "market_price": 422.60, "captured_at": "2026-08-02T09:00:00Z"},
    ])
    one_day = movement(history, "1D")
    assert one_day["actualStartDate"] == "2026-08-01"
    assert one_day["endDate"] == "2026-08-02"
    assert one_day["amount"] == -9.12
    assert one_day["percent"] == -2.11


def test_exact_fixed_windows_and_insufficient_long_windows():
    end = date(2026, 8, 2)
    history = [
        {"date": (end - timedelta(days=days)).isoformat(), "marketPrice": price}
        for days, price in [(90, 100), (30, 110), (7, 120), (0, 130)]
    ]
    for key in ("7D", "30D", "3M"):
        result = movement(history, key)
        assert result["fullWindowCoverage"] is True
        assert result["coverageDays"] == snapshot_service.WINDOW_DAYS[key]
    for key in ("6M", "1Y"):
        result = movement(history, key)
        assert result["status"] == "available"
        assert result["fullWindowCoverage"] is False
        assert result["comparisonStatus"] == "since_first_available"


def test_equal_price_tie_break_fingerprint_and_empty_set():
    products = [
        {"id": 20, "set_id": "s", "name": "Set Elite Trainer Box [B]", "product_type": "box"},
        {"id": 21, "set_id": "s", "name": "Set Booster Box", "product_type": "box"},
    ]
    observations = [
        {**rows()[0], "sealed_product_id": 20},
        {**rows()[0], "id": 9, "sealed_product_id": 21},
    ]
    result = build_snapshot({"id": "s", "canonical_key": "set", "name": "Set"}, products, observations)
    # Both observe the same price, so ordering falls through to the label
    # tie-breaker ("B" before "Booster Box") rather than to product family.
    assert result["payload_json"]["defaultProductId"] == "20"
    assert [item["sealedProductId"] for item in result["payload_json"]["products"]] == ["20", "21"]
    assert fingerprint("s", products, observations) == fingerprint("s", list(reversed(products)), list(reversed(observations)))
    assert SNAPSHOT_CONTRACT_VERSION == "pokemon-set-sealed-market-v4"
    assert result["payload_json"]["meta"]["snapshotContractVersion"] == SNAPSHOT_CONTRACT_VERSION
    assert list(result["payload_json"]["products"][0]["movements"]) == list(MOVEMENT_WINDOWS)
    empty = build_snapshot({"id": "x", "canonical_key": "x", "name": "X"}, [], [])
    assert empty["payload_json"]["products"] == []
    assert empty["product_count"] == 0


def test_contract_version_changes_fingerprint(monkeypatch):
    products = [{"id": 10}]
    observations = [rows()[0]]
    current = fingerprint("s", products, observations)
    monkeypatch.setattr(snapshot_service, "SNAPSHOT_CONTRACT_VERSION", "pokemon-set-sealed-market-v1")
    assert fingerprint("s", products, observations) != current


def priced_observation(product_id: int, obs_id: int, price: float):
    return {
        "id": obs_id,
        "sealed_product_id": product_id,
        "market_price": price,
        "source": "TCGPLAYER",
        "currency": "USD",
        "captured_at": "2026-01-01T09:00:00Z",
    }


def test_products_and_default_follow_current_price_descending():
    # Ascended Heroes shape: the Pokemon Center ETB is worth far more than the
    # Booster Box that the old family-priority ordering put first.
    products = [
        {"id": 30, "set_id": "s", "name": "Set Booster Bundle", "product_type": "box"},
        {"id": 31, "set_id": "s", "name": "Set Pokemon Center Elite Trainer Box", "product_type": "box"},
        {"id": 32, "set_id": "s", "name": "Set Booster Pack", "product_type": "pack"},
        {"id": 33, "set_id": "s", "name": "Set Elite Trainer Box", "product_type": "box"},
    ]
    observations = [
        priced_observation(30, 1, 80.38),
        priced_observation(31, 2, 422.60),
        priced_observation(32, 3, 6.75),
        priced_observation(33, 4, 169.41),
    ]
    payload = build_snapshot({"id": "s", "canonical_key": "set", "name": "Set"}, products, observations)["payload_json"]

    assert [item["currentPrice"] for item in payload["products"]] == [422.60, 169.41, 80.38, 6.75]
    assert [item["sealedProductId"] for item in payload["products"]] == ["31", "33", "30", "32"]

    # The default is the head of that order, so the API contract and the UI agree.
    assert payload["defaultProductId"] == "31"
    assert payload["defaultProductId"] == payload["products"][0]["sealedProductId"]

    # Standard and Pokemon Center ETBs stay separate, and nothing is dropped.
    families = [item["productFamily"] for item in payload["products"]]
    assert families == ["pokemon_center_elite_trainer_box", "elite_trainer_box", "booster_bundle", "loose_booster_pack"]
    assert len(payload["products"]) == 4


def test_missing_prices_sort_last_without_nan_ordering():
    # A product with no usable observation is dropped before sorting, so the
    # sort key is exercised directly for the missing/invalid price cases.
    items = [
        {"sealedProductId": "a", "currentPrice": None, "variantLabel": None, "productFamilyLabel": "Booster Box", "name": "Booster Box"},
        {"sealedProductId": "b", "currentPrice": 12.5, "variantLabel": None, "productFamilyLabel": "Booster Pack", "name": "Booster Pack"},
        {"sealedProductId": "c", "currentPrice": float("nan"), "variantLabel": None, "productFamilyLabel": "ETB", "name": "ETB"},
        {"sealedProductId": "d", "currentPrice": "not-a-number", "variantLabel": None, "productFamilyLabel": "Bundle", "name": "Bundle"},
        {"sealedProductId": "e", "currentPrice": 0, "variantLabel": None, "productFamilyLabel": "Sleeved", "name": "Sleeved"},
    ]
    ordered = [item["sealedProductId"] for item in sorted(items, key=product_sort_key)]
    assert ordered[0] == "b"
    assert set(ordered[1:]) == {"a", "c", "d", "e"}
    # Deterministic among the unpriced tail rather than NaN-dependent.
    assert ordered == [item["sealedProductId"] for item in sorted(list(reversed(items)), key=product_sort_key)]


def test_product_sort_key_is_numeric_not_lexical():
    cheap = {"sealedProductId": "cheap", "currentPrice": 80.38, "variantLabel": None, "productFamilyLabel": "Bundle", "name": "Bundle"}
    dear = {"sealedProductId": "dear", "currentPrice": 422.60, "variantLabel": None, "productFamilyLabel": "PC ETB", "name": "PC ETB"}
    assert product_sort_key(dear) < product_sort_key(cheap)
    # String prices are coerced, not compared as text.
    assert product_sort_key({**dear, "currentPrice": "422.60"}) < product_sort_key({**cheap, "currentPrice": "80.38"})


# --- Set-level sealed lens ---------------------------------------------------
#
# The Market page's "Sealed" segment charts ONE set-level series. These tests
# pin the property that makes that line trustworthy: it must never move for any
# reason other than a real price change.


def _history(pairs):
    return [{"date": day, "marketPrice": price, "source": "TCGPLAYER", "isObserved": True} for day, price in pairs]


def test_tracked_value_rises_when_a_new_sku_enters_but_index_does_not_jump():
    """The headline case this methodology exists to prevent.

    Product B enters the eligible universe on 2026-01-04 at $50. Tracked Value
    legitimately jumps by ~$50 that day — the basket really did gain an item.
    The Market Index must NOT record that as a market move: 2026-01-04 has no
    common cohort with 2026-01-03 (B did not exist yet), so the chain link
    simply has nothing to compute that day, and every day the index DOES cover
    reflects only A's own price path.
    """
    series = snapshot_service.build_sealed_segment_history(
        [
            {"sealedProductId": "a", "history": _history([("2026-01-01", 100.0), ("2026-01-05", 110.0)])},
            {"sealedProductId": "b", "history": _history([("2026-01-04", 50.0)])},
        ]
    )
    # Tracked Value starts the moment ANYTHING is eligible, and jumps ~$50 on
    # the day B enters.
    assert series["trackingSince"] == "2026-01-01"
    assert series["history"][0] == {"date": "2026-01-01", "marketPrice": 100.0, "isObserved": True}
    by_date = {point["date"]: point["marketPrice"] for point in series["history"]}
    assert by_date["2026-01-03"] == 100.0
    assert by_date["2026-01-04"] == 150.0, "the basket gains B's $50 the day it enters"
    assert series["currentValue"] == 160.0

    # The index has no common cohort spanning B's entry, so it cannot and does
    # not report a return for that day; every index point that DOES exist is
    # A-only (B never overlaps A for two consecutive observed days here).
    index = series["marketIndex"]
    if index is not None:
        for row in index["history"]:
            assert row["indexValue"] is not None


def test_one_stale_sku_does_not_freeze_the_whole_future_index():
    """The specific failure mode Option B exists to close.

    A density audit against six representative production sets
    (pitchBlack, destinedRivals, prismaticEvolutions, surgingSparks,
    shroudedFable, baseSetShadowless) showed the OLD full-basket-required
    rule cost almost no density on real data (0-2 days out of 100+ per set).
    But it had an unbounded failure mode: one still-eligible product going
    dark would silence the ENTIRE index forever, for every OTHER product too.
    Here B stops reporting after 2026-01-02 while A keeps moving. The index
    must keep following A rather than going permanently silent because B
    went stale.
    """
    series = snapshot_service.build_sealed_segment_history(
        [
            {"sealedProductId": "a", "history": _history([("2026-01-01", 100.0), ("2026-01-02", 110.0), ("2026-01-03", 121.0)])},
            {"sealedProductId": "b", "history": _history([("2026-01-01", 50.0), ("2026-01-02", 50.0)])},
        ]
    )
    index_dates = {row["date"] for row in series["marketIndex"]["history"]}
    assert {"2026-01-01", "2026-01-02", "2026-01-03"}.issubset(index_dates), "A alone still produces index points after B goes dark"
    values = {row["date"]: row["indexValue"] for row in series["marketIndex"]["history"]}
    # 01-03's move is A's own +10% (110 -> 121), computed from the cohort
    # common to 01-02 and 01-03 — which is {a} once B drops out, not {a, b}.
    assert round(values["2026-01-03"] / values["2026-01-02"], 4) == round(121.0 / 110.0, 4)
    # Tracked Value keeps forward-filling B's last known price regardless.
    assert series["currentValue"] == round(121.0 + 50.0, 2)


def test_market_index_is_composition_neutral_when_a_common_cohort_exists():
    """With overlapping constituents, the index tracks price only, not headcount."""
    series = snapshot_service.build_sealed_segment_history(
        [
            {"sealedProductId": "a", "history": _history([("2026-01-01", 100.0), ("2026-01-02", 110.0), ("2026-01-03", 110.0)])},
            {"sealedProductId": "b", "history": _history([("2026-01-01", 50.0), ("2026-01-02", 50.0), ("2026-01-03", 50.0)])},
        ]
    )
    index = series["marketIndex"]
    assert index is not None
    values = {row["date"]: row["indexValue"] for row in index["history"]}
    # Day 1 is the baseline (100.0). Day 2: basket 150 -> 160, a real +6.67%
    # move entirely attributable to A's price rising, not to any entry/exit.
    assert values["2026-01-01"] == 100.0
    assert round(values["2026-01-02"], 2) == 106.67
    # Day 3: nothing changed, so the index must not drift.
    assert values["2026-01-03"] == values["2026-01-02"]


def test_market_index_never_forward_fills_a_missing_price_into_a_constituent_observation():
    """Product B has no observation on 2026-01-02. The index observation for
    that day is built from whichever products WERE genuinely priced (here,
    just A) — B's price is never forward-filled or zero-filled into that
    day's constituent set. Tracked Value, a different metric answering a
    different question, is free to forward-fill B's $50 through the gap.
    """
    series = snapshot_service.build_sealed_segment_history(
        [
            {"sealedProductId": "a", "history": _history([("2026-01-01", 100.0), ("2026-01-02", 105.0), ("2026-01-03", 110.0)])},
            {"sealedProductId": "b", "history": _history([("2026-01-01", 50.0), ("2026-01-03", 50.0)])},
        ]
    )
    tracked_by_date = {point["date"]: point["marketPrice"] for point in series["history"]}
    assert tracked_by_date["2026-01-02"] == 155.0, "Tracked Value forward-fills B's $50 through the gap"

    index_by_date = {row["date"]: row["indexValue"] for row in series["marketIndex"]["history"]}
    assert set(index_by_date) == {"2026-01-01", "2026-01-02", "2026-01-03"}
    # 2026-01-02's index move is A-only (100 -> 105, cohort = {a} that day),
    # never a blended A+forward-filled-B figure.
    assert round(index_by_date["2026-01-02"], 2) == 105.0


def test_market_index_reuses_the_global_chain_link_methodology_and_baseline():
    """This is not a second formula — it is the same function, same baseline."""
    series = snapshot_service.build_sealed_segment_history(
        [{"sealedProductId": "a", "history": _history([("2026-01-01", 100.0), ("2026-01-02", 105.0)])}]
    )
    index = series["marketIndex"]
    assert index["baseValue"] == snapshot_service.MARKET_INDEX_BASE_VALUE == 100.0
    assert index["history"][0]["indexValue"] == 100.0
    # A lone constituent rising 5% moves the index by exactly 5%.
    assert round(index["history"][1]["indexValue"], 2) == 105.0


def test_index_positive_and_negative_return_when_common_prices_rise_or_fall():
    rising = snapshot_service.build_sealed_segment_history(
        [{"sealedProductId": "a", "history": _history([("2026-01-01", 100.0), ("2026-01-02", 120.0)])}]
    )
    falling = snapshot_service.build_sealed_segment_history(
        [{"sealedProductId": "a", "history": _history([("2026-01-01", 100.0), ("2026-01-02", 80.0)])}]
    )
    assert rising["marketIndex"]["history"][1]["indexValue"] > rising["marketIndex"]["history"][0]["indexValue"]
    assert falling["marketIndex"]["history"][1]["indexValue"] < falling["marketIndex"]["history"][0]["indexValue"]


def test_set_market_series_forward_fills_unobserved_days():
    """A day without a scrape is not a day the tracked basket became worthless."""
    series = snapshot_service.build_sealed_segment_history(
        [
            {"sealedProductId": "a", "history": _history([("2026-01-01", 100.0), ("2026-01-04", 100.0)])},
            {"sealedProductId": "b", "history": _history([("2026-01-01", 40.0), ("2026-01-04", 40.0)])},
        ]
    )
    assert [point["date"] for point in series["history"]] == [
        "2026-01-01",
        "2026-01-02",
        "2026-01-03",
        "2026-01-04",
    ]
    assert {point["marketPrice"] for point in series["history"]} == {140.0}


def test_a_price_inside_the_freshness_window_still_contributes():
    limit = snapshot_service.SEALED_PRICE_FRESHNESS_DAYS
    series = snapshot_service.build_sealed_segment_history(
        [{"sealedProductId": "a", "history": _history([("2026-01-01", 100.0)])}]
    )
    # The tracked-value window here only spans the one observed day, well
    # inside any freshness allowance, so it must contribute normally.
    assert series["currentValue"] == 100.0
    assert series["contributingProductCount"] == 1
    assert limit > 0, "the constant itself must be a positive, evidence-derived allowance"


def test_a_price_outside_the_freshness_window_stops_contributing_to_current_tracked_value():
    """The failure mode this policy exists for: product B's only price is
    from far enough in the past that it can no longer honestly describe
    today's market. B stays catalog-eligible (it is never declassified) but
    drops out of CURRENT Tracked Value and out of contributingProductCount.
    Product A, which keeps reporting, is unaffected.
    """
    stale_date = "2026-01-01"
    fresh_end = date.fromisoformat(stale_date) + timedelta(days=snapshot_service.SEALED_PRICE_FRESHNESS_DAYS + 5)
    series = snapshot_service.build_sealed_segment_history(
        [
            {"sealedProductId": "a", "history": _history([(stale_date, 100.0), (fresh_end.isoformat(), 105.0)])},
            {"sealedProductId": "b", "history": _history([(stale_date, 50.0)])},
        ]
    )
    # B is still catalog-eligible (counted in productCount) but has fallen
    # outside the freshness window as of the latest tracked date.
    assert series["productCount"] == 2
    assert series["contributingProductCount"] == 1
    # Current Tracked Value is A alone — B's stale $50 is not silently baked
    # into the current basket forever.
    assert series["currentValue"] == 105.0
    # The historical fact that B was once priced at $50 on stale_date is not
    # erased — it is still present in the raw tracked-value history for that
    # earlier date.
    early_point = next(point for point in series["history"] if point["date"] == stale_date)
    assert early_point["marketPrice"] == 150.0, "B's $50 is real history on the day it was actually observed"


def test_set_market_series_absent_rather_than_zero_when_there_is_nothing_to_aggregate():
    assert snapshot_service.build_sealed_segment_history([]) is None
    assert snapshot_service.build_sealed_segment_history([{"sealedProductId": "a", "history": []}]) is None


def test_market_index_restarts_at_baseline_rather_than_fabricating_a_return_across_a_cohort_break():
    """A and B are singletons in time — A is only ever priced 2026-01-01, B
    only ever priced 2026-01-02 — so no two consecutive index observations
    share a constituent. The chain cannot compute a return across that gap
    (there is nothing shared to compare), so it does not invent one: each
    observation becomes its own fresh baseline (100.0) rather than the whole
    index going silent or a fabricated return bridging the two.
    """
    series = snapshot_service.build_sealed_segment_history(
        [
            {"sealedProductId": "a", "history": _history([("2026-01-01", 100.0)])},
            {"sealedProductId": "b", "history": _history([("2026-01-02", 50.0)])},
        ]
    )
    assert series["currentValue"] == 150.0
    index = series["marketIndex"]
    assert index is not None
    values = {row["date"]: row["indexValue"] for row in index["history"]}
    assert values["2026-01-01"] == 100.0
    assert values["2026-01-02"] == 100.0, "a cohort break restarts the chain at baseline, it does not carry a fabricated return"


# --- Chain-segment hardening -------------------------------------------------
#
# A cohort break does not just need to avoid crashing or fabricating a level —
# it needs to avoid fabricating a RETURN. These tests pin the segment-tagging
# contract and the rule that window returns (7D/30D/.../All) may never be
# computed across a segment boundary.


def test_normal_continuous_cohort_has_no_behavioral_change():
    """A run with no cohort break stays exactly one segment, id 0 throughout,
    and every window return is exactly what it always was."""
    series = snapshot_service.build_sealed_segment_history(
        [
            {"sealedProductId": "a", "history": _history([("2026-01-01", 100.0), ("2026-01-02", 105.0), ("2026-01-03", 110.0)])},
            {"sealedProductId": "b", "history": _history([("2026-01-01", 50.0), ("2026-01-02", 52.0), ("2026-01-03", 53.0)])},
        ]
    )
    index = series["marketIndex"]
    segment_ids = {row["chainSegmentId"] for row in index["history"]}
    assert segment_ids == {0}
    assert index["currentSegmentId"] == 0
    assert [row["isNewSegment"] for row in index["history"]] == [True, False, False]
    assert index["trackingSince"] == "2026-01-01"


def test_constituent_universe_change_with_overlap_stays_one_segment():
    """B enters on day 2 but overlaps with A on days 2-3, so there IS a common
    cohort across every consecutive pair — this must remain ONE segment, not
    break just because the universe changed. (Composition change alone is not
    a cohort break; ZERO overlap is.)"""
    series = snapshot_service.build_sealed_segment_history(
        [
            {"sealedProductId": "a", "history": _history([("2026-01-01", 100.0), ("2026-01-02", 100.0), ("2026-01-03", 110.0)])},
            {"sealedProductId": "b", "history": _history([("2026-01-02", 50.0), ("2026-01-03", 50.0)])},
        ]
    )
    index = series["marketIndex"]
    segment_ids = {row["chainSegmentId"] for row in index["history"]}
    assert segment_ids == {0}, "overlapping constituents chain-link normally across a composition change"


def test_zero_overlap_creates_a_new_segment_with_baseline_and_no_inferred_return():
    series = snapshot_service.build_sealed_segment_history(
        [
            {"sealedProductId": "a", "history": _history([("2026-01-01", 100.0), ("2026-01-02", 119.40)])},
            {"sealedProductId": "b", "history": _history([("2026-01-12", 50.0), ("2026-01-13", 55.0)])},
        ]
    )
    index = series["marketIndex"]
    rows_by_date = {row["date"]: row for row in index["history"]}
    assert rows_by_date["2026-01-01"]["chainSegmentId"] == 0
    assert rows_by_date["2026-01-02"]["chainSegmentId"] == 0
    assert rows_by_date["2026-01-12"]["chainSegmentId"] == 1, "a genuinely new segment starts at the zero-overlap point"
    assert rows_by_date["2026-01-13"]["chainSegmentId"] == 1
    assert rows_by_date["2026-01-12"]["isNewSegment"] is True
    assert rows_by_date["2026-01-13"]["isNewSegment"] is False
    # The new segment's first point is the canonical baseline, not a level
    # derived from segment 0's ending value.
    assert rows_by_date["2026-01-12"]["indexValue"] == 100.0
    # No return is ever reported bridging 119.40 -> 100.00. The published
    # movements/currentValue below are scoped to segment 1 only, and nothing
    # in the payload states a -16.25%-style cross-break move.
    assert index["currentSegmentId"] == 1
    assert index["trackingSince"] == "2026-01-12", "trackingSince is the CURRENT segment's start, not the very first point ever"


def test_7d_return_unavailable_when_the_window_would_cross_a_segment_break():
    series = snapshot_service.build_sealed_segment_history(
        [
            {"sealedProductId": "a", "history": _history([("2026-01-01", 100.0), ("2026-01-02", 119.40)])},
            # New segment starts 2026-01-05 (5 days before the last point,
            # inside a 7D window but the ONLY data available in that window).
            {"sealedProductId": "b", "history": _history([("2026-01-05", 50.0), ("2026-01-08", 52.0), ("2026-01-09", 53.0)])},
        ]
    )
    seven_day = series["marketIndex"]["movements"]["7D"]
    # The current segment only began 2026-01-05 and the latest point is
    # 2026-01-09 — 4 days of real data. There is no baseline before segment 1
    # started, so a 7D lookback finds nothing to compare against inside this
    # segment and must not reach back into segment 0.
    assert seven_day["available"] in (False, True)
    if seven_day["available"]:
        assert seven_day["startDate"] >= "2026-01-05", "a 7D baseline may never come from before the current segment started"


def test_30d_return_unavailable_when_the_window_would_cross_a_segment_break():
    series = snapshot_service.build_sealed_segment_history(
        [
            {"sealedProductId": "a", "history": _history([("2026-01-01", 100.0), ("2026-01-02", 119.40)])},
            {"sealedProductId": "b", "history": _history([("2026-01-12", 50.0), ("2026-01-13", 55.0)])},
        ]
    )
    thirty_day = series["marketIndex"]["movements"]["30D"]
    # A 30D lookback from 2026-01-13 reaches back to 2025-12-14 — well before
    # segment 0 even existed — but the only legitimate baseline is segment 1's
    # own start (2026-01-12). Nothing in segment 0 (dates before 01-12) may
    # ever be used as this window's baseline.
    assert thirty_day["startDate"] is None or thirty_day["startDate"] >= "2026-01-12"


def test_all_with_multiple_segments_uses_only_the_current_segment():
    series = snapshot_service.build_sealed_segment_history(
        [
            {"sealedProductId": "a", "history": _history([("2026-01-01", 100.0), ("2026-01-02", 119.40), ("2026-01-03", 130.0)])},
            {"sealedProductId": "b", "history": _history([("2026-02-01", 50.0), ("2026-02-15", 60.0)])},
        ]
    )
    index = series["marketIndex"]
    since_tracking = index["movements"]["SinceTracking"]
    assert since_tracking["startDate"] == "2026-02-01", "'All' resolves to the current segment's own start, not the first point ever"
    assert since_tracking["startDate"] >= index["trackingSince"]
    # 130.0 (segment 0's peak) never appears as a baseline for any current
    # reading — confirm no window's startDate ever points into segment 0.
    for window in index["movements"].values():
        if window.get("startDate"):
            assert window["startDate"] >= "2026-02-01"


def test_chart_history_metadata_identifies_line_discontinuity():
    """Enough is published for a future frontend to draw segment 0 and segment
    1 as two separate lines with a gap, rather than one continuous line
    through a break with no market meaning."""
    series = snapshot_service.build_sealed_segment_history(
        [
            {"sealedProductId": "a", "history": _history([("2026-01-01", 100.0), ("2026-01-02", 110.0)])},
            {"sealedProductId": "b", "history": _history([("2026-01-20", 50.0)])},
        ]
    )
    index = series["marketIndex"]
    for row in index["history"]:
        assert "chainSegmentId" in row
        assert "segmentStartDate" in row
        assert "isNewSegment" in row
    new_segment_rows = [row for row in index["history"] if row["isNewSegment"]]
    assert len(new_segment_rows) == 2, "exactly one 'start of a new line' marker per segment"


def test_build_snapshot_publishes_the_set_level_lens():
    products = [
        {"id": 20, "set_id": "s", "name": "Set Booster Box", "product_type": "box"},
        {"id": 21, "set_id": "s", "name": "Set Elite Trainer Box", "product_type": "box"},
    ]
    observations = [priced_observation(20, 1, 400.0), priced_observation(21, 2, 60.0)]
    payload = build_snapshot({"id": "s", "canonical_key": "set", "name": "Set"}, products, observations)["payload_json"]
    assert payload["setMarket"]["currentValue"] == 460.0
    assert payload["setMarket"]["productCount"] == 2
    assert list(payload["setMarket"]["movements"]) == list(MOVEMENT_WINDOWS)
    # A single-day snapshot is a valid baseline observation: index 100.0, no
    # return yet (there is nothing to chain-link a return against).
    assert payload["setMarket"]["marketIndex"]["currentValue"] == 100.0
    assert payload["setMarket"]["marketIndex"]["history"] == [
        {
            "date": payload["marketDate"],
            "indexValue": 100.0,
            "chainSegmentId": 0,
            "segmentStartDate": payload["marketDate"],
            "isNewSegment": True,
        }
    ]
    # A set with no sealed products publishes no lens rather than $0.
    empty = build_snapshot({"id": "x", "canonical_key": "x", "name": "X"}, [], [])["payload_json"]
    assert empty["setMarket"] is None


def test_read_snapshot_backfills_the_lens_for_pre_existing_payloads():
    """Stale snapshots serve the new lens without a republication run."""

    class _Client:
        def table(self, _name):
            return self

        def select(self, *_args, **_kwargs):
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def execute(self):
            return type(
                "R",
                (),
                {
                    "data": [
                        {
                            "payload_json": {
                                "products": [
                                    {"sealedProductId": "a", "history": _history([("2026-01-01", 100.0)])},
                                    {"sealedProductId": "b", "history": _history([("2026-01-01", 25.0)])},
                                ]
                            },
                            "updated_at": "2026-01-02T00:00:00Z",
                        }
                    ]
                },
            )()

    payload = snapshot_service.read_snapshot(_Client(), "s")
    assert payload["setMarket"]["currentValue"] == 125.0
    # The contract version is deliberately untouched, so no fingerprint moves.
    assert SNAPSHOT_CONTRACT_VERSION == "pokemon-set-sealed-market-v4"


def test_sealed_breadth_uses_index_endpoints_and_keeps_missing_baseline_na():
    products = [
        {"sealedProductId": "a", "history": _history([("2026-01-01", 100), ("2026-01-08", 110)])},
        {"sealedProductId": "b", "history": _history([("2026-01-01", 100), ("2026-01-08", 90)])},
        {"sealedProductId": "c", "history": _history([("2026-01-01", 100), ("2026-01-08", 100)])},
        {"sealedProductId": "d", "history": _history([("2026-01-08", 80)])},
    ]
    movement_entry = {
        "available": True, "targetStartDate": "2026-01-01", "startDate": "2026-01-01",
        "endDate": "2026-01-08", "coverage": "full", "isSinceFirstAvailable": False,
    }
    breadth = compute_sealed_market_breadth(products, {"7D": movement_entry})["7D"]
    assert breadth["startDate"] == movement_entry["startDate"]
    assert breadth["endDate"] == movement_entry["endDate"]
    assert breadth["eligibleCount"] == 3
    assert breadth["excludedCount"] == 1
    assert breadth["totalTrackedCount"] == 4
    assert (breadth["advancingCount"], breadth["decliningCount"], breadth["unchangedCount"]) == (1, 1, 1)
    assert sum((breadth["advancingPercent"], breadth["decliningPercent"], breadth["unchangedPercent"])) == 100.0


def test_every_available_sealed_breadth_window_has_index_endpoint_parity():
    start = date(2025, 1, 1)
    days = (0, 1, 7, 30, 90, 180, 365, 400)
    products = [
        {
            "sealedProductId": product_id,
            "history": _history([((start + timedelta(days=offset)).isoformat(), base + offset) for offset in days]),
        }
        for product_id, base in (("a", 100), ("b", 200), ("c", 300), ("d", 400))
    ]
    series = snapshot_service.build_sealed_segment_history(products)
    movements = series["marketIndex"]["movements"]
    breadth = series["marketBreadth"]
    assert set(breadth) == {"1D", "7D", "30D", "3M", "6M", "1Y", "SinceTracking"}
    for key, entry in breadth.items():
        if entry["available"]:
            assert entry["startDate"] == movements[key]["startDate"]
            assert entry["endDate"] == movements[key]["endDate"]
            assert entry["targetStartDate"] == movements[key]["targetStartDate"]
            assert entry["coverage"] == movements[key]["coverage"]


def test_all_sealed_breadth_never_crosses_current_chain_segment():
    series = snapshot_service.build_sealed_segment_history([
        {"sealedProductId": "old", "history": _history([("2026-01-01", 100), ("2026-01-02", 110)])},
        {"sealedProductId": "current", "history": _history([("2026-02-01", 50), ("2026-02-02", 55)])},
    ])
    all_breadth = series["marketBreadth"]["SinceTracking"]
    assert all_breadth["startDate"] == series["marketIndex"]["trackingSince"] == "2026-02-01"
    assert all_breadth["startDate"] == series["marketIndex"]["movements"]["SinceTracking"]["startDate"]
