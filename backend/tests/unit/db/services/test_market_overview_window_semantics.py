"""Market Overview window semantics: three statements, never conflated.

The defect this guards: `build_market_overview` computed each family's own
window movements and then OVERWROTE them, under the same `changes` key, with
returns measured over the shared cross-market comparison domain. Anything
labelling that column "Since Tracking" was reporting the shared comparable
start instead — which is why a Sealed index of 106.18 could sit next to a
"Since Tracking" of +4.06% and look self-contradictory.

Both series are now published. These tests assert they are BOTH present, that
they are genuinely different when the histories differ, and that adding Sealed
submarkets does not move any parent's numbers.
"""

from __future__ import annotations

import pytest

from backend.db.services.pokemon_market_index_service import build_market_overview
from backend.domain.pokemon.market_index import deterministic_fingerprint

FINGERPRINT = deterministic_fingerprint(["cohort"])


def index_row(index_key, day, value, basket, *, sets=3, cards=30):
    return {
        "index_key": index_key,
        "market_date": day,
        "normalized_index_value": value,
        "basket_value": basket,
        "set_count": sets,
        "card_count": cards if index_key == "raw" else sets * 10,
        "cohort_fingerprint": FINGERPRINT,
        "source_generation_fingerprint": f"{index_key}-{day}",
    }


# Raw/Top10 start on Jan 1. Sealed starts LATER (Jan 3), so the shared
# comparable start and Sealed's own tracking start are genuinely different
# dates — the exact situation that produced the contradictory labels.
RAW_DAYS = {"2026-01-01": 100.0, "2026-01-02": 102.0, "2026-01-03": 104.0, "2026-01-04": 106.0}
CHASE_DAYS = {"2026-01-01": 100.0, "2026-01-02": 99.0, "2026-01-03": 98.0, "2026-01-04": 97.0}
SEALED_DAYS = {"2026-01-03": 100.0, "2026-01-04": 106.18}

HISTORY = (
    [index_row("raw", day, value, 8000.0 + index) for index, (day, value) in enumerate(RAW_DAYS.items())]
    + [index_row("top10", day, value, 4000.0 + index) for index, (day, value) in enumerate(CHASE_DAYS.items())]
)


def sealed_market():
    """A Sealed payload shaped like build_global_sealed_market's output."""
    return {
        "basketValue": 22929.90,
        "indexValue": 106.18,
        "historyStartDate": "2026-01-03",
        # Sealed's own strict, current-segment movements: +6.18% since ITS
        # tracking start on Jan 3.
        "changes": {
            "SinceTracking": {
                "available": True, "percent": 6.18, "startDate": "2026-01-03",
                "endDate": "2026-01-04", "targetStartDate": None, "coverage": "full",
            },
        },
        "trend": [[day, value] for day, value in SEALED_DAYS.items()],
        "history": [{"date": day, "indexValue": value, "chainSegmentId": 0} for day, value in SEALED_DAYS.items()],
        "metadata": {"eligibleProductCount": 391},
        "sourceGenerationFingerprint": "sealed",
    }


def overview(**kwargs):
    return build_market_overview(HISTORY, market_date="2026-01-04", **kwargs)


# --- the two vocabularies are both published ------------------------------

def test_every_family_publishes_both_family_specific_and_shared_comparison_windows():
    result = overview(sealed_market=sealed_market())
    for key in ("raw", "topChase", "sealedMarket"):
        assert "familyChanges" in result[key], key
        assert "changes" in result[key], key
        assert result[key]["familyChanges"], key


def test_family_since_tracking_uses_the_family_s_own_start_not_the_shared_one():
    result = overview(sealed_market=sealed_market())
    # Sealed's own tracking began Jan 3 and it is +6.18% since then.
    assert result["sealedMarket"]["familyChanges"]["SinceTracking"]["percent"] == pytest.approx(6.18)
    assert result["sealedMarket"]["familyChanges"]["SinceTracking"]["startDate"] == "2026-01-03"
    # The index level says the same thing about its own base of 100.
    assert result["sealedMarket"]["indexValue"] == pytest.approx(106.18)


