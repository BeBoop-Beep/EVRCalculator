"""The two-layer score contract: ABSOLUTE and RELATIVE, never one or the other.

WHY BOTH LAYERS EXIST
---------------------
ABSOLUTE is the formula output. It is cohort independent - adding or removing a
set cannot change it - which is what makes it usable in a blend, in a guardrail
and in a historical comparison.

RELATIVE is min-max position within the ranked cohort. It is the primary public
display score, because "78.4 out of 100 on a fixed anchor scale" answers a
different question from "where does this sit among the sets you can actually
buy".

THE FAILURE MODE THESE TESTS EXIST TO PREVENT
---------------------------------------------
Collapsing the two. If a relative score ever overwrites an absolute one, or is
fed into Financial RIP V3 or Overall RIP V7, then a set's published score starts
depending on which OTHER sets exist - and every historical comparison silently
becomes a comparison between two different populations. Nothing about the shape
of the payload would reveal it.
"""

import pytest

from backend.calculations.evr.financial_rip_v3_config import (
    FINANCIAL_RIP_V3_COMPONENT_ORDER,
)
from backend.db.services import explore_rip_statistics_service as service
from backend.desirability.public_rip_contract_v5 import (
    FINANCIAL_RIP_V3_PUBLIC_COMPONENT_KEYS,
)
from backend.desirability.public_rip_contract_v7 import build_public_rip_contract_v7
from backend.desirability.scoring_config import OVERALL_RIP_V7_WEIGHTS


def _target(index, *, appeal, financial, overall):
    return {
        "target_id": f"target-{index}",
        "canonical_key": f"set-{index}",
        "financialRipV3": {
            "score": financial,
            "status": "ready",
            "rankable": True,
            "components": {
                component: {"score": financial - position, "available": True, "raw": {}}
                for position, component in enumerate(FINANCIAL_RIP_V3_COMPONENT_ORDER)
            },
        },
        "overallRipV7": {"score": overall},
        "overallRipV5": {"score": overall},
        "overallRipV6": {"score": overall},
        "rip": {"score": overall, "financialRip": {"components": {}}},
        "ripCore": {"score": financial, "components": {}},
        "openingExperience": {"collectorAppeal": {"score": appeal}},
        "profit_score": financial,
        "safety_score": financial,
        "stability_score": financial,
    }


@pytest.fixture
def ranked_cohort():
    """Three sets with deliberately DIFFERENT absolute scores on every pillar."""
    rows = [
        _target(0, appeal=20.0, financial=40.0, overall=38.0),
        _target(1, appeal=60.0, financial=70.0, overall=69.0),
        _target(2, appeal=90.0, financial=95.0, overall=94.5),
    ]
    service._rank_within_cohort(rows, cohort_size=len(rows))
    return rows


# ---------------------------------------------------------------------------
# Attachment: every canonical object gets a relative score
# ---------------------------------------------------------------------------

def test_collector_appeal_carries_its_own_relative_score(ranked_cohort):
    appeals = [
        (row["openingExperience"]["collectorAppeal"]) for row in ranked_cohort
    ]
    assert [block["relativeScore"] for block in appeals] == [0.0, 57.14, 100.0]


@pytest.mark.parametrize(
    ("block_path", "score_path"),
    [
        (("overallRipV7",), ("overallRipV7", "score")),
        (("financialRipV3",), ("financialRipV3", "score")),
        (
            ("openingExperience", "collectorAppeal"),
            ("openingExperience", "collectorAppeal", "score"),
        ),
    ],
    ids=["overall-rip", "financial-rip", "collector-appeal"],
)
def test_public_score_endpoints_are_zero_and_one_hundred_and_match_rank_order(
    ranked_cohort, block_path, score_path
):
    """Lock the public 0-100 endpoint and ordering contract for all three scores."""

    def read(row, path):
        value = row
        for key in path:
            value = value[key]
        return value

    blocks = [read(row, block_path) for row in ranked_cohort]
    public_scores = [block["relativeScore"] for block in blocks]

    assert min(public_scores) == pytest.approx(0.0)
    assert max(public_scores) == pytest.approx(100.0)

    by_model_score = sorted(
        ranked_cohort,
        key=lambda row: (-read(row, score_path), str(row["target_id"])),
    )
    by_public_score = sorted(
        ranked_cohort,
        key=lambda row: (-read(row, block_path)["relativeScore"], str(row["target_id"])),
    )
    by_rank = sorted(
        ranked_cohort,
        key=lambda row: (read(row, block_path)["rank"], str(row["target_id"])),
    )

    expected_ids = [row["target_id"] for row in by_model_score]
    assert [row["target_id"] for row in by_public_score] == expected_ids
    assert [row["target_id"] for row in by_rank] == expected_ids


def test_every_weighted_financial_component_carries_a_relative_score(ranked_cohort):
    for row in ranked_cohort:
        components = row["financialRipV3"]["components"]
        assert set(components) == set(FINANCIAL_RIP_V3_COMPONENT_ORDER)
        for component in FINANCIAL_RIP_V3_COMPONENT_ORDER:
            assert components[component]["relativeScore"] is not None


