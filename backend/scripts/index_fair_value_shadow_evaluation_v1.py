"""FV-S3 evaluation side of the prospective shadow ledger (pure; no I/O).

Everything here consumes a *frozen anchor publication* and returns NEW records. Nothing
here can alter an anchor: publications are deep-copied on entry and never returned.
The anchor builder (``index_fair_value_shadow_anchor_v1``) must never import this module.

Contents
* ``build_component_observation`` -- keeps TCGplayer market, sold anchor, structural
  baseline, scarcity and Collector Appeal as SEPARATE fields plus their divergences.
  It deliberately produces no blended "Fair Value" number.
* ``build_evaluation_outcome`` -- one horizon's realized comparison for one publication.
* ``anchor_accuracy`` / ``forward_diagnostics`` -- the metrics frozen in PREREGISTRATION.
"""
from __future__ import annotations

import copy
import math
from collections.abc import Mapping as _Mapping
from datetime import date, timedelta
from typing import Any, Mapping, Sequence

import numpy as np

SCHEMA_VERSION = "fv_shadow_evaluation_v1"
HORIZONS_DAYS = (0, 1, 7, 30)
SHADOW_STATUSES = ("COMPLETE", "ANCHOR_INSUFFICIENT", "MARKET_MISSING", "STRUCTURAL_MISSING")
BOOTSTRAP_SEED = 20261001
BOOTSTRAP_ITERATIONS = 2000
MIN_N_FOR_INFERENCE = 30
DIVERGENCE_THRESHOLD = 0.05
STRATA_FLOORS_USD = (("all", 0.0), ("ge_25", 25.0), ("ge_100", 100.0), ("ge_250", 250.0))

PREREGISTRATION: dict[str, Any] = {
    "preregistration_version": "fv_s3_prospective_shadow_preregistration_v1",
    "rule_under_test": "EXPLICIT_NM_SOLD_CLEARING_ANCHOR_V1",
    "rule_is_frozen": "Any change to eligibility, windows, minimum comps, estimator or availability gate requires a NEW rule version; results never retune V1.",
    "components_kept_separate": True,
    "blending_in_this_phase": False,
    "evidence_status_required": "PROSPECTIVE_AS_KNOWN_AT_CUTOFF",
    "retrospective_evidence_excluded_from_prospective_claims": True,
    "unit": "one anchor publication per (rule_version, canonical_card_id, evaluation_date, information_cutoff)",
    "publication_precedes_outcome": "anchor publications are appended before any comparison price for that evaluation date is read",
    "anchor_accuracy": {
        "evaluated_at": "publication evaluation date (horizon 0), against the canonical TCGplayer NM market price of that date",
        "metrics": ["mdape_pct", "mae_usd", "r2_dollars", "spearman", "within_10pct", "within_20pct", "within_30pct"],
        "formulas": {
            "mdape_pct": "100 * median(|anchor - market| / market)",
            "mae_usd": "mean(|anchor - market|)",
            "r2_dollars": "1 - sum((market - anchor)^2) / sum((market - mean(market))^2)",
            "spearman": "Pearson correlation of average ranks of (anchor, market)",
            "within_k_pct": "share of cards with |anchor - market| / market <= k/100",
        },
        "strata_by_market_price_usd": {name: floor for name, floor in STRATA_FLOORS_USD},
        "denominator": "cards with status ANCHORED and a market price at the comparison date; coverage reported separately",
    },
    "forward_behavior": {
        "horizons_days": [1, 7, 30],
        "market_convergence_required": False,
        "diagnostic_only": True,
        "no_conclusion_chosen_in_advance": True,
        "definitions": {
            "divergence": "d = (anchor - market_t0) / market_t0",
            "forward_return": "r_h = (market_t0+h - market_t0) / market_t0",
        },
        "statistics": [
            "spearman(d, r_h)",
            f"sign agreement among |d| >= {DIVERGENCE_THRESHOLD} (zero-return cards excluded)",
            "OLS slope of r_h on d with set-clustered bootstrap 95% interval "
            f"(B={BOOTSTRAP_ITERATIONS}, seed={BOOTSTRAP_SEED}, cluster=root_set_id)",
            "mean r_h by d tercile",
            "predictor test: MdAPE of anchor vs MdAPE of market_t0 as predictors of market_t0+h, and share of cards where the anchor is closer",
        ],
        "alternatives_not_ranked_in_advance": [
            "divergence carries forward information (anchor > market precedes rises, anchor < market precedes falls)",
            "anchor is only a contemporaneous alternative price estimator",
        ],
        "minimum_n_for_any_inference": MIN_N_FOR_INFERENCE,
        "below_minimum_n": "report descriptives only and label INSUFFICIENT_N",
        "missing_outcomes": "never imputed; reported as coverage per horizon",
        "multiplicity": "3 horizons x 4 strata are all reported; no horizon or stratum is selected after seeing results",
    },
    "rule_change_policy": "Observing prospective results never edits V1. A change creates ANCHOR_V2 and restarts the prospective clock.",
    "enrichment_policy": "FIRST_SEEN_PROVIDER_ENRICHMENT_RESEARCH_ONLY",
}


