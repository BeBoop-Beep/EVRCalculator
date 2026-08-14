"""The validation framework itself: determinism, correctness, and read-only-ness.

A validation instrument that is not itself validated is decoration. These tests
cover the properties the report's credibility rests on: identical seeds give
identical numbers, input ordering is irrelevant, the variance decomposition
actually reconstructs the variance it claims to explain, and the script cannot
write to the database or fall back to Financial RIP V2.
"""

from __future__ import annotations

import ast
import inspect
import random

import pytest

from backend.research import validation_stats as stats
from backend.research import validation_uncertainty as uncertainty
from backend.scripts import build_rip_v3_collector_appeal_validation as script

XS = [3.0, 1.0, 4.0, 1.5, 5.0, 9.0, 2.0, 6.0, 5.5, 3.5, 8.0, 7.0]
YS = [2.0, 1.2, 5.0, 1.1, 4.0, 8.0, 3.0, 7.0, 4.5, 2.5, 9.0, 6.5]


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_bootstrap_is_reproducible_under_a_fixed_seed():
    first = stats.bootstrap_correlation_ci(XS, YS, draws=300, seed=42)
    second = stats.bootstrap_correlation_ci(XS, YS, draws=300, seed=42)
    assert first == second


def test_bootstrap_differs_under_a_different_seed():
    """Otherwise the seed would be decorative and the CI not a real resample."""
    a = stats.bootstrap_correlation_ci(XS, YS, draws=300, seed=1)
    b = stats.bootstrap_correlation_ci(XS, YS, draws=300, seed=2)
    assert (a["ciLow"], a["ciHigh"]) != (b["ciLow"], b["ciHigh"])


def test_bootstrap_uses_the_requested_number_of_draws():
    result = stats.bootstrap_correlation_ci(XS, YS, draws=250, seed=7)
    assert result["draws"] == 250


def test_permutation_p_value_is_reproducible_and_never_exactly_zero():
    first = stats.permutation_p_value(XS, YS, draws=300, seed=11)
    second = stats.permutation_p_value(XS, YS, draws=300, seed=11)
    assert first == second
    assert first["pValue"] > 0.0


def test_uncertainty_draws_are_reproducible_under_a_fixed_seed():
    subjects = [
        {
            "subject_key": "s1",
            "subject_name": "A",
            "appeal_excess": 10.0,
            "cards": [{"pull_probability": 0.2, "slot_group": "x", "rarity": "UR"}],
        }
    ]
    first = uncertainty.shock_pull_rates(subjects, rng=random.Random(5), magnitude=0.2)
    second = uncertainty.shock_pull_rates(subjects, rng=random.Random(5), magnitude=0.2)
    assert first[0]["cards"][0]["pull_probability"] == second[0]["cards"][0]["pull_probability"]


# ---------------------------------------------------------------------------
# Order independence
# ---------------------------------------------------------------------------

def test_correlations_are_invariant_to_input_ordering():
    """Reordering the cohort must not change any statistic."""
    order = list(range(len(XS)))
    shuffled = order[::-1]
    xs2 = [XS[i] for i in shuffled]
    ys2 = [YS[i] for i in shuffled]
    assert stats.spearman(XS, YS) == pytest.approx(stats.spearman(xs2, ys2))
    assert stats.kendall_tau_b(XS, YS) == pytest.approx(stats.kendall_tau_b(xs2, ys2))


def test_dense_ranks_break_ties_deterministically_by_key_not_insertion_order():
    forward = stats.dense_ranks({"alpha": 10.0, "beta": 10.0, "gamma": 5.0})
    backward = stats.dense_ranks({"gamma": 5.0, "beta": 10.0, "alpha": 10.0})
    assert forward == backward
    assert forward["alpha"] == 1 and forward["beta"] == 2


def test_benjamini_hochberg_is_deterministic_including_ties():
    values = [0.02, 0.02, 0.04, 0.20, 0.001]
    assert stats.benjamini_hochberg(values) == stats.benjamini_hochberg(list(values))


def test_benjamini_hochberg_matches_a_hand_computed_case():
    """m=4, sorted p = .01 .02 .03 .04 -> q = .04 .04 .04 .04 (monotone step-up)."""
    adjusted = stats.benjamini_hochberg([0.01, 0.02, 0.03, 0.04])
    assert adjusted == [0.04, 0.04, 0.04, 0.04]


def test_benjamini_hochberg_excludes_none_from_the_family_size():
    """A test that could not be computed is not a test that was performed."""
    with_none = stats.benjamini_hochberg([0.01, 0.02, None, None])
    without = stats.benjamini_hochberg([0.01, 0.02])
    assert with_none[:2] == without
    assert with_none[2] is None and with_none[3] is None


