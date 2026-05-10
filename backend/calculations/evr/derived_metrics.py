"""Derived decision-metrics layer for pack simulation output.

This module consumes simulation outcomes produced by the Monte Carlo simulation
engine and returns structured, product-facing metrics. It is intentionally
kept separate from simulation execution, validation/calibration orchestration,
and UI presentation.

Layering contract
-----------------
  simulation layer    -> produces raw outcome arrays (values, slot logs, ...)
  derived metrics     -> interprets those outcomes into product metrics
  persistence/UI      -> stores or presents the derived metrics

Nothing in this file runs a simulation from scratch.
All public functions accept pre-computed simulation outputs as inputs.

Scoring modes in this module
----------------------------
V1 population scoring (cross-set min-max)
    :func:`compute_pack_scores_for_set_records` computes population-relative
    scores across a list of set records using cross-set min-max normalization.
    This is retained for set-vs-set ranking workflows.

V2 runtime scoring (fixed anchors)
    :func:`compute_all_derived_metrics` builds a real runtime score payload via
    fixed-anchor normalization (not a placeholder singleton). The runtime
    payload reports:
            score_version = "pack_score_v2_1_runtime"
            normalization_mode = "fixed_anchor_runtime_v2_1"
      pack_score_is_placeholder = False

V2 runtime component inputs
---------------------------
Profit Score (0-100)
    Inputs: prob_profit, mean_value_to_cost_ratio, median_value_to_cost_ratio,
    p95_value_to_cost_ratio.

Safety Score (0-100)
    Inputs: expected_loss_when_losing, median_loss_when_losing,
    p05_shortfall_to_cost where
    p05_shortfall_to_cost = max(pack_cost - tail_value_p05, 0) / pack_cost.

Stability Score (0-100)
    Inputs: coefficient_of_variation and full-distribution concentration from
    EV shares via HHI and effective chase count.
    HHI = sum(p_i^2), effective_chase_count = 1 / HHI when HHI > 0.

PACK Score (0-100)
    Weighted blend of interpretable components:
    40% Profit Score + 30% Safety Score + 30% Stability Score.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _to_array(values: Sequence[float]) -> np.ndarray:
    """Convert any sequence to a 1-D float64 numpy array."""
    return np.asarray(values, dtype=np.float64).ravel()


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _safe_mean(arr: np.ndarray, fallback: float = 0.0) -> float:
    return float(arr.mean()) if arr.size > 0 else fallback


def _safe_median(arr: np.ndarray, fallback: float = 0.0) -> float:
    return float(np.median(arr)) if arr.size > 0 else fallback


def _safe_percentile(arr: np.ndarray, q: float, fallback: float = 0.0) -> float:
    return float(np.percentile(arr, q)) if arr.size > 0 else fallback


# ---------------------------------------------------------------------------
# Goal 1 — Probability metrics
# ---------------------------------------------------------------------------

def compute_probability_metrics(
    values: Sequence[float],
    pack_cost: float,
    *,
    big_hit_threshold_fixed: Optional[float] = None,
    big_hit_dynamic_mode: str = "cost_multiple",
    big_hit_dynamic_param: float = 5.0,
) -> Dict[str, Any]:
    """Compute probability-of-profit and big-hit probability metrics.

    Parameters
    ----------
    values:
        Raw per-pack simulation output values (length = n_runs).
    pack_cost:
        Cost of a single pack in the same currency units as *values*.
    big_hit_threshold_fixed:
        Absolute value threshold for the "fixed big hit" metric.
        If None, no fixed metric is computed (both fields become None).
    big_hit_dynamic_mode:
        "cost_multiple"  →  threshold = big_hit_dynamic_param × pack_cost
        "percentile"     →  threshold = big_hit_dynamic_param-th percentile
    big_hit_dynamic_param:
        Numeric parameter for the chosen dynamic mode.

    Returns
    -------
    dict with keys:
        n_runs, prob_profit,
        prob_big_hit_fixed, big_hit_threshold_fixed,
        prob_big_hit_dynamic, big_hit_threshold_dynamic,
        big_hit_dynamic_mode, big_hit_dynamic_param.
    """
    arr = _to_array(values)
    n = len(arr)
    if n == 0:
        raise ValueError("values must not be empty.")

    prob_profit = float((arr >= pack_cost).sum()) / n

    # Fixed big-hit
    if big_hit_threshold_fixed is not None:
        prob_bh_fixed: Optional[float] = float((arr >= big_hit_threshold_fixed).sum()) / n
        threshold_fixed: Optional[float] = float(big_hit_threshold_fixed)
    else:
        prob_bh_fixed = None
        threshold_fixed = None

    # Dynamic big-hit semantics:
    #   cost_multiple: threshold = big_hit_dynamic_param * pack_cost
    #   percentile:    threshold = percentile(values, big_hit_dynamic_param)
    # The probability is always a direct count over pack outcomes:
    #   count(value >= threshold) / n_runs
    if big_hit_dynamic_mode == "cost_multiple":
        dyn_threshold = float(big_hit_dynamic_param) * float(pack_cost)
    elif big_hit_dynamic_mode == "percentile":
        dyn_threshold = _safe_percentile(arr, float(big_hit_dynamic_param))
    else:
        raise ValueError(
            f"Unknown big_hit_dynamic_mode '{big_hit_dynamic_mode}'. "
            "Use 'cost_multiple' or 'percentile'."
        )
    prob_bh_dynamic = float((arr >= dyn_threshold).sum()) / n

    return {
        "n_runs": n,
        "prob_profit": prob_profit,
        "prob_big_hit_fixed": prob_bh_fixed,
        "big_hit_threshold_fixed": threshold_fixed,
        "prob_big_hit_dynamic": prob_bh_dynamic,
        "big_hit_threshold_dynamic": dyn_threshold,
        "big_hit_dynamic_mode": big_hit_dynamic_mode,
        "big_hit_dynamic_param": float(big_hit_dynamic_param),
    }


# ---------------------------------------------------------------------------
# Goal 2 — Downside metrics
# ---------------------------------------------------------------------------

def compute_downside_metrics(
    values: Sequence[float],
    pack_cost: float,
) -> Dict[str, Any]:
    """Compute conditional and unconditional downside metrics.

    Definitions are explicit and separate — see module docstring.

    Returns
    -------
    dict with keys:
        n_runs, n_losing_runs,
        expected_loss_given_loss,   (None if no losing runs)
        median_loss_given_loss,     (None if no losing runs)
        expected_loss_unconditional,
        tail_value_p05.
    """
    arr = _to_array(values)
    n = len(arr)
    if n == 0:
        raise ValueError("values must not be empty.")

    pack_cost_f = float(pack_cost)
    losing_mask = arr < pack_cost_f
    losing_runs = arr[losing_mask]
    n_losing = int(losing_mask.sum())

    if n_losing > 0:
        loss_amounts = pack_cost_f - losing_runs
        egl: Optional[float] = float(loss_amounts.mean())
        mgl: Optional[float] = float(np.median(loss_amounts))
    else:
        egl = None
        mgl = None

    # Unconditional: average downside burden across all runs
    unconditional_losses = np.maximum(pack_cost_f - arr, 0.0)
    expected_loss_unconditional = float(unconditional_losses.mean())

    tail_p05 = _safe_percentile(arr, 5)

    return {
        "n_runs": n,
        "n_losing_runs": n_losing,
        "expected_loss_given_loss": egl,
        "median_loss_given_loss": mgl,
        "expected_loss_unconditional": expected_loss_unconditional,
        "tail_value_p05": tail_p05,
    }


# ---------------------------------------------------------------------------
# Goal 3 — Volatility / risk normalization
# ---------------------------------------------------------------------------

def compute_volatility_metrics(
    values: Sequence[float],
) -> Dict[str, Any]:
    """Compute normalized volatility and distribution summary statistics.

    Returns
    -------
    dict with keys:
        n_runs, mean, median, std_dev, coefficient_of_variation (may be None),
        p05, p25, p50, p75, p95, p99.
    """
    arr = _to_array(values)
    n = len(arr)
    if n == 0:
        raise ValueError("values must not be empty.")

    mean_val = float(arr.mean())
    std_val = float(arr.std())
    cv: Optional[float] = (std_val / mean_val) if mean_val > 0 else None

    return {
        "n_runs": n,
        "mean": mean_val,
        "median": float(np.median(arr)),
        "std_dev": std_val,
        "coefficient_of_variation": cv,
        "p05": _safe_percentile(arr, 5),
        "p25": _safe_percentile(arr, 25),
        "p50": _safe_percentile(arr, 50),
        "p75": _safe_percentile(arr, 75),
        "p95": _safe_percentile(arr, 95),
        "p99": _safe_percentile(arr, 99),
    }


# ---------------------------------------------------------------------------
# Goal 4 — Chase dependency
# ---------------------------------------------------------------------------

def compute_chase_dependency_metrics(
    card_ev_contributions: Dict[str, float],
    *,
    return_ranked_cards: bool = False,
) -> Dict[str, Any]:
    """Compute EV concentration / chase-dependency metrics.

    Parameters
    ----------
    card_ev_contributions:
        Mapping of card_id → EV contribution (non-negative floats).
        Negative contributions are treated as zero in share calculations.
    return_ranked_cards:
        If True, include the ranked list of (card_id, ev_contribution) in
        the output under key "ranked_cards".  Useful for debugging.

    Returns
    -------
    dict with keys:
        n_cards, total_ev,
        top1_ev_share, top3_ev_share, top5_ev_share,
        and optionally ranked_cards.

    Notes
    -----
    If total_ev <= 0 all share metrics are returned as None to signal that
    the calculation is not meaningful rather than returning misleading zeros.
    """
    if not card_ev_contributions:
        result: Dict[str, Any] = {
            "n_cards": 0,
            "cards_tracked": 0,
            "total_ev": 0.0,
            "total_card_ev": 0.0,
            "top1_ev_share": None,
            "top3_ev_share": None,
            "top5_ev_share": None,
            "hhi_ev_concentration": None,
            "effective_chase_count": None,
        }
        if return_ranked_cards:
            result["ranked_cards"] = []
        return result

    # Rank by contribution descending; treat negatives as 0 in share math
    ranked: List[Tuple[str, float]] = sorted(
        [
            (card_id, max(0.0, _to_finite_float(ev) or 0.0))
            for card_id, ev in card_ev_contributions.items()
        ],
        key=lambda kv: kv[1],
        reverse=True,
    )
    contributions = [v for _, v in ranked]
    total_ev = float(sum(contributions))
    n_cards = len(contributions)
    hhi_ev_concentration = _compute_hhi_from_ev_contributions(contributions)
    effective_chase_count = _compute_effective_chase_count(hhi_ev_concentration)

    if total_ev <= 0:
        shares: Dict[str, Optional[float]] = {
            "top1_ev_share": None,
            "top3_ev_share": None,
            "top5_ev_share": None,
        }
    else:
        def _share(top_n: int) -> float:
            return sum(contributions[:top_n]) / total_ev

        shares = {
            "top1_ev_share": _share(1),
            "top3_ev_share": _share(min(3, n_cards)),
            "top5_ev_share": _share(min(5, n_cards)),
        }

    result = {
        "n_cards": n_cards,
        "cards_tracked": n_cards,
        "total_ev": total_ev,
        "total_card_ev": total_ev,
        "hhi_ev_concentration": hhi_ev_concentration,
        "effective_chase_count": effective_chase_count,
        **shares,
    }
    if return_ranked_cards:
        result["ranked_cards"] = ranked

    return result


# ---------------------------------------------------------------------------
# Goal 4b — EV Composition Reconciliation (Hit vs Non-Hit)
# ---------------------------------------------------------------------------

def compute_ev_composition_metrics(
    total_pack_ev: float,
    hit_ev: float,
    *,
    hit_cards_count: Optional[int] = None,
) -> Dict[str, Any]:
    """Compute EV composition reconciliation: hit vs non-hit breakdown.
    
    Reconciles the relationship between simulated pack EV and the hit-only
    EV contribution pool. This clarifies why simulated pack EV may be higher
    than hit EV: the difference is bulk/non-hit contribution.
    
    Parameters
    ----------
    total_pack_ev : float
        Total simulated pack EV (from Monte Carlo engine).
    hit_ev : float
        Sum of EV contributions from cards mapped to 'hits' via config
        rarity mapping. This is the EV from chase/tracked cards only.
    hit_cards_count : int, optional
        Total count of unique hit cards in the pool (for context only).
    
    Returns
    -------
    dict with keys:
        total_pack_ev, hit_ev, non_hit_ev, hit_ev_share_of_pack_ev,
        hit_cards_count (if provided).
    
    Notes
    -----
    - non_hit_ev = total_pack_ev - hit_ev
    - hit_ev_share_of_pack_ev = hit_ev / total_pack_ev when total > 0, else None
    - All values are floats (not clamped to [0, 1])
    - If total_pack_ev <= 0, hit_ev_share is None to signal meaninglessness
    
    Examples
    --------
    >>> metrics = compute_ev_composition_metrics(7.18, 6.16)
    >>> print(metrics['non_hit_ev'])
    1.02
    >>> print(f"{metrics['hit_ev_share_of_pack_ev']:.1%}")
    85.8%
    """
    total_pack_ev_f = float(total_pack_ev)
    hit_ev_f = float(hit_ev)
    non_hit_ev_f = total_pack_ev_f - hit_ev_f
    
    if total_pack_ev_f > 0:
        hit_share = hit_ev_f / total_pack_ev_f
    else:
        hit_share = None
    
    result: Dict[str, Any] = {
        "total_pack_ev": total_pack_ev_f,
        "hit_ev": hit_ev_f,
        "non_hit_ev": non_hit_ev_f,
        "hit_ev_share_of_pack_ev": hit_share,
    }
    if hit_cards_count is not None:
        result["hit_cards_count"] = int(hit_cards_count)
    
    return result


# ---------------------------------------------------------------------------
# Goal 5 — Session / box-level simulation
# ---------------------------------------------------------------------------

def simulate_session(
    simulate_one_pack_fn: Callable[[], float],
    n_packs: int,
    n_runs: int,
    pack_cost: float,
    *,
    chase_hit_fn: Optional[Callable[[float], bool]] = None,
    rng: Optional[np.random.Generator] = None,
) -> Dict[str, Any]:
    """Simulate *n_runs* sessions each consisting of *n_packs* pack openings.

    Sessions are simulated by calling *simulate_one_pack_fn* repeatedly.
    The session cost is always `pack_cost * n_packs` — no approximation.

    Parameters
    ----------
    simulate_one_pack_fn:
        A zero-argument callable that returns a single pack's float value.
        Must be the same function used to produce the underlying distribution.
    n_packs:
        Number of packs per session (e.g. 10 for ETB, 36 for booster box).
    n_runs:
        Number of session repetitions.
    pack_cost:
        Cost per individual pack.
    chase_hit_fn:
        Optional.  Callable(value: float) → bool.  Returns True when the
        pack value qualifies as a "chase hit" for this session.  Used only
        to compute prob_no_chase_hit_in_box.  If None, that field is None.
    rng:
        Optional numpy Generator for reproducibility.

    Returns
    -------
    dict with keys:
        n_packs, n_runs, session_cost,
        session_values  (list of per-session totals, length n_runs),
        chase_hit_counts (list of per-session hit counts, or None).
    """
    if n_packs <= 0:
        raise ValueError("n_packs must be a positive integer.")
    if n_runs <= 0:
        raise ValueError("n_runs must be a positive integer.")

    session_cost = float(pack_cost) * int(n_packs)
    session_values: List[float] = []
    chase_hit_counts: Optional[List[int]] = [] if chase_hit_fn is not None else None

    for _ in range(n_runs):
        total = 0.0
        hits = 0
        for _ in range(n_packs):
            v = float(simulate_one_pack_fn())
            total += v
            if chase_hit_fn is not None and chase_hit_fn(v):
                hits += 1
        session_values.append(total)
        if chase_hit_counts is not None:
            chase_hit_counts.append(hits)

    return {
        "n_packs": n_packs,
        "n_runs": n_runs,
        "session_cost": session_cost,
        "session_values": session_values,
        "chase_hit_counts": chase_hit_counts,
    }


def derive_session_metrics(
    session_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Derive product-facing metrics from session simulation output.

    Parameters
    ----------
    session_data:
        The dict returned by :func:`simulate_session`.

    Returns
    -------
    dict with keys:
        n_packs, n_runs, session_cost,
        prob_box_profit, expected_box_value, median_box_value,
        std_dev_box_value, p05_box_value, p95_box_value,
        prob_no_chase_hit_in_box (None if chase tracking was not used).
    """
    session_values = _to_array(session_data["session_values"])
    n_runs = int(session_data["n_runs"])
    session_cost = float(session_data["session_cost"])

    if session_values.size == 0:
        raise ValueError("session_values must not be empty.")

    prob_profit = float((session_values >= session_cost).sum()) / n_runs
    expected_val = float(session_values.mean())
    median_val = float(np.median(session_values))

    chase_hit_counts = session_data.get("chase_hit_counts")
    if chase_hit_counts is not None:
        counts_arr = np.asarray(chase_hit_counts, dtype=np.int64)
        prob_no_chase = float((counts_arr == 0).sum()) / n_runs
    else:
        prob_no_chase = None

    return {
        "n_packs": int(session_data["n_packs"]),
        "n_runs": n_runs,
        "session_cost": session_cost,
        "prob_box_profit": prob_profit,
        "expected_box_value": expected_val,
        "median_box_value": median_val,
        "std_dev_box_value": float(session_values.std()),
        "p05_box_value": _safe_percentile(session_values, 5),
        "p95_box_value": _safe_percentile(session_values, 95),
        "prob_no_chase_hit_in_box": prob_no_chase,
    }


