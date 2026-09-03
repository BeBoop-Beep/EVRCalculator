"""Chase Accessibility V1 production invariants.

The permanent regressions this file exists to prevent, all of which have already
produced a plausible-looking wrong answer at least once in the research lineage:

* reading ``effective_pull_rate`` (1-in-N odds) as a probability;
* substituting ``pull_count / simulation_count`` (expected copies) for the
  per-pack presence probability;
* renormalising Chase Significance around missing probability rows, which makes
  a set look MORE accessible because an important card went missing;
* letting sealed-product economics into a set-level access metric;
* describing the metric as "the chance of pulling a chase card".
"""

from __future__ import annotations

import inspect
import math

import pytest

from backend.desirability import chase_accessibility as ca


def _row(variant, price, probability, **extra):
    row = {
        "set_id": "set-1",
        "calculation_run_id": "run-1",
        "card_variant_id": variant,
        "price_used": price,
        "modeled_probability": probability,
    }
    row.update(extra)
    return row


# --------------------------------------------------------------------------
# Math
# --------------------------------------------------------------------------

def test_chase_significance_sums_to_one():
    hc = ca.compute_chase_significance([10.0, 20.0, 30.0, 1.0])
    assert math.fsum(hc) == pytest.approx(1.0, abs=1e-12)


def test_chase_significance_is_the_squared_value_share():
    hc = ca.compute_chase_significance([1.0, 2.0])
    assert hc == pytest.approx([1 / 5, 4 / 5])


def test_chase_significance_is_exactly_invariant_to_uniform_price_scaling():
    """The scale cancels between numerator and denominator."""
    base = ca.compute_chase_significance([3.0, 7.0, 11.0, 0.25])
    for factor in (1e-6, 0.5, 3.0, 1e6):
        scaled = ca.compute_chase_significance([v * factor for v in (3.0, 7.0, 11.0, 0.25)])
        assert scaled == pytest.approx(base, rel=1e-12)


def test_chase_depth_is_the_inverse_herfindahl():
    hc = [0.25, 0.25, 0.25, 0.25]
    assert ca.compute_chase_depth(hc) == pytest.approx(4.0)
    assert ca.compute_chase_depth([1.0]) == pytest.approx(1.0)


def test_chase_depth_is_continuous_and_not_a_card_count():
    """3.9 is not "about four cards" and must not be rounded into one."""
    hc = ca.compute_chase_significance([100.0, 90.0, 80.0, 5.0, 1.0])
    depth = ca.compute_chase_depth(hc)
    assert depth != round(depth)
    assert 1.0 < depth < 5.0


def test_accessibility_matches_the_direct_form():
    values = [100.0, 40.0, 5.0, 1.0]
    probabilities = [0.001, 0.02, 0.3, 0.9]
    rows = [_row("v%d" % i, values[i], probabilities[i]) for i in range(4)]
    result = ca.compute_chase_accessibility(variants=rows)
    squares = [v * v for v in values]
    direct = sum(s * p for s, p in zip(squares, probabilities)) / sum(squares)
    assert result["accessibility"] == pytest.approx(direct, abs=1e-15)
    assert result["parityDelta"] < 1e-15


def test_accessibility_is_bounded_by_the_probability_range():
    values = [10.0, 3.0, 1.0]
    for probability in (0.0, 0.25, 1.0):
        rows = [_row("v%d" % i, values[i], probability) for i in range(3)]
        result = ca.compute_chase_accessibility(variants=rows)
        assert result["accessibility"] == pytest.approx(probability)
    rows = [_row("v%d" % i, values[i], p) for i, p in enumerate((0.1, 0.5, 0.9))]
    result = ca.compute_chase_accessibility(variants=rows)
    assert 0.1 <= result["accessibility"] <= 0.9


def test_accessibility_is_monotone_in_probability():
    values = [50.0, 10.0, 2.0]
    previous = None
    for bump in (0.01, 0.05, 0.2, 0.6):
        rows = [_row("v%d" % i, values[i], bump) for i in range(3)]
        current = ca.compute_chase_accessibility(variants=rows)["accessibility"]
        if previous is not None:
            assert current > previous
        previous = current


