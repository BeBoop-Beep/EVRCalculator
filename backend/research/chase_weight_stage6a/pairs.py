"""Phases 7, 8, 9 and 10: the binding behavioral tests.

RESEARCH ONLY.

WHAT AN OVERRIDE IS, STATED SO IT CANNOT DRIFT
-----------------------------------------------
A tertiary pillar earns its place if it can settle CLOSE comparisons and rarely
overturns CLEAR ones. Both halves need a definition that does not move between
weight candidates:

    An OVERRIDE of a pair (a, b) at weight w is:
        CONTROL ranks a above b,
        the candidate at weight w ranks b above a.

    The pair's BAND is the absolute Financial RIP gap |F_a - F_b|, cut at
    pre-registered thresholds. Bands are reported side by side; the brief
    forbids collapsing them to one boundary before the data has been seen.

Only pairs where CONTROL and Financial AGREE on the ordering are counted in the
"clear Financial override" statistic. A pair where Collector Appeal has already
inverted the Financial ordering inside CONTROL is not a case of Chase
overturning a clearly superior financial profile - it is a case of Chase
disagreeing with Collector, and counting it as the former would inflate the
override rate with pairs Chase had nothing to do with.
"""

from __future__ import annotations

import itertools
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

#: Phase 7's pre-registered Financial-gap bands, in Financial RIP points.
GAP_BANDS: Tuple[Tuple[str, float, float], ...] = (
    ("<=2", 0.0, 2.0),
    ("2-5", 2.0, 5.0),
    ("5-10", 5.0, 10.0),
    ("10-15", 10.0, 15.0),
    ("15-20", 15.0, 20.0),
    (">20", 20.0, float("inf")),
)

#: Bands treated as CLOSE and as CLEAR in the headline statistics. Both are
#: reported per band as well, so a reader can move the line and re-read.
CLOSE_MAX = 2.0
CLEAR_MIN = 10.0


def band_of(gap: float) -> str:
    for label, low, high in GAP_BANDS:
        if low <= gap < high or (high == float("inf") and gap >= low):
            return label
    return GAP_BANDS[-1][0]


