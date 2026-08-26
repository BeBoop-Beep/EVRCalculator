from datetime import date, timedelta

import pytest

from backend.db.services.pokemon_global_sealed_market_service import (
    GlobalSealedMarketUnavailable,
    build_global_sealed_market,
)
from backend.db.services.pokemon_market_index_service import build_market_overview


def product(product_id, points):
    return {
        "sealedProductId": product_id,
        "name": product_id,
        "history": [
            {"date": day, "marketPrice": value, "source": "TEST", "isObserved": True}
            for day, value in points
        ],
    }


def snapshot(*products):
    return {"products": list(products)}


def test_global_sealed_aggregates_eligible_prepared_products_and_tracked_value():
    sealed = build_global_sealed_market([
        snapshot(product("box-a", [("2026-01-01", 100), ("2026-01-02", 110)])),
        snapshot(product("etb-b", [("2026-01-01", 50), ("2026-01-02", 55)])),
    ], market_date="2026-01-02")
    assert sealed["basketValue"] == pytest.approx(165)
    assert sealed["indexValue"] == pytest.approx(110)
    assert sealed["changes"]["1D"]["percent"] == pytest.approx(10)
    assert sealed["metadata"] == {
        "eligibleProductCount": 2,
        "contributingProductCount": 2,
        "observationCount": 4,
        "trackingStart": "2026-01-01",
        "currentSegmentId": 0,
        "historyPointCount": 2,
        "sourceSetCount": 2,
    }


def test_product_entry_and_exit_change_value_without_fake_index_return():
    entered = build_global_sealed_market([snapshot(
        product("a", [("2026-01-01", 100), ("2026-01-02", 100), ("2026-01-03", 100)]),
        product("b", [("2026-01-02", 500)]),
    )], market_date="2026-01-03")
    # Entry adds $500 to tracked value on Jan 2; common-cohort A stayed flat.
    assert entered["basketValue"] == pytest.approx(600)
    assert entered["indexValue"] == pytest.approx(100)
    assert entered["changes"]["1D"]["percent"] == pytest.approx(0)

    exited = build_global_sealed_market([snapshot(
        product("a", [("2026-01-01", 100), ("2026-01-02", 100)]),
        product("b", [("2026-01-01", 500)]),
    )], market_date="2026-01-02")
    assert exited["indexValue"] == pytest.approx(100)


def test_stale_product_stops_contributing_after_canonical_freshness_window():
    sealed = build_global_sealed_market([snapshot(
        product("stale", [("2026-01-01", 100)]),
        product("fresh", [("2026-01-01", 50), ("2026-02-01", 50)]),
    )], market_date="2026-02-01")
    assert sealed["basketValue"] == pytest.approx(50)
    assert sealed["metadata"]["eligibleProductCount"] == 2
    assert sealed["metadata"]["contributingProductCount"] == 1


def test_zero_overlap_starts_new_segment_and_since_tracking_is_current_segment_only():
    sealed = build_global_sealed_market([snapshot(
        product("old", [("2026-01-01", 100)]),
        product("new", [("2026-02-01", 200), ("2026-02-02", 220)]),
    )], market_date="2026-02-02")
    assert [point["chainSegmentId"] for point in sealed["history"]] == [0, 1, 1]
    assert sealed["trend"] == [["2026-02-01", 100.0], ["2026-02-02", 110.00000000000001]]
    assert sealed["changes"]["SinceTracking"]["percent"] == pytest.approx(10)


def test_insufficient_history_and_promoted_date_forward_fill_safely():
    one = build_global_sealed_market(
        [snapshot(product("a", [("2026-01-01", 100)]))], market_date="2026-01-01"
    )
    assert one["changes"]["1D"]["available"] is False
    assert one["changes"]["7D"]["available"] is False
    filled = build_global_sealed_market(
        [snapshot(product("a", [("2026-01-01", 100)]))], market_date="2026-01-02"
    )
    assert filled["basketValue"] == pytest.approx(100)
    assert filled["metadata"]["historyPointCount"] == 1


