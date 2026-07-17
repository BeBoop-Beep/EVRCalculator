"""Financial RIP, Overall RIP, and the 21-set public cohort, end to end in the service.

Drives ``_attach_public_rip_contract`` with stubbed bundles, so cohort/rank/weight
behaviour is tested without a database.

THE ARCHITECTURE THESE PIN
--------------------------
Universal Set Desirability is the authoritative desirability score. It needs no
simulation and no CA7. Financial RIP is exactly 60/25/15 over the simulation
pillars. Overall RIP is Financial RIP plus a bounded desirability adjustment.

CA7 is NOT a RIP pillar. It is a Simulation Opening Experience diagnostic that
exists only where a pull model loads, so its absence is an expected state - not
a reason to null a RIP. The previous suite asserted the opposite on every count
(a 58/20/12/10 blend, CA7 as the 10% pillar, and
``incomplete_missing_desirability`` whenever CA7 was missing); those assertions
are retired with the model they described.
"""

from __future__ import annotations

import pytest

from backend.db.services import explore_rip_statistics_service as service
from backend.desirability.public_analytics_policy import (
    HIDDEN_PENDING_VALIDATION,
    SWORD_AND_SHIELD_ERA_ID,
)
from backend.desirability.scoring_config import (
    DESIRABILITY_ADJUSTMENT_CAP,
    FINANCIAL_RIP_WEIGHTS,
)

SV_ERA = "dfb0dfa1-6a8e-4335-850f-e003867e19ee"
ME_ERA = "fb22f860-ae41-4879-a41a-857ca11bf0da"

# name -> (era_id, CA7 x100, profit, safety, stability, universal_desirability)
READY = {
    "Ascended Heroes": (ME_ERA, 96.0942, 90.0, 80.0, 70.0, 95.4809),
    "Chaos Rising": (ME_ERA, 75.4929, 60.0, 55.0, 50.0, 69.8947),
    "Shrouded Fable": (SV_ERA, 56.7918, 40.0, 45.0, 42.0, 52.0),
    "Prismatic Evolutions": (SV_ERA, 94.6179, 95.0, 85.0, 60.0, 93.0),
    "Black Bolt": (SV_ERA, 85.1027, 70.0, 60.0, 65.0, 80.0),
    "Destined Rivals": (SV_ERA, 89.8659, 65.0, 62.0, 58.0, 84.0),
    "Journey Together": (SV_ERA, 89.3347, 55.0, 52.0, 48.0, 83.0),
    "Mega Evolution": (ME_ERA, 90.0581, 75.0, 70.0, 68.0, 86.0),
    "Obsidian Flames": (SV_ERA, 88.8906, 50.0, 48.0, 44.0, 82.0),
    "Paldea Evolved": (SV_ERA, 91.3821, 52.0, 50.0, 46.0, 88.0),
    "Paldean Fates": (SV_ERA, 95.7943, 80.0, 75.0, 72.0, 94.0),
    "Paradox Rift": (SV_ERA, 88.6375, 45.0, 43.0, 41.0, 81.0),
    "Perfect Order": (ME_ERA, 84.7975, 68.0, 66.0, 64.0, 79.0),
    "Phantasmal Flames": (ME_ERA, 92.4631, 72.0, 71.0, 69.0, 90.0),
    "Scarlet and Violet 151": (SV_ERA, 94.5391, 85.0, 82.0, 78.0, 92.0),
    "Scarlet and Violet Base Set": (SV_ERA, 79.6771, 42.0, 40.0, 38.0, 74.0),
    "Stellar Crown": (SV_ERA, 88.1232, 58.0, 56.0, 54.0, 78.0),
    "Surging Sparks": (SV_ERA, 90.8714, 62.0, 60.0, 59.0, 87.0),
    "Temporal Forces": (SV_ERA, 88.0610, 48.0, 46.0, 45.0, 77.0),
    "Twilight Masquerade": (SV_ERA, 84.2445, 44.0, 42.0, 43.0, 76.0),
    "White Flare": (SV_ERA, 88.1582, 66.0, 64.0, 62.0, 85.0),
}

# The 12 SWSH sets: simulated, but not approved for public analytics. They have
# NO CA7 (no pull model) yet DO have universal desirability, which is exactly the
# combination the old model could not score and this one can.
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
        "dualPathDepth": {"rawValue": None, "displayPercent": None},
        "collectorAppeal": {"score": None, "rawValue": None},
        "chaseAppeal": {"score": None, "rawValue": None},
        "topSubjects": [],
        "coverage": {
            "status": "unavailable",
            "reasons": ["dual_path_depth_unavailable_no_pull_model"],
        },
    }


