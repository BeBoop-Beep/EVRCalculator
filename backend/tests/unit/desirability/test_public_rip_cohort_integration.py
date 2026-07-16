"""Canonical RIP, RIP Core, and the 21-set public cohort, end to end in the service.

Drives ``_attach_public_rip_contract`` with a stubbed Collector Appeal bundle, so
the cohort/rank/weight behaviour is tested without a database. The numbers are
the real ones: the CA7 values below are production's, per the dry-run artifact.
"""

from __future__ import annotations

import pytest

from backend.db.services import explore_rip_statistics_service as service
from backend.desirability.public_analytics_policy import (
    HIDDEN_PENDING_VALIDATION,
    SWORD_AND_SHIELD_ERA_ID,
)
from backend.desirability.scoring_config import DEFAULT_RIP_WEIGHTS

SV_ERA = "dfb0dfa1-6a8e-4335-850f-e003867e19ee"
ME_ERA = "fb22f860-ae41-4879-a41a-857ca11bf0da"

# name -> (era_id, CA7 x100, profit, safety, stability)
READY = {
    "Ascended Heroes": (ME_ERA, 96.0942, 90.0, 80.0, 70.0),
    "Chaos Rising": (ME_ERA, 75.4929, 60.0, 55.0, 50.0),
    "Shrouded Fable": (SV_ERA, 56.7918, 40.0, 45.0, 42.0),
    "Prismatic Evolutions": (SV_ERA, 94.6179, 95.0, 85.0, 60.0),
    "Black Bolt": (SV_ERA, 85.1027, 70.0, 60.0, 65.0),
    "Destined Rivals": (SV_ERA, 89.8659, 65.0, 62.0, 58.0),
    "Journey Together": (SV_ERA, 89.3347, 55.0, 52.0, 48.0),
    "Mega Evolution": (ME_ERA, 90.0581, 75.0, 70.0, 68.0),
    "Obsidian Flames": (SV_ERA, 88.8906, 50.0, 48.0, 44.0),
    "Paldea Evolved": (SV_ERA, 91.3821, 52.0, 50.0, 46.0),
    "Paldean Fates": (SV_ERA, 95.7943, 80.0, 75.0, 72.0),
    "Paradox Rift": (SV_ERA, 88.6375, 45.0, 43.0, 41.0),
    "Perfect Order": (ME_ERA, 84.7975, 68.0, 66.0, 64.0),
    "Phantasmal Flames": (ME_ERA, 92.4631, 72.0, 71.0, 69.0),
    "Scarlet and Violet 151": (SV_ERA, 94.5391, 85.0, 82.0, 78.0),
    "Scarlet and Violet Base Set": (SV_ERA, 79.6771, 42.0, 40.0, 38.0),
    "Stellar Crown": (SV_ERA, 88.1232, 58.0, 56.0, 54.0),
    "Surging Sparks": (SV_ERA, 90.8714, 62.0, 60.0, 59.0),
    "Temporal Forces": (SV_ERA, 88.0610, 48.0, 46.0, 45.0),
    "Twilight Masquerade": (SV_ERA, 84.2445, 44.0, 42.0, 43.0),
    "White Flare": (SV_ERA, 88.1582, 66.0, 64.0, 62.0),
}

# The 12 SWSH sets: simulated, but no CA7 and not approved for public analytics.
HIDDEN = [
    "Astral Radiance", "Battle Styles", "Brilliant Stars", "Chilling Reign",
    "Darkness Ablaze", "Evolving Skies", "Fusion Strike", "Lost Origin",
    "Rebel Clash", "Silver Tempest", "Sword & Shield", "Vivid Voltage",
]


def _collector_payload(name, ca7_x100):
    return {
        "setId": name,
        "setName": name,
        "status": "available",
        "asOf": "2026-07-16T00:00:00Z",
        "rosterDesirability": {"score": 90.0, "version": "universal_set_desirability_v3"},
        "dualPathDepth": {"rawValue": 0.27143, "displayPercent": 27.1, "version": "dual_path_depth_v1"},
        "collectorAppeal": {"score": ca7_x100, "rawValue": ca7_x100 / 100.0, "version": "collector_appeal_ca7_v1"},
        "chaseAppeal": {"score": 70.0, "rawValue": 0.70, "version": "chase_appeal_ca2_v1"},
        "topSubjects": [],
        "coverage": {"status": "available", "reasons": []},
    }