def pairwise_overrides(*, control: Sequence[float], candidate: Sequence[float],
                       financial: Sequence[float], labels: Sequence[str],
                       core_k: Sequence[int],
                       sets: Optional[Sequence[str]] = None,
                       tolerance: float = 1e-9) -> Dict[str, Any]:
    """Every ordered pair, classified by Financial gap and by what Chase did."""
    control = np.asarray([float(v) for v in control], dtype=np.float64)
    candidate = np.asarray([float(v) for v in candidate], dtype=np.float64)
    financial = np.asarray([float(v) for v in financial], dtype=np.float64)
    n = control.size

    per_band: Dict[str, Dict[str, Any]] = {
        label: {"pairs": 0, "overrides": 0, "financialAligned": 0,
                "financialAlignedOverrides": 0, "kGaps": [], "gapsOverturned": []}
        for label, _, _ in GAP_BANDS}
    examples: List[Dict[str, Any]] = []
    same_set_pairs = same_set_overrides = 0

    for i, j in itertools.combinations(range(n), 2):
        gap = abs(financial[i] - financial[j])
        band = per_band[band_of(gap)]
        band["pairs"] += 1

        control_order = control[i] - control[j]
        candidate_order = candidate[i] - candidate[j]
        if abs(control_order) <= tolerance:
            continue
        flipped = (control_order > 0) != (candidate_order > 0) and abs(candidate_order) > tolerance
        # Does the Financial ordering agree with CONTROL's? Only then can a flip
        # be described as Chase overturning a superior financial profile.
        financial_order = financial[i] - financial[j]
        aligned = (financial_order > 0) == (control_order > 0) and abs(financial_order) > tolerance
        if aligned:
            band["financialAligned"] += 1
        if sets is not None and sets[i] == sets[j]:
            same_set_pairs += 1
        if not flipped:
            continue
        band["overrides"] += 1
        band["kGaps"].append(abs(int(core_k[i]) - int(core_k[j])))
        if sets is not None and sets[i] == sets[j]:
            same_set_overrides += 1
        if aligned:
            band["financialAlignedOverrides"] += 1
            band["gapsOverturned"].append(gap)
            if gap >= CLEAR_MIN:
                loser, winner = (i, j) if control_order > 0 else (j, i)
                examples.append({
                    "winner": labels[winner], "loser": labels[loser],
                    "financialGapOverturned": gap,
                    "coreKWinner": int(core_k[winner]),
                    "coreKLoser": int(core_k[loser]),
                    "sameSet": sets is not None and sets[i] == sets[j],
                })

    for block in per_band.values():
        block["overrideRate"] = (block["overrides"] / block["pairs"]
                                 if block["pairs"] else None)
        block["financialAlignedOverrideRate"] = (
            block["financialAlignedOverrides"] / block["financialAligned"]
            if block["financialAligned"] else None)
        block["medianKGap"] = (float(np.median(block["kGaps"])) if block["kGaps"] else None)
        block["maxGapOverturned"] = (max(block["gapsOverturned"])
                                     if block["gapsOverturned"] else None)
        del block["kGaps"], block["gapsOverturned"]

    close = [b for label, b in per_band.items()
             if label in ("<=2",)]
    clear = [b for label, b in per_band.items()
             if label in ("10-15", "15-20", ">20")]

    def rate(blocks, key_num, key_den):
        num = sum(b[key_num] for b in blocks)
        den = sum(b[key_den] for b in blocks)
        return (num / den if den else None), num, den

    close_rate, close_num, close_den = rate(close, "overrides", "pairs")
    clear_rate, clear_num, clear_den = rate(
        clear, "financialAlignedOverrides", "financialAligned")
    examples.sort(key=lambda e: -e["financialGapOverturned"])
    return {
        "pairs": n * (n - 1) // 2,
        "perBand": per_band,
        "closeMax": CLOSE_MAX, "clearMin": CLEAR_MIN,
        "closeOverrideRate": close_rate,
        "closeOverrides": close_num, "closePairs": close_den,
        "clearOverrideRate": clear_rate,
        "clearOverrides": clear_num, "clearAlignedPairs": clear_den,
        "sameSetPairs": same_set_pairs, "sameSetOverrides": same_set_overrides,
        "worstOverrides": examples[:8],
    }


def within_set_winners(*, rows: Sequence[Mapping[str, Any]],
                       control: Sequence[float],
                       candidate: Sequence[float]) -> Dict[str, Any]:
    """Phase 9: which product wins its own set, and whether Chase changed it.

    The set is the comparison a buyer actually makes - "which Mega Evolution
    product should I open" - and Stage VI found it is the one comparison
    Collector Appeal cannot speak to at all, because it is set-level and
    therefore identical for every product in the set.
    """
    by_set: Dict[str, List[int]] = {}
    for index, row in enumerate(rows):
        by_set.setdefault(row["set"], []).append(index)

    changes: List[Dict[str, Any]] = []
    examined = 0
    for name, members in sorted(by_set.items()):
        if len(members) < 2:
            continue
        examined += 1
        base_winner = max(members, key=lambda i: control[i])
        new_winner = max(members, key=lambda i: candidate[i])
        if base_winner == new_winner:
            continue
        changes.append({
            "set": name,
            "controlWinner": rows[base_winner]["productName"],
            "candidateWinner": rows[new_winner]["productName"],
            "financialGap": float(rows[base_winner]["financialRip"]
                                  - rows[new_winner]["financialRip"]),
            "collectorGap": float(rows[base_winner]["collectorAppeal"]
                                  - rows[new_winner]["collectorAppeal"]),
            "coreKControl": int(rows[base_winner]["coreK"]),
            "coreKCandidate": int(rows[new_winner]["coreK"]),
            "controlScoreGap": float(control[base_winner] - control[new_winner]),
        })
    changes.sort(key=lambda c: -c["financialGap"])
    helpful = [c for c in changes if c["financialGap"] <= CLOSE_MAX]
    excessive = [c for c in changes if c["financialGap"] >= CLEAR_MIN]
    return {
        "setsExamined": examined,
        "winnerChanges": len(changes),
        "helpfulDifferentiation": len(helpful),
        "excessiveOverride": len(excessive),
        "changes": changes,
    }
