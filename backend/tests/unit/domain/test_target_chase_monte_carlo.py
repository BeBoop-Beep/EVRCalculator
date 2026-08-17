"""Monte Carlo agreement check for the analytical chase model.

TEST-ONLY. There is no production Monte Carlo path and there must not be one:
these numbers are exact under the model assumptions, so simulating in
production would buy sampling noise and minutes of runtime per set.

What this proves: the closed forms in ``target_chase_economics`` are what a
literal open-until-hit simulation of the SAME model produces. It proves nothing
about real collation, which the model does not claim to capture.
"""

import numpy as np
import pytest

from backend.domain.pokemon.target_chase_economics import (
    PackGroup,
    target_chase_for_product,
)

TRIALS = 50_000
SEED = 20260816

# A moderate rate keeps the journey short enough to simulate 50k times quickly
# while still exercising the multi-product path.
P_PER_PACK = 0.02
PACKS_PER_PRODUCT = 6
PRODUCT_PRICE = 25.0
EV_PER_PACK = 3.5
TARGET_PRICE = 40.0


def _simulate():
    """Literal open-until-hit journeys under the module's own assumptions.

    The whole product is opened every time, including the successful one -
    matching ``successfulProductFullyOpened``. Products are drawn i.i.d.
    """
    rng = np.random.default_rng(SEED)
    products_used = np.empty(TRIALS, dtype=np.int64)
    value_pulled = np.empty(TRIALS, dtype=np.float64)
    target_copies = np.empty(TRIALS, dtype=np.int64)

    for trial in range(TRIALS):
        products = 0
        copies = 0
        while True:
            products += 1
            hits = int(rng.binomial(PACKS_PER_PRODUCT, P_PER_PACK))
            copies += hits
            if hits > 0:
                break
        products_used[trial] = products
        target_copies[trial] = copies
        # Every pack opened contributes its expected value; the variance of the
        # per-pack value is irrelevant to the expectations under test.
        value_pulled[trial] = products * PACKS_PER_PRODUCT * EV_PER_PACK

    return products_used, value_pulled, target_copies


@pytest.fixture(scope="module")
def simulated():
    return _simulate()


@pytest.fixture(scope="module")
def analytical():
    return target_chase_for_product(
        product_price=PRODUCT_PRICE,
        pack_groups=[
            PackGroup(
                pack_count=PACKS_PER_PRODUCT,
                target_probability_per_pack=P_PER_PACK,
                expected_target_copies_per_pack=P_PER_PACK,
                expected_pack_value=EV_PER_PACK,
            )
        ],
        target_value_used_in_ev=TARGET_PRICE,
        current_target_market_price=TARGET_PRICE,
    )


def test_expected_products_matches_simulation(simulated, analytical):
    products_used, _, _ = simulated
    assert analytical["expectedProductsToHit"] == pytest.approx(
        products_used.mean(), rel=0.02
    )


def test_gross_spend_matches_simulation(simulated, analytical):
    products_used, _, _ = simulated
    assert analytical["grossSpend"] == pytest.approx(
        (products_used * PRODUCT_PRICE).mean(), rel=0.02
    )


def test_gross_pull_value_matches_simulation(simulated, analytical):
    _, value_pulled, _ = simulated
    assert analytical["grossPullValue"] == pytest.approx(value_pulled.mean(), rel=0.02)


def test_expected_target_copies_matches_simulation(simulated, analytical):
    _, _, target_copies = simulated
    assert analytical["expectedTargetCopies"] == pytest.approx(
        target_copies.mean(), rel=0.02
    )


def test_incidental_recovery_matches_simulation(simulated, analytical):
    _, value_pulled, _ = simulated
    # One retained copy is removed at the EV basis, regardless of how many
    # copies the stopping product happened to contain.
    expected = value_pulled.mean() - TARGET_PRICE
    assert analytical["incidentalRecovery"] == pytest.approx(expected, rel=0.02)


def test_rip_acquisition_cost_matches_simulation(simulated, analytical):
    products_used, value_pulled, _ = simulated
    expected = (products_used * PRODUCT_PRICE).mean() - (value_pulled.mean() - TARGET_PRICE)
    assert analytical["ripAcquisitionCost"] == pytest.approx(expected, rel=0.02)


def test_probability_thresholds_match_empirical_hit_frequency(simulated, analytical):
    """``ceil(log(1-q)/log(1-p))`` really is the q-th cumulative threshold."""
    products_used, _, _ = simulated
    for threshold in (0.50, 0.75, 0.90, 0.95):
        n = analytical[f"productsFor{int(threshold * 100)}PercentChance"]
        empirical = float((products_used <= n).mean())
        assert empirical >= threshold - 0.02
        # The ceiling means the threshold is met, not wildly overshot.
        assert empirical <= threshold + 0.08
