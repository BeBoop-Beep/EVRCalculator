"""Weighted four-component RIP (v3), set-value association, pillar diagnostics.

    RIP = w_profit*Profit + w_safety*Safety + w_stability*Stability
          + w_desirability*Desirability

Weights are read from :mod:`backend.desirability.scoring_config` (reasoned
defaults, never hardcoded at call sites, never fitted to price/value). There
are **no caps or clamps** on desirability's contribution - its influence is
bounded linearly by its small weight. When a component is absent (a user
weight of 0, or missing data for a set) the remaining weights renormalize
proportionally to 1.0 via the single config renormalization rule.

Set-value association is a DESCRIPTIVE DIAGNOSTIC, not a gate. An earlier
design auto-forced desirability's weight to 0 when its Spearman against total
set value fell below 0.50; that was removed deliberately. Universal Set
Desirability excludes scarcity/Treatment/price by construction, while price is
jointly produced by demand, scarcity, prestige, supply, and age - so demanding
that the pure score reproduce price would optimize it back toward price
contamination. See ``scoring_config.SET_VALUE_ASSOCIATION_DISCLOSURE`` and the
card-level amplification study for the real construct validation.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from backend.desirability.scoring_config import (
    DEFAULT_RIP_WEIGHTS,
    DESIRABILITY_ADJUSTMENT_BASELINE,
    DESIRABILITY_ADJUSTMENT_CAP,
    DESIRABILITY_ADJUSTMENT_DIVISOR,
    FINANCIAL_PILLARS,
    FINANCIAL_RIP_V2_LEGACY_VERSION,
    FINANCIAL_RIP_V2_VERSION,
    FINANCIAL_RIP_WEIGHTS,
    OVERALL_RIP_EFFECTIVE_WEIGHTS,
    OVERALL_RIP_V4_VERSION,
    OVERALL_RIP_WEIGHTS,
    RIP_V3_VERSION,
    SET_VALUE_ASSOCIATION_DISCLOSURE,
    SET_VALUE_ASSOCIATION_PRIOR_BENCHMARK,
    WEIGHT_SENSITIVITY_ALTERNATIVES,
    WEIGHTS_DISCLOSURE,
    renormalize_weights,
    resolve_rip_weights,
    rip_weights_payload,
)


def _as_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


# ---------------------------------------------------------------------------
# Rank / correlation helpers (tie-corrected average ranks)
# ---------------------------------------------------------------------------

def average_ranks(values: Sequence[float]) -> List[float]:
    """Average (midrank) ranks, 1-based, ties share the mean rank."""
    indexed = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    position = 0
    while position < len(indexed):
        tie_end = position
        while (
            tie_end + 1 < len(indexed)
            and values[indexed[tie_end + 1]] == values[indexed[position]]
        ):
            tie_end += 1
        mean_rank = (position + tie_end) / 2.0 + 1.0
        for tie_index in range(position, tie_end + 1):
            ranks[indexed[tie_index]] = mean_rank
        position = tie_end + 1
    return ranks


def pearson(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    n = len(xs)
    if n < 3 or n != len(ys):
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x <= 0 or var_y <= 0:
        return None
    return cov / math.sqrt(var_x * var_y)


def spearman(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    return pearson(average_ranks(xs), average_ranks(ys))


def paired_finite(rows: Iterable[Mapping[str, Any]], x_key: str, y_key: str) -> Tuple[List[float], List[float]]:
    xs: List[float] = []
    ys: List[float] = []
    for row in rows:
        x = _as_float(row.get(x_key))
        y = _as_float(row.get(y_key))
        if x is None or y is None:
            continue
        xs.append(x)
        ys.append(y)
    return xs, ys


# ---------------------------------------------------------------------------
# Set-value association (descriptive diagnostic - NOT a gate)
# ---------------------------------------------------------------------------

def evaluate_set_value_association(
    rows: Iterable[Mapping[str, Any]],
    *,
    desirability_key: str = "score",
    set_value_key: str = "set_value",
    prior_benchmark_spearman: Optional[float] = None,
) -> Dict[str, Any]:
    """Correlate Universal Set Desirability v3 with set value across sets.

    Reported for transparency only. There is deliberately no pass/fail here
    and no ``clearedToInfluenceRip`` flag: a price-independent construct is not
    expected to reproduce price, and gating on this number would optimize the
    score back toward price contamination. Construct validation lives in the
    card-level amplification study instead.

    ``rows`` should be the ``desirabilityCoverage=full`` sets that also carry
    a set value.
    """
    xs, ys = paired_finite(rows, desirability_key, set_value_key)
    spearman_rho = spearman(xs, ys)
    pearson_r = pearson(xs, ys)
    return {
        "n": len(xs),
        "spearman": round(spearman_rho, 4) if spearman_rho is not None else None,
        "pearson": round(pearson_r, 4) if pearson_r is not None else None,
        "isDiagnosticOnly": True,
        "priorScoreBenchmarkSpearman": (
            prior_benchmark_spearman
            if prior_benchmark_spearman is not None
            else SET_VALUE_ASSOCIATION_PRIOR_BENCHMARK
        ),
        "disclosure": SET_VALUE_ASSOCIATION_DISCLOSURE,
        "policy": (
            "Descriptive only. Desirability's RIP weight comes from the config "
            "defaults and is never auto-zeroed by this correlation."
        ),
    }


# ---------------------------------------------------------------------------
# Weighted RIP (Phase 10)
# ---------------------------------------------------------------------------

def compute_weighted_rip(
    pillar_scores: Mapping[str, Any],
    *,
    weights: Optional[Mapping[str, float]] = None,
    include_desirability: bool = True,
) -> Dict[str, Any]:
    """Linear four-component RIP from config weights.

    - Missing FINANCIAL components are dropped and the remaining weights
      renormalize to 1.0.
    - A missing DESIRABILITY pillar does NOT renormalize. When desirability
      carries weight in the model but no value is available, the canonical RIP
      is reported as unavailable (``score=None``, ``status="incomplete"``). See
      the missing-pillar policy below.
    - ``include_desirability`` is a configuration switch only. It is NOT driven
      by any price or set-value correlation - see the module docstring.
    - The final score is clamped to 0-100 purely as a numeric safety net,
      never as an influence cap.
    - Returns None score if no financial pillar is available.

    MISSING-PILLAR POLICY (explicit, and deliberately not silent)
    ------------------------------------------------------------
    Renormalizing Profit/Safety/Stability to 100% when Collector Appeal is
    missing produces a number that LOOKS like a canonical RIP, sorts alongside
    real canonical RIPs, and is not comparable to them. A fixed-contents product
    would then out- or under-rank real booster sets purely because a pillar was
    absent - the absence of evidence rendered as a competitive score. That is
    the option-C behaviour this codebase shipped by accident, as a side effect of
    the renormalization rule rather than as a decision.

    The policy is option B: canonical RIP is unavailable when a weighted pillar
    is missing. Financial-only numbers remain available under the distinct
    ``financial_rip_v2`` label via :func:`compute_financial_rip`, and are echoed
    here under ``financialOnly`` so a caller can display them - clearly labelled
    as financial-only, never as RIP, and never ranked in the canonical cohort.

    Two ways desirability legitimately leaves the model, neither of which is a
    missing pillar:
      * ``include_desirability=False`` - the caller explicitly asked for the
        financial-only view.
      * configured weight of 0 - desirability is not part of the model at all.
    In both cases the remaining weights renormalize as before and the result is
    a valid, comparable financial RIP.
    """
    base = resolve_rip_weights(weights, include_desirability=True)
    values = {key: _as_float(pillar_scores.get(key)) for key in base}
    desirability_weighted = base.get("desirability", 0.0) > 0.0
    desirability_missing = (
        include_desirability and desirability_weighted and values.get("desirability") is None
    )
    if not include_desirability:
        values["desirability"] = None

    present = {key: value for key, value in values.items() if value is not None and base.get(key, 0.0) > 0.0}
    if not any(key in present for key in FINANCIAL_PILLARS):
        return {
            "score": None,
            "version": RIP_V3_VERSION,
            "status": "unavailable_no_financial_pillar",
            "components": {},
            **rip_weights_payload(base),
            "effectiveWeights": {},
            "desirabilityIncluded": bool(include_desirability),
            "rankable": False,
        }

    if desirability_missing:
        # Do NOT renormalize the financial pillars into a canonical-looking RIP.
        financial = compute_financial_rip(pillar_scores, weights=weights)
        return {
            "score": None,
            "version": RIP_V3_VERSION,
            "status": "incomplete_missing_desirability",
            "statusReason": (
                "Collector Appeal is unavailable for this product, so the canonical "
                "four-pillar RIP cannot be computed. Financial-only scores are "
                "reported separately and are NOT comparable to a canonical RIP."
            ),
            "missingPillars": ["desirability"],
            "components": {},
            **rip_weights_payload(base),
            "effectiveWeights": {},
            "desirabilityIncluded": False,
            "rankable": False,
            "financialOnly": {
                "score": financial.get("score"),
                "version": financial.get("version"),
                "label": "Financial-only score. Not a RIP score; not comparable to canonical RIP.",
                "components": financial.get("components"),
            },
        }

    effective = renormalize_weights({key: base[key] for key in present})
    score = sum(present[key] * weight for key, weight in effective.items())
    components = {
        key: {
            "score": round(present[key], 4),
            "weight": round(effective[key], 6),
            "contribution": round(present[key] * effective[key], 4),
        }
        for key in effective
    }
    # The legacy label, not `financial_rip_v2_60_25_15`: this branch renormalizes
    # the four-pillar weights and is a different model from the shipping
    # Financial RIP, so it must not borrow its version string.
    version = RIP_V3_VERSION if "desirability" in effective else FINANCIAL_RIP_V2_LEGACY_VERSION
    return {
        "score": round(max(0.0, min(100.0, score)), 4),
        "version": version,
        "components": components,
        **rip_weights_payload(base),
        "effectiveWeights": {key: round(value, 6) for key, value in effective.items()},
        "desirabilityIncluded": "desirability" in effective,
    }


def compute_financial_rip(
    pillar_scores: Mapping[str, Any],
    *,
    weights: Optional[Mapping[str, float]] = None,
) -> Dict[str, Any]:
    """Financial RIP: exactly 0.60*Profit + 0.25*Safety + 0.15*Stability.

    The weights sum to 1.00 across the three pillars, so the published weight is
    the applied weight. The previous implementation delegated to the four-pillar
    blend with desirability excluded, which renormalized 0.58/0.20/0.12 up to
    0.644/0.222/0.133 - the displayed weights were never the arithmetic.

    Desirability is not a pillar here and cannot be passed as one; it enters via
    :func:`compute_overall_rip`.

    A missing pillar makes Financial RIP UNAVAILABLE rather than renormalizing
    the survivors. Renormalizing would emit a number that looks like a Financial
    RIP, sorts against real ones, and silently means something else - a set
    missing Stability would be scored purely on Profit and Safety and compared
    to sets scored on all three.
    """
    resolved = dict(FINANCIAL_RIP_WEIGHTS)
    if weights:
        for key, value in weights.items():
            if key in resolved:
                resolved[key] = float(value)

    values = {key: _as_float(pillar_scores.get(key)) for key in FINANCIAL_PILLARS}
    missing = sorted(key for key, value in values.items() if value is None)
    if missing:
        return {
            "score": None,
            "version": FINANCIAL_RIP_V2_VERSION,
            "status": "unavailable_missing_financial_pillar",
            "statusReason": (
                "Financial RIP needs all three simulation pillars. Missing: "
                + ", ".join(missing)
                + ". The present pillars are NOT renormalized into a comparable score."
            ),
            "missingPillars": missing,
            "components": {},
            "weights": {key: round(value, 6) for key, value in resolved.items()},
            "weightsLabel": WEIGHTS_DISCLOSURE,
            "rankable": False,
        }

    score = sum(values[key] * resolved[key] for key in FINANCIAL_PILLARS)
    return {
        "score": round(max(0.0, min(100.0, score)), 4),
        "version": FINANCIAL_RIP_V2_VERSION,
        "components": {
            key: {
                "score": round(values[key], 4),
                "weight": round(resolved[key], 6),
                "contribution": round(values[key] * resolved[key], 4),
            }
            for key in FINANCIAL_PILLARS
        },
        "weights": {key: round(value, 6) for key, value in resolved.items()},
        "weightsLabel": WEIGHTS_DISCLOSURE,
        "rankable": True,
    }


def compute_desirability_adjustment(
    universal_desirability_score: Any,
    *,
    cap: float = DESIRABILITY_ADJUSTMENT_CAP,
) -> Dict[str, Any]:
    """SUPERSEDED. ``clamp((D - 50) / 10, -cap, +cap)``, with the clamp reported.

    This was the additive, capped desirability adjustment of the retired Overall
    RIP v3. It is NO LONGER part of the authoritative scoring path:
    :func:`compute_overall_rip` now blends Financial RIP with CA7 and never calls
    this. The function is retained ONLY for the historical cap-selection research
    (``build_desirability_cap_study.py``); do not wire it back into scoring.
    """
    score = _as_float(universal_desirability_score)
    if score is None:
        return {
            "adjustment": None,
            "rawAdjustment": None,
            "clamped": False,
            "cap": cap,
            "baseline": DESIRABILITY_ADJUSTMENT_BASELINE,
        }
    raw = (score - DESIRABILITY_ADJUSTMENT_BASELINE) / DESIRABILITY_ADJUSTMENT_DIVISOR
    adjustment = max(-cap, min(cap, raw))
    return {
        "adjustment": round(adjustment, 4),
        "rawAdjustment": round(raw, 4),
        "clamped": abs(raw) > cap,
        "cap": cap,
        "baseline": DESIRABILITY_ADJUSTMENT_BASELINE,
        "formula": "clamp((universal_set_desirability - 50) / 10, -cap, +cap)",
    }


def compute_overall_rip(
    pillar_scores: Mapping[str, Any],
    opening_desirability_score: Any,
    *,
    weights: Optional[Mapping[str, float]] = None,
) -> Dict[str, Any]:
    """Overall RIP = 0.90 * Financial RIP + 0.10 * CA7 Opening Desirability.

    A weighted blend, with NO cap, NO recentering, and NO additive adjustment.
    The full internal precision of both inputs is preserved; the final score is
    clamped to 0-100 purely as a numeric safety net, never as an influence cap.

    REQUIRES BOTH a valid Financial RIP and a valid CA7 Opening Desirability
    score (already on the 0-100 scale). When CA7 is missing, Overall RIP is
    UNAVAILABLE with a precise reason - it deliberately does NOT fall back to
    Universal Set Desirability. Universal Set Desirability already enters Overall
    RIP once, as CA7's D base; substituting it for CA7 would both double-count it
    and mix two different constructs in one leaderboard column.

    ``opening_desirability_score`` is the CA7 score (0-100), the SAME number the
    Collector Appeal service publishes under ``collectorAppeal.score``. The
    financial-only Financial RIP and the Universal Set Desirability score both
    remain available to a caller even when this returns unavailable.
    """
    financial = compute_financial_rip(pillar_scores, weights=weights)
    financial_score = financial.get("score")
    ca7_score = _as_float(opening_desirability_score)

    w_financial = OVERALL_RIP_WEIGHTS["financial_rip"]
    w_ca7 = OVERALL_RIP_WEIGHTS["opening_desirability"]

    if financial_score is None or ca7_score is None:
        missing = list(financial.get("missingPillars") or [])
        if ca7_score is None:
            missing.append("opening_desirability_ca7")
        return {
            "score": None,
            "version": OVERALL_RIP_V4_VERSION,
            "status": "unavailable_missing_input",
            "statusReason": (
                "Overall RIP needs a valid Financial RIP and a valid CA7 Opening "
                "Desirability score. Missing: " + ", ".join(missing) + ". CA7 is "
                "never substituted with Universal Set Desirability."
            ),
            "missingInputs": missing,
            "financialRip": financial,
            "openingDesirability": {"score": ca7_score},
            "rankable": False,
        }

    financial_contribution = w_financial * financial_score
    ca7_contribution = w_ca7 * ca7_score
    score = max(0.0, min(100.0, financial_contribution + ca7_contribution))
    return {
        "score": round(score, 4),
        "version": OVERALL_RIP_V4_VERSION,
        "financialRip": financial,
        "openingDesirability": {
            "score": round(ca7_score, 4),
            "weight": round(w_ca7, 6),
            "contribution": round(ca7_contribution, 4),
        },
        "components": {
            "financialRip": {
                "score": round(financial_score, 4),
                "weight": round(w_financial, 6),
                "contribution": round(financial_contribution, 4),
            },
            "openingDesirability": {
                "score": round(ca7_score, 4),
                "weight": round(w_ca7, 6),
                "contribution": round(ca7_contribution, 4),
            },
        },
        "weights": {key: round(value, 6) for key, value in OVERALL_RIP_WEIGHTS.items()},
        "effectiveWeights": {
            key: round(value, 6) for key, value in OVERALL_RIP_EFFECTIVE_WEIGHTS.items()
        },
        "formula": "0.90 * financial_rip + 0.10 * opening_desirability_ca7",
        "rankable": True,
    }


# ---------------------------------------------------------------------------
# Desirability-influence report (Phase 10, results-doc transparency)
# ---------------------------------------------------------------------------

def build_desirability_influence_report(
    rows: Sequence[Mapping[str, Any]],
    *,
    pillar_keys: Mapping[str, str] = None,
    id_key: str = "set_id",
    name_key: str = "set_name",
    top_movers: int = 10,
) -> Dict[str, Any]:
    """RIP-with vs RIP-without desirability per set, with rank deltas.

    Transparency evidence only - there is no cap to select and nothing here
    feeds back into the weights.
    """
    keys = dict(pillar_keys or {
        "profit": "profit_score",
        "safety": "safety_score",
        "stability": "stability_score",
        "desirability": "desirability_score",
    })
    entries: List[Dict[str, Any]] = []
    for row in rows:
        pillars = {pillar: row.get(source) for pillar, source in keys.items()}
        with_result = compute_weighted_rip(pillars, include_desirability=True)
        without_result = compute_financial_rip(pillars)
        with_score = with_result.get("score")
        without_score = without_result.get("score")
        entries.append(
            {
                "set_id": row.get(id_key),
                "set_name": row.get(name_key),
                "desirability_score": _as_float(pillars.get("desirability")),
                "rip_with_desirability": with_score,
                "rip_without_desirability": without_score,
                "score_delta": (
                    round(with_score - without_score, 4)
                    if with_score is not None and without_score is not None
                    else None
                ),
            }
        )

    _assign_ranks(entries, "rip_with_desirability", "rank_with")
    _assign_ranks(entries, "rip_without_desirability", "rank_without")
    for entry in entries:
        rank_with = entry.get("rank_with")
        rank_without = entry.get("rank_without")
        entry["rank_delta"] = (
            rank_without - rank_with
            if rank_with is not None and rank_without is not None
            else None
        )

    movers = sorted(
        (entry for entry in entries if entry.get("rank_delta") is not None),
        key=lambda entry: abs(entry["rank_delta"]),
        reverse=True,
    )[:top_movers]
    return {
        "rows": entries,
        "largest_movers": movers,
        "note": (
            "Per-set RIP with vs without the 10%-weight desirability component. "
            "Transparency only; not a gate and not a cap selector."
        ),
    }


def _assign_ranks(entries: List[Dict[str, Any]], score_key: str, rank_key: str) -> None:
    scored = [entry for entry in entries if _as_float(entry.get(score_key)) is not None]
    scored.sort(key=lambda entry: (-(_as_float(entry.get(score_key)) or 0.0), str(entry.get("set_id") or "")))
    for entry in entries:
        entry[rank_key] = None
    for rank, entry in enumerate(scored, start=1):
        entry[rank_key] = rank


# ---------------------------------------------------------------------------
# Pillar diagnostics (Phase 9 - report-only; never mutates shipping weights)
# ---------------------------------------------------------------------------

REDUNDANCY_FLAG_THRESHOLD = 0.8


def pillar_redundancy_matrix(
    rows: Iterable[Mapping[str, Any]],
    *,
    pillar_keys: Mapping[str, str] = None,
) -> Dict[str, Any]:
    """Pairwise Spearman among Profit/Safety/Stability across simulated sets.

    |rho| > 0.8 flags potential double-counting (two pillars measuring one
    shared axis). Finding to surface, not to act on automatically.
    """
    keys = dict(pillar_keys or {
        "profit": "profit_score",
        "safety": "safety_score",
        "stability": "stability_score",
    })
    materialized = [dict(row) for row in rows]
    pairs: List[Dict[str, Any]] = []
    names = list(keys)
    for index, left in enumerate(names):
        for right in names[index + 1:]:
            xs, ys = paired_finite(materialized, keys[left], keys[right])
            rho = spearman(xs, ys)
            pairs.append(
                {
                    "pillars": [left, right],
                    "n": len(xs),
                    "spearman": round(rho, 4) if rho is not None else None,
                    "redundancy_flag": bool(rho is not None and abs(rho) > REDUNDANCY_FLAG_THRESHOLD),
                }
            )
    return {
        "pairs": pairs,
        "flag_threshold": REDUNDANCY_FLAG_THRESHOLD,
        "note": (
            "Report-only. Flagged pairs may double-count one shared axis, "
            "implicitly overweighting it. Weights are NOT auto-adjusted, and "
            "pillars are never weighted by correlation to price or set value."
        ),
    }


def weight_sensitivity_report(
    rows: Sequence[Mapping[str, Any]],
    *,
    pillar_keys: Mapping[str, str] = None,
    alternatives: Optional[Mapping[str, Mapping[str, float]]] = None,
    top_movers: int = 10,
) -> Dict[str, Any]:
    """Rank stability of the RIP leaderboard under alternative weightings.

    Report-only: measures how load-bearing the subjective weight choice is.
    High rank correlation between alternatives means the exact weights matter
    little; low means presentations must be extra clear they are defaults.
    """
    keys = dict(pillar_keys or {
        "profit": "profit_score",
        "safety": "safety_score",
        "stability": "stability_score",
        "desirability": "desirability_score",
    })
    schemes = dict(alternatives or WEIGHT_SENSITIVITY_ALTERNATIVES)
    default_name = next(iter(schemes))

    scores_by_scheme: Dict[str, List[Optional[float]]] = {}
    set_labels: List[str] = []
    for row in rows:
        set_labels.append(str(row.get("set_name") or row.get("set_id") or ""))
    for scheme_name, scheme_weights in schemes.items():
        include_desirability = float(scheme_weights.get("desirability", 0.0)) > 0.0
        scheme_scores: List[Optional[float]] = []
        for row in rows:
            pillars = {pillar: row.get(source) for pillar, source in keys.items()}
            result = compute_weighted_rip(
                pillars,
                weights=scheme_weights,
                include_desirability=include_desirability,
            )
            scheme_scores.append(result.get("score"))
        scores_by_scheme[scheme_name] = scheme_scores

    default_scores = scores_by_scheme[default_name]
    comparisons: List[Dict[str, Any]] = []
    for scheme_name, scheme_scores in scores_by_scheme.items():
        if scheme_name == default_name:
            continue
        paired = [
            (default_value, alt_value, label)
            for default_value, alt_value, label in zip(default_scores, scheme_scores, set_labels)
            if default_value is not None and alt_value is not None
        ]
        xs = [item[0] for item in paired]
        ys = [item[1] for item in paired]
        rho = spearman(xs, ys)

        default_ranks = _dense_ranks(xs)
        alt_ranks = _dense_ranks(ys)
        movers = sorted(
            (
                {
                    "set": paired[index][2],
                    "default_rank": default_ranks[index],
                    "alternative_rank": alt_ranks[index],
                    "rank_delta": default_ranks[index] - alt_ranks[index],
                }
                for index in range(len(paired))
            ),
            key=lambda item: abs(item["rank_delta"]),
            reverse=True,
        )[:top_movers]
        comparisons.append(
            {
                "alternative": scheme_name,
                "weights": dict(schemes[scheme_name]),
                "n": len(paired),
                "rank_spearman_vs_default": round(rho, 4) if rho is not None else None,
                "top_movers": movers,
            }
        )
    return {
        "default": {"name": default_name, "weights": dict(schemes[default_name])},
        "comparisons": comparisons,
        "note": (
            "Report-only diagnostics. The shipping weights stay the reasoned "
            "defaults regardless of these results; nothing here tunes weights "
            "toward price or set value."
        ),
    }


def _dense_ranks(values: Sequence[float]) -> List[int]:
    order = sorted(range(len(values)), key=lambda index: -values[index])
    ranks = [0] * len(values)
    for rank, index in enumerate(order, start=1):
        ranks[index] = rank
    return ranks
