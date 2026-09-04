"""Shared helpers for Pass 1B. Read-only research. No production imports mutated."""
import json, math, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DOCS = REPO / "docs" / "research"


def load_primary_cohort():
    with open(DOCS / "overall_rip_accessibility_primary_cohort.json") as f:
        return json.load(f)


def load_product_cohort():
    with open(DOCS / "overall_rip_accessibility_product_cohort.json") as f:
        return json.load(f)


def compute_chase_significance(values):
    """HC_i = V_i^2 / sum_j V_j^2. Byte-identical logic to
    backend/desirability/chase_accessibility.py::compute_chase_significance."""
    squares = []
    for v in values:
        try:
            price = float(v)
        except (TypeError, ValueError):
            price = None
        if price is None or not math.isfinite(price) or price <= 0.0:
            squares.append(0.0)
        else:
            squares.append(price * price)
    total = math.fsum(squares)
    if total <= 0.0:
        return [0.0] * len(squares)
    return [s / total for s in squares]


def a_raw_from_variants(prices, probs):
    hc = compute_chase_significance(prices)
    return math.fsum(w * p for w, p in zip(hc, probs)), hc


def a_score(a_raw, k):
    return 100.0 * a_raw / (a_raw + k) if (a_raw + k) != 0 else 0.0


K_ANCHORS = [0.0005, 0.001, 0.002, 0.004, 0.008]
WEIGHTS_PCT = [0, 2, 4, 6, 8, 10]
COLLECTOR_PCT = 10.0


def overall_candidate(financial, collector, a_score_val, weight_pct):
    financial_pct = 90.0 - weight_pct
    return (financial_pct / 100.0) * financial + (COLLECTOR_PCT / 100.0) * collector + \
        (weight_pct / 100.0) * a_score_val
