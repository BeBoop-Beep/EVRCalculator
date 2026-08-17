import ast
from pathlib import Path

import pytest

from backend.scripts import research_set_rip_consensus as research


TARGETS = [
    {"set_id": "a", "canonical_key": "alpha", "calculation_run_id": "run-a", "name": "Alpha", "pack_rank": 2},
    {"set_id": "b", "canonical_key": "beta", "calculation_run_id": "run-b", "name": "Beta", "pack_rank": 1},
]


def passing_gate_facts():
    loo = [{"spearman": 0.9, "top5Overlap": 4, "meanAbsoluteRankMovement": 1.0, "maximumRankMovement": 5}]
    comparison = {"spearman": 0.9, "top5Overlap": 4, "meanAbsoluteRankMovement": 1.0, "maximumRankMovement": 5}
    return {"runAuthorityMatchRate": 1.0, "canonicalVersionMatchRate": 1.0,
            "rankedSetCount": 10, "rankableSetCount": 9, "ineligibleParticipatingFamilies": [],
            "deferredCoverage": {"halfBoosterBox": True, "expandedEtb": True,
                                 "expandedPokemonCenterEtb": True},
            "informativeLeaveOneFamilyOut": loo,
            "representativeSensitivity": {"best": comparison, "median": comparison,
                "coverage3": comparison, "familyCohort5": comparison, "groupBalanced": comparison},
            "familyCountSpearman": 0.2, "multiSkuInvariantHolds": True}


def gate_facts_with(**changes):
    facts = passing_gate_facts()
    facts.update(changes)
    return facts


def projection(extra=None):
    products = [
        {"setId": "a", "sealedProductId": "a1", "productName": "A Box", "familyRank": 1,
         "overallRipScore": -999999, "financialRipScore": 999999},
        {"setId": "b", "sealedProductId": "b1", "productName": "B Box", "familyRank": 2,
         "overallRipScore": 999999, "financialRipScore": -999999},
    ]
    products.extend(extra or [])
    return {"comparisonScope": "within_product_family_only", "crossFormatComparable": False,
            "families": {"booster_box": {"count": len(products), "products": products}}}


def test_raw_rip_magnitudes_never_enter_matrix_or_consensus():
    matrix = research.build_matrix(projection(), TARGETS)
    assert all("overallRipScore" not in cell and "financialRipScore" not in cell for cell in matrix)
    ranked = research.rank_candidate(matrix, representative_policy="best", method="mean")
    assert [row["setId"] for row in ranked if row.get("rank")] == ["a", "b"]


def test_rank_relative_standing_does_feed_consensus():
    matrix = research.build_matrix(projection(), TARGETS)
    ranked = research.rank_candidate(matrix, representative_policy="best", method="mean")
    assert ranked[0]["consensusValue"] == 1.0
    assert ranked[1]["consensusValue"] == 0.0
    assert research.rank_standing(1, 1) == 0.5


def test_missing_family_is_absent_not_zero_and_gate_is_unavailable():
    matrix = research.build_matrix(projection(), TARGETS)
    alpha_bundle = next(c for c in matrix if c["setId"] == "a" and c["family"] == "booster_bundle")
    assert alpha_bundle["bestFamilyPercentile"] is None
    assert alpha_bundle["availabilityStatus"] == "no_catalogued_product"
    gated = research.rank_candidate(matrix, representative_policy="best", method="mean", minimum_coverage=2)
    assert all(row["status"] == "insufficient_coverage" and row["consensusValue"] is None for row in gated)
    assert [row["setRipUnit"] for row in gated] == [1.0, 0.0]


@pytest.mark.parametrize("policy,expected", [("best", 1.0), ("median", 0.75), ("mean", 0.75)])
def test_representative_policy_is_explicit(policy, expected):
    assert research.representative([1.0, 0.5], policy) == expected


def test_candidate_grid_is_predeclared_and_deterministic():
    assert research.candidate_grid() == research.candidate_grid()
    assert {row["representativePolicy"] for row in research.candidate_grid()} == {"best", "median", "mean"}
    assert {row["priorStrength"] for row in research.candidate_grid() if row["method"] == "mean"} == {0, 1, 2, 3}
    assert len(research.candidate_grid()) == 189


def test_leading_spec_is_unshrunk_two_level_equal_family_mean():
    assert research.LEADING_SPEC == {"representativePolicy": "mean", "method": "mean", "priorStrength": 0,
                                     "minimumCoverage": 2, "minimumFamilySetCohort": 3}
    matrix = [
        {"setId": "a", "family": "booster_box", "familySetCohortSize": 3, "rankableSkuCount": 3,
         "meanSkuPercentile": 0.6, "bestFamilyPercentile": 1.0, "medianSkuPercentile": 0.5},
        {"setId": "a", "family": "elite_trainer_box", "familySetCohortSize": 3, "rankableSkuCount": 1,
         "meanSkuPercentile": 0.2, "bestFamilyPercentile": 0.2, "medianSkuPercentile": 0.2},
    ]
    ranked = research.rank_candidate(matrix, representative_policy="mean", method="mean",
                                     prior_strength=0, minimum_coverage=2, minimum_family_sets=3)
    assert ranked[0]["setRipUnit"] == 0.4
    assert ranked[0]["setRipScore"] == 40.0
    assert ranked[0]["rankableSkuEvidenceCount"] == 4


