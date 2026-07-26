"""Card-level Chase Appeal + current fair-value estimation (READ-ONLY research).

Three separate questions, deliberately not merged:

  Model One   - given only non-price fundamentals, how closely can we estimate a
                card's CURRENT market price?
  Model Two   - where does the actual price sit relative to the model-implied
                estimate? (A residual. NOT a claim of under/overvaluation.)
  Card Chase  - does Subject Desirability x Card Scarcity explain price beyond
                rarity, scarcity, or desirability alone?

Validation is GROUPED BY SET throughout: every card from a held-out set is
absent from training, so a set's own price level cannot leak into its cards'
predictions. Every reported metric is out-of-fold.

Card Chase Appeal is constructed WITHOUT price. Price appears only as the
regression target and as the actual value in the valuation gap.

Nothing is committed, nothing is wired into production, no database writes.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.calculations.utils.rarity_classification import normalize_rarity_key  # noqa: E402
from backend.desirability.card_appeal import get_treatment_score  # noqa: E402
from backend.desirability.opening_appeal import (  # noqa: E402
    appeal_excess,
    scarcity_transform,
)
from backend.desirability.rarity_buckets import HIT_BUCKETS, classify_rarity  # noqa: E402
from backend.desirability.weighted_rip import spearman  # noqa: E402
from backend.scripts.build_opening_appeal_study import (  # noqa: E402
    load_appeal_by_card,
    load_cards,
    load_latest_v2_rows,
    load_prices,
    load_pull_rate_model,
    _paged_select,
)

logger = logging.getLogger(__name__)

STUDY_VERSION = "card_fair_value_v1_research"
CARD_CHASE_APPEAL_VERSION = "card_chase_appeal_v1_research"
RANDOM_SEED = 20260718
RIDGE_LAMBDA = 1.0

# Pre-registered model ladder. Registered before any metric was computed.
MODEL_SPECS: Tuple[Tuple[str, str], ...] = (
    ("B0_global_or_rarity_median", "Rarity median only - the naive benchmark"),
    ("B1_set_and_rarity_controls", "Set + rarity controls"),
    ("B2_desirability_only", "Subject desirability only"),
    ("B3_scarcity_only", "Modeled card scarcity only"),
    ("B4_desirability_plus_scarcity", "Desirability + scarcity"),
    ("B5_desirability_x_scarcity", "Desirability + scarcity + their interaction"),
    ("B6_card_chase_appeal", "Card Chase Appeal (the single composite)"),
    ("B7_full_permitted", "All permitted non-price features"),
)


def _as_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


# ---------------------------------------------------------------------------
# Card Chase Appeal (research-only, price-free by construction)
# ---------------------------------------------------------------------------

def card_chase_appeal(subject_demand: Any, pull_probability: Any) -> Optional[float]:
    """``Card Chase Appeal = subject_desirability_excess x card_scarcity``.

    Deliberately narrow: treatment, rarity, supply and age are kept as SEPARATE
    explanatory features rather than hidden inside this score, so the model can
    tell us whether the composite adds anything they do not.

    Price is never an input. Returns None (never 0) when scarcity is unmodeled.
    """
    scarcity = scarcity_transform(pull_probability)
    if scarcity is None:
        return None
    excess = appeal_excess(subject_demand)
    return excess * scarcity


# ---------------------------------------------------------------------------
# Feature assembly
# ---------------------------------------------------------------------------

def build_card_rows(client) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    pull_model = load_pull_rate_model(client)
    v2_rows = load_latest_v2_rows(client)
    set_rows = {
        str(r["id"]): r
        for r in _paged_select(client.table("sets").select("id,name,canonical_key,release_date,era_id"))
    }
    eras = {str(r["id"]): str(r.get("name") or "") for r in _paged_select(client.table("eras").select("id,name"))}

    covered = sorted(set(pull_model) & set(v2_rows))
    cards = load_cards(client, covered)
    prices = load_prices(client, covered)
    appeal_by_card = load_appeal_by_card(client, [str(c["id"]) for c in cards])

    # Per-subject printing counts WITHIN a set: "alternative premium printings".
    printings_by_set_subject: Dict[Tuple[str, str], int] = defaultdict(int)
    hits_by_set: Dict[str, int] = defaultdict(int)
    for card in cards:
        set_id = str(card.get("set_id"))
        classification = classify_rarity(card.get("rarity"))
        if classification.bucket not in HIT_BUCKETS:
            continue
        hits_by_set[set_id] += 1
        appeal_row = appeal_by_card.get(str(card.get("id")))
        if appeal_row:
            printings_by_set_subject[(set_id, str(appeal_row["primary_reference_id"]))] += 1

    today = datetime.now(timezone.utc).date()
    rows: List[Dict[str, Any]] = []
    skipped = defaultdict(int)
    for card in cards:
        card_id = str(card.get("id"))
        set_id = str(card.get("set_id"))
        classification = classify_rarity(card.get("rarity"))
        if classification.bucket not in HIT_BUCKETS:
            skipped["not_a_hit"] += 1
            continue
        price = prices.get(card_id)
        if price is None or price <= 0:
            skipped["no_price"] += 1
            continue
        appeal_row = appeal_by_card.get(card_id)
        if appeal_row is None:
            skipped["no_appeal_link"] += 1
            continue
        model = (pull_model.get(set_id) or {}).get(classification.normalized_key)
        if model is None:
            skipped["no_pull_model"] += 1
            continue

        set_row = set_rows.get(set_id) or {}
        try:
            release = datetime.fromisoformat(str(set_row.get("release_date"))).date()
            age_days = max((today - release).days, 1)
        except (TypeError, ValueError):
            skipped["no_release_date"] += 1
            continue

        probability = model["probability"]
        scarcity = scarcity_transform(probability)
        if scarcity is None:
            skipped["unmodelable_scarcity"] += 1
            continue
        subject_key = str(appeal_row["primary_reference_id"])
        demand = appeal_row["appeal"]

        rows.append({
            "card_id": card_id,
            "card_name": card.get("name"),
            "set_id": set_id,
            "set_name": set_row.get("name"),
            "era": eras.get(str(set_row.get("era_id") or "")),
            "rarity": card.get("rarity"),
            "rarity_key": classification.normalized_key,
            "subject_key": subject_key,
            "subject_name": appeal_row.get("primary_species"),
            # --- price-free features ---
            "subject_demand": demand,
            "subject_demand_excess": appeal_excess(demand),
            "pull_probability": probability,
            "card_scarcity": scarcity,
            "card_chase_appeal": card_chase_appeal(demand, probability),
            "treatment_prestige": get_treatment_score(card.get("rarity")) / 100.0,
            "set_age_days": age_days,
            "log_set_age": math.log(age_days),
            "alternative_printings_of_subject": printings_by_set_subject.get((set_id, subject_key), 1),
            "competing_hits_in_set": hits_by_set.get(set_id, 0),
            "log_competing_hits": math.log(max(hits_by_set.get(set_id, 1), 1)),
            # --- outcome (never an input) ---
            "market_price": price,
            "log_price": math.log(price),
        })
    return rows, {"skipped": dict(skipped), "sets_covered": len(covered)}


# ---------------------------------------------------------------------------
# Grouped-by-set ridge regression
# ---------------------------------------------------------------------------

def _design(rows, numeric, categoricals, levels) -> np.ndarray:
    pieces = [np.ones((len(rows), 1))]
    if numeric:
        pieces.append(np.column_stack([[float(r[c]) for r in rows] for c in numeric]))
    for column, values in ((c, levels[c]) for c in categoricals):
        for level in values[1:]:
            pieces.append(np.array([[1.0 if str(r.get(column)) == level else 0.0] for r in rows]))
    return np.hstack(pieces)


def ridge_fit(X: np.ndarray, y: np.ndarray, lam: float = RIDGE_LAMBDA) -> np.ndarray:
    """Ridge with the intercept left unpenalized."""
    penalty = lam * np.eye(X.shape[1])
    penalty[0, 0] = 0.0
    return np.linalg.solve(X.T @ X + penalty, X.T @ y)


def model_features(name: str) -> Tuple[List[str], List[str]]:
    """(numeric, categorical) per pre-registered spec."""
    if name == "B0_global_or_rarity_median":
        return [], ["rarity_key"]
    if name == "B1_set_and_rarity_controls":
        return ["log_set_age"], ["rarity_key", "era"]
    if name == "B2_desirability_only":
        return ["subject_demand_excess"], []
    if name == "B3_scarcity_only":
        return ["card_scarcity"], []
    if name == "B4_desirability_plus_scarcity":
        return ["subject_demand_excess", "card_scarcity"], []
    if name == "B5_desirability_x_scarcity":
        return ["subject_demand_excess", "card_scarcity", "card_chase_appeal"], []
    if name == "B6_card_chase_appeal":
        return ["card_chase_appeal"], []
    if name == "B7_full_permitted":
        return ["subject_demand_excess", "card_scarcity", "card_chase_appeal",
                "treatment_prestige", "log_set_age", "alternative_printings_of_subject",
                "log_competing_hits"], ["rarity_key", "era"]
    raise ValueError(name)


def grouped_cv(rows: Sequence[Mapping[str, Any]], name: str) -> Optional[Dict[str, Any]]:
    """Leave-one-SET-out predictions. A set's own cards never train its own model."""
    numeric, categoricals = model_features(name)
    levels = {c: sorted({str(r.get(c)) for r in rows}) for c in categoricals}
    set_ids = sorted({str(r["set_id"]) for r in rows})
    if len(set_ids) < 3:
        return None

    predictions: List[float] = []
    actuals: List[float] = []
    keep: List[Mapping[str, Any]] = []
    for held_out in set_ids:
        train = [r for r in rows if str(r["set_id"]) != held_out]
        test = [r for r in rows if str(r["set_id"]) == held_out]
        if not train or not test:
            continue
        if name == "B0_global_or_rarity_median":
            # Median by rarity, falling back to the global median: no design matrix.
            by_rarity: Dict[str, List[float]] = defaultdict(list)
            for r in train:
                by_rarity[str(r["rarity_key"])].append(r["log_price"])
            global_median = statistics.median([r["log_price"] for r in train])
            y_hat = np.array([
                statistics.median(by_rarity[str(r["rarity_key"])])
                if by_rarity.get(str(r["rarity_key"])) else global_median
                for r in test
            ])
        else:
            X = _design(train, numeric, categoricals, levels)
            y = np.array([r["log_price"] for r in train], dtype=float)
            beta = ridge_fit(X, y)
            y_hat = _design(test, numeric, categoricals, levels) @ beta
        predictions.extend(y_hat.tolist())
        actuals.extend([r["log_price"] for r in test])
        keep.extend(test)

    if len(predictions) < 20:
        return None
    predicted = np.array(predictions)
    actual = np.array(actuals)
    errors = actual - predicted
    tss = float(np.sum((actual - actual.mean()) ** 2))
    rss = float(np.sum(errors ** 2))
    dollar_actual = np.exp(actual)
    dollar_predicted = np.exp(predicted)
    ape = np.abs(dollar_predicted - dollar_actual) / dollar_actual

    return {
        "n_cards": len(predicted),
        "n_sets": len(set_ids),
        "out_of_fold_r2": round(1.0 - rss / tss, 4) if tss > 0 else None,
        "mae_log": round(float(np.mean(np.abs(errors))), 4),
        "rmse_log": round(float(np.sqrt(np.mean(errors ** 2))), 4),
        "mae_dollars": round(float(np.mean(np.abs(dollar_predicted - dollar_actual))), 2),
        "median_abs_pct_error": round(float(np.median(ape) * 100), 2),
        "spearman": round(spearman(predicted.tolist(), actual.tolist()) or 0.0, 4),
        "beats_predicting_the_mean": bool(tss > 0 and (1.0 - rss / tss) > 0),
        "_oof": [
            {**{k: r[k] for k in ("card_id", "card_name", "set_name", "rarity", "subject_name",
                                  "market_price", "log_price", "card_scarcity",
                                  "subject_demand", "card_chase_appeal", "pull_probability",
                                  "alternative_printings_of_subject", "set_age_days")},
             "predicted_log_price": round(float(p), 5),
             "predicted_price": round(float(math.exp(p)), 2)}
            for r, p in zip(keep, predicted)
        ],
    }


