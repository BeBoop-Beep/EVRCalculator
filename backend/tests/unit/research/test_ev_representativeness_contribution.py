"""Part 34 fixtures for the Tier B contribution and counterfactual layers.

The two that matter most:

  * ``test_recorder_does_not_perturb_sampling`` - proves the instrumentation is
    observational. If it ever fails, every Tier B number in the research is
    describing a simulator that production does not run.
  * ``test_recorded_decomposition_reproduces_the_simulated_values`` - proves the
    recorder saw every draw. If a slot were missed, card EV shares would be
    silently wrong in a way no other check would catch.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.research.ev_representativeness.contribution import (
    collective_hit_probability_empirical,
    collective_hit_probability_from_state_model,
    compute_card_concentration,
    compute_card_contributions,
    economic_hit_frequencies,
    rarity_contributions_from_pull_summary,
)
from backend.research.ev_representativeness.counterfactual import (
    build_counterfactuals,
    shock_entities,
    winsorize_upper,
    zero_entities,
    zero_rarity,
)
from backend.research.ev_representativeness.recorder import PackDecompositionRecorder


# ---------------------------------------------------------------------------
# A hand-built decomposition with known answers
# ---------------------------------------------------------------------------

def _fixture_decomposition():
    """Four entities, six packs, contributions computable by hand.

        e0 "Bulk"    $1    drawn 6 times  -> 1.0 /pack
        e1 "Mid"     $10   drawn 3 times  -> 5.0 /pack
        e2 "Chase"   $300  drawn 1 time   -> 50.0 /pack
        e3 "Dead"    $0    drawn 2 times  -> 0.0 /pack

        total EV/pack = 56.0
    """
    recorder = PackDecompositionRecorder(expected_packs=6)
    ids = {
        "bulk": recorder.register_row(
            source_row_index=0, price_column="Price ($)", price=1.0,
            rarity_key="common", card_name="Bulk", card_number="001",
        ),
        "mid": recorder.register_row(
            source_row_index=1, price_column="Price ($)", price=10.0,
            rarity_key="double rare", card_name="Mid", card_number="002",
        ),
        "chase": recorder.register_row(
            source_row_index=2, price_column="Price ($)", price=300.0,
            rarity_key="special illustration rare", card_name="Chase", card_number="003",
        ),
        "dead": recorder.register_row(
            source_row_index=3, price_column="Price ($)", price=0.0,
            rarity_key="uncommon", card_name="Dead", card_number="004",
        ),
    }
    plan = [
        ["bulk", "dead"],
        ["bulk", "mid"],
        ["bulk", "mid"],
        ["bulk", "mid", "chase"],
        ["bulk", "dead"],
        ["bulk"],
    ]
    for pack in plan:
        recorder.open_pack()
        for name in pack:
            recorder.add(ids[name])
        recorder.close_pack()
    return recorder.finalize(), ids


def test_card_contributions_match_hand_computed_values():
    decomposition, ids = _fixture_decomposition()
    contributions = compute_card_contributions(decomposition)
    by_name = {item.card_name: item for item in contributions}

    assert by_name["Bulk"].expected_copies_per_pack == pytest.approx(1.0)
    assert by_name["Bulk"].ev_contribution_per_pack == pytest.approx(1.0)
    assert by_name["Mid"].expected_copies_per_pack == pytest.approx(0.5)
    assert by_name["Mid"].ev_contribution_per_pack == pytest.approx(5.0)
    assert by_name["Chase"].expected_copies_per_pack == pytest.approx(1 / 6)
    assert by_name["Chase"].ev_contribution_per_pack == pytest.approx(50.0)
    assert by_name["Dead"].ev_contribution_per_pack == pytest.approx(0.0)

    assert by_name["Chase"].ev_rank == 1
    assert by_name["Mid"].ev_rank == 2

    # The identity that gates every Tier B write.
    total = sum(item.ev_contribution_per_pack for item in contributions)
    assert total == pytest.approx(float(decomposition.pack_values().mean()))
    assert total == pytest.approx(56.0)


def test_card_concentration_matches_exact_shares():
    decomposition, _ = _fixture_decomposition()
    concentration = compute_card_concentration(compute_card_contributions(decomposition))

    assert concentration.top1_ev_share == pytest.approx(50.0 / 56.0)
    assert concentration.top5_ev_share == pytest.approx(1.0)   # only 4 cards exist
    assert concentration.top10_ev_share == pytest.approx(1.0)
    assert concentration.contributing_card_count == 3          # Dead contributes nothing

    expected_hhi = (50 / 56) ** 2 + (5 / 56) ** 2 + (1 / 56) ** 2 + 0.0
    assert concentration.hhi == pytest.approx(expected_hhi)
    assert concentration.effective_card_count == pytest.approx(1.0 / expected_hhi)


def test_hhi_recognises_a_perfectly_even_spread():
    """N equal contributors must give HHI = 1/N and effective count = N exactly."""
    recorder = PackDecompositionRecorder(expected_packs=4)
    ids = [
        recorder.register_row(
            source_row_index=i, price_column="Price ($)", price=10.0, rarity_key="rare",
            card_name=f"Card{i}",
        )
        for i in range(4)
    ]
    for entity in ids:
        recorder.open_pack()
        recorder.add(entity)
        recorder.close_pack()

    concentration = compute_card_concentration(
        compute_card_contributions(recorder.finalize())
    )
    assert concentration.hhi == pytest.approx(0.25)
    assert concentration.effective_card_count == pytest.approx(4.0)
    assert concentration.top1_ev_share == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# Parts 9 and 10
# ---------------------------------------------------------------------------

def test_collective_hit_probability_counts_packs_not_copies():
    """P(at least one) and expected copies are different numbers; both are reported."""
    decomposition, _ = _fixture_decomposition()
    result = collective_hit_probability_empirical(
        decomposition,
        {"sir": ["special illustration rare"], "premium": ["special illustration rare", "double rare"]},
    )
    groups = result["groups"]
    assert groups["sir"]["probabilityAtLeastOne"] == pytest.approx(1 / 6)
    # Three packs contain a double rare, one of which also has the SIR.
    assert groups["premium"]["probabilityAtLeastOne"] == pytest.approx(3 / 6)
    assert groups["premium"]["expectedCopiesPerPack"] == pytest.approx(4 / 6)
    assert groups["premium"]["expectedCopiesPerPack"] > groups["premium"]["probabilityAtLeastOne"]


def test_unreachable_rarity_group_is_flagged_not_silently_zero():
    decomposition, _ = _fixture_decomposition()
    result = collective_hit_probability_empirical(decomposition, {"hyper": ["hyper rare"]})
    assert result["groups"]["hyper"]["reachable"] is False
    assert result["groups"]["hyper"]["probabilityAtLeastOne"] == 0.0


def test_state_model_probability_is_a_lower_bound_on_the_empirical_one():
    """The model-derived figure omits special packs, so it must not exceed truth."""
    result = collective_hit_probability_from_state_model(
        state_probabilities={"baseline": 0.9, "sir_only": 0.1},
        coerced_state_outcomes={
            "baseline": {"rare": "rare", "reverse_1": "regular reverse", "reverse_2": "regular reverse"},
            "sir_only": {"rare": "rare", "reverse_1": "special illustration rare", "reverse_2": "regular reverse"},
        },
        rarity_groups={"sir": ["special illustration rare"]},
        normal_path_probability=0.98,
    )
    group = result["groups"]["sir"]
    assert group["probabilityAtLeastOneGivenNormalPack"] == pytest.approx(0.10)
    assert group["probabilityAtLeastOne"] == pytest.approx(0.098)
    assert result["isLowerBound"] is True


def test_economic_hit_frequency_uses_the_best_single_card_not_the_pack_total():
    """Four $3 commons in a $10 pack is not an economically meaningful hit."""
    recorder = PackDecompositionRecorder(expected_packs=2)
    small = recorder.register_row(
        source_row_index=0, price_column="Price ($)", price=3.0, rarity_key="common"
    )
    big = recorder.register_row(
        source_row_index=1, price_column="Price ($)", price=12.0, rarity_key="hyper rare"
    )
    recorder.open_pack()
    for _ in range(4):
        recorder.add(small)          # pack total 12.0, best single card 3.0
    recorder.close_pack()
    recorder.open_pack()
    recorder.add(big)                # pack total 12.0, best single card 12.0
    recorder.close_pack()

    result = economic_hit_frequencies(recorder.finalize(), pack_cost=10.0, cost_multiples=[1.0])
    assert result["thresholds"][0]["probability"] == pytest.approx(0.5)
    assert result["thresholds"][0]["packsWithHit"] == 1


def test_economic_hit_frequency_rejects_non_positive_cost():
    decomposition, _ = _fixture_decomposition()
    with pytest.raises(ValueError):
        economic_hit_frequencies(decomposition, pack_cost=0.0)


# ---------------------------------------------------------------------------
# Part 8 reuse
# ---------------------------------------------------------------------------

def test_rarity_contributions_reconcile_to_the_simulated_mean():
    rows = [
        {"rarity_bucket": "common", "pulled_count": 4_000_000, "total_sampled_value": 400_000.0},
        {"rarity_bucket": "special illustration rare", "pulled_count": 31_000, "total_sampled_value": 5_600_000.0},
    ]
    result = rarity_contributions_from_pull_summary(
        rows, packs_simulated=1_000_000, simulated_mean=6.0
    )
    assert result["totalEvPerPack"] == pytest.approx(6.0)
    assert result["reconciliationAbsolute"] == pytest.approx(0.0)

    sir = next(b for b in result["buckets"] if b["rarityKey"] == "special illustration rare")
    assert sir["expectedCopiesPerPack"] == pytest.approx(0.031)
    assert sir["evContributionPerPack"] == pytest.approx(5.6)
    assert sir["evShare"] == pytest.approx(5.6 / 6.0)
    assert sir["averageValueWhenHit"] == pytest.approx(5_600_000.0 / 31_000)
    # Ranked by contribution, so the tail-driving layer leads.
    assert result["buckets"][0]["rarityKey"] == "special illustration rare"


# ---------------------------------------------------------------------------
# Parts 18 and 19
# ---------------------------------------------------------------------------

def test_counterfactual_revaluation_is_exact_and_paired():
    decomposition, ids = _fixture_decomposition()
    baseline = decomposition.pack_values()
    prices = decomposition.price_vector()

    ablated = decomposition.pack_values(zero_entities(prices, [ids["chase"]]))
    # Exactly one pack contained the chase; every other pack is untouched.
    difference = baseline - ablated
    assert np.count_nonzero(difference) == 1
    assert difference.sum() == pytest.approx(300.0)
    assert ablated.mean() == pytest.approx(6.0)   # 56.0 - 50.0

    shocked = decomposition.pack_values(shock_entities(prices, [ids["chase"]], -0.50))
    assert shocked.mean() == pytest.approx(56.0 - 25.0)


def test_rarity_ablation_zeroes_only_that_class():
    decomposition, _ = _fixture_decomposition()
    prices = zero_rarity(
        decomposition.price_vector(), decomposition.rarity_keys(), "Special Illustration Rare"
    )
    # Matching is case-insensitive, so a differently-cased rarity still ablates.
    assert decomposition.pack_values(prices).mean() == pytest.approx(6.0)


def test_winsorization_caps_exactly_the_rank_based_top_share():
    values = np.arange(1.0, 101.0)            # 100 outcomes, mean 50.5
    capped = winsorize_upper(values, 0.01)    # rank rule -> exactly 1 observation
    assert capped.max() == pytest.approx(99.0)
    assert np.count_nonzero(capped != values) == 1
    assert capped.mean() == pytest.approx(50.5 - 1 / 100)


def test_counterfactual_sweep_reports_paired_deltas():
    decomposition, _ = _fixture_decomposition()
    contributions = compute_card_contributions(decomposition)
    results = build_counterfactuals(
        decomposition,
        contributions,
        baseline_values=decomposition.pack_values(),
        pack_cost=10.0,
        top_card_depths=[1],
        winsor_quantiles=[],
        shock_factors=[-0.50],
        shock_depths=[1],
    )
    by_key = {item.scenario_key: item for item in results}

    ablation = by_key["top_card_ablation:1"]
    assert ablation.ev == pytest.approx(6.0)
    assert ablation.delta_vs_baseline["ev"]["absolute"] == pytest.approx(-50.0)
    assert ablation.baseline_kind == "tier_b_paired"

    shock = by_key["price_shock:top1:-0.50"]
    assert shock.ev == pytest.approx(31.0)
    # Removing the chase must widen capture, since the median pack is unchanged.
    assert ablation.typical_capture > by_key["price_shock:top1:-0.50"].typical_capture


# ---------------------------------------------------------------------------
# The instrumentation guardrails
# ---------------------------------------------------------------------------

def _tiny_pool(names, prices, rarity, start_index):
    return pd.DataFrame(
        {
            "Card Name": names,
            "Card Number": [f"{start_index + i:03d}" for i in range(len(names))],
            "Rarity": [rarity] * len(names),
            "Price ($)": prices,
            "Reverse Variant Price ($)": [round(p * 0.5, 2) for p in prices],
            "__source_row_index__": list(range(start_index, start_index + len(names))),
        }
    )


class _ToyConfig:
    SET_NAME = "Recorder Guardrail Set"
    ERA = "scarlet and violet"
    USE_MONTE_CARLO_V2 = True
    SLOTS_PER_RARITY = {"common": 4, "uncommon": 3}
    GOD_PACK_CONFIG = {"enabled": False}
    DEMI_GOD_PACK_CONFIG = {"enabled": False}
    PACK_STATE_MODEL = {
        "state_probabilities": {"baseline": 0.7, "hit": 0.3},
        "state_outcomes": {
            "baseline": {"rare": "rare", "reverse_1": "regular reverse", "reverse_2": "regular reverse"},
            "hit": {"rare": "rare", "reverse_1": "double rare", "reverse_2": "regular reverse"},
        },
    }


def _build_pack_fn(recorder):
    from backend.simulations.monteCarloSimV2 import make_simulate_pack_fn_v2

    commons = _tiny_pool(["C1", "C2", "C3"], [0.05, 0.10, 0.15], "Common", 0)
    uncommons = _tiny_pool(["U1", "U2"], [0.20, 0.25], "Uncommon", 10)
    rares = _tiny_pool(["R1", "R2"], [0.50, 0.75], "Rare", 20)
    hits = _tiny_pool(["H1", "H2"], [40.0, 90.0], "Double Rare", 30)
    reverse = _tiny_pool(["C1", "C2"], [0.05, 0.10], "Common", 0)

    return make_simulate_pack_fn_v2(
        common_cards=commons,
        uncommon_cards=uncommons,
        rare_cards=rares,
        hit_cards=hits,
        reverse_pool=reverse,
        slots_per_rarity=_ToyConfig.SLOTS_PER_RARITY,
        config=_ToyConfig(),
        df=pd.concat([commons, uncommons, rares, hits], ignore_index=True),
        rarity_pull_counts=__import__("collections").defaultdict(int),
        rarity_value_totals=__import__("collections").defaultdict(float),
        rng=np.random.default_rng(20260822),
        research_recorder=recorder,
    )


def test_recorder_does_not_perturb_sampling():
    """Instrumented and uninstrumented runs must be BIT-IDENTICAL.

    Same seed, same draws, same values. If this ever fails, the recorder is
    consuming randomness or changing a sampling decision, and every Tier B
    number would be describing a different simulator from the one production
    runs.
    """
    plain = [float(_build_pack_fn(None)()) for _ in range(0)]  # build check
    baseline_fn = _build_pack_fn(None)
    baseline = [float(baseline_fn()) for _ in range(2_000)]

    recorder = PackDecompositionRecorder(expected_packs=2_000)
    recorded_fn = _build_pack_fn(recorder)
    recorded = [float(recorded_fn()) for _ in range(2_000)]

    assert baseline == recorded


def test_recorded_decomposition_reproduces_the_simulated_values():
    """Every draw must be captured - the totals must agree elementwise.

    This is what proves card-level EV shares are complete rather than merely
    plausible. A missed slot would leave the shares wrong with no other symptom.
    """
    recorder = PackDecompositionRecorder(expected_packs=2_000)
    pack_fn = _build_pack_fn(recorder)
    simulated = np.array([float(pack_fn()) for _ in range(2_000)])

    decomposition = recorder.finalize()
    assert decomposition.pack_count == 2_000
    np.testing.assert_allclose(decomposition.pack_values(), simulated, rtol=0, atol=1e-9)

    contributions = compute_card_contributions(decomposition)
    assert sum(c.ev_contribution_per_pack for c in contributions) == pytest.approx(
        simulated.mean(), rel=1e-12
    )


def test_reverse_and_normal_printings_are_distinct_entities():
    """The same card at two price columns must not be collapsed into one entity.

    C1 sells for $0.05 normally and $0.025 as a reverse; merging them would
    attribute reverse-slot money to the normal printing and corrupt both the
    per-card EV share and any price-shock counterfactual on that card.
    """
    recorder = PackDecompositionRecorder(expected_packs=8)
    pack_fn = _build_pack_fn(recorder)
    for _ in range(200):
        pack_fn()
    decomposition = recorder.finalize()

    columns = {(e.source_row_index, e.price_column) for e in decomposition.entities}
    assert (0, "Price ($)") in columns
    assert (0, "Reverse Variant Price ($)") in columns
