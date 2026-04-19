"""Derived decision-metrics layer for pack simulation output.

This module consumes simulation outcomes produced by the Monte Carlo simulation
engine and returns structured, product-facing metrics.  It is intentionally
kept separate from:

  * the simulation engine  (monteCarloSimV2 / monteCarloSim)
  * validation / calibration modules
  * front-end glue code

Layering contract
-----------------
  simulation layer    →  produces raw outcome arrays (values, slot logs, …)
  derived metrics     →  interprets those outcomes into product metrics
  persistence/UI      →  stores or presents the derived metrics

Nothing in this file runs a simulation from scratch.
All public functions accept pre-computed simulation outputs as inputs.

Metric definitions
------------------
prob_profit
    Fraction of simulated packs whose total value is >= pack_cost.
    Direct count, no smoothing.

prob_big_hit_fixed
    Fraction of simulated packs whose total value is >= a fixed absolute
    threshold supplied by the caller.

prob_big_hit_dynamic
    Fraction of simulated packs whose total value is >= a threshold derived
    at call time.  Two modes are supported:
      "cost_multiple"  – threshold = param * pack_cost  (e.g. 5×)
      "percentile"     – threshold = the p-th percentile of the distribution

expected_loss_given_loss
    Mean of (pack_cost − value) over *only* the runs where value < pack_cost.
    Represents: "when you lose, how much do you lose on average?"

median_loss_given_loss
    Median of (pack_cost − value) over losing runs only.

expected_loss_unconditional
    Mean of max(pack_cost − value, 0) over *all* runs.
    Represents: "per pack, what is the average downside burden?"
    This is always <= expected_loss_given_loss * (1 − prob_profit).

coefficient_of_variation (CV)
    std_dev / mean_value.  Normalized volatility.  None if mean_value <= 0.

top1_ev_share / top3_ev_share / top5_ev_share
    The EV fraction contributed by the single highest / top-3 / top-5 cards,
    computed from a caller-supplied card_ev_contributions dict.

prob_box_profit / expected_box_value / median_box_value
    Session-level (box or ETB) metrics computed by *simulating* sessions
    as repeated pack draws — not by approximating from pack averages.

prob_no_chase_hit_in_box
    Fraction of simulated sessions where zero chase hits were obtained.
    Requires the caller to supply a chase-hit detection callable.

expected_packs_to_hit / median_packs_to_hit
    Estimated number of packs needed to obtain at least one qualifying hit,
    derived from repeated simulation runs each continued until a hit lands.
    Fails explicitly if the target rarity/card is unavailable in the model.

ind_ex_score_v1
    A bounded 0–100 score (version "v1") combining:
      • probability-of-profit component   (weight w1, default 0.40)
      • stability component               (weight w2, default 0.30)
      • diversification component         (weight w3, default 0.30)
    Each component is normalized to [0, 1] before weighting.
    Stability  = 1 − clamp(CV / CV_MAX, 0, 1)  where CV_MAX = 5.0
    Diversification = 1 − clamp(top5_ev_share, 0, 1)
    The score and all component values are always returned together so the
    calculation can be audited.
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
        }
        if return_ranked_cards:
            result["ranked_cards"] = []
        return result

    # Rank by contribution descending; treat negatives as 0 in share math
    ranked: List[Tuple[str, float]] = sorted(
        card_ev_contributions.items(), key=lambda kv: kv[1], reverse=True
    )
    contributions = [max(0.0, float(v)) for _, v in ranked]
    total_ev = float(sum(contributions))
    n_cards = len(contributions)

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
# Goal 8 — inDex Score v1
# ---------------------------------------------------------------------------

#: Maximum CV used as the ceiling for stability normalization.
#: A CV of this value or above maps to 0 stability.  Hard-coded per v1 spec.
_CV_MAX_V1: float = 5.0

#: Default weights for ind_ex_score_v1 components.
_DEFAULT_WEIGHTS_V1: Tuple[float, float, float] = (0.40, 0.30, 0.30)


def compute_index_score_v1(
    prob_profit: float,
    coefficient_of_variation: Optional[float],
    top5_ev_share: Optional[float],
    *,
    weights: Optional[Tuple[float, float, float]] = None,
    cv_max: float = _CV_MAX_V1,
) -> Dict[str, Any]:
    """Compute the inDex Score v1 — a bounded, explainable 0–100 product score.

    Formula
    -------
    Three components, each normalized to [0, 1]:

      prob_profit_component   =  clamp(prob_profit, 0, 1)
      stability_component     =  1 − clamp(CV / cv_max, 0, 1)
      diversification_component = 1 − clamp(top5_ev_share, 0, 1)

    score_raw = w1 * pp + w2 * stab + w3 * div
    ind_ex_score_v1 = round(100 * score_raw, 2)

    Missing inputs (None) fall back to neutral values:
      CV = None      → stability_component = 0.5  (moderate, not zero)
      top5 = None    → diversification_component = 0.5

    These fallbacks are explicit and surfaced in the breakdown.

    Parameters
    ----------
    prob_profit:
        Probability of profit in [0, 1].
    coefficient_of_variation:
        CV from compute_volatility_metrics, may be None.
    top5_ev_share:
        Top-5-card EV share from compute_chase_dependency_metrics, may be None.
    weights:
        (w1, w2, w3) tuple, must sum to 1.0.  Defaults to (0.40, 0.30, 0.30).
    cv_max:
        CV ceiling for stability normalization.  Do not change this for v1
        scores — use a new score version instead.

    Returns
    -------
    dict with keys:
        ind_ex_score_v1, score_version, score_raw,
        weights (tuple),
        prob_profit_component,
        stability_component, cv_used, cv_max,
        diversification_component, top5_ev_share_used.
    """
    w1, w2, w3 = weights if weights is not None else _DEFAULT_WEIGHTS_V1

    weight_sum = w1 + w2 + w3
    if not math.isclose(weight_sum, 1.0, abs_tol=1e-6):
        raise ValueError(
            f"Weights must sum to 1.0 (got {weight_sum:.8f}).  "
            "Adjust the weights tuple."
        )

    pp_component = _clamp(float(prob_profit), 0.0, 1.0)

    if coefficient_of_variation is None:
        stab_component = 0.5
        cv_used = None
    else:
        cv_used = float(coefficient_of_variation)
        stab_component = 1.0 - _clamp(cv_used / float(cv_max), 0.0, 1.0)

    if top5_ev_share is None:
        div_component = 0.5
        top5_used = None
    else:
        top5_used = _clamp(float(top5_ev_share), 0.0, 1.0)
        div_component = 1.0 - top5_used

    score_raw = w1 * pp_component + w2 * stab_component + w3 * div_component
    ind_ex_score = round(100.0 * score_raw, 2)

    return {
        "ind_ex_score_v1": ind_ex_score,
        "score_version": "v1",
        "score_raw": score_raw,
        "weights": (w1, w2, w3),
        "prob_profit_component": pp_component,
        "stability_component": stab_component,
        "cv_used": cv_used,
        "cv_max": float(cv_max),
        "diversification_component": div_component,
        "top5_ev_share_used": top5_used if top5_ev_share is not None else None,
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
        (w1, w2, w3) for the inDex Score.  Defaults to (0.40, 0.30, 0.30).
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
        index_score.
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

    top5 = chase_metrics["top5_ev_share"] if chase_metrics is not None else None
    idx_score = compute_index_score_v1(
        prob_profit=pack_metrics["prob_profit"],
        coefficient_of_variation=pack_metrics["coefficient_of_variation"],
        top5_ev_share=top5,
        weights=index_score_weights,
    )

    return {
        "pack_decision_metrics": pack_metrics,
        "chase_dependency_metrics": chase_metrics,
        "ev_composition_metrics": ev_comp_metrics,
        "session_metrics": sess_metrics,
        "packs_to_hit_metrics": pth_metrics,
        "index_score": idx_score,
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

    # --- Score ---
    ind_ex_score_v1: Optional[float]


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
    idx = all_metrics.get("index_score") or {}

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
        ind_ex_score_v1=idx.get("ind_ex_score_v1"),
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
    idx = all_metrics.get("index_score") or {}

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

    # --- inDex Score ---
    if idx:
        print()
        print(sep)
        print(f"inDex Score  (version: {idx.get('score_version', 'v1')})")
        print(sep)
        print(f"  Score:                      {_fmt_float(idx.get('ind_ex_score_v1'))} / 100")
        print(f"  --- Component Breakdown ---")
        w = idx.get("weights", (0.40, 0.30, 0.30))
        print(f"  Prob. Profit  (w={w[0]:.2f}):     {_fmt_float(idx.get('prob_profit_component'))}")
        print(f"  Stability     (w={w[1]:.2f}):     {_fmt_float(idx.get('stability_component'))}  (CV={_fmt_float(idx.get('cv_used'))}, max={_fmt_float(idx.get('cv_max'))})")
        print(f"  Diversif.     (w={w[2]:.2f}):     {_fmt_float(idx.get('diversification_component'))}  (top5 share={_fmt_pct(idx.get('top5_ev_share_used'))})")

    print(sep)
