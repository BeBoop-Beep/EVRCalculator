"""Market Overview parity audit: it must fail for real reasons, and only those.

This audit exists to answer one question — "is the published `marketOverview`
the one this market date should have?" — and it previously answered it wrongly.
It composed its own expected overview WITHOUT `cardSegments`, so a healthy
snapshot was reported as having an unexpected key; and because a keys mismatch
stopped the comparison at that level, the false failure also hid the genuine
one underneath it (prepared `currentConstituents` missing from a stale
snapshot). Both halves of that bug are pinned here.
"""

from __future__ import annotations

from backend.scripts.audit_pokemon_market_index_publication import (
    _compare_json,
    _prepared_constituent_failures,
)


def _segment(key, *, available=True, constituents=True):
    segment = {"key": key, "available": available, "basketValue": 1.0}
    if available and constituents:
        segment["currentConstituents"] = {
            "asOf": "2026-08-25",
            "totalConstituentCount": 3,
            "topConstituents": [{"id": "a"}],
        }
    return segment


def _overview(*, card_constituents=True, sealed_constituents=True, with_card_segments=True):
    overview = {
        "raw": {"indexValue": 100.0, "changes": {"7D": 1.0}, "basketChanges": {"7D": 2.0}},
        "topChase": {"indexValue": 101.0, "changes": {"7D": 1.0}, "basketChanges": {"7D": 2.0}},
        "sealedMarket": {"basketValue": 10.0},
        "sealedSegments": {
            "segments": {
                "eliteTrainerBox": _segment("eliteTrainerBox", constituents=sealed_constituents),
                "boosterBox": _segment("boosterBox", constituents=sealed_constituents),
            }
        },
    }
    if with_card_segments:
        overview["cardSegments"] = {
            "raw": {
                "segments": {
                    "specialIllustrationRare": _segment(
                        "specialIllustrationRare", constituents=card_constituents
                    ),
                    "rareHolo": _segment("rareHolo", available=False),
                }
            }
        }
    return overview


# A. A healthy current payload — cardSegments included — passes cleanly.
def test_healthy_payload_with_card_segments_passes():
    expected = _overview()
    failures: list[str] = []
    _compare_json(expected, _overview(), "marketOverview", failures)
    assert failures == []
    assert _prepared_constituent_failures(expected, _overview()) == []


# B. A snapshot genuinely missing cardSegments still fails, and says so.
def test_missing_card_segments_fails_meaningfully():
    failures: list[str] = []
    _compare_json(_overview(), _overview(with_card_segments=False), "marketOverview", failures)
    assert any("cardSegments" in line for line in failures)
    assert any("missing from actual" in line for line in failures)


# C. The drift that actually shipped: prepared segments without their summaries.
def test_missing_prepared_constituents_is_detected_and_named():
    failures = _prepared_constituent_failures(
        _overview(), _overview(card_constituents=False, sealed_constituents=False)
    )
    joined = "\n".join(failures)
    assert "marketOverview.cardSegments.raw.segments" in joined
    assert "specialIllustrationRare" in joined
    assert "marketOverview.sealedSegments.segments" in joined
    assert "eliteTrainerBox" in joined and "boosterBox" in joined
    assert "republish required" in joined
    # An UNAVAILABLE segment carries no constituents by design and must not be
    # reported as drift.
    assert "rareHolo" not in joined


# C2. The masking bug: a top-level difference must not hide a nested one.
def test_a_top_level_key_difference_does_not_mask_nested_drift():
    failures: list[str] = []
    _compare_json(
        _overview(),
        _overview(with_card_segments=False, sealed_constituents=False),
        "marketOverview",
        failures,
    )
    # The top-level cardSegments difference is reported...
    assert any("marketOverview keys mismatch" in line for line in failures)
    # ...AND the walk continues into the keys both sides share, so the sealed
    # drift beneath it is still found. Returning early is what hid this.
    assert any(
        "sealedSegments.segments.eliteTrainerBox keys mismatch" in line for line in failures
    )


# D. Contract-irrelevant extra metadata on a segment is still a difference, but
#    it is reported as an unexpected key rather than as corruption.
def test_extra_metadata_is_named_not_conflated_with_corruption():
    actual = _overview()
    actual["sealedSegments"]["segments"]["eliteTrainerBox"]["diagnosticNote"] = "x"
    failures: list[str] = []
    _compare_json(_overview(), actual, "marketOverview", failures)
    assert any("unexpected in actual: ['diagnosticNote']" in line for line in failures)
    assert not any("numeric mismatch" in line for line in failures)
    # It is not prepared-constituent drift, so that verdict stays silent.
    assert _prepared_constituent_failures(_overview(), actual) == []


# E. Raw / Top Chase / Sealed comparisons are unchanged by the repair.
def test_raw_top_chase_and_sealed_comparisons_are_unchanged():
    actual = _overview()
    actual["raw"]["indexValue"] = 99.0
    actual["topChase"]["changes"] = {"7D": 5.0}
    actual["sealedMarket"]["basketValue"] = 11.0
    failures: list[str] = []
    _compare_json(_overview(), actual, "marketOverview", failures)
    assert any("marketOverview.raw.indexValue numeric mismatch" in line for line in failures)
    assert any("marketOverview.topChase.changes.7D numeric mismatch" in line for line in failures)
    assert any("marketOverview.sealedMarket.basketValue numeric mismatch" in line for line in failures)


def test_publisher_and_audit_share_one_overview_authority():
    """Neither may build its own expected overview again."""
    from backend.scripts import audit_pokemon_market_index_publication as audit
    from backend.scripts import build_pokemon_explore_set_value_snapshot as publisher

    assert audit.build_canonical_market_overview is publisher.build_canonical_market_overview
    assert audit.resolve_canonical_overview_sets is publisher.resolve_canonical_overview_sets