def _unavailable_payload(name):
    return {
        "setId": name,
        "setName": name,
        "status": "unavailable",
        "rosterDesirability": {"score": 60.0},
        "dualPathDepth": {"rawValue": None, "displayPercent": None},
        "collectorAppeal": {"score": None, "rawValue": None},
        "chaseAppeal": {"score": None, "rawValue": None},
        "topSubjects": [],
        "coverage": {
            "status": "unavailable",
            "reasons": ["dual_path_depth_unavailable_no_pull_model"],
        },
    }


@pytest.fixture
def targets(monkeypatch):
    rows = []
    payloads = {}
    for name, (era_id, ca7, profit, safety, stability) in READY.items():
        rows.append(
            {
                "target_id": name,
                "set_id": name,
                "name": name,
                "era_id": era_id,
                "era": "Scarlet and Violet" if era_id == SV_ERA else "Mega Evolution",
                "profit_score": profit,
                "safety_score": safety,
                "stability_score": stability,
                # Legacy fields present, and deliberately inconsistent with the
                # canonical ones so a test can prove nothing reads them.
                "pack_score": 12.3,
                "relative_pack_score": 98.4,
                "pack_rank": 99,
            }
        )
        payloads[name] = _collector_payload(name, ca7)
    for name in HIDDEN:
        rows.append(
            {
                "target_id": name,
                "set_id": name,
                "name": name,
                "era_id": SWORD_AND_SHIELD_ERA_ID,
                "era": "Sword and Shield",
                "profit_score": 99.0,  # would top every financial rank if included
                "safety_score": 99.0,
                "stability_score": 99.0,
                "pack_score": 99.0,
                "relative_pack_score": 100.0,
            }
        )
        payloads[name] = _unavailable_payload(name)

    monkeypatch.setattr(
        service, "get_collector_appeal_bundle", lambda **_: {"payloads": payloads}
    )
    return rows


def _attach(rows):
    sources, warnings = {}, []
    cohort = service._attach_public_rip_contract(rows, sources=sources, warnings=warnings)
    return cohort, warnings


# ---------------------------------------------------------------------------
# Cohort
# ---------------------------------------------------------------------------

def test_public_cohort_is_exactly_21(targets):
    cohort, warnings = _attach(targets)
    assert cohort["eligibleSetCount"] == 21
    assert cohort["excludedCountsByReason"][HIDDEN_PENDING_VALIDATION] == 12
    assert warnings == []


def test_all_21_public_sets_have_collector_appeal(targets):
    _attach(targets)
    ready = [row for row in targets if row["name"] in READY]
    assert len(ready) == 21
    for row in ready:
        assert row["openingExperience"]["collectorAppeal"]["score"] is not None, row["name"]


def test_all_21_public_sets_receive_a_canonical_rip(targets):
    _attach(targets)
    for row in (r for r in targets if r["name"] in READY):
        assert row["rip"]["score"] is not None, row["name"]
        assert row["rip"]["rank"] is not None
        assert row["rip"]["cohortSize"] == 21


def test_every_public_rank_denominator_is_21(targets):
    _attach(targets)
    for row in (r for r in targets if r["name"] in READY):
        assert row["rip"]["cohortSize"] == 21
        assert row["ripCore"]["cohortSize"] == 21
        for pillar in ("profit", "safety", "stability", "desirability"):
            assert row["rip"]["components"][pillar]["cohortSize"] == 21
        opening = row["openingExperience"]
        for key in ("rosterDesirability", "collectorAppeal", "chaseAppeal", "dualPathDepth"):
            assert opening[key]["cohortSize"] == 21, key
        assert opening["cohort"]["eligibleSetCount"] == 21