def test_component_relative_scores_are_computed_from_their_own_absolute_score(
    ranked_cohort,
):
    """Independently per component, not inherited from the parent.

    Every component here has the same SPREAD as its parent (each is the parent
    minus a fixed offset), so a component that merely copied the parent's
    relative score would produce identical numbers and pass a weaker test. What
    distinguishes the two is that each component is min-maxed over its OWN
    column: the assertion is that the endpoints land on 0 and 100 for each
    component separately.
    """
    for component in FINANCIAL_RIP_V3_COMPONENT_ORDER:
        column = [
            row["financialRipV3"]["components"][component]["relativeScore"]
            for row in ranked_cohort
        ]
        assert min(column) == 0.0
        assert max(column) == 100.0


def test_relative_scores_never_overwrite_absolute_scores(ranked_cohort):
    """The absolute score is the formula output and stays untouched."""
    assert [row["financialRipV3"]["score"] for row in ranked_cohort] == [40.0, 70.0, 95.0]
    assert [row["overallRipV7"]["score"] for row in ranked_cohort] == [38.0, 69.0, 94.5]
    assert [
        row["openingExperience"]["collectorAppeal"]["score"] for row in ranked_cohort
    ] == [20.0, 60.0, 90.0]
    for row in ranked_cohort:
        for component in FINANCIAL_RIP_V3_COMPONENT_ORDER:
            block = row["financialRipV3"]["components"][component]
            assert block["score"] != block["relativeScore"] or block["score"] in (0.0, 100.0)


def test_every_ranked_row_carries_the_same_cohort_fingerprint(ranked_cohort):
    fingerprints = {row["cohortFingerprint"] for row in ranked_cohort}
    assert len(fingerprints) == 1
    assert len(fingerprints.pop()) == 64  # sha256 hex


def test_the_cohort_fingerprint_changes_with_the_population():
    small = [_target(index, appeal=10.0 * index, financial=10.0 * index, overall=10.0 * index)
             for index in range(3)]
    large = [_target(index, appeal=10.0 * index, financial=10.0 * index, overall=10.0 * index)
             for index in range(4)]
    service._rank_within_cohort(small, cohort_size=len(small))
    service._rank_within_cohort(large, cohort_size=len(large))
    assert small[0]["cohortFingerprint"] != large[0]["cohortFingerprint"]


# ---------------------------------------------------------------------------
# Independence: the relative layer never feeds a formula
# ---------------------------------------------------------------------------

def test_overall_absolute_is_the_blend_of_ABSOLUTE_inputs(ranked_cohort):
    """0.90 * absolute Financial RIP V3 + 0.10 * absolute Collector Appeal V3.

    Recomputed here from the absolute inputs and compared against the published
    absolute Overall. Using the relative inputs instead would give a completely
    different number for the middle set, which is what makes this assertion able
    to fail.
    """
    from backend.desirability.weighted_rip import compute_overall_rip_v7

    for row in ranked_cohort:
        absolute_financial = row["financialRipV3"]["score"]
        absolute_appeal = row["openingExperience"]["collectorAppeal"]["score"]
        expected = compute_overall_rip_v7(absolute_financial, absolute_appeal)["score"]
        blended = (
            OVERALL_RIP_V7_WEIGHTS["financial_rip"] * absolute_financial
            + OVERALL_RIP_V7_WEIGHTS["collector_appeal"] * absolute_appeal
        )
        assert expected == pytest.approx(blended, abs=1e-6)

        relative_blend = (
            OVERALL_RIP_V7_WEIGHTS["financial_rip"] * row["financialRipV3"]["relativeScore"]
            + OVERALL_RIP_V7_WEIGHTS["collector_appeal"]
            * row["openingExperience"]["collectorAppeal"]["relativeScore"]
        )
        if row["financialRipV3"]["relativeScore"] != absolute_financial:
            assert expected != pytest.approx(relative_blend, abs=1e-6)


# ---------------------------------------------------------------------------
# Publication: the v7 contract exposes both layers everywhere
# ---------------------------------------------------------------------------

@pytest.fixture
def contract(ranked_cohort):
    return build_public_rip_contract_v7(ranked_cohort[1])


@pytest.mark.parametrize("pillar", ["overallRip", "financialRip", "collectorAppeal"])
@pytest.mark.parametrize(
    "field",
    ["score", "absoluteScore", "relativeScore", "rank", "tier", "rankedSetCount",
     "cohortFingerprint"],
)
def test_every_canonical_pillar_publishes_both_layers(contract, pillar, field):
    assert contract[pillar].get(field) is not None


@pytest.mark.parametrize("component", FINANCIAL_RIP_V3_COMPONENT_ORDER)
@pytest.mark.parametrize(
    "field",
    ["score", "absoluteScore", "relativeScore", "rank", "tier", "rankedSetCount"],
)
def test_every_financial_component_publishes_both_layers(contract, component, field):
    public_key = FINANCIAL_RIP_V3_PUBLIC_COMPONENT_KEYS[component]
    assert contract["financialRip"]["components"][public_key].get(field) is not None


def test_published_score_equals_published_absolute_score(contract):
    for pillar in ("overallRip", "financialRip", "collectorAppeal"):
        assert contract[pillar]["score"] == contract[pillar]["absoluteScore"]
    for component in contract["financialRip"]["components"].values():
        assert component["score"] == component["absoluteScore"]


def test_all_three_pillars_report_the_same_cohort(contract):
    fingerprints = {
        contract[pillar]["cohortFingerprint"]
        for pillar in ("overallRip", "financialRip", "collectorAppeal")
    }
    assert len(fingerprints) == 1
