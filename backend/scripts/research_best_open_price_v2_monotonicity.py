"""Best-Open Price V2 - Bucket 1 monotonicity research auditor (READ ONLY).

This module answers one question with evidence instead of assumption: is the
Best-Open *winner predicate* monotone in acquisition price for a fixed physical
quantity ``q``, under the two active V2 authorities (``FINANCIAL_V4`` and
``OVERALL_V12``)?

Everything numeric here goes through the canonical scorer
(``PreparedCanonicalCandidate.score_candidate`` -> ``PreparedFinancialRipDistribution.score``
-> Financial V4 projection -> Overall V12) and the canonical comparators
(``PreparedCanonicalCandidate.compare``).  Nothing is reimplemented.  The only
new arithmetic is the *conservative upper bound* used by the branch-and-bound
replay, and that bound is verified against exhaustive real scores.

Two halves:

* pure analysis helpers (no I/O) that the regression tests import, and
* a real-data runner that sweeps every integer cent of the fixed-q intervals
  around the frozen Sep-14 thresholds.  It never writes to Supabase, never
  publishes a snapshot, and never moves a pointer.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.calculations.evr.best_open_price import (  # noqa: E402
    COMPARISON_AUTHORITY_FINANCIAL_V4,
    COMPARISON_AUTHORITY_OVERALL_V12,
    PreparedCanonicalCandidate,
    quantity_price_interval_cents,
)
from backend.calculations.evr.financial_rip_v4 import (  # noqa: E402
    project_financial_rip_v4_from_v3_payload,
)
from backend.desirability.weighted_rip import compute_overall_rip_v12  # noqa: E402

SOURCE_SNAPSHOT_ID = "0e65fb6d-ff33-4331-99d5-d6a214ecc712"
EXPECTED_AUTHORITY_FINGERPRINT = "faad453f7d29eff1831fb2e212a13dad7d9d553536dc283af90c9bfbd53e48b0"
FROZEN_CONTROL = Path("docs/research/financial_rip_v5_best_open_v2_control.json")
ADVERSARIAL_PRODUCTS = (
    "c29f8489-22db-4ad0-9022-c1a40e503f14",
    "dbfd9f2d-5509-45b2-a08f-ba5e09ad2ff4",
    "9f17422e-60e7-4487-a2bf-f11819a48f34",
    "2c4b1825-03d4-4bfa-9438-2878a3f05d58",
)
AXES = ("financial", "overall")
AUTHORITY_FOR_AXIS = {
    "financial": COMPARISON_AUTHORITY_FINANCIAL_V4,
    "overall": COMPARISON_AUTHORITY_OVERALL_V12,
}
# Non-Loss-Resilience Financial V4 components: each is provably non-increasing
# in cost (see the certification report, section 1A).
NON_LR_COMPONENTS = (
    "true_win_frequency",
    "typical_retention",
    "realistic_upside",
    "jackpot_upside",
    "base_economic_efficiency",
)
# Slack added to the Loss Resilience component bound (component points, 0-100
# scale).  The engine rounds raw inputs to 6-8 dp and component scores to 4 dp;
# 1e-3 dominates every one of those roundings.
LR_BOUND_SLACK_POINTS = 1e-3


# ---------------------------------------------------------------------------
# Row model
# ---------------------------------------------------------------------------

@dataclass
class SweepRow:
    price_cents: int
    quantity: int
    capital: float
    financial: Optional[float]
    overall: Optional[float]
    true_win: Optional[float]
    lr_score: Optional[float]
    avg_retention: Optional[float]
    soft_share: Optional[float]
    hard_loss: Optional[float]
    no_losing_runs: Optional[bool]
    win_financial: bool
    win_overall: bool
    mismatch: float

    def win(self, axis: str) -> bool:
        return self.win_financial if axis == "financial" else self.win_overall

    def score(self, axis: str) -> Optional[float]:
        return self.financial if axis == "financial" else self.overall


def benchmark_row(
    product_id: str,
    *,
    financial: Optional[float],
    overall: Optional[float],
    recover: Optional[float],
    capital: float,
    target: float,
) -> Dict[str, Any]:
    """A comparator row shaped exactly like ``_comparator_row`` output."""
    return {
        "sealedProductId": product_id,
        "financialRipV4Score": financial,
        "overallRipV12Score": overall,
        "overallRipV12Rankable": overall is not None,
        "chanceToRecoverCapital": recover,
        "actualCommittedCapital": capital,
        "targetBudget": target,
    }


def score_with_detail(candidate: PreparedCanonicalCandidate, price_cents: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Canonical score record plus the Loss-Resilience raw inputs at the same price.

    The record is the canonical ``score_candidate`` output.  The detail dict is
    obtained by running the identical ``distribution.score`` call (same capital
    expression) so LR raw inputs can be disclosed; the two Financial V4 scores
    are asserted equal so a divergence can never go unnoticed.
    """
    record = candidate.score_candidate(price_cents)
    unit_price = price_cents / 100.0
    capital = candidate.quantity * unit_price
    kwargs = {} if not candidate.min_simulation_count else {"min_simulation_count": candidate.min_simulation_count}
    v3 = candidate.distribution.score(capital, **kwargs)
    v4 = project_financial_rip_v4_from_v3_payload(v3)
    if v4.get("score") != record.get("financialRipV4Score"):
        raise AssertionError("detail re-score diverged from canonical score_candidate")
    components = v4.get("components") or {}
    lr = components.get("loss_resilience") or {}
    lr_raw = lr.get("raw") or {}
    detail = {
        "lrScore": lr.get("score"),
        "avgRetention": lr_raw.get("averageRetentionGivenLoss"),
        "softShare": lr_raw.get("softLossShareGivenLoss"),
        "hardLoss": lr_raw.get("hardLossProbability"),
        "noLosingRuns": lr_raw.get("noLosingRuns"),
        "components": {k: (components.get(k) or {}).get("score") for k in components},
    }
    return record, detail


