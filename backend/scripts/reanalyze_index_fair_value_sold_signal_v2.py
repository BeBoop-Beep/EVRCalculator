"""Leakage-free reanalysis for the inDex Fair Value sold-signal pilot.

This script consumes the aggregate CSV produced by
run_index_fair_value_sold_signal_pilot.py. It performs NO provider calls and NO
database writes.

V1 included sold_median_to_nm_ratio = sold_median / target_nm_market_price as a
model feature. That uses the target being predicted and is therefore label
leakage. V2 explicitly ignores that column and derives all model inputs only
from deployable sold evidence plus the baseline prediction available at
inference time.

The target is used only to fit/evaluate the residual model. Raw eBay condition
remains unknown; sold price is treated as noisy market-clearing evidence, not
as a Near Mint price authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "backend/artifacts/index_fair_value/sold_signal_pilot_v1/sample_features.csv"
OUT = ROOT / "backend/artifacts/index_fair_value/sold_signal_pilot_v2"
VERSION = "index_fair_value_sold_signal_pilot_v2"
RIDGE_ALPHA = 10.0

BASE_COLUMNS = (
    "sold_30d",
    "sold_90d",
    "sold_180d",
    "last_sale_age_days",
    "sold_median",
    "sold_mad",
    "sold_iqr",
    "sold_trend_fraction",
)
FORBIDDEN_MODEL_COLUMNS = {
    "target_nm_market_price",
    "sold_median_to_nm_ratio",
}
BASELINES = ("structural_price", "market_anchored_price")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _metrics(actual: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    pred = np.maximum(np.asarray(pred, dtype=float), 0.01)
    actual = np.asarray(actual, dtype=float)
    ape = np.abs(pred - actual) / actual
    tss = np.sum((actual - actual.mean()) ** 2)
    rho = (
        pd.Series(actual).rank(method="average").corr(
            pd.Series(pred).rank(method="average"), method="pearson"
        )
        if len(actual) > 2
        else np.nan
    )
    return {
        "n": int(len(actual)),
        "mae": float(np.mean(np.abs(pred - actual))),
        "mdape": float(np.median(ape) * 100),
        "within30Pct": float(np.mean(ape <= 0.30) * 100),
        "r2Dollars": float(1 - np.sum((pred - actual) ** 2) / tss) if tss else float("nan"),
        "spearman": float(rho) if not np.isnan(rho) else float("nan"),
    }


def _safe_log_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    a = pd.to_numeric(numerator, errors="coerce")
    b = pd.to_numeric(denominator, errors="coerce")
    out = pd.Series(np.nan, index=a.index, dtype=float)
    valid = (a > 0) & (b > 0)
    out.loc[valid] = np.log(a.loc[valid] / b.loc[valid])
    return out


def _deployable_features(
    frame: pd.DataFrame,
    baseline_col: str,
    feature_set: str,
) -> tuple[pd.DataFrame, list[str]]:
    if baseline_col not in BASELINES:
        raise ValueError(f"unsupported baseline: {baseline_col}")
    x = pd.DataFrame(index=frame.index)
    x["log1p_sold_30d"] = np.log1p(pd.to_numeric(frame["sold_30d"], errors="coerce"))
    x["log1p_sold_90d"] = np.log1p(pd.to_numeric(frame["sold_90d"], errors="coerce"))
    x["log1p_sold_180d"] = np.log1p(pd.to_numeric(frame["sold_180d"], errors="coerce"))
    x["last_sale_age_days"] = pd.to_numeric(frame["last_sale_age_days"], errors="coerce")

    if feature_set == "liquidity_only":
        columns = list(x.columns)
    elif feature_set == "price_context":
        median = pd.to_numeric(frame["sold_median"], errors="coerce")
        x["sold_relative_mad"] = pd.to_numeric(frame["sold_mad"], errors="coerce") / median
        x["sold_relative_iqr"] = pd.to_numeric(frame["sold_iqr"], errors="coerce") / median
        x["sold_trend_fraction"] = pd.to_numeric(frame["sold_trend_fraction"], errors="coerce")
        x["log_sold_median_to_baseline"] = _safe_log_ratio(
            median, pd.to_numeric(frame[baseline_col], errors="coerce")
        )
        columns = list(x.columns)
    else:
        raise ValueError(f"unsupported feature set: {feature_set}")

    leaked = FORBIDDEN_MODEL_COLUMNS.intersection(columns)
    if leaked or any("to_nm_ratio" in col or col.startswith("target_") for col in columns):
        raise RuntimeError(f"SOLD_SIGNAL_V2_TARGET_LEAKAGE_GUARD: {sorted(leaked)}")
    return x, columns


def _grouped_ridge(
    frame: pd.DataFrame,
    baseline_col: str,
    feature_set: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    usable = frame[
        (pd.to_numeric(frame["eligible_sold_count"], errors="coerce") >= 3)
        & (pd.to_numeric(frame["target_nm_market_price"], errors="coerce") > 0)
        & (pd.to_numeric(frame[baseline_col], errors="coerce") > 0)
    ].copy()
    if usable["root_set_id"].nunique() < 3 or len(usable) < 20:
        return usable, {
            "status": "INSUFFICIENT_SAMPLE",
            "n": int(len(usable)),
            "rootSets": int(usable["root_set_id"].nunique()),
        }

    X_frame, feature_names = _deployable_features(usable, baseline_col, feature_set)
    X = X_frame.to_numpy(dtype=float)
    actual = pd.to_numeric(usable["target_nm_market_price"], errors="raise").to_numpy(dtype=float)
    baseline = pd.to_numeric(usable[baseline_col], errors="raise").to_numpy(dtype=float)
    y = np.log(actual) - np.log(baseline)

    groups = usable["root_set_id"].astype(str).to_numpy()
    unique_groups = sorted(set(groups))
    splits = min(5, len(unique_groups))
    fold_for_group = {group: i % splits for i, group in enumerate(unique_groups)}
    pred_residual = np.zeros(len(usable), dtype=float)

    for fold in range(splits):
        test = np.array([fold_for_group[group] == fold for group in groups])
        train = ~test
        train_x = X[train].copy()
        test_x = X[test].copy()

        medians = np.nanmedian(train_x, axis=0)
        medians = np.where(np.isfinite(medians), medians, 0.0)
        train_x = np.where(np.isfinite(train_x), train_x, medians)
        test_x = np.where(np.isfinite(test_x), test_x, medians)

        means = train_x.mean(axis=0)
        scales = train_x.std(axis=0)
        scales = np.where(scales > 1e-12, scales, 1.0)
        train_x = (train_x - means) / scales
        test_x = (test_x - means) / scales

        design = np.column_stack([np.ones(len(train_x)), train_x])
        penalty = np.eye(design.shape[1]) * RIDGE_ALPHA
        penalty[0, 0] = 0.0
        beta = np.linalg.solve(design.T @ design + penalty, design.T @ y[train])
        pred_residual[test] = np.column_stack([np.ones(len(test_x)), test_x]) @ beta

    predicted = baseline * np.exp(pred_residual)
    output = usable.copy()
    output[f"{baseline_col}_{feature_set}_sold_v2"] = predicted
    output[f"{baseline_col}_{feature_set}_predicted_log_residual_v2"] = pred_residual

    return output, {
        "status": "EVALUATED",
        "n": int(len(usable)),
        "rootSets": int(len(unique_groups)),
        "folds": int(splits),
        "ridgeAlpha": RIDGE_ALPHA,
        "features": feature_names,
        "baseline": _metrics(actual, baseline),
        "plusSoldSignals": _metrics(actual, predicted),
    }


def _spearman(a: pd.Series, b: pd.Series) -> float | None:
    pair = pd.concat(
        [pd.to_numeric(a, errors="coerce"), pd.to_numeric(b, errors="coerce")],
        axis=1,
    ).dropna()
    if len(pair) < 8:
        return None
    value = pair.iloc[:, 0].rank().corr(pair.iloc[:, 1].rank())
    return None if pd.isna(value) else float(value)


def _diagnostics(frame: pd.DataFrame, baseline_col: str) -> dict[str, Any]:
    usable = frame[
        (pd.to_numeric(frame["eligible_sold_count"], errors="coerce") >= 3)
        & (pd.to_numeric(frame["target_nm_market_price"], errors="coerce") > 0)
        & (pd.to_numeric(frame[baseline_col], errors="coerce") > 0)
    ].copy()
    if usable.empty:
        return {"status": "NO_ROWS"}

    actual = pd.to_numeric(usable["target_nm_market_price"], errors="coerce")
    baseline = pd.to_numeric(usable[baseline_col], errors="coerce")
    median = pd.to_numeric(usable["sold_median"], errors="coerce")
    abs_log_error = (_safe_log_ratio(actual, baseline)).abs()
    abs_sold_disagreement = (_safe_log_ratio(median, baseline)).abs()
    rel_iqr = pd.to_numeric(usable["sold_iqr"], errors="coerce") / median
    rel_mad = pd.to_numeric(usable["sold_mad"], errors="coerce") / median

    return {
        "status": "DESCRIPTIVE_ONLY",
        "n": int(len(usable)),
        "note": "These correlations use the target only to diagnose baseline error; they are not model inputs.",
        "spearmanAbsBaselineErrorVsEligibleSoldCount": _spearman(
            abs_log_error, usable["eligible_sold_count"]
        ),
        "spearmanAbsBaselineErrorVsLastSaleAge": _spearman(
            abs_log_error, usable["last_sale_age_days"]
        ),
        "spearmanAbsBaselineErrorVsRelativeIqr": _spearman(abs_log_error, rel_iqr),
        "spearmanAbsBaselineErrorVsRelativeMad": _spearman(abs_log_error, rel_mad),
        "spearmanAbsBaselineErrorVsSoldBaselineDisagreement": _spearman(
            abs_log_error, abs_sold_disagreement
        ),
    }


def analyze(input_path: Path) -> dict[str, Any]:
    if not input_path.exists():
        raise FileNotFoundError(input_path)
    frame = pd.read_csv(input_path)
    required = {
        "canonical_card_id",
        "root_set_id",
        "target_nm_market_price",
        "structural_price",
        "market_anchored_price",
        "eligible_sold_count",
        *BASE_COLUMNS,
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise RuntimeError(f"SOLD_SIGNAL_V2_MISSING_COLUMNS: {missing}")

    # V1's leaked feature may be present in the input for audit continuity, but
    # V2 must never consume it.
    source_contains_v1_leaked_column = "sold_median_to_nm_ratio" in frame.columns

    reports: dict[str, Any] = {}
    prediction_frames = []
    for baseline_col in BASELINES:
        reports[baseline_col] = {
            "diagnostics": _diagnostics(frame, baseline_col),
            "featureSets": {},
        }
        for feature_set in ("liquidity_only", "price_context"):
            predicted, result = _grouped_ridge(frame, baseline_col, feature_set)
            reports[baseline_col]["featureSets"][feature_set] = result
            if result.get("status") == "EVALUATED":
                keep = [
                    "canonical_card_id",
                    f"{baseline_col}_{feature_set}_sold_v2",
                    f"{baseline_col}_{feature_set}_predicted_log_residual_v2",
                ]
                prediction_frames.append(predicted[keep])

    predictions = frame[["canonical_card_id"]].drop_duplicates().copy()
    for pred in prediction_frames:
        predictions = predictions.merge(pred, on="canonical_card_id", how="left", validate="one_to_one")

    OUT.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(OUT / "oof_predictions.csv", index=False)

    report = {
        "version": VERSION,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "researchOnly": True,
        "productionAuthorityChanged": False,
        "providerCalls": 0,
        "providerCreditsUsed": 0,
        "conditionEquivalenceAssumed": False,
        "inputPath": str(input_path.relative_to(ROOT) if input_path.is_relative_to(ROOT) else input_path),
        "inputSha256": _sha256(input_path),
        "inputRows": int(len(frame)),
        "sourceContainsV1LeakedColumn": source_contains_v1_leaked_column,
        "v1MethodologyReassessment": {
            "feature": "sold_median_to_nm_ratio",
            "definition": "sold_median / target_nm_market_price",
            "finding": "TARGET_LEAKAGE",
            "consequence": (
                "V1 plus-sold model metrics are not valid promotion evidence. "
                "The V1 baseline metrics remain descriptive, and the fact that dollar "
                "accuracy worsened even with leakage reinforces the do-not-promote decision."
            ),
        },
        "leakageGuard": {
            "forbiddenModelColumns": sorted(FORBIDDEN_MODEL_COLUMNS),
            "targetUsedOnlyForFitAndEvaluation": True,
            "soldPriceInterpretation": "noisy_market_clearing_evidence_not_nm_authority",
        },
        "results": reports,
        "nextGate": (
            "No sold-price feature may be promoted unless leakage-free grouped OOF results "
            "improve dollar error and rank/calibration metrics without materially worsening "
            "another primary metric, followed by forward-time validation."
        ),
    }
    (OUT / "pilot_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    args = parser.parse_args()
    analyze(args.input)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