def test_ranks_run_1_to_21_with_no_gaps(targets):
    _attach(targets)
    ranks = sorted(row["rip"]["rank"] for row in targets if row["name"] in READY)
    assert ranks == list(range(1, 22))


def test_hidden_sets_are_never_ranked(targets):
    _attach(targets)
    for row in (r for r in targets if r["name"] in HIDDEN):
        assert row["rip"].get("rank") is None, row["name"]
        assert row["ripCore"].get("rank") is None
        assert row["publicAnalyticsStatus"] == HIDDEN_PENDING_VALIDATION


def test_hidden_sets_do_not_influence_any_public_rank(targets):
    """The SWSH rows carry 99.0 financials - top of every pillar if counted."""
    _attach(targets)
    best_profit = min(
        (r for r in targets if r["name"] in READY),
        key=lambda r: r["rip"]["components"]["profit"]["rank"],
    )
    # Prismatic Evolutions has the highest profit among ELIGIBLE sets (95.0).
    assert best_profit["name"] == "Prismatic Evolutions"
    assert best_profit["rip"]["components"]["profit"]["rank"] == 1


def test_a_hidden_set_does_not_receive_a_canonical_public_rip(targets):
    _attach(targets)
    hidden = next(r for r in targets if r["name"] == "Evolving Skies")
    assert hidden["rip"]["score"] is None
    assert hidden["rip"]["status"] == "incomplete_missing_desirability"


# ---------------------------------------------------------------------------
# RIP weights and the CA7 pillar
# ---------------------------------------------------------------------------

def test_full_rip_uses_58_20_12_10(targets):
    _attach(targets)
    row = next(r for r in targets if r["name"] == "Ascended Heroes")
    weights = row["rip"]["effectiveWeights"]
    assert weights["profit"] == pytest.approx(0.58)
    assert weights["safety"] == pytest.approx(0.20)
    assert weights["stability"] == pytest.approx(0.12)
    assert weights["desirability"] == pytest.approx(0.10)


def test_the_ten_percent_pillar_is_ca7_not_universal_desirability(targets):
    _attach(targets)
    row = next(r for r in targets if r["name"] == "Ascended Heroes")
    pillar = row["rip"]["components"]["desirability"]["score"]
    # CA7 x100 = 96.0942, Roster Desirability = 90.0 in the fixture.
    assert pillar == pytest.approx(96.0942, abs=5e-4)
    assert pillar != row["openingExperience"]["rosterDesirability"]["score"]


def test_direct_collector_appeal_contribution_is_score_times_010(targets):
    _attach(targets)
    row = next(r for r in targets if r["name"] == "Ascended Heroes")
    component = row["rip"]["components"]["desirability"]
    assert component["contribution"] == pytest.approx(component["score"] * 0.10, abs=1e-3)
    assert component["contribution"] == pytest.approx(9.6094, abs=1e-3)


def test_rip_score_is_the_weighted_sum_not_pack_score(targets):
    _attach(targets)
    row = next(r for r in targets if r["name"] == "Ascended Heroes")
    expected = 0.58 * 90.0 + 0.20 * 80.0 + 0.12 * 70.0 + 0.10 * 96.0942
    assert row["rip"]["score"] == pytest.approx(expected, abs=1e-3)
    # The legacy fields are present and different - proving they are not read.
    assert row["pack_score"] == 12.3
    assert row["relative_pack_score"] == 98.4
    assert row["rip"]["score"] != row["pack_score"]
    assert row["rip"]["score"] != row["relative_pack_score"]


def test_missing_collector_appeal_prevents_canonical_rip_rather_than_renormalizing(targets):
    _attach(targets)
    hidden = next(r for r in targets if r["name"] == "Sword & Shield")
    assert hidden["rip"]["score"] is None
    assert hidden["rip"]["missingPillars"] == ["desirability"]
    # Financial-only remains available, clearly labelled, and NOT called RIP.
    assert hidden["rip"]["financialOnly"]["score"] is not None
    assert "Not a RIP score" in hidden["rip"]["financialOnly"]["label"]


