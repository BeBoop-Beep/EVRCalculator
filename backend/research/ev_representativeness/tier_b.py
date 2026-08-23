"""Tier B: the seeded, instrumented research re-simulation.

WHY THIS EXISTS AT ALL
----------------------
Parts 6, 7, 9, 10, 18 and 19 need per-card and per-pack detail that the
authoritative run does not record, and cannot be reconstructed from what it does
record:

  * ``simulation_input_cards.ev_contribution`` is the ANALYTIC model
    ``Price / Effective_Pull_Rate``. Measured on prismaticEvolutions it sums to
    $5.80/pack against the simulator's $8.53/pack - a 47% divergence. It is a
    different quantity, not a lossy view of the same one.
  * A closed form ``P(card) * price`` would be a SECOND model of the simulator,
    which is what the brief forbids and what the pack-state distribution, the
    without-replacement slot exclusion and the two special-pack entry paths would
    make wrong anyway.

So the simulator is asked directly, with a seed so the answer is reproducible.

WHAT IT COSTS, AND WHY IT IS OPT-IN
-----------------------------------
A faithful Tier B run re-executes the full 1,000,000-pack Python simulation loop
(~60-70 s per set before instrumentation). That is why it lives behind
``--with-research-resimulation`` and is never part of the daily path.

WHAT IT IS NOT ALLOWED TO CLAIM
-------------------------------
Tier B is an INDEPENDENT sample from the same model, so its mean is not the
published mean. Its output is gated by ``reconcile_tiers``: a run whose Tier B
distribution fails the z-test against its own Tier A artifact still gets its
card rows written for audit, but is marked
``card_attribution_authoritative = FALSE`` so nothing downstream reads it as this
run's decomposition.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence

import numpy as np

from .contribution import (
    collective_hit_probability_empirical,
    compute_card_concentration,
    compute_card_contributions,
    economic_hit_frequencies,
)
from .counterfactual import build_counterfactuals
from .finite_sample import research_seed
from .recorder import PackDecompositionRecorder
from .version import EV_REPRESENTATIVENESS_VERSION, TIER_B_PACK_COUNT, TIER_B_SOURCE

logger = logging.getLogger(__name__)

#: Rarity groups the collective-hit question is asked for (Part 9).
#: Keys are labels; members are matched against the simulator's own normalized
#: rarity keys, so nothing here hardcodes a rarity taxonomy - a set that has no
#: hyper rares simply reports that group as unreachable.
DEFAULT_RARITY_GROUPS: Dict[str, Sequence[str]] = {
    "illustration_rare": ("illustration rare",),
    "special_illustration_rare": ("special illustration rare",),
    "double_rare": ("double rare",),
    "ultra_rare": ("ultra rare",),
    "hyper_rare": ("hyper rare",),
    "ace_spec_rare": ("ace spec rare",),
    "any_premium": (
        "illustration rare",
        "special illustration rare",
        "ultra rare",
        "hyper rare",
        "double rare",
        "ace spec rare",
        "black white rare",
        "shiny rare",
        "shiny ultra rare",
    ),
    "any_top_tier": (
        "special illustration rare",
        "hyper rare",
        "ultra rare",
        "black white rare",
    ),
}


def run_tier_b(
    *,
    config: Any,
    calculation_input: Any,
    calculation_run_id: str,
    canonical_key: str,
    pack_cost: float,
    tier_a_outcomes: np.ndarray,
    pack_count: int = TIER_B_PACK_COUNT,
    rarity_groups: Mapping[str, Sequence[str]] = None,
    reconciler=None,
) -> Dict[str, Any]:
    """Re-simulate one set with instrumentation and derive everything Tier B owns.

    ``reconciler`` is injected rather than imported so this module stays free of
    a database-service dependency; the CLI supplies
    ``ev_representativeness_service.reconcile_tiers``.
    """
    from backend.simulations.monteCarloSimV2 import (
        make_simulate_pack_fn_v2,
        validate_pack_state_model,
    )
    from backend.simulations.utils.extractScarletAndVioletCardGroups import (
        extract_scarletandviolet_card_groups,
    )

    started = time.perf_counter()
    groups = dict(rarity_groups or DEFAULT_RARITY_GROUPS)

    # The extractor adds this identity to its private copy. Special-pack row
    # resolution, however, operates on the frame passed directly to the
    # simulator. Stamp the same stable identity there as well; otherwise those
    # rows fall back to reset DataFrame indices and can collide with unrelated
    # pool entities (most visibly on god packs).
    simulation_input = calculation_input.copy()
    if "__source_row_index__" not in simulation_input.columns:
        simulation_input["__source_row_index__"] = simulation_input.index
    card_groups = extract_scarletandviolet_card_groups(config, simulation_input)
    validate_pack_state_model(config, card_groups)

    # The seed is derived from the run identity, so the same authoritative run
    # re-simulates to the same Tier B vector forever - which is what makes an
    # ablation delta reproducible rather than merely repeatable-ish.
    seed = research_seed(
        [EV_REPRESENTATIVENESS_VERSION, TIER_B_SOURCE, calculation_run_id, canonical_key, pack_count]
    )
    rng = np.random.default_rng(seed)

    recorder = PackDecompositionRecorder(expected_packs=pack_count)
    rarity_pull_counts: MutableMapping[str, int] = defaultdict(int)
    rarity_value_totals: MutableMapping[str, float] = defaultdict(float)

    simulate_one_pack = make_simulate_pack_fn_v2(
        common_cards=card_groups["common"],
        uncommon_cards=card_groups["uncommon"],
        rare_cards=card_groups["rare"],
        hit_cards=card_groups["hit"],
        reverse_pool=card_groups["reverse"],
        slots_per_rarity=config.SLOTS_PER_RARITY,
        config=config,
        df=simulation_input,
        rarity_pull_counts=rarity_pull_counts,
        rarity_value_totals=rarity_value_totals,
        pack_logs=None,
        rng=rng,
        research_recorder=recorder,
    )

    values = np.empty(pack_count, dtype=np.float64)
    for index in range(pack_count):
        values[index] = float(simulate_one_pack())
    simulation_seconds = time.perf_counter() - started

    decomposition = recorder.finalize()

    # COMPLETENESS GATE. If the recorder missed a single draw, card EV shares
    # would be wrong with no other symptom, so this is checked before anything is
    # derived from the decomposition rather than after.
    rebuilt = decomposition.pack_values()
    max_error = float(np.max(np.abs(rebuilt - values))) if values.size else 0.0
    if max_error > 1e-6:
        mismatch = np.flatnonzero(np.abs(rebuilt - values) > 1e-6)
        first = int(mismatch[0])
        raise RuntimeError(
            f"{canonical_key}: recorded decomposition does not reproduce the simulated "
            f"pack values (max abs error {max_error:.9f}; mismatches={mismatch.size}; "
            f"first_pack={first}; simulated={values[first]:.9f}; "
            f"recorded={rebuilt[first]:.9f}; recorded_draws={decomposition.pack_lengths()[first]}); "
            "card attribution would be incomplete"
        )

    contributions = compute_card_contributions(decomposition)
    concentration = compute_card_concentration(contributions)

    reconciliation = (
        reconciler(tier_a=tier_a_outcomes, tier_b=values)
        if reconciler is not None
        else {"status": "not_evaluated", "passed": False, "quantiles": {}}
    )

    scenarios = build_counterfactuals(
        decomposition,
        contributions,
        baseline_values=values,
        pack_cost=pack_cost,
    )

    return {
        "source": TIER_B_SOURCE,
        "seed": seed,
        "pack_count": pack_count,
        "values": values,
        "decomposition": decomposition,
        "contributions": contributions,
        "concentration": concentration,
        "reconciliation": reconciliation,
        "scenarios": scenarios,
        "collective_hits": collective_hit_probability_empirical(decomposition, groups),
        "economic_hits": economic_hit_frequencies(
            decomposition, pack_cost=pack_cost
        ),
        "rarity_pull_counts": dict(rarity_pull_counts),
        "rarity_value_totals": dict(rarity_value_totals),
        "simulation_seconds": simulation_seconds,
        "total_seconds": time.perf_counter() - started,
        "decomposition_max_abs_error": max_error,
    }
