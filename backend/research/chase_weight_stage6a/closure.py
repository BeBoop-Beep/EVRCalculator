"""Stage VI-B: closure audit for the Chase weight recommendation.

RESEARCH ONLY. Nothing here is read by production.

WHY THIS MODULE EXISTS
----------------------
Stage VI-A recommended ``0.84F + 0.10C + 0.06S`` with ``S = 100K/(K+10)`` and
described ``0.87F + 0.10C + 0.03T`` with ``T = 200K/(K+10)`` as "equivalent".

That is wrong, and the error is not merely textual. Because ``T = 2S``:

    B = 0.87F + 0.10C + 0.03T = 0.87F + 0.10C + 0.06S
    A = 0.84F + 0.10C + 0.06S
    B - A = 0.03F

The two share a Chase contribution term but differ by three points of Financial
weight. Worse, every Stage VI-A table - the finalist tournament, the shock grid,
the temporal grid, and therefore the C1-C5 verdicts - was produced with
``TRANSFORM = approved_unclamped`` and ``financial = 0.90 - share``, i.e. with
**Candidate B**. Candidate A was evaluated exactly once, on the base cohort
only, with no shocks, no dates and no criteria applied.

So the recommended production candidate had never been run through the gate that
was used to select it. This module exists to do that directly, rather than to
infer it from B.

WHAT IS REUSED AND WHAT IS NEW
------------------------------
Nothing about the evaluation is reimplemented. ``pairs.pairwise_overrides``,
``attribution.attribute``, ``decisions.rank_influence`` and
``pairs.within_set_winners`` are the Stage VI-A functions, called unchanged, so
a difference in the result cannot come from a difference in the measuring
instrument. What is new is only that the transform and the three pillar weights
become explicit parameters of a :class:`Candidate` instead of a module-level
constant and an implicit ``0.90 - share``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from backend.research.chase_weight_stage6a import attribution, decisions, pairs, scale, weights

#: The +/-10% shocks Stage VI-A's C1 evaluated. Kept identical on purpose.
C1_SHOCK_KEYS = ("card+10%", "card-10%", "prod+10%", "prod-10%")

#: The full shock set Stage VI-A reported.
SHOCK_KEYS = ("card+5%", "card-5%", "card+10%", "card-10%", "card+20%", "card-20%",
              "prod+5%", "prod-5%", "prod+10%", "prod-10%", "prod+20%", "prod-20%")


@dataclass(frozen=True)
class Candidate:
    """One fully-specified Overall RIP candidate: three weights and a transform.

    Weights are given explicitly rather than derived as ``0.90 - chase``,
    because that derivation is exactly the step that made Stage VI-A's
    "equivalent" claim false. A candidate that does not sum to one is refused at
    construction.
    """

    key: str
    financial: float
    collector: float
    chase: float
    transform: Callable[[Any], float]
    transform_name: str
    note: str = ""

    def __post_init__(self) -> None:
        total = self.financial + self.collector + self.chase
        if abs(total - 1.0) > 1e-12:
            raise ValueError("%s weights sum to %.12f, not 1.0" % (self.key, total))

    @property
    def weight_set(self) -> Dict[str, float]:
        return {"financial_rip": self.financial, "collector_appeal": self.collector,
                "chase": self.chase}

    def chase_column(self, core_k: Sequence[Any]) -> List[float]:
        return [self.transform(k) for k in core_k]

    def score(self, *, financial: Sequence[float], collector: Sequence[float],
              core_k: Sequence[Any]) -> List[Optional[float]]:
        chase = self.chase_column(core_k)
        return [weights.blend(financial=financial[i], collector=collector[i],
                              chase=chase[i], weights=self.weight_set)
                for i in range(len(core_k))]

    @property
    def label(self) -> str:
        return "%.4g/%.4g/%.4g x %s" % (self.financial * 100, self.collector * 100,
                                        self.chase * 100, self.transform_name)


#: The production candidate Stage VI-A recommended in words.
CANDIDATE_A = Candidate(
    key="A", financial=0.84, collector=0.10, chase=0.06,
    transform=scale.rescaled_0_100, transform_name="100K/(K+10)",
    note="the Stage VI-A recommendation as written; never previously gated")

#: The candidate Stage VI-A actually measured and reported as the 0.03 row.
CANDIDATE_B = Candidate(
    key="B", financial=0.87, collector=0.10, chase=0.03,
    transform=scale.approved_unclamped, transform_name="200K/(K+10)",
    note="what every Stage VI-A table, shock and date grid actually evaluated")

#: The B-scale weight whose FINANCIAL coefficient matches A. Present so the
#: 0.03F difference can be attributed to the coefficient rather than the scale.
CANDIDATE_A_PRIME = Candidate(
    key="A'", financial=0.84, collector=0.10, chase=0.06,
    transform=scale.approved_unclamped, transform_name="200K/(K+10)",
    note="A's weights on B's scale - twice A's Chase strength; diagnostic only")


def analytic_difference(*, financial: Sequence[float], left: Candidate,
                        right: Candidate) -> Dict[str, Any]:
    """The closed-form score difference between two candidates.

    Only defined when the two agree on Collector weight and on the effective
    Chase term; otherwise the difference is not a single multiple of ``F`` and
    the caller is told so rather than handed a misleading scalar.
    """
    left_chase_strength = left.chase * (2.0 if left.transform is scale.approved_unclamped else 1.0)
    right_chase_strength = right.chase * (2.0 if right.transform is scale.approved_unclamped else 1.0)
    same_chase = abs(left_chase_strength - right_chase_strength) < 1e-12
    same_collector = abs(left.collector - right.collector) < 1e-12
    if not (same_chase and same_collector):
        return {"closedForm": False,
                "reason": "candidates differ in Chase strength or Collector weight"}
    coefficient = right.financial - left.financial
    return {
        "closedForm": True,
        "expression": "%s - %s = %+.12g * F" % (right.key, left.key, coefficient),
        "financialCoefficient": coefficient,
        "predicted": [coefficient * float(f) for f in financial],
    }


def evaluate(candidate: Candidate, *, rows: Sequence[Mapping[str, Any]],
             control: Sequence[float],
             positions: Optional[Sequence[int]] = None,
             core_k: Optional[Mapping[int, int]] = None) -> Dict[str, Any]:
    """Every Stage VI-A diagnostic, for one candidate, over one scenario.

    ``core_k`` lets a shock or dated scenario supply its own Core K per row
    position while the pillar scores stay fixed, which is exactly how Stage VI-A
    built its shock and temporal grids.
    """
    if positions is None:
        positions = list(range(len(rows)))
    financial = [float(rows[p]["financialRip"]) for p in positions]
    collector = [float(rows[p]["collectorAppeal"]) for p in positions]
    ks = [int(core_k[p]) if core_k is not None else int(rows[p]["coreK"])
          for p in positions]
    labels = [rows[p]["productName"] for p in positions]
    sets = [rows[p]["set"] for p in positions]
    base = [float(control[p]) for p in positions]

    chase = candidate.chase_column(ks)
    scores = [weights.blend(financial=financial[i], collector=collector[i],
                            chase=chase[i], weights=candidate.weight_set)
              for i in range(len(positions))]

    override = pairs.pairwise_overrides(
        control=base, candidate=scores, financial=financial, labels=labels,
        core_k=ks, sets=sets)
    att = attribution.attribute(
        {"financial_rip": financial, "collector_appeal": collector, "chase": chase},
        candidate.weight_set)
    influence = decisions.rank_influence(control=base, candidate=scores, labels=labels)
    winners = pairs.within_set_winners(
        rows=[rows[p] for p in positions], control=base, candidate=scores)
    worst = max((b["maxGapOverturned"] or 0.0) for b in override["perBand"].values())

    return {
        "candidate": candidate.key,
        "n": len(positions),
        "scores": scores,
        "chase": chase,
        "shapley": att["shares"]["shapley"],
        "leverage": att["chaseLeverage"]["shapley"],
        "closeOverrideRate": override["closeOverrideRate"],
        "clearOverrides": override["clearOverrides"],
        "maxGapOverturned": worst,
        "sameSetOverrides": override["sameSetOverrides"],
        "spearman": influence["spearman"],
        "kendallTau": influence["kendallTau"],
        "top5Turnover": influence["turnover"]["top5"]["turnover"],
        "top10Turnover": influence["turnover"]["top10"]["turnover"],
        "tierChanges": influence["tierChanges"],
        "medianMovement": influence["medianAbsoluteMovement"],
        "maxMovement": influence["maxMovement"],
        "winnerChanges": winners["winnerChanges"],
        "perBand": override["perBand"],
        "influence": influence,
        "winners": winners,
    }


def criteria(base: Mapping[str, Any],
             shocked: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Stage VI-A's five pre-registered gates, transcribed unchanged.

    The thresholds and the boolean expressions are copied from
    ``report_chase_weight_stage6a.phase19_finalists`` so that a Stage VI-B PASS
    means the same thing a Stage VI-A PASS meant. Margins are added, because a
    verdict without a margin cannot distinguish "comfortably" from "barely".
    """
    shocked = [s for s in shocked if s]
    worst_shock_gap = max([s["maxGapOverturned"] for s in shocked], default=0.0)
    c1 = (base["clearOverrides"] == 0
          and all(s["clearOverrides"] == 0 for s in shocked)
          and base["maxGapOverturned"] < 10.0
          and all(s["maxGapOverturned"] < 10.0 for s in shocked))
    c2 = (base["closeOverrideRate"] or 0.0) >= 0.10
    c3 = base["shapley"]["financial_rip"] > 0.80 and base["shapley"]["chase"] < 0.20
    c4 = (base["spearman"] or 0.0) >= 0.98 and base["top5Turnover"] <= 1
    c5 = base["sameSetOverrides"] > 0
    return {
        "C1": {"passed": c1, "threshold": "clear overrides == 0 and max gap < 10, "
                                          "on base and all +/-10% shocks",
               "observed": "clear=%d, maxGap base %.2f, worst shock %.2f"
                           % (base["clearOverrides"], base["maxGapOverturned"],
                              worst_shock_gap),
               "margin": 10.0 - max(base["maxGapOverturned"], worst_shock_gap)},
        "C2": {"passed": c2, "threshold": ">= 0.10 close-pair override rate",
               "observed": base["closeOverrideRate"],
               "margin": (base["closeOverrideRate"] or 0.0) - 0.10},
        "C3": {"passed": c3, "threshold": "financial share > 0.80 and chase < 0.20",
               "observed": "financial %.4f, chase %.4f"
                           % (base["shapley"]["financial_rip"], base["shapley"]["chase"]),
               "margin": min(base["shapley"]["financial_rip"] - 0.80,
                             0.20 - base["shapley"]["chase"])},
        "C4": {"passed": c4, "threshold": "spearman >= 0.98 and top5 turnover <= 1",
               "observed": "spearman %.4f, top5 turnover %d"
                           % (base["spearman"], base["top5Turnover"]),
               "margin": (base["spearman"] or 0.0) - 0.98},
        "C5": {"passed": c5, "threshold": "> 0 same-set pairwise reversals",
               "observed": base["sameSetOverrides"],
               "margin": float(base["sameSetOverrides"])},
        "allPassed": all((c1, c2, c3, c4, c5)),
        "flags": "".join("Y" if c else "n" for c in (c1, c2, c3, c4, c5)),
    }
