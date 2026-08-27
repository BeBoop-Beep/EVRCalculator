import pytest

from backend.db.services.era_set_strength_service import build_era_set_strength


def target(identity, era, score, *, rankable=True, version="set-rip-v1"):
    return {"set_id": identity, "name": identity, "era": era, "era_id": era,
            "publicAnalyticsStatus": "analytics_ready",
            "setRipV1": {"score": score, "rank": 1, "tier": "B", "rankable": rankable,
                         "methodologyVersion": version}}


def test_equal_set_mean_rank_tier_and_constituent_context():
    result = build_era_set_strength([
        target("a1", "A", 90), target("a2", "A", 89), target("a3", "A", 40),
        target("b1", "B", 75), target("b2", "B", 74), target("b3", "B", 73),
    ])
    by_name = {row["eraName"]: row for row in result["eras"]}
    assert by_name["B"]["score"] == pytest.approx(74)
    assert by_name["B"]["rank"] == 1
    assert by_name["A"]["score"] == pytest.approx(73)
    assert by_name["A"]["strongestSet"]["setName"] == "a1"
    assert len(by_name["A"]["constituentSets"]) == 3


def test_incomplete_coverage_is_not_partially_averaged():
    result = build_era_set_strength([
        target("a1", "A", 90), target("a2", "A", 80), target("a3", "A", None, rankable=False)
    ])
    era = result["eras"][0]
    assert era["score"] is None
    assert era["statusReason"] == "incomplete_set_rip_coverage"


def test_mixed_set_rip_versions_fail_closed():
    with pytest.raises(ValueError):
        build_era_set_strength([
            target("a1", "A", 90, version="one"), target("a2", "A", 80, version="one"),
            target("a3", "A", 70, version="two")
        ])