def test_global_sealed_windows_use_true_elapsed_day_baselines():
    end = date(2026, 8, 24)
    points = [
        ((end - timedelta(days=offset)).isoformat(), 400 - offset)
        for offset in reversed(range(91))
    ]
    sealed = build_global_sealed_market([snapshot(product("daily", points))], market_date=end.isoformat())
    assert sealed["changes"]["7D"]["targetStartDate"] == "2026-08-17"
    assert sealed["changes"]["7D"]["startDate"] == "2026-08-17"
    assert sealed["changes"]["30D"]["targetStartDate"] == "2026-07-25"
    assert sealed["changes"]["30D"]["startDate"] == "2026-07-25"
    assert sealed["changes"]["3M"]["targetStartDate"] == "2026-05-26"
    assert sealed["changes"]["3M"]["startDate"] == "2026-05-26"


def test_market_overview_extension_does_not_change_raw_or_top10():
    # A minimal valid persisted history, already prepared by the unchanged card path.
    history = []
    for key, basket, cards in (("raw", 100, 20), ("top10", 60, 10)):
        history.append({
            "index_key": key, "market_date": "2026-01-01", "basket_value": basket,
            "normalized_index_value": 100, "set_count": 1, "card_count": cards,
            "cohort_fingerprint": "same", "source_generation_fingerprint": key,
        })
    baseline = build_market_overview(history, market_date="2026-01-01")
    sealed = build_global_sealed_market(
        [snapshot(product("a", [("2026-01-01", 25)]))], market_date="2026-01-01"
    )
    extended = build_market_overview(history, market_date="2026-01-01", sealed_market=sealed)
    assert extended["raw"] == baseline["raw"]
    assert extended["topChase"] == baseline["topChase"]
    assert extended["sealedMarket"]["indexValue"] == sealed["indexValue"]
    assert extended["sealedMarket"]["basketValue"] == sealed["basketValue"]
    assert extended["sealedMarket"]["trend"] == sealed["trend"]
    assert "comparisonWindows" in extended


def test_total_sealed_publishes_its_own_current_constituents_including_the_residual():
    """Total Sealed must show every eligible product, residual families included.

    The five published families cover 129 of 139 eligible products; the other
    ten are the `otherSealed` residual and belong to no child market. Total
    Sealed is the only surface that can show them, so summarising it from the
    children instead of from the parent's own universe would silently drop
    exactly those ten and break reconciliation against
    metadata.eligibleProductCount.
    """
    market_date = "2026-08-25"
    payloads = [
        {
            "setId": "set-a",
            "setName": "Alpha",
            "marketDate": market_date,
            "products": [
                {
                    "sealedProductId": f"product-{index}",
                    "name": f"Product {index}",
                    "productFamily": family,
                    "productFamilyLabel": family.replace("_", " ").title(),
                    "currentPrice": 100.0 + index,
                    "history": [
                        {"date": "2026-08-24", "marketPrice": 100.0 + index},
                        {"date": market_date, "marketPrice": 100.0 + index},
                    ],
                }
                for index, family in enumerate(
                    ["booster_box", "elite_trainer_box", "half_booster_box", "enhanced_booster_box"]
                )
            ],
        }
    ]

    total = build_global_sealed_market(payloads, market_date=market_date)
    summary = total.get("currentConstituents")
    assert summary is not None, "Total Sealed must publish its current composition"

    # Reconciles with the parent's own eligibility count.
    assert summary["totalCount"] == total["metadata"]["eligibleProductCount"]

    ids = [row["sealedProductId"] for row in summary["topConstituents"]]
    assert len(ids) == len(set(ids)), "no product may appear twice"

    # The residual families are present, which is the whole point.
    families = {row["productFamily"] for row in summary["topConstituents"]}
    assert "half_booster_box" in families
    assert "enhanced_booster_box" in families
    # And so are the published ones.
    assert "booster_box" in families and "elite_trainer_box" in families

    # Current composition only: no historical observation series leaks out.
    for row in summary["topConstituents"]:
        assert "history" not in row