# ---------------------------------------------------------------------------
# Goal 6 — Packs-to-hit
# ---------------------------------------------------------------------------

def simulate_packs_until_hit(
    simulate_one_pack_fn: Callable[[], float],
    is_hit_fn: Callable[[float], bool],
    n_runs: int,
    *,
    max_packs: int = 10_000,
    verify_reachable: bool = True,
    verify_n_packs: int = 1_000,
    rng: Optional[np.random.Generator] = None,
) -> List[int]:
    """Return a list of pack counts needed to obtain the first qualifying hit.

    Each element represents one run: how many packs were opened before the
    first hit landed.  If *max_packs* is reached without a hit the run is
    recorded as *max_packs* (censored observation) and a warning is noted.

    Parameters
    ----------
    simulate_one_pack_fn:
        Zero-argument callable returning a float pack value.
    is_hit_fn:
        Callable(value: float) → bool.  Returns True when a pack qualifies
        as the target hit.  Must be unambiguously defined by the caller.
    n_runs:
        Number of repetitions.
    max_packs:
        Safety ceiling per run to prevent infinite loops.
    verify_reachable:
        If True (default), first checks that *is_hit_fn* returns True for
        at least one pack in a short pilot sample.  Raises ValueError if no
        hit is reachable, to prevent misleading results.
    verify_n_packs:
        Size of the pilot verification sample.

    Returns
    -------
    List[int] of length n_runs.  Each value is the number of packs opened.
    """
    if n_runs <= 0:
        raise ValueError("n_runs must be positive.")

    if verify_reachable:
        # Quick pilot: open verify_n_packs and check at least one hit
        any_hit = any(is_hit_fn(float(simulate_one_pack_fn())) for _ in range(verify_n_packs))
        if not any_hit:
            raise ValueError(
                "No qualifying hit was observed in a pilot sample of "
                f"{verify_n_packs} packs.  The target may be impossible "
                "under the current model/pools.  Check is_hit_fn and "
                "the simulation configuration."
            )

    packs_to_hit: List[int] = []
    for _ in range(n_runs):
        count = 0
        while count < max_packs:
            count += 1
            v = float(simulate_one_pack_fn())
            if is_hit_fn(v):
                break
        packs_to_hit.append(count)

    return packs_to_hit