def test_the_shared_all_window_is_the_common_comparable_start_not_a_tracking_start():
    result = overview(sealed_market=sealed_market())
    window = result["comparisonWindows"]["SinceTracking"]
    # Raw/Top10 reach back to Jan 1, Sealed only to Jan 3, so the only date
    # every compared family shares is Jan 3.
    assert window["displayStartDate"] == "2026-01-03"
    raw_shared = result["raw"]["changes"]["SinceTracking"]
    assert raw_shared["startDate"] == "2026-01-03"
    # Raw moved 104 -> 106 over the shared domain...
    assert raw_shared["percent"] == pytest.approx((106.0 / 104.0 - 1.0) * 100.0)
    # ...but 100 -> 106 since its OWN tracking start. Two different, both-true
    # numbers, which is exactly why they need different labels.
    assert result["raw"]["familyChanges"]["SinceTracking"]["percent"] == pytest.approx(6.0)
    assert raw_shared["percent"] != pytest.approx(
        result["raw"]["familyChanges"]["SinceTracking"]["percent"]
    )


def test_the_payload_names_what_each_window_vocabulary_means():
    semantics = overview(sealed_market=sealed_market())["windowSemantics"]
    assert semantics["familySinceTrackingLabel"] == "Since Tracking"
    assert semantics["sharedComparisonLabel"] == "Since Comparable Start"
    assert "own base of 100" in semantics["indexValue"]
    assert "own tracking start" in semantics["familyChanges"]
    assert "shared comparison domain" in semantics["changes"]


def test_tracked_value_changes_remain_a_third_separate_series():
    result = overview(sealed_market=sealed_market())
    # basketChanges measures dollars (cohort entry INCLUDED) and is never
    # rewritten by the shared-comparison pass.
    assert result["raw"]["basketChanges"]["SinceTracking"]["available"] is True
    assert result["raw"]["basketChanges"] != result["raw"]["changes"]
    assert result["raw"]["basketChanges"] != result["raw"]["familyChanges"]


# --- adding submarkets must not disturb the parents (spec 27 / 28) --------

def sealed_segments():
    child = {
        "key": "boosterBox",
        "label": "Booster Boxes",
        "available": True,
        "isParent": False,
        "basketValue": 5000.0,
        "indexValue": 112.0,
        "historyStartDate": "2026-01-03",
        "familyChanges": {"SinceTracking": {"available": True, "percent": 12.0,
                                            "startDate": "2026-01-03", "endDate": "2026-01-04",
                                            "targetStartDate": None, "coverage": "full"}},
        "trend": [["2026-01-03", 100.0], ["2026-01-04", 112.0]],
        "metadata": {"eligibleProductCount": 52},
    }
    return {
        "segments": {"total": {**sealed_market(), "key": "total", "label": "Total Sealed",
                               "isParent": True, "available": True},
                     "boosterBox": child},
        "definitions": {"contractVersion": "pokemon-sealed-segments-v1"},
        "reconciliation": {"parentBasketValue": 22929.90},
        "sourceGenerationFingerprint": "segments",
    }


def test_attaching_sealed_segments_leaves_every_parent_number_identical():
    without = overview(sealed_market=sealed_market())
    with_segments = overview(sealed_market=sealed_market(), sealed_segments=sealed_segments())
    for key in ("raw", "topChase", "sealedMarket"):
        assert with_segments[key]["basketValue"] == without[key]["basketValue"], key
        assert with_segments[key]["indexValue"] == without[key]["indexValue"], key
        assert with_segments[key]["changes"] == without[key]["changes"], key
        assert with_segments[key]["familyChanges"] == without[key]["familyChanges"], key
        assert with_segments[key]["trend"] == without[key]["trend"], key


def test_segments_do_not_widen_or_narrow_the_shared_comparison_domain():
    without = overview(sealed_market=sealed_market())
    with_segments = overview(sealed_market=sealed_market(), sealed_segments=sealed_segments())
    assert with_segments["comparisonWindows"] == without["comparisonWindows"]


def test_each_segment_is_measured_against_the_domain_the_parents_established():
    result = overview(sealed_market=sealed_market(), sealed_segments=sealed_segments())
    child = result["sealedSegments"]["segments"]["boosterBox"]
    # Comparable against every other series on the chart...
    assert child["changes"]["SinceTracking"]["startDate"] == "2026-01-03"
    assert child["changes"]["SinceTracking"]["percent"] == pytest.approx(12.0)
    # ...while keeping its own family-specific statement intact.
    assert child["familyChanges"]["SinceTracking"]["percent"] == pytest.approx(12.0)


def test_the_overview_omits_sealed_segments_entirely_when_none_are_supplied():
    assert "sealedSegments" not in overview(sealed_market=sealed_market())
    assert "sealedSegments" not in overview()


def test_a_snapshot_without_sealed_still_builds_raw_and_top_chase():
    result = overview()
    assert result["raw"]["familyChanges"]["SinceTracking"]["percent"] == pytest.approx(6.0)
    assert "sealedMarket" not in result
