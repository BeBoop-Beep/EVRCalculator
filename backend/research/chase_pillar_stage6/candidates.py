"""Phases 11, 12 and 14: the Chase pillar candidate families and weight grids.

RESEARCH ONLY.

WHAT MAY AND MAY NOT BE COMBINED (Phase 12)
-------------------------------------------
Stage V-C already falsified three pairs as independent, and
:data:`FORBIDDEN_PAIRS` makes them unrepresentable rather than merely
discouraged. :func:`build_candidate` raises on any factor set containing one, so
a redundant pillar cannot reach the tournament by accident:

* Beat-the-Buy with Chase EV Return - rho = +1.00
* Median Chase Cost Gap with 50% Chase Spend - rho = +1.00
* Chase Depth with Core K - rho = +0.984

Chase Depth is excluded from the factor vocabulary entirely, per the Stage V-C
lock, and survives only as descriptive output elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

#: The only factors a Stage VI Chase pillar may be built from.
ALLOWED_FACTORS: Tuple[str, ...] = (
    "anyChasePerProduct",
    "chaseSpend50",
    "coreK",
    "chaseEvReturn",
)

#: Falsified in Stage V-C. Membership here is enforced, not advisory.
FORBIDDEN_PAIRS: Tuple[Tuple[str, str], ...] = (
    ("beatTheBuy", "chaseEvReturn"),
    ("medianCostGap", "chaseSpend50"),
    ("chaseDepth", "coreK"),
)

#: Rejected as a score input by Stage V-C; retained descriptively only.
REJECTED_FACTORS: Tuple[str, ...] = ("chaseDepth", "beatTheBuy", "medianCostGap")


@dataclass(frozen=True)
class ChaseCandidate:
    """One Chase pillar definition: which factors, at which internal weights."""

    key: str
    label: str
    factors: Tuple[str, ...]
    weights: Tuple[float, ...]
    rationale: str = ""

    def weight_map(self) -> Dict[str, float]:
        return dict(zip(self.factors, self.weights))

    def score(self, normalized: Mapping[str, Any]) -> Optional[float]:
        total = 0.0
        for factor, weight in zip(self.factors, self.weights):
            value = normalized.get(factor)
            if value is None:
                return None
            total += weight * float(value)
        return total


def validate_factors(factors: Sequence[str]) -> None:
    """Refuse a factor set Stage V-C already falsified."""
    chosen = set(factors)
    unknown = chosen - set(ALLOWED_FACTORS)
    if unknown:
        raise ValueError(
            "factors %s are not admissible Stage VI Chase inputs; %s were rejected "
            "by Stage V-C and the rest are not defined"
            % (sorted(unknown), sorted(chosen & set(REJECTED_FACTORS))))
    for left, right in FORBIDDEN_PAIRS:
        if left in chosen and right in chosen:
            raise ValueError(
                "%s and %s were falsified as an independent pair in Stage V-C and "
                "may not appear in one Chase pillar" % (left, right))


def build_candidate(key: str, label: str, factors: Sequence[str],
                    weights: Sequence[float], rationale: str = "") -> ChaseCandidate:
    validate_factors(factors)
    if len(factors) != len(weights):
        raise ValueError("each factor needs exactly one weight")
    total = sum(float(w) for w in weights)
    if abs(total - 1.0) > 1e-9:
        raise ValueError("internal Chase weights must sum to 1.0, got %.6f" % total)
    return ChaseCandidate(key=key, label=label, factors=tuple(factors),
                          weights=tuple(float(w) for w in weights), rationale=rationale)


#: Phase 14 grids. Deliberately coarse and pre-registered: the brief forbids
#: unconstrained optimization, and a fine grid searched for the best number is
#: unconstrained optimization wearing a grid's clothes.
TWO_FACTOR_GRID: Tuple[Tuple[float, float], ...] = (
    (0.70, 0.30), (0.60, 0.40), (0.50, 0.50), (0.40, 0.60), (0.30, 0.70),
)

THREE_FACTOR_GRID: Tuple[Tuple[float, float, float], ...] = (
    (0.50, 0.30, 0.20), (0.50, 0.25, 0.25), (0.40, 0.40, 0.20),
    (0.40, 0.30, 0.30), (1 / 3, 1 / 3, 1 / 3), (0.30, 0.40, 0.30),
)

#: Chase EV Return is held to a minority weight in every four-factor grid,
#: because it is the factor that overlaps Financial RIP and the four-factor
#: family exists mainly as a double-counting control.
FOUR_FACTOR_GRID: Tuple[Tuple[float, float, float, float], ...] = (
    (0.35, 0.30, 0.25, 0.10),
    (0.30, 0.30, 0.25, 0.15),
    (0.30, 0.25, 0.25, 0.20),
    (0.25, 0.25, 0.25, 0.25),
)


def candidate_families() -> Dict[str, Dict[str, Any]]:
    """Phase 11's nine families, each with its pre-registered grid."""
    return {
        "A": {"label": "Accessibility only", "factors": ("anyChasePerProduct",),
              "grid": ((1.0,),),
              "rationale": "the most orthogonal metric Stage V-C found, alone"},
        "B": {"label": "Cost-normalized accessibility only", "factors": ("chaseSpend50",),
              "grid": ((1.0,),),
              "rationale": "dollars to even odds, inverted so higher is better"},
        "C": {"label": "Structure only", "factors": ("coreK",), "grid": ((1.0,),),
              "rationale": "breadth of qualifying chases, saturating"},
        "D": {"label": "Economics only", "factors": ("chaseEvReturn",), "grid": ((1.0,),),
              "rationale": "intentional control: expected to overlap Financial RIP"},
        "E": {"label": "Accessibility + structure",
              "factors": ("anyChasePerProduct", "coreK"), "grid": TWO_FACTOR_GRID},
        "F": {"label": "Accessibility + cost",
              "factors": ("anyChasePerProduct", "chaseSpend50"), "grid": TWO_FACTOR_GRID},
        "G": {"label": "Structure + cost",
              "factors": ("coreK", "chaseSpend50"), "grid": TWO_FACTOR_GRID},
        "H": {"label": "Three-factor chase experience",
              "factors": ("anyChasePerProduct", "chaseSpend50", "coreK"),
              "grid": THREE_FACTOR_GRID},
        "I": {"label": "Full economic chase",
              "factors": ("anyChasePerProduct", "chaseSpend50", "coreK", "chaseEvReturn"),
              "grid": FOUR_FACTOR_GRID,
              "rationale": "double-counting control, EV Return minority-weighted"},
    }


def enumerate_candidates() -> List[ChaseCandidate]:
    """Every (family, weight point) pair the tournament will consider."""
    out: List[ChaseCandidate] = []
    for key, family in sorted(candidate_families().items()):
        for weights in family["grid"]:
            if len(weights) != len(family["factors"]):
                continue
            suffix = "-".join("%02d" % round(w * 100) for w in weights)
            out.append(build_candidate(
                key="%s_%s" % (key, suffix), label=family["label"],
                factors=family["factors"], weights=weights,
                rationale=family.get("rationale", "")))
    return out