def test_default_rip_weights_are_the_expected_four(targets):
    assert DEFAULT_RIP_WEIGHTS["profit"] == pytest.approx(0.58)
    assert DEFAULT_RIP_WEIGHTS["safety"] == pytest.approx(0.20)
    assert DEFAULT_RIP_WEIGHTS["stability"] == pytest.approx(0.12)
    assert DEFAULT_RIP_WEIGHTS["desirability"] == pytest.approx(0.10)


# ---------------------------------------------------------------------------
# RIP Core
# ---------------------------------------------------------------------------

def test_rip_core_excludes_collector_appeal_and_renormalizes(targets):
    _attach(targets)
    row = next(r for r in targets if r["name"] == "Ascended Heroes")
    core = row["ripCore"]
    assert "desirability" not in core["components"]
    total = 0.58 + 0.20 + 0.12
    expected = (0.58 * 90.0 + 0.20 * 80.0 + 0.12 * 70.0) / total
    assert core["score"] == pytest.approx(expected, abs=1e-3)
    assert sum(core["effectiveWeights"].values()) == pytest.approx(1.0)


def test_rip_core_is_computed_by_the_backend_financial_implementation(targets):
    from backend.desirability.weighted_rip import FINANCIAL_RIP_V2_VERSION

    _attach(targets)
    row = next(r for r in targets if r["name"] == "Ascended Heroes")
    assert row["ripCore"]["version"] == FINANCIAL_RIP_V2_VERSION


def test_rip_and_rip_core_ranks_are_calculated_separately(targets):
    _attach(targets)
    pairs = [
        (r["name"], r["rip"]["rank"], r["ripCore"]["rank"])
        for r in targets
        if r["name"] in READY
    ]
    # The two orderings must not be the same object, and Collector Appeal must
    # actually move at least one set's placement.
    assert any(rip != core for _, rip, core in pairs)


def test_rip_core_is_not_full_rip_minus_a_contribution(targets):
    """RIP Core is renormalized, so subtraction would misstate the contribution."""
    _attach(targets)
    row = next(r for r in targets if r["name"] == "Ascended Heroes")
    contribution = row["rip"]["components"]["desirability"]["contribution"]
    naive = row["rip"]["score"] - row["ripCore"]["score"]
    assert naive != pytest.approx(contribution, abs=0.05)


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------

def test_opening_experience_exposes_the_explicit_fields(targets):
    _attach(targets)
    row = next(r for r in targets if r["name"] == "Chaos Rising")
    opening = row["openingExperience"]
    for field in ("rosterDesirability", "dualPathDepth", "collectorAppeal", "chaseAppeal"):
        assert field in opening
    assert opening["collectorAppeal"]["score"] == pytest.approx(75.4929, abs=5e-4)


def test_dual_path_depth_carries_a_rank_but_no_tier(targets):
    _attach(targets)
    row = next(r for r in targets if r["name"] == "Ascended Heroes")
    depth = row["openingExperience"]["dualPathDepth"]
    assert depth["rank"] is not None
    assert "tier" not in depth


def test_legacy_collector_appeal_score_is_not_silently_redefined(targets):
    """The ambiguous legacy field must not be repointed to CA7."""
    _attach(targets)
    row = next(r for r in targets if r["name"] == "Ascended Heroes")
    # The new contract lives under openingExperience; the legacy top-level field
    # is untouched by this service (it comes from the opening-desirability join).
    assert row.get("collector_appeal_score") != row["openingExperience"]["collectorAppeal"]["score"]


def test_cohort_integrity_error_is_reported_not_swallowed(targets, monkeypatch):
    """An eligible set with no CA7 must surface, not quietly shrink the cohort."""
    payloads = {row["name"]: _collector_payload(row["name"], 90.0) for row in targets}
    payloads["Chaos Rising"] = _unavailable_payload("Chaos Rising")
    monkeypatch.setattr(service, "get_collector_appeal_bundle", lambda **_: {"payloads": payloads})

    cohort, warnings = _attach(targets)
    assert cohort["status"] == "integrity_error"
    assert any("cannot be ranked" in w for w in warnings)