def _universal(score):
    return {
        "score": score,
        "rank": 1,
        "rankedSetCount": 135,
        "percentile": 100.0,
        "version": "universal_set_desirability_v3",
        "components": {
            "chase_subject_strength": 86.6628,
            "chase_subject_depth": 100.0,
            "favorite_hit_coverage": 99.8113,
        },
        "coverage": {"status": "full", "reasons": []},
    }


@pytest.fixture
def targets(monkeypatch):
    rows = []
    payloads = {}
    for name, (era_id, ca7, profit, safety, stability, usd) in READY.items():
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
                "universalSetDesirability": _universal(usd),
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
                "universalSetDesirability": _universal(70.0),
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


def _row(targets, name):
    return next(r for r in targets if r["name"] == name)


# ---------------------------------------------------------------------------
# Cohort
# ---------------------------------------------------------------------------

def test_public_cohort_is_exactly_21(targets):
    cohort, warnings = _attach(targets)
    assert cohort["eligibleSetCount"] == 21
    assert cohort["excludedCountsByReason"][HIDDEN_PENDING_VALIDATION] == 12
    assert warnings == []


def test_all_21_public_sets_receive_an_overall_rip(targets):
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
        for pillar in ("profit", "safety", "stability"):
            assert row["ripCore"]["components"][pillar]["cohortSize"] == 21
        opening = row["openingExperience"]
        for key in ("collectorAppeal", "chaseAppeal", "dualPathDepth"):
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
        key=lambda r: r["ripCore"]["components"]["profit"]["rank"],
    )
    # Prismatic Evolutions has the highest profit among ELIGIBLE sets (95.0).
    assert best_profit["name"] == "Prismatic Evolutions"
    assert best_profit["ripCore"]["components"]["profit"]["rank"] == 1


# ---------------------------------------------------------------------------
# Financial RIP: exactly 60/25/15
# ---------------------------------------------------------------------------

def test_financial_rip_uses_exactly_60_25_15(targets):
    _attach(targets)
    core = _row(targets, "Ascended Heroes")["ripCore"]
    assert core["components"]["profit"]["weight"] == pytest.approx(0.60)
    assert core["components"]["safety"]["weight"] == pytest.approx(0.25)
    assert core["components"]["stability"]["weight"] == pytest.approx(0.15)


def test_financial_rip_weights_sum_to_one_and_are_not_renormalized(targets):
    """The published weight is the applied weight.

    The retired model advertised 0.58/0.20/0.12 and applied 0.644/0.222/0.133
    after dropping the desirability pillar and renormalizing.
    """
    _attach(targets)
    core = _row(targets, "Ascended Heroes")["ripCore"]
    weights = [core["components"][p]["weight"] for p in ("profit", "safety", "stability")]
    assert sum(weights) == pytest.approx(1.0)
    assert sum(FINANCIAL_RIP_WEIGHTS.values()) == pytest.approx(1.0)


def test_financial_rip_score_is_the_exact_weighted_sum(targets):
    _attach(targets)
    row = _row(targets, "Ascended Heroes")
    expected = 0.60 * 90.0 + 0.25 * 80.0 + 0.15 * 70.0
    assert row["ripCore"]["score"] == pytest.approx(expected, abs=1e-4)
    # The legacy fields are present and different - proving they are not read.
    assert row["pack_score"] == 12.3
    assert row["ripCore"]["score"] != row["pack_score"]
    assert row["ripCore"]["score"] != row["relative_pack_score"]


def test_financial_rip_has_no_desirability_component(targets):
    _attach(targets)
    core = _row(targets, "Ascended Heroes")["ripCore"]
    assert set(core["components"]) == {"profit", "safety", "stability"}


def test_financial_rip_is_unavailable_when_a_pillar_is_missing(targets):
    from backend.desirability.weighted_rip import compute_financial_rip

    result = compute_financial_rip({"profit": 90.0, "safety": None, "stability": 70.0})
    assert result["score"] is None
    assert result["missingPillars"] == ["safety"]
    assert result["rankable"] is False


# ---------------------------------------------------------------------------
# Overall RIP = Financial RIP + bounded desirability adjustment
# ---------------------------------------------------------------------------

def test_overall_rip_is_financial_plus_adjustment(targets):
    _attach(targets)
    row = _row(targets, "Ascended Heroes")
    financial = 0.60 * 90.0 + 0.25 * 80.0 + 0.15 * 70.0
    raw = (95.4809 - 50.0) / 10.0
    adjustment = min(raw, DESIRABILITY_ADJUSTMENT_CAP)
    assert row["rip"]["score"] == pytest.approx(financial + adjustment, abs=1e-3)
    assert row["rip"]["desirabilityAdjustment"]["adjustment"] == pytest.approx(adjustment, abs=1e-4)