def test_frozen_methodology_identity_and_settings_are_deterministic():
    assert research.METHODOLOGY_VERSION == "set_rip_consensus_v1_mean_sku_mean_family_unshrunk_cov2_cohort3_missing_omit"
    assert research.LEADING_SPEC == {"representativePolicy": "mean", "method": "mean", "priorStrength": 0,
                                     "minimumCoverage": 2, "minimumFamilySetCohort": 3}
    assert research.PROMOTION_GATE_REQUIREMENTS["minimumSetCoverageRate"] == 0.90
    assert research.PROMOTION_GATE_REQUIREMENTS["minimumFamilyRepresentedSets"] == 3


@pytest.mark.parametrize("rankable,status", [(89, "FAIL"), (90, "PASS")])
def test_ninety_percent_set_coverage_gate(rankable, status):
    facts = gate_facts_with(rankedSetCount=100, rankableSetCount=rankable)
    assert research.evaluate_promotion_gate(facts)["checks"]["setCoverage"]["status"] == status


@pytest.mark.parametrize("field,check", [("runAuthorityMatchRate", "runAuthority"),
                                          ("canonicalVersionMatchRate", "canonicalVersions")])
def test_authority_or_version_mismatch_fails(field, check):
    facts = passing_gate_facts()
    facts[field] = 0.99
    gate = research.evaluate_promotion_gate(facts)
    assert gate["checks"][check]["status"] == "FAIL"
    assert gate["overallStatus"] == "PROMOTION_GATE_FAILED"


@pytest.mark.parametrize("metric,value", [("spearman", 0.84), ("top5Overlap", 3),
                                            ("meanAbsoluteRankMovement", 2.01), ("maximumRankMovement", 7)])
def test_each_loo_guardrail_can_fail_stability(metric, value):
    facts = passing_gate_facts()
    omission = dict(facts["informativeLeaveOneFamilyOut"][0])
    omission[metric] = value
    facts["informativeLeaveOneFamilyOut"] = [omission]
    assert research.evaluate_promotion_gate(facts)["checks"]["leaveOneFamilyOutStability"]["status"] == "FAIL"


@pytest.mark.parametrize("representative,metric,value", [("best", "spearman", 0.84),
                                                           ("median", "top5Overlap", 3)])
def test_best_or_median_threshold_requires_methodology_review(representative, metric, value):
    facts = passing_gate_facts()
    facts["representativeSensitivity"] = {key: dict(comparison) for key, comparison in facts["representativeSensitivity"].items()}
    facts["representativeSensitivity"][representative][metric] = value
    gate = research.evaluate_promotion_gate(facts)
    assert gate["checks"]["representativeSensitivity"]["status"] == "REVIEW_REQUIRED"
    assert gate["overallStatus"] == "METHODOLOGY_SENSITIVITY_REVIEW_REQUIRED"


def test_family_count_threshold_requires_review_and_duplicate_family_votes_fail():
    fairness = research.evaluate_promotion_gate(gate_facts_with(familyCountSpearman=-0.60))
    assert fairness["checks"]["familyCountFairness"]["status"] == "REVIEW_REQUIRED"
    duplicate = research.evaluate_promotion_gate(gate_facts_with(multiSkuInvariantHolds=False))
    assert duplicate["checks"]["multiSkuInvariant"]["status"] == "FAIL"
    assert duplicate["overallStatus"] == "PROMOTION_GATE_FAILED"


def test_deferred_coverage_blocks_today_and_fully_passing_cohort_is_review_ready():
    waiting = passing_gate_facts()
    waiting["deferredCoverage"] = {"halfBoosterBox": False, "expandedEtb": False,
                                   "expandedPokemonCenterEtb": False}
    assert research.evaluate_promotion_gate(waiting)["overallStatus"] == "AWAITING_DEFERRED_COVERAGE"
    assert research.evaluate_promotion_gate(passing_gate_facts())["overallStatus"] == "METHODOLOGY_READY_FOR_PROMOTION_REVIEW"


