"""Stage-I sanity tests for Set Chase Efficiency.

These encode the properties the brief demands the candidate metric satisfy
BEFORE any ranking is interpreted. Several are deliberately written to be able
to FAIL - in particular the near-worthless-padding test, which is the metric's
most plausible pathology and is asserted here as a measured direction rather
than an assumed safety property.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from backend.research.set_chase_efficiency.baskets import (
    ChaseCandidate,
    build_baskets,
    partition_universe,
)
from backend.research.set_chase_efficiency.metrics import (
    binomial_standard_error,
    chase_efficiency,
    concentration,
    conditional_value_statistics,
    hazard,
    hit_count_distribution,
    packs_for_horizon,
    whole_packs_for_horizon,
)


def ce(value, cost, p):
    return chase_efficiency(conditional_value=value, pack_cost=cost, probability=p)


# --- Property 1: higher chase probability must not reduce CE ---------------

@pytest.mark.parametrize("p", [1e-6, 1e-4, 0.001, 0.01, 0.1, 0.4, 0.9])
def test_higher_probability_never_reduces_chase_efficiency(p):
    lower = ce(100.0, 10.0, p)
    higher = ce(100.0, 10.0, min(p * 1.05, 1.0 - 1e-12))
    assert higher > lower


# --- Property 2: higher conditional chase value must not reduce CE ---------

@pytest.mark.parametrize("value", [0.01, 1.0, 50.0, 5000.0])
def test_higher_conditional_value_never_reduces_chase_efficiency(value):
    assert ce(value * 1.01, 10.0, 0.02) > ce(value, 10.0, 0.02)


# --- Property 3: lower acquisition cost must not reduce CE -----------------

@pytest.mark.parametrize("cost", [0.5, 5.0, 30.0, 400.0])
def test_lower_acquisition_cost_never_reduces_chase_efficiency(cost):
    assert ce(100.0, cost * 0.99, 0.02) > ce(100.0, cost, 0.02)


# --- Property 4: adding a genuinely valuable reachable chase ---------------

def test_adding_a_valuable_reachable_chase_raises_chase_efficiency():
    """A second chase worth as much as the first must improve the chase.

    Both p_S and V_S rise, so CE must rise. This is the case the metric is
    supposed to reward and is the cheap half of the padding question.
    """
    before = ce(200.0, 10.0, 0.01)
    after = ce(200.0, 10.0, 0.02)  # same value, twice as reachable
    assert after > before


# --- Property 5: padding with a near-worthless card ------------------------

def test_conditional_mean_chase_efficiency_is_monotone_under_basket_expansion():
    """THE PATHOLOGY. Documented as a measured fact, not guarded against.

    With ``V_S`` = conditional arithmetic MEAN of total qualifying value, the
    identity ``V_S * p_S = E_S`` holds, where ``E_S`` is the UNCONDITIONAL
    expected qualifying value per pack. Substituting::

        CE = (V_S / C) * h(p_S) = (E_S / C) * (h(p_S) / p_S)

    ``h(p)/p`` is >= 1 and strictly increasing in ``p``
    (``test_hazard_over_probability_is_increasing``). Adding ANY card with a
    positive price strictly increases ``E_S`` and weakly increases ``p_S``, so
    CE strictly increases. The mean-based metric is therefore maximised by
    calling every card in the set a chase - at which point it degenerates into
    total pack EV over cost, which is the thing Set Chase Efficiency was
    supposed to be distinct from.

    This test exists so the defect cannot be quietly reintroduced later.
    """
    focused = ce(200.0, 10.0, 0.01)
    p_padded = 1.0 - (1.0 - 0.01) * (1.0 - 0.9)
    padded_value = (0.9 * 0.10 + 0.01 * 200.0) / p_padded
    padded = ce(padded_value, 10.0, p_padded)
    assert padded > focused, (
        "padding with a near-worthless common did NOT raise mean-based CE; the "
        "monotonicity argument above must be re-derived before trusting this suite"
    )


@pytest.mark.parametrize("p", [1e-4, 1e-3, 0.01, 0.1, 0.3, 0.7, 0.99])
def test_hazard_over_probability_is_increasing(p):
    """The exact term that makes basket expansion always look better."""
    ratio = hazard(p) / p
    assert ratio >= 1.0
    assert hazard(min(p * 1.05, 0.999)) / min(p * 1.05, 0.999) > ratio


def test_conditional_median_chase_efficiency_can_fall_under_padding():
    """The median variant is NOT degenerate, which is why it survives Stage I.

    Once padding openings outnumber real chase openings the conditional median
    collapses to the padding card's price, and CE falls even though ``p_S``
    rose. A statistic that breaks the ``V_S * p_S = E_S`` identity is the only
    kind that can produce an interior optimum in basket size.
    """
    focused = ce(200.0, 10.0, 0.01)
    p_padded = 1.0 - (1.0 - 0.01) * (1.0 - 0.9)
    padded_median = 0.10  # >50% of qualifying openings qualify only via the common
    padded = ce(padded_median, 10.0, p_padded)
    assert padded < focused


def test_padding_with_a_valueless_card_cannot_be_masked_by_the_median():
    """The median V_S is the statistic most exposed to padding.

    Once more than half of qualifying openings qualify only via the padding
    card, the conditional MEDIAN collapses to the padding card's price. This
    asserts the collapse is visible rather than absent - it is a reason the
    median is a candidate to REJECT, not evidence the metric is broken.
    """
    values = np.array([0.10] * 900 + [200.0] * 10)
    stats = conditional_value_statistics(values)
    assert stats["median"] == pytest.approx(0.10)
    assert stats["mean"] > stats["median"]


# --- Property 6: finiteness at the probability boundaries ------------------

def test_probability_of_one_is_refused_rather_than_scored_as_infinite():
    assert hazard(1.0) is None
    assert ce(100.0, 10.0, 1.0) is None


def test_tiny_probabilities_stay_finite_and_ordered():
    tiny = ce(100.0, 10.0, 1e-12)
    assert tiny is not None and math.isfinite(tiny) and tiny > 0.0
    assert ce(100.0, 10.0, 1e-11) > tiny


def test_probability_above_one_or_below_zero_is_refused():
    assert ce(100.0, 10.0, 1.5) is None
    assert ce(100.0, 10.0, -0.1) is None
    assert ce(100.0, 10.0, 0.0) is None


# --- Property 7: empty baskets receive no score ----------------------------

def test_empty_basket_is_unsupported_and_unscored():
    universe = [
        ChaseCandidate(0, "v0", "c0", "A", "001", "normal", "rare", 5.0, "2026-08-28", "src", 10)
    ]
    baskets = {b.definition_key: b for b in build_baskets(universe, pack_cost=4.0)}
    assert baskets["top_5"].supported is False
    assert baskets["top_5"].members == ()
    assert baskets["value_gte_100"].supported is False
    payload = baskets["top_5"].as_payload()
    assert payload["chaseCount"] == 0
    assert payload["unsupportedReason"]


# --- Property 8: missing data must not become zero -------------------------

def test_missing_inputs_return_none_and_never_zero():
    assert ce(None, 10.0, 0.01) is None
    assert ce(100.0, None, 0.01) is None
    assert ce(100.0, 10.0, None) is None
    assert ce(float("nan"), 10.0, 0.01) is None
    assert ce(100.0, 0.0, 0.01) is None


def test_unpriced_and_unreachable_cards_are_excluded_with_reasons():
    rows = [
        {"entity_id": 0, "card_variant_id": "v0", "price": 100.0, "pull_count": 5,
         "price_captured_at": "2026-08-28"},
        {"entity_id": 1, "card_variant_id": "v1", "price": 0.0, "pull_count": 5,
         "price_captured_at": "2026-08-28"},
        {"entity_id": 2, "card_variant_id": None, "price": 20.0, "pull_count": 5,
         "price_captured_at": "2026-08-28"},
        {"entity_id": 3, "card_variant_id": "v3", "price": 20.0, "pull_count": 0,
         "price_captured_at": "2026-08-28"},
        {"entity_id": 4, "card_variant_id": "v4", "price": 20.0, "pull_count": 5,
         "price_captured_at": "2026-08-01"},
    ]
    eligible, excluded = partition_universe(rows, market_date="2026-08-28")
    assert [c.entity_id for c in eligible] == [0]
    assert {row["reason"] for row in excluded} == {
        "non_positive_market_price",
        "missing_card_variant_identity",
        "unreachable_in_simulation",
        "price_basis_not_current_market_date",
    }
    assert all(row["reason"] for row in excluded)


# --- Basket probability identities -----------------------------------------

def test_hit_count_distribution_satisfies_the_complement_identity():
    counts = np.array([0, 0, 1, 1, 2, 3, 0, 1])
    block = hit_count_distribution(counts)
    assert block["identityHolds"]
    assert block["pAtLeastOne"] == pytest.approx(1.0 - block["pZero"])
    assert block["pExactlyOne"] + block["pTwoOrMore"] == pytest.approx(block["pAtLeastOne"])
    assert block["maxQualifyingInOnePack"] == 3


def test_basket_probability_is_not_the_sum_of_member_probabilities():
    """Guards the CORE PRINCIPLE against a future 'simplification'.

    Two members that always appear together have a union probability equal to
    either marginal, not their sum. A basket probability built by summing would
    report 0.4 here instead of 0.2.
    """
    counts = np.array([2] * 200 + [0] * 800)
    block = hit_count_distribution(counts)
    assert block["pAtLeastOne"] == pytest.approx(0.2)
    assert block["pTwoOrMore"] == pytest.approx(0.2)


# --- Horizon mathematics ----------------------------------------------------

@pytest.mark.parametrize("p", [0.001, 0.01, 0.05, 0.3])
@pytest.mark.parametrize("q", [0.50, 0.75, 0.80, 0.90])
def test_whole_pack_horizon_is_the_first_count_that_actually_reaches_the_target(p, q):
    n = whole_packs_for_horizon(p, q)
    assert 1.0 - (1.0 - p) ** n >= q
    assert n == 1 or 1.0 - (1.0 - p) ** (n - 1) < q


@pytest.mark.parametrize("p", [0.001, 0.05, 0.3])
def test_horizons_are_monotonic_in_the_target(p):
    packs = [packs_for_horizon(p, q) for q in (0.50, 0.75, 0.80, 0.90)]
    assert packs == sorted(packs)


def test_fractional_and_whole_horizons_bracket_each_other():
    exact = packs_for_horizon(0.02, 0.5)
    whole = whole_packs_for_horizon(0.02, 0.5)
    assert whole >= math.floor(exact)
    assert whole - exact < 1.0


# --- Concentration ----------------------------------------------------------

def test_single_hero_chase_and_deep_chase_are_distinguishable():
    hero = concentration([1000.0, 5.0, 4.0, 3.0, 2.0, 1.0])
    deep = concentration([100.0] * 10)
    assert hero["top1Share"] > 0.9
    assert deep["top1Share"] == pytest.approx(0.1)
    assert hero["effectiveChaseCount"] < 2.0
    assert deep["effectiveChaseCount"] == pytest.approx(10.0)


def test_concentration_of_a_worthless_basket_is_undefined_not_zero():
    block = concentration([0.0, 0.0])
    assert block["top1Share"] is None
    assert block["effectiveChaseCount"] is None


# --- Monte Carlo error reporting -------------------------------------------

def test_standard_error_is_reported_and_shrinks_with_sample_size():
    small = binomial_standard_error(0.001, 10_000)
    large = binomial_standard_error(0.001, 1_000_000)
    assert small > large > 0
    assert binomial_standard_error(None, 1_000_000) is None


def test_a_rare_top1_basket_carries_a_material_relative_error():
    """Honesty check, not a pass/fail property of the metric.

    At p ~ 1/1500 and 1,000,000 packs the relative error on p_S is a few
    percent. The study must therefore report it rather than present Top-1
    rankings as exact.
    """
    p = 1.0 / 1500.0
    relative = binomial_standard_error(p, 1_000_000) / p
    assert 0.01 < relative < 0.10