def test_overall_rip_reports_the_financial_rip_it_used(targets):
    _attach(targets)
    row = _row(targets, "Ascended Heroes")
    assert row["rip"]["financialRip"]["score"] == pytest.approx(row["ripCore"]["score"], abs=1e-6)


def test_overall_rip_version_is_the_new_model(targets):
    _attach(targets)
    row = _row(targets, "Ascended Heroes")
    assert row["rip"]["version"] == "overall_rip_v3_financial_plus_universal_desirability"
    assert row["ripCore"]["version"] == "financial_rip_v2_60_25_15"


# ---------------------------------------------------------------------------
# CA7 is not required anywhere
# ---------------------------------------------------------------------------

def test_missing_ca7_does_not_null_overall_rip(targets):
    """The regression that nulled every RIP the moment the pull model failed."""
    _attach(targets)
    hidden = _row(targets, "Evolving Skies")
    assert hidden["openingExperience"]["collectorAppeal"]["score"] is None
    assert hidden["rip"]["score"] is not None
    assert hidden["ripCore"]["score"] is not None


def test_incomplete_missing_desirability_is_unreachable(targets):
    _attach(targets)
    for row in targets:
        assert row["rip"].get("status") != "incomplete_missing_desirability", row["name"]


def test_overall_rip_needs_no_ca7_when_universal_desirability_is_present(targets):
    from backend.desirability.weighted_rip import compute_overall_rip

    result = compute_overall_rip(
        {"profit": 90.0, "safety": 80.0, "stability": 70.0}, 95.4809
    )
    assert result["score"] is not None
    assert result["rankable"] is True


def test_overall_rip_is_unavailable_without_universal_desirability(targets):
    from backend.desirability.weighted_rip import compute_overall_rip

    result = compute_overall_rip({"profit": 90.0, "safety": 80.0, "stability": 70.0}, None)
    assert result["score"] is None
    assert "universal_set_desirability" in result["missingInputs"]


def test_ca7_is_not_the_authoritative_rip_pillar(targets):
    """CA7 must appear only as an Opening Experience diagnostic."""
    _attach(targets)
    row = _row(targets, "Ascended Heroes")
    assert "desirability" not in (row["ripCore"].get("components") or {})
    assert "components" not in row["rip"] or "desirability" not in (row["rip"].get("components") or {})
    # CA7 (96.0942) is NOT what moved Overall RIP; the universal score (95.4809) is.
    assert row["rip"]["universalSetDesirabilityScore"] == pytest.approx(95.4809, abs=1e-4)
    assert row["openingExperience"]["collectorAppeal"]["score"] == pytest.approx(96.0942, abs=5e-4)


def test_opening_experience_no_longer_carries_roster_desirability(targets):
    """Roster desirability moved to `universalSetDesirability`.

    It is not simulation-scoped, so routing it through a CA7-gated block is what
    hid it whenever a pull model was missing.
    """
    _attach(targets)
    opening = _row(targets, "Ascended Heroes")["openingExperience"]
    assert "rosterDesirability" not in opening
    assert opening["coverage"]["scope"] == "simulation_opening_experience"


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------

def test_opening_experience_exposes_the_ca7_fields(targets):
    _attach(targets)
    opening = _row(targets, "Chaos Rising")["openingExperience"]
    for field in ("dualPathDepth", "collectorAppeal", "chaseAppeal"):
        assert field in opening
    assert opening["collectorAppeal"]["score"] == pytest.approx(75.4929, abs=5e-4)


def test_dual_path_depth_carries_a_rank_but_no_tier(targets):
    _attach(targets)
    depth = _row(targets, "Ascended Heroes")["openingExperience"]["dualPathDepth"]
    assert depth["rank"] is not None
    assert "tier" not in depth


def test_legacy_collector_appeal_score_is_not_silently_redefined(targets):
    """The ambiguous legacy field must not be repointed to CA7."""
    _attach(targets)
    row = _row(targets, "Ascended Heroes")
    assert row.get("collector_appeal_score") != row["openingExperience"]["collectorAppeal"]["score"]


def test_cohort_integrity_keys_on_universal_desirability_not_ca7(targets, monkeypatch):
    """An eligible set with no UNIVERSAL score must surface.

    Keyed on the universal score because a missing CA7 is now expected, so
    asserting on CA7 would raise for every set without a pull model.
    """
    _attach(targets)  # baseline: no integrity error even though HIDDEN lack CA7
    row = _row(targets, "Chaos Rising")
    row["universalSetDesirability"] = None

    cohort, warnings = _attach(targets)
    assert cohort["status"] == "integrity_error"
    assert any("cannot be ranked" in w for w in warnings)
    assert any("Universal Set Desirability" in w for w in warnings)
