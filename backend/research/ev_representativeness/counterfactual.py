"""Parts 18-19: ablation, winsorization and price-shock counterfactuals.

THE MECHANISM, AND WHY IT IS EXACT RATHER THAN ANOTHER SIMULATION
------------------------------------------------------------------
A Tier B run stores which sampling entities were drawn in each pack, not what
they were worth. So any counterfactual price vector re-values the SAME sampled
openings::

    X_scenario[p] = price_scenario[ entities_drawn_in_pack_p ].sum()

Two consequences, both important:

1. **It is exact.** Setting a rarity's contribution to zero, deleting the top
   card, or knocking 25% off the top five chases are all just edits to a
   1-D price vector. Nothing is approximated, and no scenario needs its own
   simulation run.

2. **It is perfectly paired.** Baseline and scenario share every random draw -
   common random numbers in their strongest form, since the paths are literally
   identical. The reported delta is therefore the pure effect of the price
   change, with ZERO resampling noise. Re-simulating each scenario instead would
   have buried a $0.05 ablation effect under roughly $0.10 of Monte Carlo error
   at n = 1,000,000 for the highest-variance sets in the cohort - the effect
   would have been unmeasurable precisely where it matters most.

WINSORIZATION IS THE ONE EXCEPTION
----------------------------------
Capping the top 1% of OUTCOMES is not a price edit - it is a transformation of
the outcome vector itself, and it applies equally to Tier A. It is included here
because it answers the same question as the ablations ("how much of the EV-P50
gap is genuinely extreme-tail driven?") and belongs in the same comparison table.

PRODUCTION PRICES ARE NEVER TOUCHED
-----------------------------------
Every function takes a price vector and returns a new one. Nothing writes back
to ``card_variant_price_observations``, to the run's frozen price snapshot, or to
any market table. These are arithmetic experiments on a copy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

import numpy as np

from .contribution import CardContribution
from .distribution import compute_baseline_distribution, rank_tail_count
from .recorder import PackDecomposition
from .version import (
    PRICE_SHOCK_FACTORS,
    PRICE_SHOCK_GROUP_DEPTHS,
    TOP_CARD_ABLATION_DEPTHS,
    WINSORIZATION_QUANTILES,
)

FAMILY_RARITY_ABLATION = "rarity_ablation"
FAMILY_TOP_CARD_ABLATION = "top_card_ablation"
FAMILY_WINSORIZATION = "winsorization"
FAMILY_PRICE_SHOCK = "price_shock"

BASELINE_KIND_PAIRED = "tier_b_paired"


@dataclass(frozen=True)
class ScenarioResult:
    """One counterfactual, measured against the Tier B baseline it is paired with."""

    scenario_key: str
    scenario_family: str
    scenario_params: Dict[str, Any]
    ev: float
    p50: float
    p95: float
    ev_typical_gap_absolute: float
    typical_capture: Optional[float]
    top1_outcome_ev_share: Optional[float]
    top5_outcome_ev_share: Optional[float]
    top10_outcome_ev_share: Optional[float]
    std_dev: float
    coefficient_of_variation: Optional[float]
    delta_vs_baseline: Dict[str, Any]
    baseline_kind: str = BASELINE_KIND_PAIRED

    def as_payload(self) -> Dict[str, Any]:
        return {
            "scenarioKey": self.scenario_key,
            "scenarioFamily": self.scenario_family,
            "scenarioParams": self.scenario_params,
            "ev": self.ev,
            "p50": self.p50,
            "p95": self.p95,
            "evTypicalGapAbsolute": self.ev_typical_gap_absolute,
            "typicalCapture": self.typical_capture,
            "top1OutcomeEvShare": self.top1_outcome_ev_share,
            "top5OutcomeEvShare": self.top5_outcome_ev_share,
            "top10OutcomeEvShare": self.top10_outcome_ev_share,
            "stdDev": self.std_dev,
            "coefficientOfVariation": self.coefficient_of_variation,
            "deltaVsBaseline": self.delta_vs_baseline,
            "baselineKind": self.baseline_kind,
        }


def _summarize(values: np.ndarray, *, pack_cost: Optional[float]) -> Dict[str, Any]:
    distribution = compute_baseline_distribution(values, pack_cost=pack_cost)
    return {
        "ev": distribution.ev,
        "p50": distribution.p50,
        "p95": distribution.percentiles[95],
        "gap": distribution.ev_typical_gap_absolute,
        "typical_capture": distribution.typical_capture,
        "std_dev": distribution.std_dev,
        "cv": distribution.coefficient_of_variation,
        "top1": distribution.tails[0.01].ev_share if 0.01 in distribution.tails else None,
        "top5": distribution.tails[0.05].ev_share if 0.05 in distribution.tails else None,
        "top10": distribution.tails[0.10].ev_share if 0.10 in distribution.tails else None,
    }


def _delta(scenario: Mapping[str, Any], baseline: Mapping[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in scenario.items():
        base = baseline.get(key)
        if value is None or base is None:
            out[key] = {"absolute": None, "relative": None}
            continue
        absolute = float(value) - float(base)
        relative = (absolute / float(base)) if float(base) != 0.0 else None
        out[key] = {"absolute": absolute, "relative": relative}
    return out


def _build_result(
    *,
    scenario_key: str,
    scenario_family: str,
    scenario_params: Dict[str, Any],
    values: np.ndarray,
    baseline: Mapping[str, Any],
    pack_cost: Optional[float],
) -> ScenarioResult:
    summary = _summarize(values, pack_cost=pack_cost)
    return ScenarioResult(
        scenario_key=scenario_key,
        scenario_family=scenario_family,
        scenario_params=scenario_params,
        ev=summary["ev"],
        p50=summary["p50"],
        p95=summary["p95"],
        ev_typical_gap_absolute=summary["gap"],
        typical_capture=summary["typical_capture"],
        top1_outcome_ev_share=summary["top1"],
        top5_outcome_ev_share=summary["top5"],
        top10_outcome_ev_share=summary["top10"],
        std_dev=summary["std_dev"],
        coefficient_of_variation=summary["cv"],
        delta_vs_baseline=_delta(summary, baseline),
    )


# ---------------------------------------------------------------------------
# Price-vector edits
# ---------------------------------------------------------------------------

def zero_rarity(prices: np.ndarray, rarity_keys: np.ndarray, rarity: str) -> np.ndarray:
    """Set every entity of one rarity class to zero value.

    "Ablation" here means removing the ECONOMIC contribution, not removing the
    card from the pack. The opener still pulls the same slot; it is simply worth
    nothing. That is the right counterfactual for "which rarity layers support
    the mean versus the tail": deleting the card from the pool instead would
    reshuffle every other slot's probability and confound the two effects.
    """
    target = str(rarity).strip().lower()
    edited = np.asarray(prices, dtype=np.float64).copy()
    mask = np.array([str(key).strip().lower() == target for key in rarity_keys], dtype=bool)
    edited[mask] = 0.0
    return edited


def zero_entities(prices: np.ndarray, entity_ids: Sequence[int]) -> np.ndarray:
    edited = np.asarray(prices, dtype=np.float64).copy()
    if len(entity_ids):
        edited[np.asarray(list(entity_ids), dtype=np.int64)] = 0.0
    return edited


def shock_entities(
    prices: np.ndarray, entity_ids: Sequence[int], factor: float
) -> np.ndarray:
    """Multiply selected entities by ``1 + factor`` (``factor`` negative = a fall)."""
    edited = np.asarray(prices, dtype=np.float64).copy()
    if len(entity_ids):
        edited[np.asarray(list(entity_ids), dtype=np.int64)] *= 1.0 + float(factor)
    return edited


def winsorize_upper(values: np.ndarray, quantile: float) -> np.ndarray:
    """Cap the top ``quantile`` of OUTCOMES at the highest value below that tail.

    Rank-based, using the same ``rank_tail_count`` rule as every other tail in
    this research, so "the top 1%" means the same 1% here as it does in the EV
    share table. A percentile-threshold mask would cap a different, tie-inflated
    set of observations and the two numbers would stop being comparable.

    THE CAP IS ``ordered[n - count - 1]``, NOT ``ordered[n - count]``. The latter
    is the tail's own minimum - capping there leaves every tail observation at or
    above the cap and, for a one-element tail, changes nothing at all while
    appearing to have winsorized. The cap must be the largest value OUTSIDE the
    tail, which is what "replace the top 1% with the biggest ordinary outcome"
    means.
    """
    array = np.asarray(values, dtype=np.float64)
    n = int(array.size)
    count = rank_tail_count(n, float(quantile))
    ordered = np.sort(array)
    # count == n only for quantile == 1.0, where there is no "outside" left.
    cap = float(ordered[max(0, n - count - 1)])
    return np.minimum(array, cap)


# ---------------------------------------------------------------------------
# Scenario sweep
# ---------------------------------------------------------------------------

def build_counterfactuals(
    decomposition: PackDecomposition,
    contributions: Sequence[CardContribution],
    *,
    baseline_values: np.ndarray,
    pack_cost: Optional[float],
    rarity_ablation_keys: Optional[Sequence[str]] = None,
    top_card_depths: Sequence[int] = TOP_CARD_ABLATION_DEPTHS,
    winsor_quantiles: Sequence[float] = WINSORIZATION_QUANTILES,
    shock_factors: Sequence[float] = PRICE_SHOCK_FACTORS,
    shock_depths: Sequence[int] = PRICE_SHOCK_GROUP_DEPTHS,
    min_rarity_ev_share: float = 0.005,
) -> List[ScenarioResult]:
    """Run the full Part 18 + 19 sweep off one recorded Tier B run.

    ``min_rarity_ev_share`` skips rarity classes contributing under half a
    percent of EV. Ablating them produces a delta indistinguishable from zero and
    would pad the results table with rows that say nothing; the classes that are
    skipped are still visible in the Part 8 rarity contribution table, so nothing
    is hidden by the filter.
    """
    baseline_prices = decomposition.price_vector()
    rarity_keys = decomposition.rarity_keys()
    baseline_summary = _summarize(baseline_values, pack_cost=pack_cost)
    results: List[ScenarioResult] = []

    # -- Part 18: rarity ablation ------------------------------------------
    if rarity_ablation_keys is None:
        by_rarity: Dict[str, float] = {}
        for item in contributions:
            by_rarity[item.rarity_key] = by_rarity.get(item.rarity_key, 0.0) + item.ev_contribution_per_pack
        total = sum(by_rarity.values())
        rarity_ablation_keys = [
            key
            for key, value in sorted(by_rarity.items(), key=lambda kv: -kv[1])
            if total > 0.0 and (value / total) >= min_rarity_ev_share
        ]

    for rarity in rarity_ablation_keys:
        prices = zero_rarity(baseline_prices, rarity_keys, rarity)
        values = decomposition.pack_values(prices)
        results.append(
            _build_result(
                scenario_key=f"rarity_ablation:{rarity}",
                scenario_family=FAMILY_RARITY_ABLATION,
                scenario_params={"rarityKey": rarity},
                values=values,
                baseline=baseline_summary,
                pack_cost=pack_cost,
            )
        )

    # -- Part 18: top-card ablation ----------------------------------------
    ranked = sorted(contributions, key=lambda item: item.ev_rank)
    for depth in top_card_depths:
        selected = ranked[:depth]
        prices = zero_entities(baseline_prices, [item.entity_id for item in selected])
        values = decomposition.pack_values(prices)
        results.append(
            _build_result(
                scenario_key=f"top_card_ablation:{depth}",
                scenario_family=FAMILY_TOP_CARD_ABLATION,
                scenario_params={
                    "depth": depth,
                    "cards": [
                        {
                            "cardName": item.card_name,
                            "cardNumber": item.card_number,
                            "rarityKey": item.rarity_key,
                            "priceUsed": item.price_used,
                            "evShare": item.ev_share,
                        }
                        for item in selected
                    ],
                },
                values=values,
                baseline=baseline_summary,
                pack_cost=pack_cost,
            )
        )

    # -- Part 18: tail winsorization ---------------------------------------
    for quantile in winsor_quantiles:
        values = winsorize_upper(baseline_values, quantile)
        results.append(
            _build_result(
                scenario_key=f"winsorize_top:{quantile:.4f}",
                scenario_family=FAMILY_WINSORIZATION,
                scenario_params={"quantile": float(quantile)},
                values=values,
                baseline=baseline_summary,
                pack_cost=pack_cost,
            )
        )

    # -- Part 19: chase price shocks ---------------------------------------
    for depth in shock_depths:
        selected = [item.entity_id for item in ranked[:depth]]
        for factor in shock_factors:
            prices = shock_entities(baseline_prices, selected, factor)
            values = decomposition.pack_values(prices)
            results.append(
                _build_result(
                    scenario_key=f"price_shock:top{depth}:{factor:+.2f}",
                    scenario_family=FAMILY_PRICE_SHOCK,
                    scenario_params={
                        "depth": depth,
                        "factor": float(factor),
                        "cards": [
                            {
                                "cardName": item.card_name,
                                "cardNumber": item.card_number,
                                "rarityKey": item.rarity_key,
                            }
                            for item in ranked[:depth]
                        ],
                    },
                    values=values,
                    baseline=baseline_summary,
                    pack_cost=pack_cost,
                )
            )

    return results


def chase_dependence_summary(results: Sequence[ScenarioResult]) -> Dict[str, Any]:
    """Part 19's headline: how much EV a -50% top-5 shock actually removes.

    Reported as the EV elasticity to a chase price move, which is the closest
    single number to "how dependent is this set's opening economy on a small
    number of expensive cards retaining their price".
    """
    lookup = {item.scenario_key: item for item in results}
    out: Dict[str, Any] = {}
    for depth in PRICE_SHOCK_GROUP_DEPTHS:
        for factor in PRICE_SHOCK_FACTORS:
            key = f"price_shock:top{depth}:{factor:+.2f}"
            result = lookup.get(key)
            if result is None:
                continue
            relative = result.delta_vs_baseline.get("ev", {}).get("relative")
            out[key] = {
                "evRelativeChange": relative,
                # Elasticity: fraction of EV lost per fraction of chase price lost.
                # 1.0 would mean the set's whole economy is those cards.
                "evElasticity": (relative / factor) if relative is not None and factor else None,
                "typicalCaptureAfter": result.typical_capture,
            }
    return out