def derive_packs_to_hit_metrics(
    packs_to_hit: Sequence[int],
) -> Dict[str, Any]:
    """Derive summary statistics from packs-to-hit simulation results.

    Parameters
    ----------
    packs_to_hit:
        List returned by :func:`simulate_packs_until_hit`.

    Returns
    -------
    dict with keys:
        n_runs, expected_packs_to_hit, median_packs_to_hit,
        p25_packs_to_hit, p75_packs_to_hit, p90_packs_to_hit,
        p95_packs_to_hit, min_packs_to_hit, max_packs_to_hit.
    """
    arr = np.asarray(packs_to_hit, dtype=np.float64)
    if arr.size == 0:
        raise ValueError("packs_to_hit must not be empty.")

    return {
        "n_runs": int(arr.size),
        "expected_packs_to_hit": float(arr.mean()),
        "median_packs_to_hit": float(np.median(arr)),
        "p25_packs_to_hit": float(np.percentile(arr, 25)),
        "p75_packs_to_hit": float(np.percentile(arr, 75)),
        "p90_packs_to_hit": float(np.percentile(arr, 90)),
        "p95_packs_to_hit": float(np.percentile(arr, 95)),
        "min_packs_to_hit": float(arr.min()),
        "max_packs_to_hit": float(arr.max()),
    }


# ---------------------------------------------------------------------------
# Goal 8 — PACK Score (component-based, cross-set min-max normalized)
# ---------------------------------------------------------------------------

_NEUTRAL_SCORE: float = 50.0

_SCORE_DIRECTION_HIGHER_IS_BETTER = "higher_is_better"
_SCORE_DIRECTION_LOWER_IS_BETTER = "lower_is_better"

# Component composition weights.
_PROFIT_COMPONENT_WEIGHTS: Tuple[float, float] = (0.50, 0.50)
_SAFETY_COMPONENT_WEIGHTS: Tuple[float, float] = (0.50, 0.50)
_STABILITY_COMPONENT_WEIGHTS: Tuple[float, float] = (0.50, 0.50)

# Overall PACK Score weights.
_PACK_SCORE_WEIGHTS: Tuple[float, float, float] = (0.40, 0.30, 0.30)


# Runtime V2 component weights are declared as percentage-style values and
# normalized internally for weighted averages.
_PROFIT_V2_WEIGHTS_PCT: Dict[str, float] = {
    "prob_profit": 27.5,
    "mean_value_to_cost_ratio": 25.0,
    "median_value_to_cost_ratio": 20.0,
    "p95_value_to_cost_ratio": 27.5,
}
_SAFETY_V2_WEIGHTS_PCT: Dict[str, float] = {
    "expected_loss_when_losing_ratio": 34.0,
    "median_loss_when_losing_ratio": 33.0,
    "p05_shortfall_to_cost": 33.0,
}
_STABILITY_V2_WEIGHTS_PCT: Dict[str, float] = {
    "coefficient_of_variation": 65.0,
    "effective_chase_count": 35.0,
}
_PACK_SCORE_V2_WEIGHTS_PCT: Dict[str, float] = {
    "profit_score": 45.0,
    "safety_score": 30.0,
    "stability_score": 25.0,
}

# Stage 1 derived metrics component weights (percentage-style)
_CHASE_POTENTIAL_V1_WEIGHTS_PCT: Dict[str, float] = {
    "big_hit_frequency_score": 30.0,
    "big_hit_upside_score": 30.0,
    "chase_depth_score": 20.0,
    "pack_affordability_score": 10.0,
    "profit_score": 10.0,
}
_EXPERIENCE_V1_WEIGHTS_PCT: Dict[str, float] = {
    "prob_profit_score": 35.0,
    "median_value_to_cost_score": 25.0,
    "safety_score": 20.0,
    "big_hit_frequency_score": 10.0,
    "stability_score": 10.0,
}

_RUNTIME_V2_ANCHORS: Dict[str, Dict[str, float | str]] = {
    # Profit anchors
    "prob_profit": {
        "min": 0.00,
        "max": 1.00,
        "direction": _SCORE_DIRECTION_HIGHER_IS_BETTER,
    },
    "mean_value_to_cost_ratio": {
        "min": 0.25,
        "max": 1.25,
        "direction": _SCORE_DIRECTION_HIGHER_IS_BETTER,
    },
    "median_value_to_cost_ratio": {
        "min": 0.10,
        "max": 1.00,
        "direction": _SCORE_DIRECTION_HIGHER_IS_BETTER,
    },
    "p95_value_to_cost_ratio": {
        "min": 0.25,
        "max": 5.00,
        "direction": _SCORE_DIRECTION_HIGHER_IS_BETTER,
    },
    # Safety anchors (all normalized downside ratios)
    "expected_loss_when_losing_ratio": {
        "min": 0.00,
        "max": 1.00,
        "direction": _SCORE_DIRECTION_LOWER_IS_BETTER,
    },
    "median_loss_when_losing_ratio": {
        "min": 0.00,
        "max": 1.00,
        "direction": _SCORE_DIRECTION_LOWER_IS_BETTER,
    },
    "p05_shortfall_to_cost": {
        "min": 0.00,
        "max": 1.00,
        "direction": _SCORE_DIRECTION_LOWER_IS_BETTER,
    },
    # Stability anchors
    "coefficient_of_variation": {
        "min": 0.25,
        "max": 6.00,
        "direction": _SCORE_DIRECTION_LOWER_IS_BETTER,
    },
    "effective_chase_count": {
        "min": 1.0,
        "max": 40.0,
        "direction": _SCORE_DIRECTION_HIGHER_IS_BETTER,
    },
    # Stage 1 derived intelligence metrics component anchors
    "pack_affordability_score": {
        "min": 5.0,
        "max": 50.0,
        "direction": _SCORE_DIRECTION_LOWER_IS_BETTER,  # cheaper = better, so lower pack cost is better
    },
    "big_hit_frequency_score": {
        "min": 0.0,
        "max": 1.0,
        "direction": _SCORE_DIRECTION_HIGHER_IS_BETTER,  # probability, higher is better
    },
    "big_hit_upside_score": {
        "min": 0.25,
        "max": 5.0,
        "direction": _SCORE_DIRECTION_HIGHER_IS_BETTER,  # p95_value_to_cost, higher is better
    },
    "chase_depth_score": {
        "min": 1.0,
        "max": 40.0,
        "direction": _SCORE_DIRECTION_HIGHER_IS_BETTER,  # effective chase count, higher is better
    },
}


