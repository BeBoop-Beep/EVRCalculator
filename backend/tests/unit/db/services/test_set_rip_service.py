from __future__ import annotations

import inspect
import copy

import pytest

from backend.db.services import set_rip_service as service
from backend.desirability.scoring_config import (
    CANONICAL_FINANCIAL_RIP_VERSION,
    CANONICAL_OVERALL_RIP_VERSION,
    canonical_collector_appeal_version,
)


def target(set_id, rank):
    return {"set_id": set_id, "name": set_id.upper(), "calculation_run_id": f"run-{set_id}",
            "overallRipV10": {"rank": rank}}


def product(set_id, family, rank, size, sku="1", **overrides):
    row = {"sealedProductId": f"{set_id}-{family}-{sku}", "setId": set_id,
           "productFamily": family, "familyRank": rank, "familySize": size,
           "calculationRunId": f"run-{set_id}",
           "financialRipVersion": CANONICAL_FINANCIAL_RIP_VERSION,
           "collectorAppealVersion": canonical_collector_appeal_version(),
           "overallRipVersion": CANONICAL_OVERALL_RIP_VERSION}
    row.update(overrides)
    return row


def projection(targets, families):
    blocks = {}
    for family, products in families.items():
        blocks[family] = {"family": family, "count": len(products),
                          "currentlyRankableCount": len(products), "products": products}
    return {"runAuthority": "set_targets.calculation_run_id",
            "authorityTargetCount": len(targets), "families": blocks}


def test_frozen_formula_distinct_families_multi_sku_equal_votes_and_missing_omit():
    targets = [target("a", 1), target("b", 2), target("c", 3)]
    loose = [product("a", "loose_booster_pack", 1, 4, "a1"),
             product("a", "loose_booster_pack", 2, 4, "a2"),
             product("b", "loose_booster_pack", 3, 4), product("c", "loose_booster_pack", 4, 4)]
    sleeved = [product("a", "sleeved_booster_pack", 3, 3),
               product("b", "sleeved_booster_pack", 1, 3), product("c", "sleeved_booster_pack", 2, 3)]
    bundle = [product("a", "booster_bundle", 1, 3),
              product("b", "booster_bundle", 2, 3), product("c", "booster_bundle", 3, 3)]
    result = service.build_set_rip(projection(targets, {
        "loose_booster_pack": loose, "sleeved_booster_pack": sleeved, "booster_bundle": bundle,
    }), set_targets=targets)
    a = next(row for row in result["sets"] if row["setId"] == "a")
    # Loose mean=(1 + 2/3)/2=5/6; sleeved=0; bundle=1. Each family gets one equal vote.
    assert a["score"] == pytest.approx(((5 / 6) + 0 + 1) / 3 * 100)
    assert a["skuEvidenceCount"] == 4
    assert a["participatingFamilies"] == ["booster_bundle", "loose_booster_pack", "sleeved_booster_pack"]
    assert {x["family"]: x["skuCount"] for x in a["familyScores"]}["loose_booster_pack"] == 2
    assert result["methodologyVersion"] == service.METHODOLOGY_VERSION


def test_family_eligibility_rankability_and_future_family_are_generic():
    targets = [target("a", 1), target("b", 2), target("c", 3)]
    eligible = [product(s, "three_pack_blister", i, 3) for i, s in enumerate(("a", "b", "c"), 1)]
    half = [product(s, "half_booster_box", i, 3) for i, s in enumerate(("a", "b", "c"), 1)]
    enhanced = [product(s, "enhanced_booster_box", i, 2) for i, s in enumerate(("a", "b"), 1)]
    result = service.build_set_rip(projection(targets, {
        "three_pack_blister": eligible, "half_booster_box": half, "enhanced_booster_box": enhanced,
    }), set_targets=targets)
    assert set(result["eligibleFamilyRepresentedSetCounts"]) == {"half_booster_box", "three_pack_blister"}
    assert "enhanced_booster_box" not in result["eligibleFamilyRepresentedSetCounts"]
    assert [row["rankable"] for row in result["sets"] if row["setId"] in {"a", "b"}] == [True, True]
    c = next(row for row in result["sets"] if row["setId"] == "c")
    assert c["rankable"] and c["rank"] is not None


def test_one_family_is_unrankable_and_never_receives_fake_score_or_rank():
    targets = [target("a", 1), target("b", 2), target("c", 3)]
    only = [product(s, "loose_booster_pack", i, 3) for i, s in enumerate(("a", "b", "c"), 1)]
    result = service.build_set_rip(projection(targets, {"loose_booster_pack": only}), set_targets=targets)
    assert all(row["score"] is None and row["rank"] is None and not row["rankable"] for row in result["sets"])