def sweep_interval(
    candidate: PreparedCanonicalCandidate,
    low: int,
    high: int,
    *,
    financial_benchmark: Mapping[str, Any],
    overall_benchmark: Mapping[str, Any],
) -> List[SweepRow]:
    """Score EVERY integer cent in [low, high] (ascending) for one fixed q.

    The physical distribution behind ``candidate`` is prepared once by the
    caller; only the per-cent scorer runs here.
    """
    rows: List[SweepRow] = []
    for price in range(low, high + 1):
        record, detail = score_with_detail(candidate, price)
        win_fin = bool(candidate.compare(record, financial_benchmark, authority=COMPARISON_AUTHORITY_FINANCIAL_V4))
        win_ov = bool(candidate.compare(record, overall_benchmark, authority=COMPARISON_AUTHORITY_OVERALL_V12))
        rows.append(SweepRow(
            price_cents=price,
            quantity=candidate.quantity,
            capital=float(record["actualCommittedCapital"]),
            financial=record.get("financialRipV4Score"),
            overall=record.get("overallRipV12Score"),
            true_win=record.get("chanceToRecoverCapital"),
            lr_score=detail["lrScore"],
            avg_retention=detail["avgRetention"],
            soft_share=detail["softShare"],
            hard_loss=detail["hardLoss"],
            no_losing_runs=detail["noLosingRuns"],
            win_financial=win_fin,
            win_overall=win_ov,
            mismatch=abs(float(record["actualCommittedCapital"]) - float(record["targetBudget"])),
        ))
    return rows


# ---------------------------------------------------------------------------
# Pattern analysis (pure)
# ---------------------------------------------------------------------------

def run_pattern(flags: Sequence[bool]) -> str:
    """Collapse an ascending-price WIN/LOSS sequence, e.g. ``'W L W L'``."""
    out: List[str] = []
    for flag in flags:
        symbol = "W" if flag else "L"
        if not out or out[-1] != symbol:
            out.append(symbol)
    return " ".join(out)


def is_down_closed(flags: Sequence[bool]) -> bool:
    """True iff ascending flags look like ``W* L*`` (a win at price p implies a
    win at every lower price).  This is the exact property a binary search for
    the highest winning cent needs."""
    seen_loss = False
    for flag in flags:
        if not flag:
            seen_loss = True
        elif seen_loss:
            return False
    return True


def analyze_rows(rows: Sequence[SweepRow], axis: str) -> Dict[str, Any]:
    """Anomaly census for one axis over an ascending-price row sequence.

    Definitions (ascending price):
      * ``upwardScoreSteps``   - adjacent cents where the score INCREASES.
      * ``lossToWinTransitions`` - adjacent cents (L then W): the direction
        that breaks down-closure.  Any such transition means the winner set is
        not ``W* L*``.
      * ``winSegments``        - maximal W runs; >1 means separated ranges.
      * ``oneCentIslands``     - a W run of length 1 with an L on both sides.
      * ``plateaus``           - adjacent cents with an identical score.
      * ``winnerChangesWithUnchangedScore`` - identical Financial and Overall
        scores at adjacent cents but a different verdict (tie-break driven).
    """
    rows = sorted(rows, key=lambda row: row.price_cents)
    flags = [row.win(axis) for row in rows]
    scores = [row.score(axis) for row in rows]
    upward: List[Dict[str, Any]] = []
    plateaus = 0
    changes_unchanged = 0
    loss_to_win: List[Dict[str, Any]] = []
    boundary_upward = 0
    boundary_loss_to_win = 0
    within_upward = 0
    component_up = {"trueWin": 0, "avgRetention": 0, "softShare": 0, "lrScore": 0, "hardLossDecreases": 0}
    lr_up_net_up = 0
    for index in range(1, len(rows)):
        prev, cur = rows[index - 1], rows[index]
        if cur.price_cents != prev.price_cents + 1:
            # A scope gap (unswept quantity between two swept ones): adjacent-
            # cent counters must not compare cents that are not neighbours.
            continue
        boundary = prev.quantity != cur.quantity
        if not boundary:
            # Component census is a FIXED-q statement (a q change swaps the
            # whole physical distribution, so component moves are not comparable).
            for label, before, after in (
                ("trueWin", prev.true_win, cur.true_win),
                ("avgRetention", prev.avg_retention, cur.avg_retention),
                ("softShare", prev.soft_share, cur.soft_share),
                ("lrScore", prev.lr_score, cur.lr_score),
                # hard-loss probability is EXPECTED to rise with cost; count the
                # (unexpected) decreases instead by swapping the operands.
                ("hardLossDecreases", cur.hard_loss, prev.hard_loss),
            ):
                if before is not None and after is not None and after > before:
                    component_up[label] += 1
            if (prev.lr_score is not None and cur.lr_score is not None and cur.lr_score > prev.lr_score
                    and prev.financial is not None and cur.financial is not None
                    and cur.financial > prev.financial):
                lr_up_net_up += 1
        ps, cs = scores[index - 1], scores[index]
        if ps is not None and cs is not None:
            if cs > ps:
                upward.append({
                    "fromPriceCents": prev.price_cents, "toPriceCents": cur.price_cents,
                    "fromQuantity": prev.quantity, "toQuantity": cur.quantity,
                    "fromScore": ps, "toScore": cs, "quantityBoundary": boundary,
                    "fromWin": flags[index - 1], "toWin": flags[index],
                })
                if boundary:
                    boundary_upward += 1
                else:
                    within_upward += 1
            elif cs == ps:
                plateaus += 1
        if (not flags[index - 1]) and flags[index]:
            loss_to_win.append({
                "fromPriceCents": prev.price_cents, "toPriceCents": cur.price_cents,
                "fromQuantity": prev.quantity, "toQuantity": cur.quantity,
                "quantityBoundary": boundary,
            })
            if boundary:
                boundary_loss_to_win += 1
        same_scores = (prev.financial == cur.financial and prev.overall == cur.overall)
        if same_scores and flags[index - 1] != flags[index]:
            changes_unchanged += 1
    segments = 0
    islands: List[int] = []
    index = 0
    while index < len(flags):
        if flags[index]:
            start = index
            while index + 1 < len(flags) and flags[index + 1]:
                index += 1
            segments += 1
            if (index == start and start > 0 and index + 1 < len(flags)
                    and rows[start - 1].price_cents == rows[start].price_cents - 1
                    and rows[start + 1].price_cents == rows[start].price_cents + 1):
                islands.append(rows[start].price_cents)
        index += 1
    return {
        "cents": len(rows),
        "pattern": run_pattern(flags),
        "downClosed": is_down_closed(flags),
        "winCents": sum(flags),
        "winSegments": segments,
        "oneCentIslands": len(islands),
        "oneCentIslandPrices": islands[:10],
        "upwardScoreSteps": len(upward),
        "upwardScoreStepExamples": upward[:5],
        "lossToWinTransitions": len(loss_to_win),
        "lossToWinExamples": loss_to_win[:5],
        "plateauPairs": plateaus,
        "winnerChangesWithUnchangedScore": changes_unchanged,
        "quantityBoundaryUpwardSteps": boundary_upward,
        "quantityBoundaryLossToWin": boundary_loss_to_win,
        "withinQuantityUpwardSteps": within_upward,
        "withinQuantityComponentIncreases": component_up,
        "lossResilienceUpStepsThatRaiseFinancial": lr_up_net_up,
    }