def _to_finite_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _safe_ratio(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    """Return numerator/denominator when both are finite and denominator > 0."""
    if numerator is None or denominator is None:
        return None
    if not math.isfinite(numerator) or not math.isfinite(denominator):
        return None
    if denominator <= 0:
        return None
    return numerator / denominator


def _compute_p05_shortfall_to_cost(
    tail_value_p05: Optional[float],
    pack_cost: Optional[float],
) -> Optional[float]:
    """Compute max(pack_cost - p05, 0) / pack_cost for runtime V2 safety scoring."""
    if tail_value_p05 is None or pack_cost is None:
        return None
    if not math.isfinite(tail_value_p05) or not math.isfinite(pack_cost):
        return None
    if pack_cost <= 0:
        return None
    return max(pack_cost - tail_value_p05, 0.0) / pack_cost


def _compute_hhi_from_ev_contributions(contributions: Sequence[float]) -> Optional[float]:
    """Compute HHI = sum(p_i^2) from non-negative EV contributions."""
    sanitized = [max(0.0, float(v)) for v in contributions if math.isfinite(float(v))]
    if not sanitized:
        return None
    total = float(sum(sanitized))
    if total <= 0:
        return None
    shares = [v / total for v in sanitized]
    return float(sum(p * p for p in shares))


def _compute_effective_chase_count(hhi: Optional[float]) -> Optional[float]:
    """Compute effective chase count as 1/HHI when HHI > 0."""
    if hhi is None:
        return None
    if not math.isfinite(hhi) or hhi <= 0:
        return None
    return 1.0 / hhi


def _normalize_weights_from_percent(weights_pct: Dict[str, float]) -> Dict[str, float]:
    """Normalize percentage-style weights to unit-sum weights."""
    total = float(sum(weights_pct.values()))
    if total <= 0 or not math.isfinite(total):
        raise ValueError("Weight total must be positive and finite.")
    return {k: float(v) / total for k, v in weights_pct.items()}


def _weighted_average(values: Dict[str, float], weights_pct: Dict[str, float]) -> float:
    """Compute weighted average using percentage-style weights."""
    normalized_weights = _normalize_weights_from_percent(weights_pct)
    return float(sum(values[key] * normalized_weights[key] for key in values.keys()))


def _normalize_fixed_anchor_0_100(
    value: Optional[float],
    *,
    min_anchor: float,
    max_anchor: float,
    direction: str,
) -> float:
    """Normalize one metric to [0, 100] using fixed anchors.

    Missing metric values return a neutral score (50) so runtime scoring stays
    robust when an upstream metric is undefined (for example pack_cost <= 0).
    Invalid or degenerate anchor definitions raise ValueError.
    """
    if value is None or not math.isfinite(value):
        return _NEUTRAL_SCORE
    if not math.isfinite(min_anchor) or not math.isfinite(max_anchor):
        raise ValueError("Fixed anchors must be finite.")
    if max_anchor <= min_anchor:
        raise ValueError("Fixed anchor max must be greater than min.")

    range_width = max_anchor - min_anchor
    if direction == _SCORE_DIRECTION_HIGHER_IS_BETTER:
        raw = 100.0 * ((value - min_anchor) / range_width)
    elif direction == _SCORE_DIRECTION_LOWER_IS_BETTER:
        raw = 100.0 * ((max_anchor - value) / range_width)
    else:
        raise ValueError(f"Unknown normalization direction: {direction}")
    return _clamp(raw, 0.0, 100.0)


def _normalize_min_max_0_100(
    value: Optional[float],
    min_value: Optional[float],
    max_value: Optional[float],
) -> float:
    """Normalize a higher-is-better metric to [0, 100] with neutral fallbacks."""
    if value is None or min_value is None or max_value is None:
        return _NEUTRAL_SCORE
    if not math.isfinite(value) or not math.isfinite(min_value) or not math.isfinite(max_value):
        return _NEUTRAL_SCORE

    range_width = max_value - min_value
    if math.isclose(range_width, 0.0, abs_tol=1e-12):
        return _NEUTRAL_SCORE

    raw = 100.0 * ((value - min_value) / range_width)
    return _clamp(raw, 0.0, 100.0)


def _inverse_normalize_min_max_0_100(
    value: Optional[float],
    min_value: Optional[float],
    max_value: Optional[float],
) -> float:
    """Normalize a lower-is-better metric to [0, 100] with neutral fallbacks."""
    if value is None or min_value is None or max_value is None:
        return _NEUTRAL_SCORE
    if not math.isfinite(value) or not math.isfinite(min_value) or not math.isfinite(max_value):
        return _NEUTRAL_SCORE

    range_width = max_value - min_value
    if math.isclose(range_width, 0.0, abs_tol=1e-12):
        return _NEUTRAL_SCORE

    raw = 100.0 * ((max_value - value) / range_width)
    return _clamp(raw, 0.0, 100.0)


def _compute_metric_range(values: Sequence[Optional[float]]) -> Tuple[Optional[float], Optional[float]]:
    finite_values = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    if not finite_values:
        return None, None
    return min(finite_values), max(finite_values)


def _resolve_ev_to_cost_ratio(record: Dict[str, Any]) -> Optional[float]:
    ratio = _to_finite_float(record.get("ev_to_cost_ratio"))
    if ratio is not None:
        return ratio

    mean_value = _to_finite_float(
        record.get("mean_value")
        if record.get("mean_value") is not None
        else record.get("mean")
    )
    if mean_value is None:
        mean_value = _to_finite_float(record.get("total_ev"))

    pack_cost = _to_finite_float(record.get("pack_cost"))
    if mean_value is None or pack_cost is None or pack_cost <= 0:
        return None
    return mean_value / pack_cost


def _extract_score_input_record(record: Dict[str, Any]) -> Dict[str, Optional[float]]:
    return {
        # Profit drivers (higher is better).
        "prob_profit": _to_finite_float(
            record.get("probability_of_profit")
            if record.get("probability_of_profit") is not None
            else record.get("prob_profit")
        ),
        "ev_to_cost_ratio": _resolve_ev_to_cost_ratio(record),
        # Safety drivers (lower loss is better).
        "expected_loss_when_losing": _to_finite_float(
            record.get("expected_loss_when_losing")
            if record.get("expected_loss_when_losing") is not None
            else record.get("expected_loss_given_loss")
        ),
        "median_loss_when_losing": _to_finite_float(
            record.get("median_loss_when_losing")
            if record.get("median_loss_when_losing") is not None
            else record.get("median_loss_given_loss")
        ),
        # Stability drivers (lower risk concentration is better).
        "coefficient_of_variation": _to_finite_float(record.get("coefficient_of_variation")),
        "top5_ev_share": _to_finite_float(
            record.get("top_5_ev_share")
            if record.get("top_5_ev_share") is not None
            else record.get("top5_ev_share")
        ),
    }


def compute_pack_scores_for_set_records(set_records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Compute Profit/Safety/Stability/PACK scores for a set population.

    Each raw metric is min-max normalized against the supplied set population
    for this scoring run. Penalty metrics (losses, CV, concentration) are
    inverse-normalized so higher score always means better.
    """
    extracted_rows = [_extract_score_input_record(record) for record in set_records]

    prob_profit_min, prob_profit_max = _compute_metric_range(
        [row["prob_profit"] for row in extracted_rows]
    )
    ev_ratio_min, ev_ratio_max = _compute_metric_range(
        [row["ev_to_cost_ratio"] for row in extracted_rows]
    )
    expected_loss_min, expected_loss_max = _compute_metric_range(
        [row["expected_loss_when_losing"] for row in extracted_rows]
    )
    median_loss_min, median_loss_max = _compute_metric_range(
        [row["median_loss_when_losing"] for row in extracted_rows]
    )
    cv_min, cv_max = _compute_metric_range(
        [row["coefficient_of_variation"] for row in extracted_rows]
    )
    top5_min, top5_max = _compute_metric_range(
        [row["top5_ev_share"] for row in extracted_rows]
    )

    results: List[Dict[str, Any]] = []
    for row in extracted_rows:
        prob_profit_score = _normalize_min_max_0_100(row["prob_profit"], prob_profit_min, prob_profit_max)
        ev_ratio_score = _normalize_min_max_0_100(row["ev_to_cost_ratio"], ev_ratio_min, ev_ratio_max)
        expected_loss_score = _inverse_normalize_min_max_0_100(
            row["expected_loss_when_losing"], expected_loss_min, expected_loss_max
        )
        median_loss_score = _inverse_normalize_min_max_0_100(
            row["median_loss_when_losing"], median_loss_min, median_loss_max
        )
        cv_score = _inverse_normalize_min_max_0_100(row["coefficient_of_variation"], cv_min, cv_max)
        top5_score = _inverse_normalize_min_max_0_100(row["top5_ev_share"], top5_min, top5_max)

        # Profit combines probability-of-profit and EV-to-cost strength.
        profit_score = (
            _PROFIT_COMPONENT_WEIGHTS[0] * prob_profit_score
            + _PROFIT_COMPONENT_WEIGHTS[1] * ev_ratio_score
        )

        # Safety isolates downside pain from losing outcomes.
        safety_score = (
            _SAFETY_COMPONENT_WEIGHTS[0] * expected_loss_score
            + _SAFETY_COMPONENT_WEIGHTS[1] * median_loss_score
        )

        # Stability isolates dispersion and top-heaviness risk.
        stability_score = (
            _STABILITY_COMPONENT_WEIGHTS[0] * cv_score
            + _STABILITY_COMPONENT_WEIGHTS[1] * top5_score
        )

        pack_score = (
            _PACK_SCORE_WEIGHTS[0] * profit_score
            + _PACK_SCORE_WEIGHTS[1] * safety_score
            + _PACK_SCORE_WEIGHTS[2] * stability_score
        )

        results.append(
            {
                "score_version": "pack_score_v1",
                "profit_score": round(_clamp(profit_score, 0.0, 100.0), 2),
                "safety_score": round(_clamp(safety_score, 0.0, 100.0), 2),
                "stability_score": round(_clamp(stability_score, 0.0, 100.0), 2),
                "pack_score": round(_clamp(pack_score, 0.0, 100.0), 2),
                "weights": {
                    "pack_score": {
                        "profit_score": _PACK_SCORE_WEIGHTS[0],
                        "safety_score": _PACK_SCORE_WEIGHTS[1],
                        "stability_score": _PACK_SCORE_WEIGHTS[2],
                    },
                    "profit_score": {
                        "prob_profit": _PROFIT_COMPONENT_WEIGHTS[0],
                        "ev_to_cost_ratio": _PROFIT_COMPONENT_WEIGHTS[1],
                    },
                    "safety_score": {
                        "expected_loss_when_losing": _SAFETY_COMPONENT_WEIGHTS[0],
                        "median_loss_when_losing": _SAFETY_COMPONENT_WEIGHTS[1],
                    },
                    "stability_score": {
                        "coefficient_of_variation": _STABILITY_COMPONENT_WEIGHTS[0],
                        "top5_ev_share": _STABILITY_COMPONENT_WEIGHTS[1],
                    },
                },
                "normalization": {
                    "prob_profit": {
                        "value": row["prob_profit"],
                        "min": prob_profit_min,
                        "max": prob_profit_max,
                        "score": round(prob_profit_score, 2),
                        "direction": "higher_is_better",
                    },
                    "ev_to_cost_ratio": {
                        "value": row["ev_to_cost_ratio"],
                        "min": ev_ratio_min,
                        "max": ev_ratio_max,
                        "score": round(ev_ratio_score, 2),
                        "direction": "higher_is_better",
                    },
                    "expected_loss_when_losing": {
                        "value": row["expected_loss_when_losing"],
                        "min": expected_loss_min,
                        "max": expected_loss_max,
                        "score": round(expected_loss_score, 2),
                        "direction": "lower_is_better",
                    },
                    "median_loss_when_losing": {
                        "value": row["median_loss_when_losing"],
                        "min": median_loss_min,
                        "max": median_loss_max,
                        "score": round(median_loss_score, 2),
                        "direction": "lower_is_better",
                    },
                    "coefficient_of_variation": {
                        "value": row["coefficient_of_variation"],
                        "min": cv_min,
                        "max": cv_max,
                        "score": round(cv_score, 2),
                        "direction": "lower_is_better",
                    },
                    "top5_ev_share": {
                        "value": row["top5_ev_share"],
                        "min": top5_min,
                        "max": top5_max,
                        "score": round(top5_score, 2),
                        "direction": "lower_is_better",
                    },
                },
            }
        )

    return results


# ---------------------------------------------------------------------------
# Stage 1 Derived Intelligence Metrics
# ---------------------------------------------------------------------------

def _compute_pack_affordability_component(
    pack_cost: Optional[float],
) -> Optional[float]:
    """Compute the raw pack affordability component (pack cost in dollars).

    Lower pack cost = more affordable = higher score when normalized.
    Returns the pack_cost to be normalized by anchors (lower_is_better direction).
    """
    return _to_finite_float(pack_cost)


def _compute_big_hit_frequency_component(
    prob_big_hit_dynamic: Optional[float],
) -> Optional[float]:
    """Compute the raw big hit frequency component.

    Uses prob_big_hit_dynamic (probability of hitting a big value threshold).
    """
    return _to_finite_float(prob_big_hit_dynamic)


def _compute_big_hit_upside_component(
    p95_value_to_cost_ratio: Optional[float],
) -> Optional[float]:
    """Compute the raw big hit upside component.

    Uses p95_value_to_cost_ratio (strength of the p95 outcome relative to cost).
    """
    return _to_finite_float(p95_value_to_cost_ratio)


def _compute_chase_depth_component(
    effective_chase_count: Optional[float],
) -> Optional[float]:
    """Compute the raw chase depth component.

    Uses effective_chase_count (concentration-adjusted count of meaningful chase outcomes).
    Returns None if effective_chase_count is None or invalid.
    """
    return _to_finite_float(effective_chase_count)


# ---------------------------------------------------------------------------
# Stage 1 Composite Metrics Assembly
# ---------------------------------------------------------------------------

def _assemble_chase_potential_score(
    *,
    big_hit_frequency_normalized: float,
    big_hit_upside_normalized: float,
    chase_depth_normalized: float,
    pack_affordability_normalized: float,
    profit_score: float,
) -> float:
    """Assemble chase_potential_score from normalized component scores.

    Formula v1:
        30% big_hit_frequency + 30% big_hit_upside + 20% chase_depth
        + 10% pack_affordability + 10% profit_score

    All inputs should be 0-100 normalized scores.
    """
    return _weighted_average(
        {
            "big_hit_frequency_score": big_hit_frequency_normalized,
            "big_hit_upside_score": big_hit_upside_normalized,
            "chase_depth_score": chase_depth_normalized,
            "pack_affordability_score": pack_affordability_normalized,
            "profit_score": profit_score,
        },
        _CHASE_POTENTIAL_V1_WEIGHTS_PCT,
    )


def _assemble_experience_score(
    *,
    prob_profit_normalized: float,
    median_value_to_cost_normalized: float,
    safety_score: float,
    big_hit_frequency_normalized: float,
    stability_score: float,
) -> float:
    """Assemble experience_score from normalized component scores.

    Formula v1:
        35% prob_profit + 25% median_value_to_cost + 20% safety_score
        + 10% big_hit_frequency + 10% stability_score

    All inputs should be 0-100 normalized scores.
    """
    return _weighted_average(
        {
            "prob_profit_score": prob_profit_normalized,
            "median_value_to_cost_score": median_value_to_cost_normalized,
            "safety_score": safety_score,
            "big_hit_frequency_score": big_hit_frequency_normalized,
            "stability_score": stability_score,
        },
        _EXPERIENCE_V1_WEIGHTS_PCT,
    )


def _build_runtime_v2_pack_score_payload(
    *,
    pack_metrics: Dict[str, Any],
    chase_metrics: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build runtime V2 PACK scoring payload from one simulation run."""
    pack_cost = _to_finite_float(pack_metrics.get("pack_cost"))
    mean_value = _to_finite_float(pack_metrics.get("mean"))
    median_value = _to_finite_float(pack_metrics.get("median"))
    p95_value = _to_finite_float(pack_metrics.get("p95"))
    expected_loss_when_losing = _to_finite_float(pack_metrics.get("expected_loss_given_loss"))
    median_loss_when_losing = _to_finite_float(pack_metrics.get("median_loss_given_loss"))
    tail_value_p05 = _to_finite_float(pack_metrics.get("tail_value_p05"))

    raw_inputs = {
        "prob_profit": _to_finite_float(pack_metrics.get("prob_profit")),
        "mean_value_to_cost_ratio": _safe_ratio(mean_value, pack_cost),
        "median_value_to_cost_ratio": _safe_ratio(median_value, pack_cost),
        "p95_value_to_cost_ratio": _safe_ratio(p95_value, pack_cost),
        "expected_loss_when_losing": expected_loss_when_losing,
        "median_loss_when_losing": median_loss_when_losing,
        "expected_loss_when_losing_ratio": _safe_ratio(expected_loss_when_losing, pack_cost),
        "median_loss_when_losing_ratio": _safe_ratio(median_loss_when_losing, pack_cost),
        "p05_shortfall_to_cost": _compute_p05_shortfall_to_cost(tail_value_p05, pack_cost),
        "coefficient_of_variation": _to_finite_float(pack_metrics.get("coefficient_of_variation")),
        "hhi_ev_concentration": _to_finite_float(
            chase_metrics.get("hhi_ev_concentration") if chase_metrics is not None else None
        ),
        "effective_chase_count": _to_finite_float(
            chase_metrics.get("effective_chase_count") if chase_metrics is not None else None
        ),
    }

    def _score_metric(metric_name: str, value: Optional[float]) -> Dict[str, Any]:
        anchor = _RUNTIME_V2_ANCHORS[metric_name]
        score = _normalize_fixed_anchor_0_100(
            value,
            min_anchor=float(anchor["min"]),
            max_anchor=float(anchor["max"]),
            direction=str(anchor["direction"]),
        )
        return {
            "value": value,
            "min": float(anchor["min"]),
            "max": float(anchor["max"]),
            "direction": str(anchor["direction"]),
            "score": score,
        }

    normalized_inputs = {
        "prob_profit": _score_metric("prob_profit", raw_inputs["prob_profit"]),
        "mean_value_to_cost_ratio": _score_metric(
            "mean_value_to_cost_ratio",
            raw_inputs["mean_value_to_cost_ratio"],
        ),
        "median_value_to_cost_ratio": _score_metric(
            "median_value_to_cost_ratio",
            raw_inputs["median_value_to_cost_ratio"],
        ),
        "p95_value_to_cost_ratio": _score_metric(
            "p95_value_to_cost_ratio",
            raw_inputs["p95_value_to_cost_ratio"],
        ),
        "expected_loss_when_losing_ratio": _score_metric(
            "expected_loss_when_losing_ratio",
            raw_inputs["expected_loss_when_losing_ratio"],
        ),
        "median_loss_when_losing_ratio": _score_metric(
            "median_loss_when_losing_ratio",
            raw_inputs["median_loss_when_losing_ratio"],
        ),
        "p05_shortfall_to_cost": _score_metric(
            "p05_shortfall_to_cost",
            raw_inputs["p05_shortfall_to_cost"],
        ),
        "coefficient_of_variation": _score_metric(
            "coefficient_of_variation",
            raw_inputs["coefficient_of_variation"],
        ),
        "effective_chase_count": _score_metric(
            "effective_chase_count",
            raw_inputs["effective_chase_count"],
        ),
    }

    profit_score = _weighted_average(
        {
            "prob_profit": normalized_inputs["prob_profit"]["score"],
            "mean_value_to_cost_ratio": normalized_inputs["mean_value_to_cost_ratio"]["score"],
            "median_value_to_cost_ratio": normalized_inputs["median_value_to_cost_ratio"]["score"],
            "p95_value_to_cost_ratio": normalized_inputs["p95_value_to_cost_ratio"]["score"],
        },
        _PROFIT_V2_WEIGHTS_PCT,
    )
    safety_score = _weighted_average(
        {
            "expected_loss_when_losing_ratio": normalized_inputs[
                "expected_loss_when_losing_ratio"
            ]["score"],
            "median_loss_when_losing_ratio": normalized_inputs[
                "median_loss_when_losing_ratio"
            ]["score"],
            "p05_shortfall_to_cost": normalized_inputs["p05_shortfall_to_cost"]["score"],
        },
        _SAFETY_V2_WEIGHTS_PCT,
    )
    stability_score = _weighted_average(
        {
            "coefficient_of_variation": normalized_inputs["coefficient_of_variation"]["score"],
            "effective_chase_count": normalized_inputs["effective_chase_count"]["score"],
        },
        _STABILITY_V2_WEIGHTS_PCT,
    )
    pack_score = _weighted_average(
        {
            "profit_score": profit_score,
            "safety_score": safety_score,
            "stability_score": stability_score,
        },
        _PACK_SCORE_V2_WEIGHTS_PCT,
    )

    # =========================================================================
    # Stage 1: Derived Intelligence Metrics
    # =========================================================================
    # Compute raw component values for the new derived metrics
    pack_affordability_raw = _compute_pack_affordability_component(pack_cost)
    big_hit_frequency_raw = _compute_big_hit_frequency_component(
        pack_metrics.get("prob_big_hit_dynamic")
    )
    big_hit_upside_raw = _compute_big_hit_upside_component(
        raw_inputs.get("p95_value_to_cost_ratio")
    )
    chase_depth_raw = _compute_chase_depth_component(
        raw_inputs.get("effective_chase_count")
    )

    # Normalize the new component metrics using fixed anchors
    pack_affordability_score = _normalize_fixed_anchor_0_100(
        pack_affordability_raw,
        min_anchor=float(_RUNTIME_V2_ANCHORS["pack_affordability_score"]["min"]),
        max_anchor=float(_RUNTIME_V2_ANCHORS["pack_affordability_score"]["max"]),
        direction=str(_RUNTIME_V2_ANCHORS["pack_affordability_score"]["direction"]),
    )
    big_hit_frequency_score = _normalize_fixed_anchor_0_100(
        big_hit_frequency_raw,
        min_anchor=float(_RUNTIME_V2_ANCHORS["big_hit_frequency_score"]["min"]),
        max_anchor=float(_RUNTIME_V2_ANCHORS["big_hit_frequency_score"]["max"]),
        direction=str(_RUNTIME_V2_ANCHORS["big_hit_frequency_score"]["direction"]),
    )
    big_hit_upside_score = _normalize_fixed_anchor_0_100(
        big_hit_upside_raw,
        min_anchor=float(_RUNTIME_V2_ANCHORS["big_hit_upside_score"]["min"]),
        max_anchor=float(_RUNTIME_V2_ANCHORS["big_hit_upside_score"]["max"]),
        direction=str(_RUNTIME_V2_ANCHORS["big_hit_upside_score"]["direction"]),
    )
    chase_depth_score = _normalize_fixed_anchor_0_100(
        chase_depth_raw,
        min_anchor=float(_RUNTIME_V2_ANCHORS["chase_depth_score"]["min"]),
        max_anchor=float(_RUNTIME_V2_ANCHORS["chase_depth_score"]["max"]),
        direction=str(_RUNTIME_V2_ANCHORS["chase_depth_score"]["direction"]),
    )

    # Assemble composite metrics from normalized components
    chase_potential_score = _assemble_chase_potential_score(
        big_hit_frequency_normalized=big_hit_frequency_score,
        big_hit_upside_normalized=big_hit_upside_score,
        chase_depth_normalized=chase_depth_score,
        pack_affordability_normalized=pack_affordability_score,
        profit_score=profit_score,
    )

    experience_score = _assemble_experience_score(
        prob_profit_normalized=normalized_inputs["prob_profit"]["score"],
        median_value_to_cost_normalized=normalized_inputs["median_value_to_cost_ratio"]["score"],
        safety_score=safety_score,
        big_hit_frequency_normalized=big_hit_frequency_score,
        stability_score=stability_score,
    )

    # =========================================================================

    return {
        "score_version": "pack_score_v2_chase_weighted",
        "normalization_mode": "fixed_anchor_runtime_v2_chase_weighted",
        "pack_score_is_placeholder": False,
        "profit_score": round(_clamp(profit_score, 0.0, 100.0), 2),
        "safety_score": round(_clamp(safety_score, 0.0, 100.0), 2),
        "stability_score": round(_clamp(stability_score, 0.0, 100.0), 2),
        "pack_score": round(_clamp(pack_score, 0.0, 100.0), 2),
        "chase_potential_score": round(_clamp(chase_potential_score, 0.0, 100.0), 2),
        "experience_score": round(_clamp(experience_score, 0.0, 100.0), 2),
        "chase_potential_tier": None,
        "experience_tier": None,
        "derived_metric_version": "derived_intelligence_v1",
        "weights_pct": {
            "pack_score": dict(_PACK_SCORE_V2_WEIGHTS_PCT),
            "profit_score": dict(_PROFIT_V2_WEIGHTS_PCT),
            "safety_score": dict(_SAFETY_V2_WEIGHTS_PCT),
            "stability_score": dict(_STABILITY_V2_WEIGHTS_PCT),
            "chase_potential_score": dict(_CHASE_POTENTIAL_V1_WEIGHTS_PCT),
            "experience_score": dict(_EXPERIENCE_V1_WEIGHTS_PCT),
        },
        "weights_normalized": {
            "pack_score": _normalize_weights_from_percent(_PACK_SCORE_V2_WEIGHTS_PCT),
            "profit_score": _normalize_weights_from_percent(_PROFIT_V2_WEIGHTS_PCT),
            "safety_score": _normalize_weights_from_percent(_SAFETY_V2_WEIGHTS_PCT),
            "stability_score": _normalize_weights_from_percent(_STABILITY_V2_WEIGHTS_PCT),
            "chase_potential_score": _normalize_weights_from_percent(_CHASE_POTENTIAL_V1_WEIGHTS_PCT),
            "experience_score": _normalize_weights_from_percent(_EXPERIENCE_V1_WEIGHTS_PCT),
        },
        "raw_inputs": raw_inputs,
        "normalized_inputs": {
            key: {
                **entry,
                "score": round(float(entry["score"]), 4),
            }
            for key, entry in normalized_inputs.items()
        }
        | {
            # Keep Stage 1 components nested for debugging/explanation only.
            "pack_affordability_score": {
                "value": pack_affordability_raw,
                "min": float(_RUNTIME_V2_ANCHORS["pack_affordability_score"]["min"]),
                "max": float(_RUNTIME_V2_ANCHORS["pack_affordability_score"]["max"]),
                "direction": str(_RUNTIME_V2_ANCHORS["pack_affordability_score"]["direction"]),
                "score": round(float(pack_affordability_score), 4),
            },
            "big_hit_frequency_score": {
                "value": big_hit_frequency_raw,
                "min": float(_RUNTIME_V2_ANCHORS["big_hit_frequency_score"]["min"]),
                "max": float(_RUNTIME_V2_ANCHORS["big_hit_frequency_score"]["max"]),
                "direction": str(_RUNTIME_V2_ANCHORS["big_hit_frequency_score"]["direction"]),
                "score": round(float(big_hit_frequency_score), 4),
            },
            "big_hit_upside_score": {
                "value": big_hit_upside_raw,
                "min": float(_RUNTIME_V2_ANCHORS["big_hit_upside_score"]["min"]),
                "max": float(_RUNTIME_V2_ANCHORS["big_hit_upside_score"]["max"]),
                "direction": str(_RUNTIME_V2_ANCHORS["big_hit_upside_score"]["direction"]),
                "score": round(float(big_hit_upside_score), 4),
            },
            "chase_depth_score": {
                "value": chase_depth_raw,
                "min": float(_RUNTIME_V2_ANCHORS["chase_depth_score"]["min"]),
                "max": float(_RUNTIME_V2_ANCHORS["chase_depth_score"]["max"]),
                "direction": str(_RUNTIME_V2_ANCHORS["chase_depth_score"]["direction"]),
                "score": round(float(chase_depth_score), 4),
            },
        },
    }


# ---------------------------------------------------------------------------
# Goal 7 — Clean derived-metrics API
# ---------------------------------------------------------------------------

def compute_pack_decision_metrics(
    values: Sequence[float],
    pack_cost: float,
    *,
    big_hit_threshold_fixed: Optional[float] = None,
    big_hit_dynamic_mode: str = "cost_multiple",
    big_hit_dynamic_param: float = 5.0,
) -> Dict[str, Any]:
    """Compute the full pack-level decision metric set.

    Combines probability, downside, and volatility metrics into one call.

    Returns
    -------
    dict with keys from all three sub-computations, plus top-level n_runs.
    """
    prob = compute_probability_metrics(
        values,
        pack_cost,
        big_hit_threshold_fixed=big_hit_threshold_fixed,
        big_hit_dynamic_mode=big_hit_dynamic_mode,
        big_hit_dynamic_param=big_hit_dynamic_param,
    )
    down = compute_downside_metrics(values, pack_cost)
    vol = compute_volatility_metrics(values)

    return {
        # Identity
        "pack_cost": float(pack_cost),
        # Probability block
        "n_runs": prob["n_runs"],
        "prob_profit": prob["prob_profit"],
        "prob_big_hit_fixed": prob["prob_big_hit_fixed"],
        "big_hit_threshold_fixed": prob["big_hit_threshold_fixed"],
        "prob_big_hit_dynamic": prob["prob_big_hit_dynamic"],
        "big_hit_threshold_dynamic": prob["big_hit_threshold_dynamic"],
        "big_hit_dynamic_mode": prob["big_hit_dynamic_mode"],
        "big_hit_dynamic_param": prob["big_hit_dynamic_param"],
        # Downside block
        "n_losing_runs": down["n_losing_runs"],
        "expected_loss_given_loss": down["expected_loss_given_loss"],
        "median_loss_given_loss": down["median_loss_given_loss"],
        "expected_loss_unconditional": down["expected_loss_unconditional"],
        "tail_value_p05": down["tail_value_p05"],
        # Volatility block
        "mean": vol["mean"],
        "median": vol["median"],
        "std_dev": vol["std_dev"],
        "coefficient_of_variation": vol["coefficient_of_variation"],
        "p05": vol["p05"],
        "p25": vol["p25"],
        "p50": vol["p50"],
        "p75": vol["p75"],
        "p95": vol["p95"],
        "p99": vol["p99"],
    }


def compute_all_derived_metrics(
    values: Sequence[float],
    pack_cost: float,
    *,
    card_ev_contributions: Optional[Dict[str, float]] = None,
    session_data: Optional[Dict[str, Any]] = None,
    packs_to_hit_data: Optional[Sequence[int]] = None,
    big_hit_threshold_fixed: Optional[float] = None,
    big_hit_dynamic_mode: str = "cost_multiple",
    big_hit_dynamic_param: float = 5.0,
    index_score_weights: Optional[Tuple[float, float, float]] = None,
    total_pack_ev: Optional[float] = None,
    hit_ev: Optional[float] = None,
    hit_cards_count: Optional[int] = None,
) -> Dict[str, Any]:
    """Compute the full derived metrics suite from simulation outputs.

    This is the primary orchestration entry point for the derived metrics
    layer.  All inputs beyond *values* and *pack_cost* are optional — pass
    only what is available.

    Parameters
    ----------
    values:
        Per-pack simulation output values (length = n_runs).
    pack_cost:
        Cost of one pack.
    card_ev_contributions:
        Optional dict of card_id → EV contribution for chase-dependency.
        Should be hit-pool contributions only (non-hit cards excluded).
    session_data:
        Optional dict returned by :func:`simulate_session`.
    packs_to_hit_data:
        Optional list returned by :func:`simulate_packs_until_hit`.
    big_hit_threshold_fixed:
        Fixed threshold for big-hit probability.
    big_hit_dynamic_mode / big_hit_dynamic_param:
        Dynamic big-hit threshold configuration.
    index_score_weights:
        Deprecated legacy parameter; kept for call-site compatibility.
    total_pack_ev:
        Optional total simulated pack EV (for EV composition reconciliation).
    hit_ev:
        Optional sum of hit-card EV contributions (for EV composition).
    hit_cards_count:
        Optional count of unique hit cards (for composition context).

    Returns
    -------
    A structured dict with keys:
        pack_decision_metrics, chase_dependency_metrics,
        ev_composition_metrics (None if total_pack_ev not provided),
        session_metrics (None if session_data not provided),
        packs_to_hit_metrics (None if packs_to_hit_data not provided),
        pack_score.
    """
    pack_metrics = compute_pack_decision_metrics(
        values,
        pack_cost,
        big_hit_threshold_fixed=big_hit_threshold_fixed,
        big_hit_dynamic_mode=big_hit_dynamic_mode,
        big_hit_dynamic_param=big_hit_dynamic_param,
    )

    if card_ev_contributions is not None:
        chase_metrics: Optional[Dict[str, Any]] = compute_chase_dependency_metrics(
            card_ev_contributions
        )
    else:
        chase_metrics = None

    if total_pack_ev is not None and hit_ev is not None:
        ev_comp_metrics: Optional[Dict[str, Any]] = compute_ev_composition_metrics(
            total_pack_ev,
            hit_ev,
            hit_cards_count=hit_cards_count,
        )
    else:
        ev_comp_metrics = None

    if session_data is not None:
        sess_metrics: Optional[Dict[str, Any]] = derive_session_metrics(session_data)
    else:
        sess_metrics = None

    if packs_to_hit_data is not None:
        pth_metrics: Optional[Dict[str, Any]] = derive_packs_to_hit_metrics(packs_to_hit_data)
    else:
        pth_metrics = None

    _ = index_score_weights

    pack_score_payload = _build_runtime_v2_pack_score_payload(
        pack_metrics=pack_metrics,
        chase_metrics=chase_metrics,
    )

    return {
        "pack_decision_metrics": pack_metrics,
        "chase_dependency_metrics": chase_metrics,
        "ev_composition_metrics": ev_comp_metrics,
        "session_metrics": sess_metrics,
        "packs_to_hit_metrics": pth_metrics,
        "pack_score": pack_score_payload,
    }


# ---------------------------------------------------------------------------
# Goal 9 — Persistence-friendly summary schema
# ---------------------------------------------------------------------------

@dataclass
class PackSimulationSummary:
    """Typed persistence-friendly summary for one pack simulation run.

    This dataclass describes the canonical shape for storage in a table such
    as ``pack_simulation_summaries``.  All fields map 1-to-1 to the derived
    metrics produced by this module.

    Nullable fields use Optional[float] and default to None rather than 0 so
    that "not computed" and "genuinely zero" remain distinguishable.

    Usage
    -----
    Populate via :func:`build_pack_simulation_summary` or construct directly
    from the output of :func:`compute_all_derived_metrics`.
    """

    # --- Identity / lineage ---
    set_id: str
    product_id: Optional[str]
    pack_cost: float
    simulation_version: str
    score_version: str
    computed_at: str  # ISO-8601 timestamp string

    # --- Run counts ---
    n_pack_runs: int
    n_session_runs: Optional[int]

    # --- Distribution summary ---
    mean_value: float
    median_value: float
    p95_value: Optional[float]
    std_dev: float
    coefficient_of_variation: Optional[float]

    # --- Probability metrics ---
    prob_profit: float
    prob_big_hit_fixed: Optional[float]
    big_hit_threshold_fixed: Optional[float]
    prob_big_hit_dynamic: Optional[float]
    big_hit_threshold_dynamic: Optional[float]

    # --- Downside metrics ---
    expected_loss_given_loss: Optional[float]
    median_loss_given_loss: Optional[float]
    expected_loss_unconditional: float

    # --- Chase dependency ---
    top1_ev_share: Optional[float]
    top3_ev_share: Optional[float]
    top5_ev_share: Optional[float]

    # --- Session / box metrics ---
    prob_box_profit: Optional[float]
    expected_box_value: Optional[float]
    median_box_value: Optional[float]
    prob_no_chase_hit_in_box: Optional[float]

    # --- Packs-to-hit ---
    expected_packs_to_hit: Optional[float]
    median_packs_to_hit: Optional[float]

    # --- Scores ---
    profit_score: Optional[float]
    safety_score: Optional[float]
    stability_score: Optional[float]
    pack_score: Optional[float]
    p95_value_to_cost_ratio: Optional[float]


def build_pack_simulation_summary(
    *,
    set_id: str,
    pack_cost: float,
    simulation_version: str,
    computed_at: str,
    all_metrics: Dict[str, Any],
    product_id: Optional[str] = None,
) -> PackSimulationSummary:
    """Assemble a :class:`PackSimulationSummary` from compute_all_derived_metrics output.

    Parameters
    ----------
    set_id:
        Identifier for the set this summary belongs to.
    pack_cost:
        Cost per pack used in the simulation run.
    simulation_version:
        Version tag of the simulation engine (e.g. "v2").
    computed_at:
        ISO-8601 timestamp of when the computation was performed.
    all_metrics:
        Dict returned by :func:`compute_all_derived_metrics`.
    product_id:
        Optional product identifier (ETB, booster box, etc.).

    Returns
    -------
    :class:`PackSimulationSummary`
    """
    pm = all_metrics.get("pack_decision_metrics", {})
    cm = all_metrics.get("chase_dependency_metrics") or {}
    sm = all_metrics.get("session_metrics") or {}
    pth = all_metrics.get("packs_to_hit_metrics") or {}
    idx = all_metrics.get("pack_score") or {}

    return PackSimulationSummary(
        set_id=set_id,
        product_id=product_id,
        pack_cost=float(pack_cost),
        simulation_version=simulation_version,
        score_version=str(idx.get("score_version", "v1")),
        computed_at=computed_at,
        n_pack_runs=int(pm.get("n_runs", 0)),
        n_session_runs=int(sm["n_runs"]) if sm.get("n_runs") is not None else None,
        mean_value=float(pm.get("mean", 0.0)),
        median_value=float(pm.get("median", 0.0)),
        p95_value=pm.get("p95"),
        std_dev=float(pm.get("std_dev", 0.0)),
        coefficient_of_variation=pm.get("coefficient_of_variation"),
        prob_profit=float(pm.get("prob_profit", 0.0)),
        prob_big_hit_fixed=pm.get("prob_big_hit_fixed"),
        big_hit_threshold_fixed=pm.get("big_hit_threshold_fixed"),
        prob_big_hit_dynamic=pm.get("prob_big_hit_dynamic"),
        big_hit_threshold_dynamic=pm.get("big_hit_threshold_dynamic"),
        expected_loss_given_loss=pm.get("expected_loss_given_loss"),
        median_loss_given_loss=pm.get("median_loss_given_loss"),
        expected_loss_unconditional=float(pm.get("expected_loss_unconditional", 0.0)),
        top1_ev_share=cm.get("top1_ev_share"),
        top3_ev_share=cm.get("top3_ev_share"),
        top5_ev_share=cm.get("top5_ev_share"),
        prob_box_profit=sm.get("prob_box_profit"),
        expected_box_value=sm.get("expected_box_value"),
        median_box_value=sm.get("median_box_value"),
        prob_no_chase_hit_in_box=sm.get("prob_no_chase_hit_in_box"),
        expected_packs_to_hit=pth.get("expected_packs_to_hit"),
        median_packs_to_hit=pth.get("median_packs_to_hit"),
        profit_score=idx.get("profit_score"),
        safety_score=idx.get("safety_score"),
        stability_score=idx.get("stability_score"),
        pack_score=idx.get("pack_score"),
        p95_value_to_cost_ratio=((idx.get("raw_inputs") or {}).get("p95_value_to_cost_ratio")),
    )


# ---------------------------------------------------------------------------
# Console print helper
# ---------------------------------------------------------------------------

def _fmt_pct(value: Optional[float], decimals: int = 1) -> str:
    """Format a 0-1 probability as a percentage string, or 'N/A'."""
    if value is None:
        return "N/A"
    return f"{value * 100:.{decimals}f}%"


def _fmt_dollar(value: Optional[float]) -> str:
    """Format a dollar value, or 'N/A'."""
    if value is None:
        return "N/A"
    return f"${value:.2f}"


def _fmt_float(value: Optional[float], decimals: int = 2) -> str:
    if value is None:
        return "N/A"
    return f"{value:.{decimals}f}"


def print_derived_metrics_summary(all_metrics: Dict[str, Any]) -> None:
    """Print derived decision metrics to the console in the project's standard format."""
    pm = all_metrics.get("pack_decision_metrics") or {}
    cm = all_metrics.get("chase_dependency_metrics") or {}
    sm = all_metrics.get("session_metrics") or {}
    pth = all_metrics.get("packs_to_hit_metrics") or {}
    idx = all_metrics.get("pack_score") or {}

    sep = "-" * 50
    n_runs = pm.get("n_runs", 0)
    pack_cost = pm.get("pack_cost")

    print(f"\n=== Derived Decision Metrics ({n_runs:,} pack simulations) ===")

    # --- Should I Open This? ---
    print(sep)
    print("Should I Open This?")
    print(sep)
    print(f"  Pack Cost:                    {_fmt_dollar(pack_cost)}")
    print(f"  Prob. of Profit:              {_fmt_pct(pm.get('prob_profit'))}")
    if pm.get("prob_big_hit_fixed") is not None:
        print(f"  Prob. Big Hit (≥{_fmt_dollar(pm.get('big_hit_threshold_fixed'))}):     {_fmt_pct(pm.get('prob_big_hit_fixed'))}")
    if pm.get("prob_big_hit_dynamic") is not None:
        mode = pm.get("big_hit_dynamic_mode", "")
        thr = pm.get("big_hit_threshold_dynamic")
        if mode == "cost_multiple":
            dynamic_param = pm.get("big_hit_dynamic_param")
            print(
                "  Prob. Big Hit "
                f"(dynamic threshold = {dynamic_param}x pack cost, >= {_fmt_dollar(thr)}): "
                f"{_fmt_pct(pm.get('prob_big_hit_dynamic'))}"
            )
        elif mode == "percentile":
            dynamic_param = pm.get("big_hit_dynamic_param")
            print(
                "  Prob. Big Hit "
                f"(dynamic threshold = value p{_fmt_float(dynamic_param)}, >= {_fmt_dollar(thr)}): "
                f"{_fmt_pct(pm.get('prob_big_hit_dynamic'))}"
            )
        else:
            print(
                f"  Prob. Big Hit (dynamic mode={mode}, >= {_fmt_dollar(thr)}): "
                f"{_fmt_pct(pm.get('prob_big_hit_dynamic'))}"
            )
    print(f"  Exp. Loss (when losing):      {_fmt_dollar(pm.get('expected_loss_given_loss'))}")
    print(f"  Median Loss (when losing):    {_fmt_dollar(pm.get('median_loss_given_loss'))}")
    print(f"  Exp. Loss (per pack, all):    {_fmt_dollar(pm.get('expected_loss_unconditional'))}")

    if sm:
        n_packs = sm.get("n_packs")
        n_sess = sm.get("n_runs", 0)
        sess_cost = sm.get("session_cost")
        label = f"{n_packs}-pack session"
        print()
        print(f"  --- {label} ({n_sess:,} simulated sessions) ---")
        print(f"  Session Cost:               {_fmt_dollar(sess_cost)}")
        print(f"  Prob. Box/Session Profit:   {_fmt_pct(sm.get('prob_box_profit'))}")
        print(f"  Expected Session Value:     {_fmt_dollar(sm.get('expected_box_value'))}")
        print(f"  Median Session Value:       {_fmt_dollar(sm.get('median_box_value'))}")
        print(f"  Prob. No Chase Hit:         {_fmt_pct(sm.get('prob_no_chase_hit_in_box'))}")

    # --- Risk Profile ---
    print()
    print(sep)
    print("Risk Profile")
    print(sep)
    print(f"  Mean Pack Value:              {_fmt_dollar(pm.get('mean'))}")
    print(f"  Median Pack Value:            {_fmt_dollar(pm.get('median'))}")
    print(f"  Std Dev:                      {_fmt_dollar(pm.get('std_dev'))}")
    cv = pm.get("coefficient_of_variation")
    print(f"  Coefficient of Variation:     {_fmt_float(cv)}")
    print(f"  Tail Value (p05):             {_fmt_dollar(pm.get('tail_value_p05'))}")

    # --- EV Composition ---
    ev_comp = all_metrics.get("ev_composition_metrics")
    if ev_comp:
        print()
        print(sep)
        print("EV Composition")
        print(sep)
        print(f"  Total Pack EV:                {_fmt_dollar(ev_comp.get('total_pack_ev'))}")
        print(f"  Hit EV:                       {_fmt_dollar(ev_comp.get('hit_ev'))}")
        print(f"  Non-Hit EV:                   {_fmt_dollar(ev_comp.get('non_hit_ev'))}")
        print(f"  Hit EV Share of Pack EV:      {_fmt_pct(ev_comp.get('hit_ev_share_of_pack_ev'))}")
        if ev_comp.get('hit_cards_count') is not None:
            print(f"  Hit Cards Tracked:            {ev_comp.get('hit_cards_count')}")

    # --- What Am I Chasing? ---
    if cm:
        print()
        print(sep)
        print("What Am I Chasing?")
        print(sep)
        print(f"  Cards tracked:              {cm.get('n_cards', 0)}")
        print(f"  Total card EV:              {_fmt_dollar(cm.get('total_ev'))}")
        print(f"  Top-1 card EV share:        {_fmt_pct(cm.get('top1_ev_share'))}")
        print(f"  Top-3 card EV share:        {_fmt_pct(cm.get('top3_ev_share'))}")
        print(f"  Top-5 card EV share:        {_fmt_pct(cm.get('top5_ev_share'))}")

    if pth:
        print()
        print(f"  Exp. packs to hit target:   {_fmt_float(pth.get('expected_packs_to_hit'))}")
        print(f"  Median packs to hit target: {_fmt_float(pth.get('median_packs_to_hit'))}")

    # --- PACK Score ---
    if idx:
        print()
        print(sep)
        print(f"PACK Score  (version: {idx.get('score_version', 'pack_score_v1')})")
        print(sep)
        print(f"  PACK Score:                 {_fmt_float(idx.get('pack_score'))} / 100")
        print(f"  --- Component Breakdown ---")
        weights = idx.get("weights", {}).get("pack_score", {})
        if not weights:
            weights = idx.get("weights_normalized", {}).get("pack_score", {})
        print(
            f"  Profit Score  (w={_fmt_float(weights.get('profit_score', 0.40), 2)}):    "
            f"{_fmt_float(idx.get('profit_score'))}"
        )
        print(
            f"  Safety Score  (w={_fmt_float(weights.get('safety_score', 0.30), 2)}):    "
            f"{_fmt_float(idx.get('safety_score'))}"
        )
        print(
            f"  Stability Score (w={_fmt_float(weights.get('stability_score', 0.30), 2)}): "
            f"{_fmt_float(idx.get('stability_score'))}"
        )

        if idx.get("score_version") in {
            "pack_score_v2_runtime",
            "pack_score_v2_1_runtime",
            "pack_score_v2_2_runtime",
            "pack_score_v2_3_runtime",
            "pack_score_v2_chase_weighted",
        }:
            print()
            print("[PACK_SCORE_V2_RUNTIME]")
            print(f"  score_version:               {idx.get('score_version')}")
            print(f"  normalization_mode:          {idx.get('normalization_mode')}")
            print(f"  pack_score_is_placeholder:   {idx.get('pack_score_is_placeholder')}")

            raw_inputs = idx.get("raw_inputs") or {}
            normalized_inputs = idx.get("normalized_inputs") or {}

            print("  raw.inputs:")
            for key in (
                "prob_profit",
                "mean_value_to_cost_ratio",
                "median_value_to_cost_ratio",
                "p95_value_to_cost_ratio",
                "expected_loss_when_losing",
                "median_loss_when_losing",
                "expected_loss_when_losing_ratio",
                "median_loss_when_losing_ratio",
                "p05_shortfall_to_cost",
                "coefficient_of_variation",
                "hhi_ev_concentration",
                "effective_chase_count",
            ):
                if key in raw_inputs:
                    print(f"    {key}: {raw_inputs.get(key)}")

            if normalized_inputs:
                print("  normalized.inputs:")
                for key, payload in normalized_inputs.items():
                    print(
                        "    "
                        f"{key}: value={payload.get('value')}, "
                        f"score={payload.get('score')}, "
                        f"min={payload.get('min')}, "
                        f"max={payload.get('max')}, "
                        f"direction={payload.get('direction')}"
                    )

            print(
                f"  component_scores:            profit={idx.get('profit_score')}, "
                f"safety={idx.get('safety_score')}, stability={idx.get('stability_score')}"
            )
            print(f"  final_pack_score:            {idx.get('pack_score')}")
            print(f"  hhi_ev_concentration:        {raw_inputs.get('hhi_ev_concentration')}")
            print(f"  effective_chase_count:       {raw_inputs.get('effective_chase_count')}")

    print(sep)