def test_four_skus_still_make_one_family_vote_and_extra_family_changes_mean_not_weight():
    matrix = [
        {"setId": "a", "family": "elite_trainer_box", "familySetCohortSize": 3, "rankableSkuCount": 4,
         "meanSkuPercentile": 0.8, "bestFamilyPercentile": 1.0, "medianSkuPercentile": 0.8},
        {"setId": "a", "family": "booster_box", "familySetCohortSize": 3, "rankableSkuCount": 1,
         "meanSkuPercentile": 0.2, "bestFamilyPercentile": 0.2, "medianSkuPercentile": 0.2},
    ]
    ranked = research.rank_candidate(matrix, representative_policy="mean", method="mean",
                                     minimum_coverage=2, minimum_family_sets=3)
    assert ranked[0]["setRipUnit"] == 0.5  # (one ETB family vote + one box family vote) / 2


@pytest.mark.parametrize("extra,expected", [(0.1, 0.5), (0.9, 0.766667)])
def test_weak_or_strong_extra_family_can_lower_or_raise_mean(extra, expected):
    matrix = [
        {"setId": "a", "family": family, "familySetCohortSize": 3, "rankableSkuCount": 1,
         "meanSkuPercentile": value, "bestFamilyPercentile": value, "medianSkuPercentile": value}
        for family, value in [("booster_box", 0.7), ("booster_bundle", 0.7), ("elite_trainer_box", extra)]
    ]
    ranked = research.rank_candidate(matrix, representative_policy="mean", method="mean", minimum_family_sets=3)
    assert ranked[0]["setRipUnit"] == expected


def test_family_cohort_threshold_controls_eligibility_without_zero_fill():
    matrix = [
        {"setId": "a", "family": "booster_box", "familySetCohortSize": 3, "rankableSkuCount": 1,
         "meanSkuPercentile": 0.8, "bestFamilyPercentile": 0.8, "medianSkuPercentile": 0.8},
        {"setId": "a", "family": "enhanced_booster_box", "familySetCohortSize": 1, "rankableSkuCount": 1,
         "meanSkuPercentile": 0.0, "bestFamilyPercentile": 0.0, "medianSkuPercentile": 0.0},
    ]
    ranked = research.rank_candidate(matrix, representative_policy="mean", method="mean", minimum_family_sets=3)
    assert ranked[0]["setRipUnit"] == 0.8
    assert ranked[0]["familyCoverageCount"] == 1


def test_future_product_rows_automatically_expand_matrix_coverage():
    before = research.build_matrix(projection(), TARGETS)
    new = {"setId": "a", "sealedProductId": "a2", "productName": "A second", "familyRank": 2}
    after = research.build_matrix(projection([new]), TARGETS)
    before_cell = next(c for c in before if c["setId"] == "a" and c["family"] == "booster_box")
    after_cell = next(c for c in after if c["setId"] == "a" and c["family"] == "booster_box")
    assert before_cell["rankableSkuCount"] == 1
    assert after_cell["rankableSkuCount"] == 2


def test_catalog_can_distinguish_existing_unscored_product():
    catalog = {"a": {"elite_trainer_box": [{"id": "etb"}]}}
    matrix = research.build_matrix(projection(), TARGETS, catalog)
    cell = next(c for c in matrix if c["setId"] == "a" and c["family"] == "elite_trainer_box")
    assert cell["availabilityStatus"] == "catalogued_product_exists_unscored"


def test_no_cross_family_comparator_or_database_write_path():
    source = Path(research.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert not ({"update", "upsert", "delete"} & attributes)
    assert source.count(".insert(") == 1  # sys.path bootstrap only
    assert "may_compare_products" not in source


def test_production_modules_do_not_import_research_harness():
    root = Path(__file__).resolve().parents[4]
    offenders = []
    for path in list((root / "backend").rglob("*.py")) + list((root / "frontend").rglob("*.ts")) + list((root / "frontend").rglob("*.tsx")):
        if path == Path(research.__file__) or "tests" in path.parts:
            continue
        if "research_set_rip_consensus" in path.read_text(encoding="utf-8", errors="ignore"):
            offenders.append(str(path.relative_to(root)))
    assert offenders == []


def test_research_main_passes_exact_target_run_authority(monkeypatch, tmp_path):
    observed = {}
    monkeypatch.setattr(research, "get_rip_statistics_targets_payload", lambda: {"targets": TARGETS})
    monkeypatch.setattr(research, "_catalog_by_set", lambda *_a, **_k: {})
    monkeypatch.setattr(research, "build_report", lambda *_a, **_k: {"promotionStatus": "AWAITING_DEFERRED_COVERAGE"})
    monkeypatch.setattr(research, "render_markdown", lambda _report: "research only")
    def project(*, set_targets):
        observed["authority"] = {row["set_id"]: row["calculation_run_id"] for row in set_targets}
        return {"families": {}}
    monkeypatch.setattr(research, "build_product_family_rankings", project)
    monkeypatch.setattr("sys.argv", ["research_set_rip_consensus", "--output-dir", str(tmp_path)])
    assert research.main() == 0
    assert observed["authority"] == {"a": "run-a", "b": "run-b"}