def merge_analysis(parts: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    keys = ("cents", "winCents", "winSegments", "oneCentIslands", "upwardScoreSteps",
            "lossToWinTransitions", "plateauPairs", "winnerChangesWithUnchangedScore",
            "quantityBoundaryUpwardSteps", "quantityBoundaryLossToWin",
            "withinQuantityUpwardSteps", "lossResilienceUpStepsThatRaiseFinancial")
    total = {key: 0 for key in keys}
    total["withinQuantityComponentIncreases"] = {
        "trueWin": 0, "avgRetention": 0, "softShare": 0, "lrScore": 0, "hardLossDecreases": 0}
    not_down_closed = 0
    count = 0
    for part in parts:
        count += 1
        for key in keys:
            total[key] += int(part.get(key) or 0)
        for label, value in (part.get("withinQuantityComponentIncreases") or {}).items():
            total["withinQuantityComponentIncreases"][label] += int(value)
        if not part.get("downClosed", True):
            not_down_closed += 1
    total["sweeps"] = count
    total["sweepsNotDownClosed"] = not_down_closed
    return total


# ---------------------------------------------------------------------------
# Structural (event) diagnostics for the certification argument
# ---------------------------------------------------------------------------

def true_win_probability_at(candidate: PreparedCanonicalCandidate, price_cents: int) -> float:
    """Exact P(X >= C) at a cent, using the engine's own ``_count_below``."""
    dist = candidate.distribution
    capital = candidate.quantity * (price_cents / 100.0)
    return (dist.n - dist._count_below(capital)) / dist.n


def event_crossing_counts(candidate: PreparedCanonicalCandidate, low: int, high: int) -> np.ndarray:
    """For each adjacent cent pair (p, p+1) in [low, high], the number of
    outcomes x with C(p) <= x < C(p+1) (approximate ``searchsorted`` diagnostic).

    Zero means no outcome value is crossed, so Loss Resilience cannot jump
    upward on that step and every Financial V4 component is non-increasing.
    """
    dist = candidate.distribution
    prices = np.arange(low, high + 1)
    costs = candidate.quantity * (prices / 100.0)
    counts = np.searchsorted(dist.sorted_base_values, costs - dist.value_offset, side="left")
    return np.diff(counts)


# ---------------------------------------------------------------------------
# Conservative upper bound for branch-and-bound
# ---------------------------------------------------------------------------

def loss_resilience_upper_bound(candidate: PreparedCanonicalCandidate, low: int, high: int) -> float:
    """Sound upper bound on the Loss Resilience component score (0-100) over
    every cent in [low, high] at this q.

    Within a gap between consecutive outcome values (fixed losing count k), the
    average-retention term ``S_k / (k C)`` strictly decreases in C and the
    soft-share term ``(k - h(C)) / k`` cannot increase (h is non-decreasing), so
    the gap's maximum sits at its left end.  Only the left end of every gap that
    intersects the cost interval therefore needs evaluating; the bound below
    evaluates them all in one vectorised pass and adds a small rounding slack.
    """
    dist = candidate.distribution
    offset = dist.value_offset
    cost_lo = candidate.quantity * (low / 100.0)
    cost_hi = candidate.quantity * (high / 100.0)
    k_lo = dist._count_below(cost_lo)
    k_hi = dist._count_below(cost_hi)
    if k_lo == 0:
        return 100.0
    ks = np.arange(max(k_lo, 1), k_hi + 1)
    v_left = dist.sorted_base_values[ks - 1] + offset
    c_left = np.maximum(cost_lo, v_left)
    total = dist.prefix_base_sums[ks] + offset * ks
    avg_ub = np.minimum(1.0, total / (ks * c_left))
    # h(C) = #{x < C/2} is non-decreasing in C, so its value at c_left is a
    # lower bound; nudge the threshold down so searchsorted can only under-count.
    threshold = (0.5 * c_left - offset) * (1.0 - 1e-12) - 1e-12
    h_lb = np.searchsorted(dist.sorted_base_values, threshold, side="left")
    soft_ub = (ks - np.minimum(h_lb, ks)) / ks
    return float(np.max(100.0 * (0.7 * avg_ub + 0.3 * soft_ub))) + LR_BOUND_SLACK_POINTS


def interval_upper_bound(
    candidate: PreparedCanonicalCandidate,
    low: int,
    high: int,
    *,
    at_low_record: Optional[Tuple[Dict[str, Any], Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """Upper bounds on Financial V4 and Overall V12 over cents [low, high].

    Non-LR components are non-increasing in cost, so their values at ``low``
    bound them everywhere in the interval; Loss Resilience uses
    :func:`loss_resilience_upper_bound`.  Returns ``None`` when the canonical
    score at ``low`` is unavailable (the caller must not prune).
    """
    record, detail = at_low_record or score_with_detail(candidate, low)
    if record.get("financialRipV4Score") is None:
        return None
    weights = _financial_v4_weights()
    partial = 0.0
    for key in NON_LR_COMPONENTS:
        score = (detail["components"] or {}).get(key)
        if score is None:
            return None
        partial += float(score) * weights[key]
    lr_ub = loss_resilience_upper_bound(candidate, low, high)
    financial_ub = round(min(100.0, partial + weights["loss_resilience"] * lr_ub), 4)
    overall = compute_overall_rip_v12(
        financial_ub, candidate.chase_accessibility_raw, candidate.collector_appeal_score
    )
    return {
        "financialUb": financial_ub,
        "overallUb": overall.get("score"),
        "lrUb": lr_ub,
        "financialAtLow": record.get("financialRipV4Score"),
    }


def _financial_v4_weights() -> Dict[str, float]:
    from backend.calculations.evr.financial_rip_v4_config import FINANCIAL_RIP_V4_WEIGHTS
    return dict(FINANCIAL_RIP_V4_WEIGHTS)


def bound_prunes(
    candidate: PreparedCanonicalCandidate,
    bound: Mapping[str, Any],
    benchmark: Mapping[str, Any],
    axis: str,
) -> bool:
    """True only if EVERY cent under this bound is provably a LOSS.

    Financial: the canonical comparator applied to the upper-bound score.  The
    comparator is monotone in the score (score desc, then a fixed id), so a
    loss at the upper bound is a loss at every lower score.

    Overall: prune only on the first two lexicographic levels (Overall score,
    then Financial score) with STRICT inequality; ties are never pruned because
    chance-to-recover / capital-closeness / id then bind.
    """
    if axis == "financial":
        record = {
            "sealedProductId": candidate.product_id,
            "financialRipV4Score": bound["financialUb"],
        }
        return not candidate.compare(record, benchmark, authority=COMPARISON_AUTHORITY_FINANCIAL_V4)
    bench_overall = benchmark.get("overallRipV12Score")
    bench_fin = benchmark.get("financialRipV4Score")
    if bound.get("overallUb") is None or bench_overall is None or bench_fin is None:
        return False
    if bound["overallUb"] < bench_overall:
        return True
    return bool(bound["overallUb"] == bench_overall and bound["financialUb"] < bench_fin)


@dataclass
class BranchAndBoundResult:
    axis: str
    highest_winning_cent: Optional[int]
    bound_evaluations: int = 0
    leaf_scores: int = 0
    pruned_cents: int = 0
    pruned_nodes: int = 0
    false_prunes: int = 0
    bound_violations: int = 0
    cents_in_interval: int = 0


def branch_and_bound_highest_win(
    candidate: PreparedCanonicalCandidate,
    low: int,
    high: int,
    *,
    benchmark: Mapping[str, Any],
    axis: str,
    exhaustive_win: Optional[Mapping[int, bool]] = None,
    exhaustive_score: Optional[Mapping[int, Optional[float]]] = None,
    leaf_width: int = 4,
) -> BranchAndBoundResult:
    """Top-down branch-and-bound search for the highest winning cent in [low, high].

    Bound evaluations and leaf scorings are counted separately.  When the
    exhaustive sweep is supplied, every pruned node is checked to contain no
    winning cent (``false_prunes``) and every bound is checked to dominate the
    true Financial score over its interval (``bound_violations``).
    """
    result = BranchAndBoundResult(axis=axis, highest_winning_cent=None,
                                  cents_in_interval=max(0, high - low + 1))
    authority = AUTHORITY_FOR_AXIS[axis]

    def leaf(price: int) -> bool:
        record = candidate.score_candidate(price)
        result.leaf_scores += 1
        return bool(candidate.compare(record, benchmark, authority=authority))

    def visit(a: int, b: int) -> Optional[int]:
        if b - a + 1 <= leaf_width:
            for price in range(b, a - 1, -1):
                if leaf(price):
                    return price
            return None
        bound = interval_upper_bound(candidate, a, b)
        result.bound_evaluations += 1
        if bound is not None:
            if exhaustive_score is not None:
                true_max = max(
                    (exhaustive_score[p] for p in range(a, b + 1) if exhaustive_score.get(p) is not None),
                    default=None,
                )
                if true_max is not None and bound["financialUb"] < true_max:
                    result.bound_violations += 1
            if bound_prunes(candidate, bound, benchmark, axis):
                result.pruned_cents += b - a + 1
                result.pruned_nodes += 1
                if exhaustive_win is not None and any(exhaustive_win[p] for p in range(a, b + 1)):
                    result.false_prunes += 1
                return None
        mid = (a + b) // 2
        upper = visit(mid + 1, b)
        if upper is not None:
            return upper
        return visit(a, mid)

    if high >= low:
        # The exhaustive descending scan always scores the top cent first, so
        # probe it first here too; a win at the top costs exactly one score.
        if leaf(high):
            result.highest_winning_cent = high
        else:
            result.highest_winning_cent = visit(low, high - 1)
    return result


# ---------------------------------------------------------------------------
# Real-data runner
# ---------------------------------------------------------------------------

def _load_control(path: Path) -> Dict[str, Dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("sourceSnapshotId") != SOURCE_SNAPSHOT_ID:
        raise RuntimeError("frozen control artifact is not the Sep-14 snapshot")
    if payload.get("sourceAuthorityFingerprint") != EXPECTED_AUTHORITY_FINGERPRINT:
        raise RuntimeError("frozen control artifact authority fingerprint mismatch")
    return {str(row["sealedProductId"]): row for row in payload["products"]}


def scope_quantities(
    budget_cents: int,
    axis_scan: Mapping[str, Tuple[int, int]],
    *,
    extra: Sequence[int] = (),
    max_quantity: int = 4096,
) -> List[int]:
    """Fixed-q intervals to sweep.

    ``axis_scan[axis] = (first_q, threshold_q)`` is the exact set of quantities
    the exact descending search touches for that axis (leaders start at q=1,
    non-leaders at the current quantity).  The sweep covers that whole range
    plus one quantity beyond the threshold (the q -> q+1 reversal check), plus
    any explicit extras, deduped across the two authorities.
    """
    wanted = set(int(q) for q in extra)
    for _axis, (first_q, threshold_q) in axis_scan.items():
        wanted.update(range(int(first_q), int(threshold_q) + 2))
    valid = []
    for quantity in sorted(wanted):
        if quantity < 1 or quantity > max_quantity:
            continue
        low, high = quantity_price_interval_cents(budget_cents, quantity)
        if low <= high:
            valid.append(quantity)
    return valid


def q_level_summary(any_win_by_q: Mapping[int, bool]) -> Dict[str, Any]:
    """Quantity-level winnability pattern over the swept q range."""
    qs = sorted(any_win_by_q)
    flags = [any_win_by_q[q] for q in qs]
    first_win = next((q for q, f in zip(qs, flags) if f), None)
    holes = []
    if first_win is not None:
        holes = [q for q, f in zip(qs, flags) if q > first_win and not f]
    alternations = sum(1 for i in range(1, len(flags)) if flags[i] != flags[i - 1])
    return {
        "quantities": [qs[0], qs[-1]] if qs else None,
        "pattern": run_pattern(flags),
        "firstWinnableQuantity": first_win,
        "holesAfterFirstWinnable": holes[:20],
        "holeCount": len(holes),
        "alternations": alternations,
    }


def _compact_rows(rows: Sequence[SweepRow]) -> List[Tuple]:
    return [(r.price_cents, r.quantity, r.financial, r.overall, r.win_financial, r.win_overall) for r in rows]


def _row_brief(row: Optional[SweepRow]) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    return {"priceCents": row.price_cents, "quantity": row.quantity, "financial": row.financial,
            "overall": row.overall, "trueWin": row.true_win, "lrScore": row.lr_score,
            "avgRetention": row.avg_retention, "softShare": row.soft_share,
            "hardLoss": row.hard_loss, "noLosingRuns": row.no_losing_runs, "mismatch": row.mismatch,
            "winFinancial": row.win_financial, "winOverall": row.win_overall}


def run_real(
    client: Any,
    *,
    snapshot_id: str = SOURCE_SNAPSHOT_ID,
    expected_fingerprint: str = EXPECTED_AUTHORITY_FINGERPRINT,
    control_path: Path = FROZEN_CONTROL,
    product_ids: Optional[Sequence[str]] = None,
    extended_products: Sequence[str] = ADVERSARIAL_PRODUCTS,
    extended_window: int = 25,
    max_extended_quantities: int = 400,
    checkpoint_path: Optional[Path] = None,
    progress: bool = True,
) -> Dict[str, Any]:
    """Sweep the frozen Sep-14 authority.  READ ONLY."""
    from backend.calculations.evr.financial_rip_v3 import PreparedFinancialRipDistribution
    from backend.calculations.evr.sealed_product_distribution import build_single_q_parity_distributions
    from backend.db.services.best_open_price_authority import validate_source
    from backend.db.services.pack_outcome_artifact_service import load_pack_outcome_artifact
    from backend.scripts.build_budget_normalized_product_rankings import build_stage1_distributions_cached
    from backend.scripts.research_best_open_price_bucket0 import (
        _comparator_row, _competitor, _financial_competitor, _historical_authority,
        _load_exact_source_products, _load_source, _verify_v12_parity,
        validate_financial_only_rank_reconstructs, validate_rank_column_contiguous,
    )

    control = _load_control(control_path)
    snapshot, source_rows, all_rows = _load_source(client, snapshot_id)
    validate_source(snapshot)
    validate_rank_column_contiguous(source_rows, "budget_rank_v12")
    validate_rank_column_contiguous(source_rows, "financial_only_rank")
    validate_financial_only_rank_reconstructs(source_rows)
    _verify_v12_parity(all_rows, label="monotonicity audit whole source snapshot")
    authority = _historical_authority(snapshot, source_rows)
    if authority["fingerprint"] != expected_fingerprint:
        raise RuntimeError("source authority fingerprint mismatch")
    budget = float(snapshot["full_market_budget"])
    budget_cents = round(budget * 100)
    products = _load_exact_source_products(client, source_rows, str(snapshot["pinned_price_as_of"]))
    product_by_id = {str(p["sealed_product_id"]): p for p in products}
    ordered = sorted(source_rows, key=lambda r: int(r["budget_rank_v12"]))
    if product_ids is not None:
        wanted = set(str(p) for p in product_ids)
        ordered = [r for r in ordered if str(r["sealed_product_id"]) in wanted]

    done: Dict[str, Dict[str, Any]] = {}
    if checkpoint_path is not None and checkpoint_path.exists():
        for line in checkpoint_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                done[row["sealedProductId"]] = row

    per_product: List[Dict[str, Any]] = []
    started = time.perf_counter()
    for position, source in enumerate(ordered, start=1):
        pid = str(source["sealed_product_id"])
        if pid in done:
            per_product.append(done[pid])
            continue
        product = product_by_id[pid]
        frozen = control[pid]
        current_cents = int(round(float(source["product_market_price"]) * 100))
        q0 = budget_cents // current_cents
        rip_bench = _comparator_row(_competitor(source, source_rows), budget)
        fin_bench = _comparator_row(_financial_competitor(source, source_rows), budget)
        info: Dict[str, Dict[str, Any]] = {}
        for axis, price_key, q_key, rank in (
            ("overall", "ripBestOpenPriceCents", "ripThresholdQuantity", int(source["budget_rank_v12"])),
            ("financial", "financialBestOpenPriceCents", "financialThresholdQuantity", int(source["financial_only_rank"])),
        ):
            leader = rank == 1
            info[axis] = {"leader": leader, "thresholdCents": int(frozen[price_key]),
                          "thresholdQuantity": int(frozen[q_key]), "firstQuantity": 1 if leader else q0,
                          "bench": rip_bench if axis == "overall" else fin_bench}
        extra: List[int] = []
        if pid in extended_products:
            q_high = min(4096, max(i["thresholdQuantity"] for i in info.values()) + extended_window)
            q_low = max(1, q_high - max_extended_quantities + 1)
            extra = list(range(q_low, q_high + 1))
        quantities = scope_quantities(
            budget_cents, {a: (i["firstQuantity"], i["thresholdQuantity"]) for a, i in info.items()}, extra=extra,
        )

        run_id = str(product["calculation_run_id"])
        artifact = None
        for attempt in range(3):
            try:
                artifact = load_pack_outcome_artifact(client, run_id)
                break
            except Exception:  # bounded retry, then fail closed
                if attempt == 2:
                    raise
                time.sleep(attempt + 1)
        random_count = int(product.get("random_pack_count") or product["pack_count"])
        base = build_stage1_distributions_cached(artifact, random_count, run_id)

        per_q: List[Dict[str, Any]] = []
        merged_rows: List[SweepRow] = []
        construction_seconds = 0.0
        scoring_seconds = 0.0
        bnb: List[Dict[str, Any]] = []
        any_win: Dict[str, Dict[int, bool]] = {"financial": {}, "overall": {}}
        theorem = {"regionCents": 0, "regionUpwardSteps": 0, "nonRegionCents": 0,
                   "nonRegionUpwardSteps": 0, "eventFreePairs": 0, "crossingPairs": 0}
        for quantity in quantities:
            built_at = time.perf_counter()
            built = build_single_q_parity_distributions(
                base, quantities=[quantity], canonical_set_key=f"budget:{pid}", run_fingerprint=None,
            )
            values = built["distributions"].pop(quantity)
            prepared = PreparedFinancialRipDistribution.prepare(
                values, value_offset=float(product.get("guaranteed_component_market_value") or 0) * quantity,
            )
            candidate = PreparedCanonicalCandidate(
                pid, quantity, prepared, float(source["collector_appeal_score"]),
                float(authority["rawBySet"][str(product["set_id"])]), budget,
            )
            construction_seconds += time.perf_counter() - built_at
            low, high = quantity_price_interval_cents(budget_cents, quantity)
            swept_at = time.perf_counter()
            rows = sweep_interval(candidate, low, high, financial_benchmark=fin_bench, overall_benchmark=rip_bench)
            scoring_seconds += time.perf_counter() - swept_at
            merged_rows.extend(rows)
            for axis in AXES:
                any_win[axis][quantity] = any(r.win(axis) for r in rows)

            # Theorem-A region: P(X >= C) <= 1/2 (engine _count_below).
            crossing = event_crossing_counts(candidate, low, high)
            theorem["eventFreePairs"] += int(np.count_nonzero(crossing == 0))
            theorem["crossingPairs"] += int(np.count_nonzero(crossing > 0))
            for index, row in enumerate(rows):
                in_region = row.true_win is not None and row.true_win <= 0.5
                theorem["regionCents" if in_region else "nonRegionCents"] += 1
                if index:
                    prev = rows[index - 1]
                    # A step p -> p+1 belongs to the theorem region when
                    # P(X >= C) at the LOWER-cost cent p is already <= 1/2.
                    prev_region = prev.true_win is not None and prev.true_win <= 0.5
                    if (row.financial is not None and prev.financial is not None
                            and row.financial > prev.financial):
                        theorem["regionUpwardSteps" if prev_region else "nonRegionUpwardSteps"] += 1

            # Branch-and-bound replay over exactly the cents the exact
            # descending search would scan for this q and axis.
            score_map = {r.price_cents: r.financial for r in rows}
            for axis in AXES:
                meta = info[axis]
                if not (meta["firstQuantity"] <= quantity <= meta["thresholdQuantity"]):
                    continue
                if meta["leader"]:
                    lo_scan, hi_scan = max(low, current_cents + 1), high
                else:
                    lo_scan, hi_scan = low, min(high, current_cents - 1)
                if lo_scan > hi_scan:
                    continue
                win_map = {r.price_cents: r.win(axis) for r in rows}
                exhaustive_top = max((p for p in range(lo_scan, hi_scan + 1) if win_map[p]), default=None)
                replay = branch_and_bound_highest_win(
                    candidate, lo_scan, hi_scan, benchmark=meta["bench"], axis=axis,
                    exhaustive_win=win_map, exhaustive_score=score_map,
                )
                exhaustive_scans = (hi_scan - exhaustive_top + 1) if exhaustive_top is not None else (hi_scan - lo_scan + 1)
                scan_rows = rows[lo_scan - low: hi_scan - low + 1]
                bench_fin_score = meta["bench"].get("financialRipV4Score")
                bench_ov_score = meta["bench"].get("overallRipV12Score")
                if axis == "financial":
                    tie_band = sum(1 for r in scan_rows if r.financial == bench_fin_score)
                else:
                    tie_band = sum(1 for r in scan_rows
                                   if r.overall == bench_ov_score and r.financial == bench_fin_score)
                bnb.append({
                    "axis": axis, "quantity": quantity, "low": lo_scan, "high": hi_scan,
                    "pWinAtLowScan": scan_rows[0].true_win, "tieBandCents": tie_band,
                    "exhaustiveTop": exhaustive_top, "bnbTop": replay.highest_winning_cent,
                    "match": exhaustive_top == replay.highest_winning_cent,
                    "exhaustiveScans": exhaustive_scans,
                    "boundEvaluations": replay.bound_evaluations, "leafScores": replay.leaf_scores,
                    "prunedCents": replay.pruned_cents, "falsePrunes": replay.false_prunes,
                    "boundViolations": replay.bound_violations,
                })
            per_q.append({
                "quantity": quantity, "low": low, "high": high, "cents": len(rows),
                "financialWinCents": sum(r.win_financial for r in rows),
                "overallWinCents": sum(r.win_overall for r in rows),
                "pWinAtLow": rows[0].true_win, "pWinAtHigh": rows[-1].true_win,
            })
            del candidate, prepared, values, built

        merged_rows.sort(key=lambda r: r.price_cents)
        by_price = {r.price_cents: r for r in merged_rows}
        analysis = {axis: analyze_rows(merged_rows, axis) for axis in AXES}
        legal: Dict[str, Any] = {}
        for axis in AXES:
            meta = info[axis]
            if meta["leader"]:
                legal_rows = [r for r in merged_rows if r.price_cents >= current_cents]
            else:
                legal_rows = [r for r in merged_rows if r.price_cents <= current_cents]
            top = max((r.price_cents for r in legal_rows if r.win(axis)), default=None)
            bench = meta["bench"]
            legal[axis] = {
                "leader": meta["leader"], "frozenThresholdCents": meta["thresholdCents"],
                "frozenQuantity": meta["thresholdQuantity"], "sweepHighestLegalWin": top,
                "thresholdReproduced": top == meta["thresholdCents"],
                "legalAnalysis": analyze_rows(legal_rows, axis),
                "benchmarkFinancial": bench.get("financialRipV4Score"),
                "benchmarkOverall": bench.get("overallRipV12Score"),
                "benchmarkChanceToRecover": bench.get("chanceToRecoverCapital"),
                "benchmarkCapital": bench.get("actualCommittedCapital"),
                "atThreshold": _row_brief(by_price.get(meta["thresholdCents"])),
                "aboveThreshold": _row_brief(by_price.get(meta["thresholdCents"] + 1)),
            }
        diag = frozen.get("diagnostics") or {}
        product_row = {
            "sealedProductId": pid, "budgetRankV12": int(source["budget_rank_v12"]),
            "financialOnlyRank": int(source["financial_only_rank"]), "currentPriceCents": current_cents,
            "currentQuantity": q0,
            "benchmarks": {"overall": rip_bench.get("sealedProductId"), "financial": fin_bench.get("sealedProductId")},
            "quantityRange": [quantities[0], quantities[-1]] if quantities else None,
            "quantityCount": len(quantities), "cents": len(merged_rows),
            "perQuantity": per_q if pid in ADVERSARIAL_PRODUCTS else None,
            "analysis": analysis, "legal": legal, "theorem": theorem,
            "qLevel": {axis: q_level_summary(any_win[axis]) for axis in AXES},
            "branchAndBound": bnb,
            "frozenDiagnostics": {
                "ripComparatorEvaluations": diag.get("ripComparatorEvaluations"),
                "financialComparatorEvaluations": diag.get("financialComparatorEvaluations"),
                "uniqueQuantitiesConstructed": diag.get("uniqueQuantitiesConstructed"),
                "uniqueCandidatePricesScored": diag.get("uniqueCandidatePricesScored"),
            },
            "constructionSeconds": construction_seconds, "scoringSeconds": scoring_seconds,
            "compactRows": _compact_rows(merged_rows) if pid in ADVERSARIAL_PRODUCTS else None,
        }
        per_product.append(product_row)
        if checkpoint_path is not None:
            checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            with checkpoint_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(product_row, default=str) + "\n")
        if progress:
            print(f"[{position}/{len(ordered)}] {pid[:8]} q={len(quantities)} cents={len(merged_rows)} "
                  f"elapsed={time.perf_counter() - started:.0f}s", flush=True)
    return {
        "snapshotId": snapshot_id, "authorityFingerprint": authority["fingerprint"],
        "budgetCents": budget_cents, "productCount": len(per_product),
        "wallSeconds": time.perf_counter() - started, "products": per_product,
    }


def summarize(products: Sequence[Mapping[str, Any]], *, control_path: Path = FROZEN_CONTROL) -> Dict[str, Any]:
    """Compact machine-readable certificate from the raw per-product sweeps."""
    payload = json.loads(control_path.read_text(encoding="utf-8"))
    control_totals = {
        key: sum(float((row.get("diagnostics") or {}).get(key) or 0) for row in payload["products"])
        for key in ("uniqueCandidatePricesScored", "uniqueQuantitiesConstructed", "priceScoringSeconds",
                    "quantityConstructionSeconds", "comparatorSeconds", "naiveScoreCount")
    }
    out: Dict[str, Any] = {"productCount": len(products)}
    out["scope"] = {
        "products": len(products),
        "quantityIntervalsSwept": sum(int(p["quantityCount"]) for p in products),
        "centsScored": sum(int(p["cents"]) for p in products),
        "thresholdsReproduced": sum(
            1 for p in products for axis in AXES if p["legal"][axis]["thresholdReproduced"]),
        "thresholdsExpected": 2 * len(products),
        "leaderAxes": sum(1 for p in products for axis in AXES if p["legal"][axis]["leader"]),
    }
    out["thresholdMismatches"] = [
        {"sealedProductId": p["sealedProductId"], "axis": axis,
         "frozen": p["legal"][axis]["frozenThresholdCents"],
         "sweepHighestLegalWin": p["legal"][axis]["sweepHighestLegalWin"]}
        for p in products for axis in AXES if not p["legal"][axis]["thresholdReproduced"]
    ]
    anomalies: Dict[str, Any] = {}
    offenders: Dict[str, Any] = {}
    for scope_name, getter in (("allSweptCents", lambda p, a: p["analysis"][a]),
                               ("legalSearchDomain", lambda p, a: p["legal"][a]["legalAnalysis"])):
        anomalies[scope_name] = {}
        offenders[scope_name] = {}
        for axis in AXES:
            parts = [getter(p, axis) for p in products]
            merged = merge_analysis(parts)
            merged["productsWithMultipleWinSegments"] = sum(1 for part in parts if part["winSegments"] > 1)
            merged["productsWithUpwardScoreStep"] = sum(1 for part in parts if part["upwardScoreSteps"] > 0)
            anomalies[scope_name][axis] = merged
            offenders[scope_name][axis] = [
                {"sealedProductId": p["sealedProductId"], "pattern": getter(p, axis)["pattern"],
                 "winSegments": getter(p, axis)["winSegments"],
                 "oneCentIslandPrices": getter(p, axis)["oneCentIslandPrices"],
                 "lossToWinExamples": getter(p, axis)["lossToWinExamples"][:3],
                 "upwardScoreStepExamples": getter(p, axis)["upwardScoreStepExamples"][:2]}
                for p in products if not getter(p, axis)["downClosed"]
            ]
    out["anomalies"] = anomalies
    out["nonDownClosedProducts"] = offenders
    theorem_keys = ("regionCents", "regionUpwardSteps", "nonRegionCents", "nonRegionUpwardSteps",
                    "eventFreePairs", "crossingPairs")
    out["theoremA"] = {key: sum(int(p["theorem"][key]) for p in products) for key in theorem_keys}
    # Class A / B / C over exactly the cents the exact descending search scans.
    classes = {name: {"intervals": 0, "intervalCents": 0, "exhaustiveScans": 0, "bnbScores": 0,
                      "idealizedBinarySearchScores": 0, "prunedCents": 0}
               for name in ("A", "B", "C")}
    per_axis_scans = {"financial": 0, "overall": 0}
    totals = {"entries": 0, "mismatches": 0, "falsePrunes": 0, "boundViolations": 0,
              "boundEvaluations": 0, "leafScores": 0, "exhaustiveScans": 0, "prunedCents": 0,
              "tieBandCents": 0, "intervalsWithTieBand": 0}
    reconciliation = {"productsChecked": 0, "productsMatching": 0, "mismatches": []}
    for p in products:
        by_axis = {"financial": 0, "overall": 0}
        for entry in p["branchAndBound"]:
            totals["entries"] += 1
            totals["mismatches"] += 0 if entry["match"] else 1
            totals["falsePrunes"] += int(entry["falsePrunes"])
            totals["boundViolations"] += int(entry["boundViolations"])
            totals["boundEvaluations"] += int(entry["boundEvaluations"])
            totals["leafScores"] += int(entry["leafScores"])
            totals["exhaustiveScans"] += int(entry["exhaustiveScans"])
            totals["prunedCents"] += int(entry["prunedCents"])
            totals["tieBandCents"] += int(entry.get("tieBandCents") or 0)
            totals["intervalsWithTieBand"] += 1 if entry.get("tieBandCents") else 0
            by_axis[entry["axis"]] += int(entry["exhaustiveScans"])
            width = int(entry["high"]) - int(entry["low"]) + 1
            in_region = entry.get("pWinAtLowScan") is not None and entry["pWinAtLowScan"] <= 0.5
            tie = int(entry.get("tieBandCents") or 0)
            is_a = in_region and (entry["axis"] == "financial" or tie == 0)
            name = "A" if is_a else ("B" if entry["prunedCents"] > 0 else "C")
            bucket = classes[name]
            bucket["intervals"] += 1
            bucket["intervalCents"] += width
            bucket["exhaustiveScans"] += int(entry["exhaustiveScans"])
            bucket["bnbScores"] += int(entry["boundEvaluations"]) + int(entry["leafScores"])
            bucket["prunedCents"] += int(entry["prunedCents"])
            bucket["idealizedBinarySearchScores"] += min(
                int(entry["exhaustiveScans"]), math.ceil(math.log2(max(width, 1))) + 1)
        for axis in AXES:
            per_axis_scans[axis] += by_axis[axis]
        diag = p.get("frozenDiagnostics") or {}
        if diag.get("financialComparatorEvaluations") is not None:
            reconciliation["productsChecked"] += 1
            # +1 for the separately evaluated current-market price on each axis.
            ok = (by_axis["financial"] + 1 == int(diag["financialComparatorEvaluations"])
                  and by_axis["overall"] + 1 == int(diag["ripComparatorEvaluations"]))
            reconciliation["productsMatching"] += 1 if ok else 0
            if not ok:
                reconciliation["mismatches"].append({
                    "sealedProductId": p["sealedProductId"],
                    "sweepFinancial": by_axis["financial"] + 1,
                    "frozenFinancial": diag["financialComparatorEvaluations"],
                    "sweepOverall": by_axis["overall"] + 1, "frozenOverall": diag["ripComparatorEvaluations"]})
    out["branchAndBound"] = {**totals, "bnbScores": totals["boundEvaluations"] + totals["leafScores"]}
    out["classes"] = classes
    out["scanReconciliation"] = {**reconciliation, "mismatches": reconciliation["mismatches"][:10]}
    out["exhaustiveScansByAxis"] = per_axis_scans
    out["frozenControlTotals"] = control_totals
    price_seconds = control_totals["priceScoringSeconds"] + control_totals["comparatorSeconds"]
    build_seconds = control_totals["quantityConstructionSeconds"]
    share = price_seconds / (price_seconds + build_seconds) if build_seconds else None
    out["runtimeOpportunity"] = {
        "centScoringPlusComparatorSeconds": price_seconds,
        "quantityConstructionSeconds": build_seconds,
        "centScoringShareOfRuntime": share,
        "physicalQuantitiesConstructed": control_totals["uniqueQuantitiesConstructed"],
        "note": "cent pruning cannot remove a physical-q construction; only an interval-level bound that "
                "needs no distribution could, and none exists",
    }
    q_stats: Dict[str, Any] = {"axesWithExtendedWindow": 0, "axesWithHoles": 0, "examples": []}
    for p in products:
        for axis in AXES:
            summary = p["qLevel"][axis]
            first = summary.get("firstWinnableQuantity")
            hi = (summary.get("quantities") or [None, None])[1]
            if first is not None and hi is not None and hi - first >= 4:
                q_stats["axesWithExtendedWindow"] += 1
                if summary["holeCount"]:
                    q_stats["axesWithHoles"] += 1
                    if len(q_stats["examples"]) < 10:
                        q_stats["examples"].append({"sealedProductId": p["sealedProductId"], "axis": axis, **summary})
    out["qLevel"] = q_stats
    out["quantityBoundary"] = {axis: {
        "upwardScoreSteps": anomalies["allSweptCents"][axis]["quantityBoundaryUpwardSteps"],
        "lossToWin": anomalies["allSweptCents"][axis]["quantityBoundaryLossToWin"],
        "legalUpwardScoreSteps": anomalies["legalSearchDomain"][axis]["quantityBoundaryUpwardSteps"],
        "legalLossToWin": anomalies["legalSearchDomain"][axis]["quantityBoundaryLossToWin"],
    } for axis in AXES}
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("logs/best_open_price_v2_monotonicity_raw.json"))
    parser.add_argument("--checkpoint", type=Path, default=None)
    parser.add_argument("--product", action="append", default=None, help="restrict to product id(s)")
    parser.add_argument("--extended-window", type=int, default=25)
    parser.add_argument("--max-extended-quantities", type=int, default=400)
    parser.add_argument("--summarize", type=Path, nargs="+", default=None,
                        help="checkpoint .jsonl files to merge into a compact summary (no database access)")
    parser.add_argument("--summary-output", type=Path,
                        default=Path("docs/research/best_open_price_v2_monotonicity_certification.json"))
    parser.add_argument("--extended-sample", type=int, default=10,
                        help="also extend the q window past the threshold for N evenly spaced non-adversarial products")
    args = parser.parse_args(argv)
    if args.summarize:
        rows = []
        for path in args.summarize:
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rows.append(json.loads(line))
        summary = summarize(rows)
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {args.summary_output}")
        return 0
    from backend.scripts.pokemon_snapshot_builders import get_client
    control = _load_control(FROZEN_CONTROL)
    ranked = sorted(control.values(), key=lambda row: int(row["currentBudgetRank"]))
    step = max(1, len(ranked) // max(1, args.extended_sample))
    sample = [str(row["sealedProductId"]) for row in ranked[::step]][: args.extended_sample]
    extended = tuple(dict.fromkeys(list(ADVERSARIAL_PRODUCTS) + sample))
    result = run_real(
        get_client(), product_ids=args.product, extended_products=extended,
        extended_window=args.extended_window, max_extended_quantities=args.max_extended_quantities,
        checkpoint_path=args.checkpoint,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, default=str) + "\n", encoding="utf-8")
    print(f"wrote {args.output} products={result['productCount']} wall={result['wallSeconds']:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