def test_output_is_deterministic():
    rows = [_row("v%d" % i, 10.0 * (i + 1), 0.01 * (i + 1)) for i in range(6)]
    first = ca.compute_chase_accessibility(variants=rows)
    second = ca.compute_chase_accessibility(variants=list(reversed(rows)))
    assert first["accessibility"] == pytest.approx(second["accessibility"], abs=1e-15)
    assert first["chaseDepth"] == pytest.approx(second["chaseDepth"], abs=1e-12)


def test_percentage_is_the_fraction_times_one_hundred():
    rows = [_row("v1", 10.0, 0.004)]
    result = ca.compute_chase_accessibility(variants=rows)
    assert result["accessibilityPct"] == pytest.approx(result["accessibility"] * 100.0)
    assert result["accessibility"] < 1.0


# --------------------------------------------------------------------------
# Probability authority - the permanent traps
# --------------------------------------------------------------------------

def test_odds_cannot_be_passed_as_a_probability():
    """``effective_pull_rate`` is 1-in-N. 430 is not a probability of 430."""
    rows = [_row("v1", 100.0, 430.0), _row("v2", 10.0, 0.5)]
    result = ca.compute_chase_accessibility(variants=rows)
    # The $100 card carries 99% of the significance; refusing its bogus
    # probability drops mapped mass far below the gate rather than clamping.
    assert result["status"] == ca.STATUS_LOW_COVERAGE
    assert result["accessibility"] is None


def test_an_out_of_range_probability_is_refused_not_clamped():
    for bad in (1.0000001, -0.0001, 2.0, 430.0):
        assert ca._valid_probability(bad) is None
    assert ca._valid_probability(1.0) == 1.0
    assert ca._valid_probability(0.0) == 0.0


def test_probability_authority_accepts_coherent_rows():
    rows = [
        _row("v1", 10.0, 0.01, pack_presence_count=100, simulation_count=10_000,
             effective_pull_rate=100.0, pull_count=100),
        _row("v2", 5.0, 0.25, pack_presence_count=2_500, simulation_count=10_000,
             effective_pull_rate=4.0, pull_count=2_500),
    ]
    report = ca.assert_probability_authority(rows)
    assert report["holds"] is True
    assert report["presenceChecked"] == 2
    assert report["oddsChecked"] == 2
    assert report["rowsWhereExpectedCopiesDiffer"] == 0


def test_probability_authority_flags_an_odds_column_masquerading_as_probability():
    rows = [_row("v1", 10.0, 0.5, effective_pull_rate=100.0,
                 pack_presence_count=100, simulation_count=10_000)]
    report = ca.assert_probability_authority(rows)
    assert report["holds"] is False
    assert report["oddsFailed"] == 1
    assert report["presenceFailed"] == 1


def test_expected_copies_is_a_different_quantity_from_presence_probability():
    """A multi-hit row: 3 copies across 2 packs of 10 is not P(N>=1).

    ``pull_count/simulation_count`` = 0.30 while the presence probability is
    0.20. Substituting the former would overstate accessibility.
    """
    rows = [_row("v1", 10.0, 0.2, pull_count=3, pack_presence_count=2,
                 simulation_count=10, effective_pull_rate=5.0)]
    report = ca.assert_probability_authority(rows)
    assert report["holds"] is True
    assert report["rowsWhereExpectedCopiesDiffer"] == 1


def test_the_two_authority_identities_are_the_documented_ones():
    source = inspect.getsource(ca.assert_probability_authority)
    assert "pack_presence_count" in source
    assert "effective_pull_rate" in source


# --------------------------------------------------------------------------
# Coverage contract
# --------------------------------------------------------------------------

def test_full_coverage_reports_mapped_mass_of_one():
    rows = [_row("v%d" % i, 10.0 * (i + 1), 0.01) for i in range(5)]
    result = ca.compute_chase_accessibility(variants=rows)
    assert result["mappedHcMass"] == pytest.approx(1.0)
    assert result["status"] == ca.STATUS_READY


def test_mapped_mass_is_measured_against_the_full_universe_not_renormalised():
    """The gate's whole purpose.

    A $100 card with no probability carries ~99% of the significance. Measured
    correctly the mass collapses to ~0.0099; renormalising around the survivors
    would report 1.0 and publish a set that has lost its most important card.
    """
    values = [100.0, 10.0]
    usable = [False, True]
    mass = ca.compute_mapped_hc_mass(values, usable)
    assert mass == pytest.approx(100.0 / 10100.0)
    assert mass < 0.99