class EvaluationError(RuntimeError):
    pass


def _plain(value: Any) -> Any:
    """Deep, independent plain-Python copy (works for read-only mapping proxies too)."""
    if isinstance(value, _Mapping):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


# ----------------------------------------------------------------- components
def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) and out > 0 else None


def _div(a: float | None, b: float | None) -> dict[str, float | None]:
    if a is None or b is None:
        return {"usd": None, "pct_of_reference": None}
    return {"usd": round(a - b, 4), "pct_of_reference": round((a - b) / b * 100, 4)}


def build_component_observation(
    publication: Mapping[str, Any],
    *,
    market: Mapping[str, Any] | None,
    structural: Mapping[str, Any] | None,
    scarcity: Mapping[str, Any] | None,
    appeal: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Side-by-side components and divergences. Publication is read, never changed."""
    pub = _plain(publication)
    anchor = _num(pub.get("median")) if pub.get("status") == "ANCHORED" else None
    market_price = _num((market or {}).get("market_price_usd"))
    structural_price = _num((structural or {}).get("structural_price_usd"))
    evaluation_date = date.fromisoformat(pub["evaluation_date"])
    newest = pub.get("sold_at_max")
    age = (evaluation_date - date.fromisoformat(newest)).days if newest else None
    if anchor is None:
        status = "ANCHOR_INSUFFICIENT"
    elif market_price is None:
        status = "MARKET_MISSING"
    elif structural_price is None:
        status = "STRUCTURAL_MISSING"
    else:
        status = "COMPLETE"
    return {
        "schema_version": SCHEMA_VERSION,
        "publication_id": pub["publication_id"],
        "canonical_card_id": pub["canonical_card_id"],
        "evaluation_date": pub["evaluation_date"],
        "shadow_status": status,
        "current_tcgplayer_market_price_usd": market_price,
        "market_price_date": (market or {}).get("market_price_date"),
        "explicit_nm_sold_clearing_anchor_v1_usd": anchor,
        "structural_baseline_usd": structural_price,
        "structural_baseline_source": (structural or {}).get("source"),
        "pull_probability": (scarcity or {}).get("pull_probability"),
        "negative_ln_pull_probability": (
            round(-math.log(float(scarcity["pull_probability"])), 6)
            if (scarcity or {}).get("pull_probability") and float(scarcity["pull_probability"]) > 0 else None
        ),
        "scarcity_source": (scarcity or {}).get("source"),
        "collector_appeal": (appeal or {}).get("collector_appeal"),
        "collector_appeal_source": (appeal or {}).get("source"),
        "comp_count": pub.get("eligible_comp_count"),
        "selected_window_days": pub.get("selected_window_days"),
        "iqr": pub.get("iqr"), "mad": pub.get("mad"),
        "evidence_age_days_since_newest_sale": age,
        "evidence_status": pub.get("evidence_status"),
        "enrichment_policy": pub.get("enrichment_policy"),
        "divergence_sold_anchor_minus_current_market": _div(anchor, market_price),
        "divergence_structural_minus_current_market": _div(structural_price, market_price),
        "divergence_sold_anchor_minus_structural": _div(anchor, structural_price),
        "blended_value": None,  # explicit: no blending in this phase
    }


# ----------------------------------------------------------------- outcomes
def build_evaluation_outcome(
    publication: Mapping[str, Any],
    comparison: Mapping[str, Any],
    *,
    baseline_market_price_usd: float | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """One horizon of realized comparison. Returns a new record; never touches the anchor."""
    pub = _plain(publication)
    horizon = int(comparison["horizon_days"])
    if horizon not in HORIZONS_DAYS:
        raise EvaluationError(f"horizon must be one of {HORIZONS_DAYS}")
    evaluation_date = date.fromisoformat(pub["evaluation_date"])
    comparison_date = date.fromisoformat(str(comparison["comparison_date"])[:10])
    if comparison_date != evaluation_date + timedelta(days=horizon):
        raise EvaluationError("comparison_date must equal evaluation_date + horizon")
    if today is not None and comparison_date > today:
        raise EvaluationError("comparison date is in the future")
    market = _num(comparison.get("market_price_usd"))
    anchor = _num(pub.get("median")) if pub.get("status") == "ANCHORED" else None
    base = _num(baseline_market_price_usd)
    out: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "publication_id": pub["publication_id"],
        "horizon_days": horizon,
        "comparison_date": comparison_date.isoformat(),
        "comparison_market_price_usd": market,
        "comparison_price_source": comparison.get("source"),
        "baseline_market_price_usd": base,
        "anchor_usd_at_publication": anchor,
        "abs_error_usd": None, "signed_pct_error": None, "abs_pct_error": None,
        "forward_market_change_pct": None, "divergence_at_publication": None,
        "outcome_status": "COMPLETE",
    }
    if anchor is None:
        out["outcome_status"] = "ANCHOR_INSUFFICIENT"
    elif market is None:
        out["outcome_status"] = "MARKET_MISSING"
    else:
        out["abs_error_usd"] = round(abs(anchor - market), 4)
        out["signed_pct_error"] = round((anchor - market) / market * 100, 4)
        out["abs_pct_error"] = round(abs(anchor - market) / market * 100, 4)
    if horizon > 0 and market is not None and base is not None:
        out["forward_market_change_pct"] = round((market - base) / base * 100, 4)
        if anchor is not None:
            out["divergence_at_publication"] = round((anchor - base) / base, 6)
    return out


# ----------------------------------------------------------------- metrics
def _average_ranks(values: Sequence[float]) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    order = np.argsort(arr, kind="mergesort")
    ranks = np.empty(len(arr), dtype=float)
    i = 0
    while i < len(arr):
        j = i
        while j + 1 < len(arr) and arr[order[j + 1]] == arr[order[i]]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return ranks


def spearman(x: Sequence[float], y: Sequence[float]) -> float | None:
    if len(x) < 3:
        return None
    rx, ry = _average_ranks(x), _average_ranks(y)
    if rx.std() == 0 or ry.std() == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def anchor_accuracy(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """rows: anchor_usd, market_price_usd. Both must be positive and finite."""
    pairs = [(float(r["anchor_usd"]), float(r["market_price_usd"])) for r in rows
             if _num(r.get("anchor_usd")) and _num(r.get("market_price_usd"))]
    if not pairs:
        return {"n": 0, "status": "NO_ROWS"}
    a = np.array([p[0] for p in pairs]); m = np.array([p[1] for p in pairs])
    ape = np.abs(a - m) / m
    sst = float(np.sum((m - m.mean()) ** 2))
    return {
        "n": len(pairs),
        "status": "OK" if len(pairs) >= MIN_N_FOR_INFERENCE else "INSUFFICIENT_N",
        "mdape_pct": round(float(np.median(ape) * 100), 4),
        "mae_usd": round(float(np.mean(np.abs(a - m))), 4),
        "r2_dollars": round(1 - float(np.sum((m - a) ** 2)) / sst, 6) if sst > 0 and len(pairs) >= 3 else None,
        "spearman": None if spearman(a, m) is None else round(spearman(a, m), 6),
        "within_10pct": round(float(np.mean(ape <= 0.10) * 100), 4),
        "within_20pct": round(float(np.mean(ape <= 0.20) * 100), 4),
        "within_30pct": round(float(np.mean(ape <= 0.30) * 100), 4),
    }


def stratified_accuracy(rows: Sequence[Mapping[str, Any]], *, eligible_cards: int | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, floor in STRATA_FLOORS_USD:
        subset = [r for r in rows if _num(r.get("market_price_usd")) and float(r["market_price_usd"]) >= floor]
        out[name] = anchor_accuracy(subset)
    if eligible_cards is not None:
        out["coverage"] = {"anchored_with_market": out["all"].get("n", 0), "eligible_cards": eligible_cards}
    return out


def forward_diagnostics(rows: Sequence[Mapping[str, Any]], *, horizon_days: int) -> dict[str, Any]:
    """rows: anchor_usd, market_t0_usd, market_th_usd, cluster (root_set_id)."""
    clean = [r for r in rows if all(_num(r.get(k)) for k in ("anchor_usd", "market_t0_usd", "market_th_usd"))]
    n = len(clean)
    out: dict[str, Any] = {"horizon_days": horizon_days, "n": n,
                           "status": "OK" if n >= MIN_N_FOR_INFERENCE else "INSUFFICIENT_N"}
    if n < 3:
        return out
    p0 = np.array([float(r["market_t0_usd"]) for r in clean])
    ph = np.array([float(r["market_th_usd"]) for r in clean])
    an = np.array([float(r["anchor_usd"]) for r in clean])
    d, ret = (an - p0) / p0, (ph - p0) / p0
    sp = spearman(d, ret)
    out["spearman_divergence_vs_forward_return"] = None if sp is None else round(sp, 6)
    big = (np.abs(d) >= DIVERGENCE_THRESHOLD) & (ret != 0)
    out["sign_agreement"] = {
        "threshold": DIVERGENCE_THRESHOLD, "n": int(big.sum()),
        "share": round(float(np.mean(np.sign(d[big]) == np.sign(ret[big]))), 6) if big.any() else None,
    }
    var = float(np.var(d))
    slope = float(np.cov(d, ret, bias=True)[0, 1] / var) if var > 0 else None
    out["ols_slope_forward_return_on_divergence"] = None if slope is None else round(slope, 6)
    clusters = np.array([str(r.get("cluster") or i) for i, r in enumerate(clean)])
    if slope is not None and n >= MIN_N_FOR_INFERENCE:
        rng = np.random.default_rng(BOOTSTRAP_SEED)
        names = sorted(set(clusters))
        idx_by = {c: np.where(clusters == c)[0] for c in names}
        slopes = []
        for _ in range(BOOTSTRAP_ITERATIONS):
            pick = rng.choice(len(names), size=len(names), replace=True)
            idx = np.concatenate([idx_by[names[i]] for i in pick])
            v = float(np.var(d[idx]))
            if v > 0:
                slopes.append(float(np.cov(d[idx], ret[idx], bias=True)[0, 1] / v))
        out["ols_slope_bootstrap_95ci"] = (
            [round(float(np.percentile(slopes, 2.5)), 6), round(float(np.percentile(slopes, 97.5)), 6)]
            if slopes else None
        )
    else:
        out["ols_slope_bootstrap_95ci"] = None
    order = np.argsort(d, kind="mergesort")
    thirds = np.array_split(order, 3)
    out["mean_forward_return_by_divergence_tercile"] = {
        name: (round(float(np.mean(ret[idx])), 6) if len(idx) else None)
        for name, idx in zip(("lowest", "middle", "highest"), thirds)
    }
    anchor_err, market_err = np.abs(an - ph) / ph, np.abs(p0 - ph) / ph
    out["predictor_comparison"] = {
        "anchor_mdape_pct": round(float(np.median(anchor_err) * 100), 4),
        "market_t0_mdape_pct": round(float(np.median(market_err) * 100), 4),
        "share_anchor_closer": round(float(np.mean(anchor_err < market_err)), 6),
    }
    return out