# ---------------------------------------------------------------------------
# Variance decomposition
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("weight", [0.00, 0.10, 0.15, 0.20, 0.25])
def test_variance_decomposition_reconstructs_the_observed_variance(weight):
    """a^2Var(F) + b^2Var(C) + 2abCov must equal Var(aF + bC) exactly."""
    financial = [55.0, 61.2, 48.9, 70.1, 66.4, 52.3, 59.8]
    appeal = [80.1, 72.5, 91.0, 66.3, 78.8, 85.2, 70.0]
    result = stats.variance_decomposition(financial, appeal, weight)
    assert result["reconstructionError"] < 1e-9
    assert result["varOverallFromTerms"] == pytest.approx(result["varOverallDirect"])


def test_variance_decomposition_reports_all_three_terms_separately():
    result = stats.variance_decomposition([1.0, 2.0, 3.0], [3.0, 1.0, 2.0], 0.20)
    for key in ("termFinancial", "termAppeal", "termCross", "covariance", "correlation"):
        assert key in result
    for key in ("dispersionShareFinancial", "dispersionShareAppeal"):
        assert 0.0 <= result[key] <= 1.0
    assert result["dispersionShareFinancial"] + result["dispersionShareAppeal"] == pytest.approx(1.0)


def test_zero_weight_gives_the_appeal_term_no_variance_contribution():
    result = stats.variance_decomposition([1.0, 5.0, 3.0], [9.0, 1.0, 4.0], 0.0)
    assert result["termAppeal"] == pytest.approx(0.0)
    assert result["termCross"] == pytest.approx(0.0)
    assert result["appealContributionMean"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Weight grids and leave-one-out treatment
# ---------------------------------------------------------------------------

def test_overall_weight_grid_is_complete_and_ordered():
    from backend.research.collector_appeal_candidates import (
        OVERALL_COLLECTOR_APPEAL_WEIGHT_GRID as grid,
    )

    from backend.desirability.scoring_config import (
        OVERALL_RIP_COLLECTOR_APPEAL_SENSITIVITY_WEIGHTS,
        OVERALL_RIP_V8_WEIGHTS,
    )

    assert grid == (0.00, 0.05, 0.075, 0.10, 0.13, 0.14, 0.15, 0.20)
    assert list(grid) == sorted(grid)
    # READ from config, not restated: the study and production must not be able
    # to disagree about which weights are candidates and which one ships.
    assert grid == tuple(OVERALL_RIP_COLLECTOR_APPEAL_SENSITIVITY_WEIGHTS)
    # 0.00 is the explicit financial-only reference column, and the canonical
    # production weight has to be in the grid or the study cannot report the
    # shipping configuration.
    assert grid[0] == 0.00
    assert OVERALL_RIP_V8_WEIGHTS["collector_appeal"] in grid
    # 0.13 and 0.14 are RESEARCH sensitivity points, never production.
    assert OVERALL_RIP_V8_WEIGHTS["collector_appeal"] not in (0.13, 0.14)


def test_leave_one_out_uses_the_intended_weight_treatment():
    """Renormalized weights must sum to 1; contribution-removal must not.

    The two methods are only informative because they differ in exactly this
    way. If the drop-and-renormalize branch failed to renormalize, it would
    silently become a second copy of contribution removal and the report would
    show two identical columns described as answering different questions.
    """
    from backend.calculations.evr.financial_rip_v3_config import (
        FINANCIAL_RIP_V3_COMPONENT_ORDER,
        FINANCIAL_RIP_V3_WEIGHTS,
    )

    rows = []
    for index in range(6):
        row = {"setId": f"s{index}", "setName": f"Set {index}"}
        for offset, key in enumerate(FINANCIAL_RIP_V3_COMPONENT_ORDER):
            row[f"v3_{key}"] = 40.0 + (index * 7 + offset * 11) % 50
        rows.append(row)

    result = script.leave_one_component_out(rows)
    assert result["available"] is True
    for dropped, payload in result["components"].items():
        remaining = {k: w for k, w in FINANCIAL_RIP_V3_WEIGHTS.items() if k != dropped}
        assert sum(remaining.values()) < 1.0  # pre-renormalization
        assert payload["contributionRemoval"]["n"] == len(rows)
        assert payload["dropAndRenormalize"]["n"] == len(rows)
        # The two methods must not produce identical score deltas, or the
        # renormalization is not happening.
        assert (
            payload["contributionRemoval"]["meanAbsScoreDelta"]
            != payload["dropAndRenormalize"]["meanAbsScoreDelta"]
        )


# ---------------------------------------------------------------------------
# Read-only guarantees
# ---------------------------------------------------------------------------

# Verbs that only ever appear on a database client. `update` is deliberately
# ABSENT: `dict.update(...)` is ordinary Python and banning the bare name would
# make this test fire on a payload assembly, teaching the reader to ignore it.
# Postgrest writes always go through `.table(...)`, so the chain check below is
# what actually catches a write, including `.table(...).update(...)`.
DB_ONLY_VERBS = {"insert", "upsert", "rpc", "execute_sql", "delete"}


def _assert_no_database_access(module_or_source, label: str) -> None:
    source = (
        module_or_source
        if isinstance(module_or_source, str)
        else inspect.getsource(module_or_source)
    )
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "attr", None)
            assert name not in DB_ONLY_VERBS, f"{label} calls {name!r}"
            # Any `.table("...")` call is a database access, read or write.
            if name == "table":
                pytest.fail(f"{label} accesses a table directly")

    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            assert "supabase_client" not in name, f"{label} imports a database client"


