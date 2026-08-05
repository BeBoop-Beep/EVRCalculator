"""Desirable Outcome Frequency (F): how often a modeled pack delivers a desirable card.

THE ONE AUTHORITATIVE CALCULATION
---------------------------------
F is computed HERE and nowhere else. The Collector Appeal service, the ranking
layer, the public presenter and the frontend all consume this module's output;
none of them recompute it. A second implementation of a probability is a second
definition of it.

WHAT F IS
---------
    F = P(a modeled pack contains at least one card tied to an eligible
          desirable Pokemon subject)

WHAT F IS NOT
-------------
F is NOT a financial measurement and must never be described as one. In
particular it is not, and must not be labelled as:

    * a win, a profitable pack, a break-even pack, or a cost recovery
    * "Hit Rate" without a qualifier
    * "Win Frequency" / "Profit Frequency" / "Chance to Beat Cost"

The financial sibling metric is a different number with a different meaning:

    True Win Frequency        = P(simulated monetary pack value >= pack cost)
    Desirable Outcome Frequency = P(pack contains >= 1 desirable-subject card)

**A desirable outcome may still be a financial loss.** Pulling the Pikachu you
wanted out of a $6 pack is a desirable outcome whether the card is worth $40 or
$0.40. Conflating the two would let a collector read an appeal statistic as a
promise about money.

Nothing monetary is read here: no price, no EV, no pack cost, no set value, no
Financial RIP component. A test asserts that at the source level.

DESIRABILITY IS USED FOR ELIGIBILITY ONLY
-----------------------------------------
A subject's desirability decides WHETHER its cards count, through the existing
``desirable_subjects(...)`` threshold. Its MAGNITUDE is deliberately not
multiplied into F.

That is the no-double-counting boundary inside Collector Appeal itself: the
canonical formula is ``CA = D + 0.50 * (0.60F + 0.40P) * (1 - D)``, so
desirability magnitude already enters once, through D. Weighting F by
desirability as well would apply the same signal twice, and the second
application would be invisible in the formula.

SLOT-AWARE UNION, NOT A SUM
---------------------------
F reuses ``union_probability_from_cards``, which respects the pack's slot
structure: probabilities ADD inside a mutually exclusive slot and slot MISS
probabilities multiply across independent slots. Naively summing every card's
probability, or applying card-level independence to cards that share a slot,
would both overstate F - and the overstatement grows with set size, so it would
read as "bigger sets are more appealing".

MISSING DATA
------------
No usable pull data returns ``None`` with a reason, never 0.0. An F of 0.0 is a
claim - "this pack essentially never contains a desirable card" - and it is not
a claim an absent pull model entitles anyone to make.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Sequence

from backend.desirability.factorized_opening_appeal import (
    demand_shares,
    desirable_subjects,
)
from backend.desirability.opening_appeal import union_probability_from_cards

DESIRABLE_OUTCOME_FREQUENCY_VERSION = "desirable_outcome_frequency_v1_slot_aware_union"
DESIRABLE_OUTCOME_FREQUENCY_SOURCE = "modeled_pull_structure"

# ---------------------------------------------------------------------------
# Coverage policy
# ---------------------------------------------------------------------------
# F is a union over the desirable subjects that carry a MODELED card. When a
# large share of a set's desirable demand has no modeled printing, the union is
# taken over a fragment of the roster and understates the real frequency - so
# publishing it as if it described the whole set would be a coverage failure
# rendered as a measurement.
#
# The floor is deliberately permissive rather than strict. Dual-Path Depth, the
# metric F sits beside, already ships on the weaker rule "at least some covered
# demand", so requiring MORE of F than of P would newly disqualify sets that the
# previous Collector Appeal served - turning a refinement into a silent
# reduction of the published cohort. The floor exists to catch the genuinely
# unusable case, and the audit script reports how many sets sit near it.
#
# Versioned because moving it changes which sets have a Collector Appeal at all.
DESIRABLE_OUTCOME_FREQUENCY_COVERAGE_POLICY_VERSION = (
    "desirable_outcome_frequency_coverage_v1_min_quarter_demand"
)
MINIMUM_COVERED_DEMAND_SHARE = 0.25

REASON_NO_PULL_MODEL = "desirable_outcome_frequency_unavailable_no_pull_model"
REASON_NO_ELIGIBLE_CARD = "desirable_outcome_frequency_unavailable_no_eligible_card"
REASON_INSUFFICIENT_COVERAGE = "desirable_outcome_frequency_unavailable_insufficient_coverage"


def _as_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _usable_cards(subject: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    """Cards of one subject that carry a usable modeled pull probability."""
    usable: List[Mapping[str, Any]] = []
    for card in subject.get("cards") or []:
        probability = _as_float(card.get("pull_probability"))
        if probability is None or probability <= 0:
            continue
        usable.append(card)
    return usable


def _unavailable(reason: str, detail: str, **extra: Any) -> Dict[str, Any]:
    return {
        "rawValue": None,
        "displayPercent": None,
        "impliedOddsOneInN": None,
        "available": False,
        "status": "unavailable",
        "statusReason": reason,
        "statusDetail": detail,
        "version": DESIRABLE_OUTCOME_FREQUENCY_VERSION,
        "coveragePolicyVersion": DESIRABLE_OUTCOME_FREQUENCY_COVERAGE_POLICY_VERSION,
        "source": DESIRABLE_OUTCOME_FREQUENCY_SOURCE,
        "interpretation": None,
        **extra,
    }


def compute_desirable_outcome_frequency(
    subjects: Optional[Sequence[Mapping[str, Any]]],
    *,
    minimum_covered_demand_share: float = MINIMUM_COVERED_DEMAND_SHARE,
) -> Dict[str, Any]:
    """``F = P(at least one eligible desirable card in one modeled pack)``.

    ``subjects`` is the existing Collector Appeal subject index - the SAME
    structure Dual-Path Depth consumes - so eligibility, subject assembly and
    the hit-eligible universe are reused rather than redefined.

    A card is eligible only when it is already in the hit-eligible universe
    (guaranteed by the subject index), belongs to a subject the existing
    ``desirable_subjects`` policy includes, and carries a valid modeled pull
    probability and slot group.

    Only the existing POKEMON subject-desirability system is used. Trainer and
    artist desirability are explicitly deferred: this module never fabricates a
    trainer or artist subject, never substitutes one for a Pokemon, and never
    assigns zero desirability to a subject type the model does not yet support.
    Unsupported subject types are simply absent, and their absence is disclosed
    rather than scored.
    """
    if not subjects:
        return _unavailable(
            REASON_NO_PULL_MODEL,
            "No modeled subject index is available for this set, so no pack "
            "composition can be evaluated.",
            eligibleCardCount=0,
            eligibleSubjectCount=0,
            desirableSubjectCount=0,
            coveredDemandShare=None,
            slotGroupCount=0,
        )

    eligible_subjects = desirable_subjects(subjects)
    if not eligible_subjects:
        return _unavailable(
            REASON_NO_ELIGIBLE_CARD,
            "No subject in this set clears the desirable-subject threshold, so "
            "there is no desirable outcome to measure.",
            eligibleCardCount=0,
            eligibleSubjectCount=0,
            desirableSubjectCount=0,
            coveredDemandShare=None,
            slotGroupCount=0,
        )

    shares = demand_shares(eligible_subjects)
    eligible_cards: List[Mapping[str, Any]] = []
    covered_demand = 0.0
    modeled_subject_count = 0
    unmodeled_subject_count = 0
    slot_groups: set = set()
    detail: List[Dict[str, Any]] = []

    for row in eligible_subjects:
        usable = _usable_cards(row)
        share = shares.get(str(row.get("subject_key")))
        if not usable:
            # Disclosed, never counted as a zero-probability contribution.
            unmodeled_subject_count += 1
            continue
        modeled_subject_count += 1
        eligible_cards.extend(usable)
        if share is not None:
            covered_demand += share
        for card in usable:
            slot_groups.add(str(card.get("slot_group") or "__unknown__"))
        subject_probability = union_probability_from_cards(usable)
        detail.append(
            {
                "subjectName": row.get("subject_name"),
                "subjectKey": row.get("subject_key"),
                "demandShare": round(share, 6) if share is not None else None,
                "subjectProbability": (
                    round(subject_probability, 8) if subject_probability is not None else None
                ),
                "modeledCardCount": len(usable),
            }
        )

    coverage_common = {
        "eligibleCardCount": len(eligible_cards),
        "eligibleSubjectCount": modeled_subject_count,
        "desirableSubjectCount": len(eligible_subjects),
        "unmodeledDesirableSubjectCount": unmodeled_subject_count,
        "coveredDemandShare": round(covered_demand, 6) if covered_demand > 0 else 0.0,
        "slotGroupCount": len(slot_groups),
    }

    if not eligible_cards:
        return _unavailable(
            REASON_NO_ELIGIBLE_CARD,
            "This set's desirable subjects have no printing with a modeled pull "
            "probability, so the frequency cannot be computed.",
            **coverage_common,
        )

    if covered_demand < float(minimum_covered_demand_share):
        return _unavailable(
            REASON_INSUFFICIENT_COVERAGE,
            "Only "
            f"{covered_demand:.1%} of this set's desirable demand has a modeled "
            "printing, below the "
            f"{float(minimum_covered_demand_share):.0%} minimum. A union over that "
            "fragment would understate the real frequency while looking complete.",
            **coverage_common,
        )

    probability = union_probability_from_cards(eligible_cards)
    if probability is None:
        return _unavailable(
            REASON_NO_ELIGIBLE_CARD,
            "No eligible desirable card carried a usable modeled probability.",
            **coverage_common,
        )

    # Clamp is a numeric safety net only; the union is already bounded.
    value = _clamp(probability)
    implied_odds = (1.0 / value) if value > 0 else None

    return {
        "rawValue": round(value, 8),
        "displayPercent": round(value * 100.0, 2),
        # "approximately 1 in N", never a guarantee. Modeled odds describe a
        # distribution, not an entitlement.
        "impliedOddsOneInN": round(implied_odds, 2) if implied_odds is not None else None,
        "available": True,
        "status": "available",
        "statusReason": None,
        "statusDetail": None,
        "version": DESIRABLE_OUTCOME_FREQUENCY_VERSION,
        "coveragePolicyVersion": DESIRABLE_OUTCOME_FREQUENCY_COVERAGE_POLICY_VERSION,
        "minimumCoveredDemandShare": float(minimum_covered_demand_share),
        "source": DESIRABLE_OUTCOME_FREQUENCY_SOURCE,
        "formula": "P(union of eligible desirable cards), slot-aware",
        "topSubjects": sorted(
            detail,
            key=lambda item: -(item["demandShare"] or 0.0),
        )[:5],
        "interpretation": (
            f"About {value * 100.0:.0f}% of modeled packs contain at least one card "
            "tied to a currently desirable Pokemon subject. A desirable outcome can "
            "still be worth less than the pack price."
        ),
        "isFinancialMetric": False,
        "financialDistinction": (
            "This is not a financial win rate. True Win Frequency measures "
            "P(pack value >= pack cost); this measures how often the pack contains "
            "a card you want."
        ),
        **coverage_common,
    }