def test_insufficient_coverage_blocks_publication():
    rows = [_row("v1", 100.0, None), _row("v2", 10.0, 0.05)]
    result = ca.compute_chase_accessibility(variants=rows)
    assert result["status"] == ca.STATUS_LOW_COVERAGE
    assert result["accessibility"] is None
    assert result["publishable"] is False
    assert result["mappedHcMass"] < ca.MIN_MAPPED_HC_MASS


def test_a_small_missing_card_still_publishes():
    rows = [_row("v1", 100.0, 0.01), _row("v2", 1.0, None)]
    result = ca.compute_chase_accessibility(variants=rows)
    assert result["status"] == ca.STATUS_READY
    assert result["mappedHcMass"] > 0.99


def test_the_gate_threshold_is_ninety_nine_percent():
    assert ca.MIN_MAPPED_HC_MASS == 0.99


def test_unavailable_returns_null_never_zero():
    """Zero means measured zero accessibility, not missing data."""
    result = ca.compute_chase_accessibility(variants=[], has_pull_model=False)
    assert result["accessibility"] is None
    assert result["accessibilityPct"] is None
    assert result["chaseDepth"] is None
    assert result["status"] == ca.STATUS_NO_PULL_MODEL
    assert result["publishable"] is False


def test_a_genuinely_zero_probability_set_publishes_zero():
    rows = [_row("v%d" % i, 10.0, 0.0) for i in range(3)]
    result = ca.compute_chase_accessibility(variants=rows)
    assert result["status"] == ca.STATUS_READY
    assert result["accessibility"] == 0.0
    assert result["accessibility"] is not None


# --------------------------------------------------------------------------
# Input validation
# --------------------------------------------------------------------------

def test_no_variants_is_unavailable_not_an_error():
    assert ca.compute_chase_accessibility(variants=[])["status"] == ca.STATUS_NO_UNIVERSE


def test_no_priced_variant_is_unavailable():
    rows = [_row("v1", 0.0, 0.1), _row("v2", None, 0.2)]
    assert (ca.compute_chase_accessibility(variants=rows)["status"]
            == ca.STATUS_NO_PRICED_UNIVERSE)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -5.0, "x", None])
def test_invalid_prices_never_become_significance(bad):
    hc = ca.compute_chase_significance([10.0, bad])
    assert hc[1] == 0.0
    assert hc[0] == pytest.approx(1.0)


def test_mixed_sets_are_refused():
    rows = [_row("v1", 10.0, 0.1), _row("v2", 10.0, 0.1, set_id="set-2")]
    with pytest.raises(ca.ChaseAccessibilityInputError):
        ca.compute_chase_accessibility(variants=rows)


def test_mixed_calculation_runs_are_refused():
    rows = [_row("v1", 10.0, 0.1), _row("v2", 10.0, 0.1, calculation_run_id="run-2")]
    with pytest.raises(ca.ChaseAccessibilityInputError):
        ca.compute_chase_accessibility(variants=rows)


def test_a_run_mismatch_against_the_requested_run_is_refused():
    rows = [_row("v1", 10.0, 0.1)]
    with pytest.raises(ca.ChaseAccessibilityInputError):
        ca.compute_chase_accessibility(variants=rows, calculation_run_id="run-9")


def test_duplicate_card_variants_are_refused():
    rows = [_row("v1", 10.0, 0.1), _row("v1", 10.0, 0.1)]
    with pytest.raises(ca.ChaseAccessibilityInputError):
        ca.compute_chase_accessibility(variants=rows)


def test_a_missing_variant_identity_is_refused():
    rows = [_row(None, 10.0, 0.1)]
    with pytest.raises(ca.ChaseAccessibilityInputError):
        ca.compute_chase_accessibility(variants=rows)


# --------------------------------------------------------------------------
# Architecture
# --------------------------------------------------------------------------

def test_the_public_api_cannot_accept_product_inputs():
    """No sealed-product cost, product id or pack count may reach this metric."""
    signature = inspect.signature(ca.compute_chase_accessibility)
    names = set(signature.parameters)
    for forbidden in ("product_market_cost", "sealed_product_id", "pack_count",
                      "random_pack_count", "product_id", "products"):
        assert forbidden not in names
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY
               for p in signature.parameters.values())
    with pytest.raises(TypeError):
        ca.compute_chase_accessibility(variants=[], product_market_cost=100.0)