def calibration_and_slices(oof: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Where the model works and where it does not."""
    def block(rows) -> Dict[str, Any]:
        if len(rows) < 5:
            return {"n": len(rows)}
        actual = np.array([r["log_price"] for r in rows])
        predicted = np.array([r["predicted_log_price"] for r in rows])
        errors = actual - predicted
        tss = float(np.sum((actual - actual.mean()) ** 2))
        return {
            "n": len(rows),
            "mae_log": round(float(np.mean(np.abs(errors))), 4),
            "median_abs_pct_error": round(float(np.median(
                np.abs(np.exp(predicted) - np.exp(actual)) / np.exp(actual)) * 100), 2),
            "mean_bias_log": round(float(np.mean(errors)), 4),
            "r2": round(1.0 - float(np.sum(errors ** 2)) / tss, 4) if tss > 0 else None,
        }

    by_band: Dict[str, Any] = {}
    ordered = sorted(oof, key=lambda r: r["predicted_price"])
    size = max(len(ordered) // 5, 1)
    for index in range(5):
        chunk = ordered[index * size:] if index == 4 else ordered[index * size:(index + 1) * size]
        if chunk:
            by_band[f"q{index+1}_pred_{chunk[0]['predicted_price']:.2f}_to_{chunk[-1]['predicted_price']:.2f}"] = block(chunk)

    by_rarity = defaultdict(list)
    by_set = defaultdict(list)
    by_tier = defaultdict(list)
    for row in oof:
        by_rarity[str(row["rarity"])].append(row)
        by_set[str(row["set_name"])].append(row)
        price = row["market_price"]
        tier = "under_5" if price < 5 else "5_to_25" if price < 25 else "25_to_100" if price < 100 else "over_100"
        by_tier[tier].append(row)
    return {
        "by_predicted_price_band": by_band,
        "by_rarity": {k: block(v) for k, v in sorted(by_rarity.items())},
        "by_set": {k: block(v) for k, v in sorted(by_set.items())},
        "by_actual_price_tier": {k: block(by_tier[k]) for k in
                                 ("under_5", "5_to_25", "25_to_100", "over_100") if k in by_tier},
    }


def valuation_gaps(oof: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """``gap = log(actual) - log(out-of-fold expected)``.

    NOT a claim of under/overvaluation. Without future-return validation this is
    a model residual, and the most likely explanation for a large residual is an
    omitted variable - of which this dataset has many (no sales volume, no
    listing count, no population, no reprint flags, no condition mix).
    """
    scored = []
    for row in oof:
        gap = row["log_price"] - row["predicted_log_price"]
        scored.append({**row, "valuation_gap": round(gap, 4),
                       "price_ratio_actual_over_expected": round(math.exp(gap), 3)})
    gaps = np.array([r["valuation_gap"] for r in scored])
    return {
        "definition": "log(actual price) - log(out-of-fold expected price)",
        "interpretation_caveat": (
            "Negative = priced below the model-implied estimate; positive = above. These are "
            "NOT under/overvaluation claims. No future-return validation is possible on this "
            "data, and no liquidity, sales-volume, listing-count, population or reprint field "
            "exists to diagnose the residuals."
        ),
        "confidence_adjustment_status": "BLOCKED",
        "confidence_adjustment_reason": (
            "A confidence-adjusted gap requires liquidity, sales-volume, price-observation "
            "sparsity or prediction-interval width. None of the first three exist in the "
            "schema, so any 'confidence' weight would be fabricated."
        ),
        "n": len(scored),
        "gap_sd": round(float(np.std(gaps)), 4),
        "gap_mean": round(float(np.mean(gaps)), 6),
        "most_below_model": sorted(scored, key=lambda r: r["valuation_gap"])[:20],
        "most_above_model": sorted(scored, key=lambda r: -r["valuation_gap"])[:20],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(Path("docs") / "research" / "card_fair_value_study.json"))
    parser.add_argument("--csv-dir", default=str(Path("docs") / "research" / "collector_appeal_tables"))
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

    from backend.db.clients.supabase_client import public_read_client

    logger.info("Building card rows...")
    rows, diagnostics = build_card_rows(public_read_client)
    logger.info("Cards usable: %s across %s sets", len(rows),
                len({r["set_id"] for r in rows}))

    models: Dict[str, Any] = {}
    oof_best: List[Mapping[str, Any]] = []
    for name, description in MODEL_SPECS:
        logger.info("Model %s...", name)
        result = grouped_cv(rows, name)
        if result is None:
            models[name] = {"description": description, "available": False}
            continue
        oof = result.pop("_oof")
        models[name] = {"description": description, "available": True,
                        "features": {"numeric": model_features(name)[0],
                                     "categorical": model_features(name)[1]},
                        **result}
        if name == "B7_full_permitted":
            oof_best = oof

    # Card Chase Appeal incremental value, judged against the pre-registered ladder.
    def r2(name):
        return (models.get(name) or {}).get("out_of_fold_r2")

    chase_verdict = {
        "question": "Does Card Chase Appeal explain price beyond its parts?",
        "vs_desirability_alone": (
            round(r2("B6_card_chase_appeal") - r2("B2_desirability_only"), 4)
            if r2("B6_card_chase_appeal") is not None and r2("B2_desirability_only") is not None else None
        ),
        "vs_scarcity_alone": (
            round(r2("B6_card_chase_appeal") - r2("B3_scarcity_only"), 4)
            if r2("B6_card_chase_appeal") is not None and r2("B3_scarcity_only") is not None else None
        ),
        "vs_rarity_alone": (
            round(r2("B6_card_chase_appeal") - r2("B0_global_or_rarity_median"), 4)
            if r2("B6_card_chase_appeal") is not None and r2("B0_global_or_rarity_median") is not None else None
        ),
        "vs_set_and_rarity_controls": (
            round(r2("B6_card_chase_appeal") - r2("B1_set_and_rarity_controls"), 4)
            if r2("B6_card_chase_appeal") is not None and r2("B1_set_and_rarity_controls") is not None else None
        ),
        "interaction_adds_over_additive": (
            round(r2("B5_desirability_x_scarcity") - r2("B4_desirability_plus_scarcity"), 4)
            if r2("B5_desirability_x_scarcity") is not None and r2("B4_desirability_plus_scarcity") is not None else None
        ),
    }

    gaps = valuation_gaps(oof_best) if oof_best else {"available": False}
    slices = calibration_and_slices(oof_best) if oof_best else {}

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "study": STUDY_VERSION,
        "card_chase_appeal_version": CARD_CHASE_APPEAL_VERSION,
        "rules": [
            "Card Chase Appeal is built from subject desirability x modeled card scarcity. No price input.",
            "Validation is grouped by SET: a held-out set's cards never appear in its own training data.",
            "Every reported metric is out-of-fold.",
            "Valuation gaps use out-of-fold predictions only.",
            "No database writes.",
        ],
        "seed": RANDOM_SEED,
        "ridge_lambda": RIDGE_LAMBDA,
        "cohort": {
            "cards_usable": len(rows),
            "sets": len({r["set_id"] for r in rows}),
            "subjects": len({r["subject_key"] for r in rows}),
            "exclusion_counts": diagnostics["skipped"],
            "price_source": "TCGPlayer market_price (listing-derived), NOT completed-sale data",
        },
        "models": models,
        "card_chase_appeal_verdict": chase_verdict,
        "calibration": slices,
        "valuation_gaps": gaps,
        "limitations": [
            "Price is a listing-derived TCGPlayer market price, not a completed-sale price.",
            "No sales volume, listing count, liquidity, grading population, gem rate, reprint flag "
            "or supply field exists in the schema; all are omitted variables here.",
            "Prediction intervals are not reported: with no repeated-observation error model and "
            "heteroskedastic residuals across price tiers, any interval would be indefensible.",
            "Contemporaneous only. Nothing here predicts future prices.",
        ],
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    csv_dir = Path(args.csv_dir)
    csv_dir.mkdir(parents=True, exist_ok=True)
    if oof_best:
        columns = ["card_name", "set_name", "rarity", "subject_name", "market_price",
                   "predicted_price", "predicted_log_price", "log_price", "card_scarcity",
                   "subject_demand", "card_chase_appeal", "pull_probability",
                   "alternative_printings_of_subject", "set_age_days"]
        with (csv_dir / "card_level_out_of_fold_estimates.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            for row in sorted(oof_best, key=lambda r: -r["market_price"]):
                writer.writerow(row)
        gap_rows = sorted(gaps["most_below_model"] + gaps["most_above_model"],
                          key=lambda r: r["valuation_gap"])
        with (csv_dir / "valuation_gaps.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["card_name", "set_name", "rarity", "subject_name", "market_price",
                            "predicted_price", "valuation_gap", "price_ratio_actual_over_expected",
                            "card_scarcity", "subject_demand", "alternative_printings_of_subject"],
                extrasaction="ignore",
            )
            writer.writeheader()
            for row in gap_rows:
                writer.writerow(row)

    print(f"\nCards: {len(rows)} across {len({r['set_id'] for r in rows})} sets")
    print(f"\n{'model':<34}{'OOF R2':>9}{'MAE(log)':>10}{'MdAPE%':>9}{'rho':>8}{'beats mean':>12}")
    for name, _d in MODEL_SPECS:
        m = models.get(name) or {}
        if not m.get("available"):
            print(f"{name:<34}{'unavailable':>9}")
            continue
        print(f"{name:<34}{str(m['out_of_fold_r2']):>9}{str(m['mae_log']):>10}"
              f"{str(m['median_abs_pct_error']):>9}{str(m['spearman']):>8}"
              f"{str(m['beats_predicting_the_mean']):>12}")
    print("\nCard Chase Appeal incremental:")
    for key, value in chase_verdict.items():
        if key != "question":
            print(f"  {key:<34} {value}")
    print(f"\nReport written to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