def test_run_versions_projection_completeness_and_deterministic_ties_fail_closed():
    targets = [target("a", 1), target("b", 2), target("c", 3)]
    families = {}
    for family in ("loose_booster_pack", "booster_bundle"):
        families[family] = [product(s, family, 2, 3) for s in ("a", "b", "c")]
    result = service.build_set_rip(projection(targets, families), set_targets=targets)
    assert [row["setId"] for row in result["sets"]] == ["a", "b", "c"]
    bad_run = projection(targets, copy.deepcopy(families))
    bad_run["families"]["booster_bundle"]["products"][0]["calculationRunId"] = "stale"
    with pytest.raises(ValueError, match="run authority mismatch"):
        service.build_set_rip(bad_run, set_targets=targets)
    bad_version = projection(targets, copy.deepcopy(families))
    bad_version["families"]["booster_bundle"]["products"][0]["overallRipVersion"] = "old"
    with pytest.raises(ValueError, match="version mismatch"):
        service.build_set_rip(bad_version, set_targets=targets)
    incomplete = projection(targets, copy.deepcopy(families))
    incomplete["families"]["booster_bundle"]["currentlyRankableCount"] = 2
    with pytest.raises(ValueError, match="incomplete"):
        service.build_set_rip(incomplete, set_targets=targets)


def test_build_set_rip_succeeds_end_to_end_with_v4_v10_canonical_product_family_rankings():
    """Regression for the Finding 1/2 chain: once product_family_rankings_service._project
    emits V4/V10 canonical versions (Finding 1) and this file's _ranked_targets reads the
    V10 rank contract key (Finding 2), build_set_rip must succeed rather than raising."""
    targets = [target("a", 1), target("b", 2), target("c", 3)]
    families = {}
    for family in ("loose_booster_pack", "booster_bundle"):
        families[family] = [product(s, family, 2, 3) for s in ("a", "b", "c")]
    result = service.build_set_rip(projection(targets, families), set_targets=targets)
    assert result["rankedSetCount"] == 3
    assert all(row["rankable"] for row in result["sets"])


def test_ranked_targets_reads_the_v10_rank_contract_key():
    v10_only = {"set_id": "a", "calculation_run_id": "run-a", "overallRipV10": {"rank": 1}}
    v9_only = {"set_id": "b", "calculation_run_id": "run-b", "overallRipV9": {"rank": 1}}
    ranked = service._ranked_targets([v10_only, v9_only])
    assert ranked == [v10_only]


def test_no_raw_scores_or_research_harness_dependency():
    source = inspect.getsource(service)
    assert "research_set_rip_consensus" not in source
    assert "overallRipScore" not in source
    assert "financialRipScore" not in source


def test_family_scores_publish_canonical_set_family_rank_and_cohort():
    targets = [target("a", 1), target("b", 2), target("c", 3)]
    loose = [product("a", "loose_booster_pack", 1, 4, "a1"),
             product("a", "loose_booster_pack", 2, 4, "a2"),
             product("b", "loose_booster_pack", 3, 4), product("c", "loose_booster_pack", 4, 4)]
    sleeved = [product("a", "sleeved_booster_pack", 3, 3),
               product("b", "sleeved_booster_pack", 1, 3), product("c", "sleeved_booster_pack", 2, 3)]
    bundle = [product("a", "booster_bundle", 1, 3),
              product("b", "booster_bundle", 2, 3), product("c", "booster_bundle", 3, 3)]
    result = service.build_set_rip(projection(targets, {
        "loose_booster_pack": loose, "sleeved_booster_pack": sleeved, "booster_bundle": bundle,
    }), set_targets=targets)
    by_set = {row["setId"]: {x["family"]: x for x in row["familyScores"]} for row in result["sets"]}

    assert by_set["a"]["loose_booster_pack"]["rank"] == 1
    assert by_set["b"]["loose_booster_pack"]["rank"] == 2
    assert by_set["a"]["sleeved_booster_pack"]["rank"] == 3
    assert by_set["b"]["sleeved_booster_pack"]["rank"] == 1
    assert by_set["a"]["loose_booster_pack"]["cohortSize"] == 3
    assert by_set["a"]["loose_booster_pack"]["skuCount"] == 2
    assert by_set["a"]["loose_booster_pack"]["score"] == pytest.approx(5 / 6 * 100)
    assert isinstance(next(row for row in result["sets"] if row["setId"] == "a")["familyScores"], list)
    assert all(
        {"family", "skuCount", "score", "rank", "cohortSize"} <= family.keys()
        for row in result["sets"] for family in row["familyScores"]
    )

    ranked = [row for row in result["sets"] if row["rankable"]]
    assert all(row["cohortSize"] == len(ranked) for row in result["sets"])
    assert sorted(row["rank"] for row in ranked) == list(range(1, len(ranked) + 1))