def test_production_does_not_import_research():
    source = inspect.getsource(ca)
    assert "backend.research" not in source
    assert "from backend.research" not in source


def test_the_module_declares_its_versions():
    assert ca.CHASE_ACCESSIBILITY_VERSION == (
        "chase_accessibility_v1_hc_value_squared_modeled_probability")
    assert ca.CHASE_SIGNIFICANCE_VERSION == "chase_significance_v1_squared_value_share"
    assert ca.CHASE_DEPTH_VERSION == "chase_depth_v1_hc_effective_count"
    result = ca.compute_chase_accessibility(variants=[_row("v1", 10.0, 0.1)])
    assert result["version"] == ca.CHASE_ACCESSIBILITY_VERSION


def test_no_dependency_on_the_superseded_v11_chase_work():
    source = inspect.getsource(ca)
    for superseded in ("core_k", "coreK", "chase_opportunity", "overall_rip_v11",
                       "saturating"):
        assert superseded not in source


def test_canonical_overall_rip_is_now_v12_at_eighty_six_four_ten():
    """2026-09-03 cutover: canonical Overall RIP promoted from V10 (90/10) to
    V12 (86% Financial + 4% Chase Accessibility + 10% Collector Appeal)."""
    from backend.desirability.scoring_config import (
        CANONICAL_OVERALL_RIP_VERSION, CANONICAL_OVERALL_RIP_WEIGHTS,
    )
    assert CANONICAL_OVERALL_RIP_VERSION == (
        "overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5")
    assert CANONICAL_OVERALL_RIP_WEIGHTS["financial_rip"] == pytest.approx(0.86)
    assert CANONICAL_OVERALL_RIP_WEIGHTS["chase_accessibility"] == pytest.approx(0.04)
    assert CANONICAL_OVERALL_RIP_WEIGHTS["collector_appeal"] == pytest.approx(0.10)


def test_chase_accessibility_is_not_wired_into_overall_rip():
    from backend.desirability import weighted_rip
    source = inspect.getsource(weighted_rip)
    assert "chase_accessibility" not in source
    assert "ChaseAccessibility" not in source


# --------------------------------------------------------------------------
# Copy discipline
# --------------------------------------------------------------------------

FORBIDDEN_PHRASES = (
    "chance of pulling a chase",
    "probability of a chase",
    "chance to hit the chase",
    "chance of a chase",
)


def test_the_module_never_describes_itself_as_a_chance_of_a_chase():
    source = inspect.getsource(ca).lower()
    for phrase in FORBIDDEN_PHRASES:
        # The docstring names these phrases only to forbid them, so each must be
        # accompanied by the prohibition.
        if phrase in source:
            assert "not" in source[max(0, source.index(phrase) - 120):source.index(phrase)]


def test_status_reasons_are_explanatory_not_bare_enums():
    for status, reason in ca.STATUS_REASONS.items():
        assert len(reason) > 40, status


# --------------------------------------------------------------------------
# Four-quadrant independence
# --------------------------------------------------------------------------

def test_depth_and_accessibility_are_independent_axes():
    """All four combinations must be constructible; neither derives the other."""
    def build(values, probabilities):
        rows = [_row("v%d" % i, values[i], probabilities[i])
                for i in range(len(values))]
        out = ca.compute_chase_accessibility(variants=rows)
        return out["chaseDepth"], out["accessibility"]

    concentrated_accessible = build([100.0, 1.0, 1.0], [0.5, 0.5, 0.5])
    concentrated_inaccessible = build([100.0, 1.0, 1.0], [0.001, 0.5, 0.5])
    deep_accessible = build([10.0, 10.0, 10.0], [0.5, 0.5, 0.5])
    deep_inaccessible = build([10.0, 10.0, 10.0], [0.001, 0.001, 0.001])

    assert concentrated_accessible[0] < 1.5
    assert deep_accessible[0] > 2.5
    assert concentrated_accessible[1] > concentrated_inaccessible[1]
    assert deep_accessible[1] > deep_inaccessible[1]
    # Same depth, different accessibility - so one cannot be read off the other.
    assert deep_accessible[0] == pytest.approx(deep_inaccessible[0])
    assert deep_accessible[1] != pytest.approx(deep_inaccessible[1])