def test_validation_script_performs_no_database_writes():
    """The script may READ through a service; it may never write.

    Table access is asserted absent entirely: the script reads the cohort
    through `explore_rip_statistics_service`, which is the publication path, so
    a direct table call here would be both a write risk and a second source of
    truth for the cohort.
    """
    _assert_no_database_access(script, "validation script")


def test_research_modules_perform_no_database_access_at_all():
    from backend.research import collector_appeal_candidates, validation_stats

    for module in (collector_appeal_candidates, validation_stats, uncertainty):
        _assert_no_database_access(module, module.__name__)


def test_validation_script_never_falls_back_to_financial_rip_v2():
    """A V2 score analysed under a V3 label would invalidate every finding."""
    source = inspect.getsource(script)
    assert "compute_financial_rip_v2" not in source
    assert "FINANCIAL_RIP_V2_VERSION" not in source
    readiness = script.assess_readiness(
        [
            {"setName": "A", "financialRipV3": None, "d": 0.5, "h": 0.2, "p": 0.3},
            {"setName": "B", "financialRipV3": 61.0, "d": 0.6, "h": 0.3, "p": 0.4},
        ]
    )
    assert readiness["financialV3Missing"] == ["A"]
    assert readiness["fullyReady"] == ["B"]
    assert "never substituted" in readiness["noFallbackPolicy"]


def test_readiness_reports_financial_and_appeal_gaps_separately():
    """They fail for different reasons and are fixed by different commands."""
    readiness = script.assess_readiness(
        [
            {"setName": "NoSim", "financialRipV3": None, "d": 0.5, "h": 0.2, "p": 0.3},
            {"setName": "NoAppeal", "financialRipV3": 55.0, "d": None, "h": None, "p": None},
        ]
    )
    assert readiness["financialV3Missing"] == ["NoSim"]
    assert readiness["collectorAppealMissing"] == ["NoAppeal"]
    assert readiness["fullyReadyCount"] == 0
    assert readiness["canRunEmpiricalAnalysis"] is False


def test_uncertainty_refuses_to_reconstruct_tails_from_percentiles():
    """Without the real outcome vector the answer is 'unavailable', not an estimate."""
    result = uncertainty.financial_draws_from_outcomes(None, 5.0, draws=10, seed=1)
    assert result["available"] is False
    assert result["reason"] == "no_retained_outcome_vector"
    assert "cannot be reconstructed" in result["detail"]


# ---------------------------------------------------------------------------
# Rank indistinguishability
# ---------------------------------------------------------------------------

def test_pairwise_dominance_marks_overlapping_sets_as_unordered():
    """Two sets drawn from the same distribution must not be reliably ordered."""
    rng = random.Random(3)
    draws = {
        "twinA": [rng.gauss(60, 5) for _ in range(400)],
        "twinB": [rng.gauss(60, 5) for _ in range(400)],
        "clearWinner": [rng.gauss(95, 1) for _ in range(400)],
    }
    result = stats.pairwise_dominance(draws)
    by_pair = {(p["setA"], p["setB"]): p for p in result["pairs"]}
    assert by_pair[("twinA", "twinB")]["reliablyOrdered"] is False
    assert by_pair[("clearWinner", "twinA")]["reliablyOrdered"] is True


def test_rank_stability_bands_recompute_ranks_within_each_draw():
    rng = random.Random(9)
    draws = {
        "top": [rng.gauss(90, 2) for _ in range(200)],
        "middle": [rng.gauss(70, 8) for _ in range(200)],
        "bottom": [rng.gauss(50, 2) for _ in range(200)],
    }
    bands = stats.rank_stability_bands(draws)
    assert bands["sets"]["top"]["pTop3"] == 1.0
    assert bands["sets"]["top"]["rankMedian"] <= bands["sets"]["bottom"]["rankMedian"]
    # The volatile middle set must show a wider rank band than a stable one.
    assert bands["sets"]["middle"]["rankIqr"] >= bands["sets"]["top"]["rankIqr"]


def test_rank_comparison_reports_positive_delta_for_a_set_moving_up():
    baseline = {"a": 10.0, "b": 20.0, "c": 30.0}   # ranks: c=1, b=2, a=3
    variant = {"a": 40.0, "b": 20.0, "c": 30.0}   # ranks: a=1, c=2, b=3
    result = stats.rank_comparison(baseline, variant)
    assert result["rankDeltas"]["a"] == 2   # 3 -> 1, moved UP
    assert result["rankDeltas"]["b"] == -1  # 2 -> 3, moved DOWN
