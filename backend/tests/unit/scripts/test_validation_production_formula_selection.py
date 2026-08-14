"""The canonical guardrail verdict must be the verdict on the SHIPPING formula.

THE DEFECT
----------
The previous validation artifact reported

    primary_matches_production() == False

and, in the same file, a ``canonicalConfigurationVerdict``. Those two statements
together mean "here is the gate result for a formula we do not ship". The CA8
grid registered by ``collector_appeal_candidates`` is the bounded-headroom
family; production moved to the Collector Appeal V3 balanced weighted sum
(0.40D + 0.35H + 0.25P). Nothing in the output distinguished them, so a reviewer
reading a PASS had no way to tell which model had passed.

The fix is a first-class production candidate keyed by the exact canonical
Collector Appeal VERSION, and a top-level verdict that selects on that key and
nothing else. These tests pin that selection: the decisive one below builds a
cohort where the old primary and Collector Appeal V3 produce DIFFERENT orderings
and asserts the verdict follows V3.
"""

import argparse

import pytest

from backend.research.collector_appeal_candidates import (
    CANONICAL_PRODUCTION_KEY,
    PRIMARY_CANDIDATE_KEY,
    PRODUCTION_CANDIDATE_KEY,
    compute_comparisons,
    production_candidate_identity,
)
from backend.scripts import build_rip_v3_collector_appeal_validation as command


def _args(**overrides):
    defaults = {"bootstrap_draws": 20, "uncertainty_draws": 20, "seed": 1}
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _rows(pairs):
    """Cohort rows from (D, H, P, financial) tuples.

    Mirrors ``build_rows``: every candidate and comparison column is scaled to
    0-100 exactly once, and both Collector Appeal V3 ablation families are
    precomputed, because the influence section reads them positionally.
    """
    from backend.research.collector_appeal_candidates import (
        collector_appeal_v3_contributions,
        compute_all_candidates,
        compute_v3_without_input,
    )

    def _scale(value):
        return None if value is None else value * 100.0

    rows = []
    for index, (d, h, p, financial) in enumerate(pairs):
        row = {
            "setId": f"set-{index}",
            "setName": f"Set {index}",
            "canonicalKey": f"set-{index}",
            "d": d, "h": h, "p": p, "m": None,
            "financialRipV3": financial,
        }
        for key, value in compute_all_candidates(d, h, p).items():
            row[key] = _scale(value)
        for key, value in compute_comparisons(d=d, h=h, p=p, m=None).items():
            row[key] = _scale(value)
        for study_key in ("d", "h", "p"):
            row[f"v3_drop_{study_key}_raw"] = _scale(
                compute_v3_without_input(d, h, p, dropped=study_key, renormalize=False)
            )
            row[f"v3_drop_{study_key}_renorm"] = _scale(
                compute_v3_without_input(d, h, p, dropped=study_key, renormalize=True)
            )
        for study_key, contribution in collector_appeal_v3_contributions(d, h, p).items():
            row[f"v3_contribution_{study_key}"] = _scale(contribution)
        rows.append(row)
    return rows


# A cohort deliberately built so the two formulas DISAGREE about the ordering.
# The bounded-headroom primary multiplies the structural term by (1 - D), so a
# set with high D and weak structure keeps a high score under it while the
# balanced sum marks it down; a set with low D and strong structure does the
# reverse.
#
# The financial scores are deliberately CLOSE (2 points apart). At the 10%
# production weight a wide financial spread swamps the appeal term entirely and
# both candidates reproduce the financial-only ordering exactly - which would
# make the regression below pass without testing anything.
_DIVERGENT = [
    (0.90, 0.05, 0.05, 60.0),
    (0.20, 0.95, 0.95, 58.0),
    (0.70, 0.30, 0.30, 56.0),
    (0.30, 0.80, 0.70, 54.0),
    (0.60, 0.40, 0.10, 52.0),
]


def test_the_fixture_cohort_actually_separates_the_two_formulas():
    """Guard on the guard: a cohort where they agree would prove nothing."""
    rows = _rows(_DIVERGENT)
    primary_order = [r["setId"] for r in sorted(rows, key=lambda r: -r[PRIMARY_CANDIDATE_KEY])]
    production_order = [
        r["setId"] for r in sorted(rows, key=lambda r: -r[PRODUCTION_CANDIDATE_KEY])
    ]
    assert primary_order != production_order


def test_production_candidate_key_is_the_canonical_collector_appeal_version():
    # The RESEARCH validation harness's production key still names V3: that
    # harness describes the study that selected V3, and repointing it would
    # rewrite what the study concluded. What must hold is that it is a real,
    # identifiable Collector Appeal version - not that it is the current one.
    from backend.desirability.collector_appeal import COLLECTOR_APPEAL_V3_VERSION

    assert PRODUCTION_CANDIDATE_KEY == COLLECTOR_APPEAL_V3_VERSION
    assert PRODUCTION_CANDIDATE_KEY == "collector_appeal_v3_balanced_d40_h35_p25"
    assert PRODUCTION_CANDIDATE_KEY != PRIMARY_CANDIDATE_KEY


def test_the_production_candidate_reproduces_the_shipping_entry_point():
    assert production_candidate_identity()["productionFormulaMatch"] is True


def test_the_version_key_and_the_nickname_key_are_the_same_numbers():
    """Two columns, one formula. They may never diverge."""
    for d, h, p, _financial in _DIVERGENT:
        comparisons = compute_comparisons(d=d, h=h, p=p)
        assert comparisons[PRODUCTION_CANDIDATE_KEY] == comparisons[CANONICAL_PRODUCTION_KEY]


# ---------------------------------------------------------------------------
# THE regression: the verdict follows Collector Appeal V3, not the CA8 primary
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def analysis():
    return command.run_analysis(_rows(_DIVERGENT), _args())


def test_the_canonical_verdict_selects_the_production_candidate(analysis):
    verdict = analysis["productionConfiguration"]
    assert verdict["candidateKey"] == PRODUCTION_CANDIDATE_KEY
    assert verdict["collectorAppealVersion"] == PRODUCTION_CANDIDATE_KEY
    assert verdict["productionFormulaMatch"] is True
    assert verdict["available"] is True


def test_the_canonical_verdict_is_not_the_old_primary_candidates_verdict(analysis):
    """The decisive assertion, on a cohort where the two orderings differ.

    Both cells exist in the sensitivity grid. The verdict must be measured off
    the production cell; if it were still being read from the CA8 primary, the
    measured statistics below would be the primary's.
    """
    verdict = analysis["productionConfiguration"]
    grid = analysis["overallWeightSensitivity"]
    production_cell = grid[PRODUCTION_CANDIDATE_KEY]
    primary_cell = grid[PRIMARY_CANDIDATE_KEY]

    weight = f"{verdict['productionWeight']:.2f}"
    production_gate = production_cell["weights"][weight]["productionGuardrails"]
    primary_gate = primary_cell["weights"][weight]["productionGuardrails"]

    assert verdict["measured"] == production_gate["measured"]
    assert production_gate["measured"] != primary_gate["measured"], (
        "the fixture cohort no longer separates the two candidates; the "
        "regression it guards would pass vacuously"
    )


def test_only_the_production_cell_claims_to_be_the_production_formula(analysis):
    grid = analysis["overallWeightSensitivity"]
    claiming = [
        key
        for key, cell in grid.items()
        if (cell.get("canonicalConfigurationVerdict") or {}).get("isProductionFormula")
    ]
    assert claiming == [PRODUCTION_CANDIDATE_KEY]


def test_the_ca8_family_is_retained_as_a_historical_comparison(analysis):
    """Kept for comparison, not deleted - and not treated as canonical."""
    grid = analysis["overallWeightSensitivity"]
    assert PRIMARY_CANDIDATE_KEY in grid
    assert "collector_appeal_v2_bounded_headroom" in grid


# ---------------------------------------------------------------------------
# --strict
# ---------------------------------------------------------------------------

def test_strict_passes_on_a_healthy_production_verdict(analysis):
    if analysis["productionConfiguration"].get("passed") is True:
        assert command.production_verdict_strict_failures(analysis) == []


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda v: v.update(candidateKey="CA8_D_H60_P40_L50"), "is absent from the"),
        (lambda v: v.update(formulaVersion="collector_appeal_bounded_headroom_v1"),
         "differs from the canonical configuration"),
        (lambda v: v.update(productionFormulaMatch=False),
         "does not reproduce the production Collector Appeal V3 entry point"),
        (lambda v: v.update(available=False, reason="no rows"), "result is unavailable"),
        (lambda v: v.update(passed=False, failedChecks=["spearmanOk"]),
         "did not pass every predeclared guardrail"),
        (lambda v: v.update(passed=None, unmeasuredChecks=["top5OverlapOk"]),
         "did not pass every predeclared guardrail"),
    ],
)
def test_strict_refuses_when_the_verdict_is_not_about_the_shipping_formula(
    analysis, mutate, expected
):
    mutated = {**analysis, "productionConfiguration": dict(analysis["productionConfiguration"])}
    mutate(mutated["productionConfiguration"])
    failures = command.production_verdict_strict_failures(mutated)
    assert any(expected in failure for failure in failures), failures


def test_strict_reports_every_problem_not_just_the_first(analysis):
    mutated = {**analysis, "productionConfiguration": dict(analysis["productionConfiguration"])}
    mutated["productionConfiguration"].update(
        candidateKey="CA8_D_H60_P40_L50",
        formulaVersion="something_else",
        productionFormulaMatch=False,
    )
    assert len(command.production_verdict_strict_failures(mutated)) >= 3


def test_a_missing_production_candidate_is_a_failure_not_a_fallback():
    """An absent production candidate never falls back to the nearest key."""
    verdict = command.production_configuration_verdict({"overallWeightSensitivity": {}})
    assert verdict["available"] is False
    assert verdict["passed"] is None
    failures = command.production_verdict_strict_failures(
        {"productionConfiguration": verdict}
    )
    assert any("unavailable" in failure for failure in failures)
