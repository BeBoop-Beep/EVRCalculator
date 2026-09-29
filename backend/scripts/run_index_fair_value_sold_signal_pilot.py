"""Research-only PkmnPrices sold-signal pilot for inDex Fair Value.

Purpose:
- deterministically sample the frozen strict F1 Fair Value cohort across the seven
  frozen price bands;
- fetch a bounded set of ungraded PkmnPrices eBay sold rows;
- aggregate transaction/liquidity descriptors without persisting raw provider rows;
- compare those descriptors with the existing structural/market-anchored Fair
  Value diagnostics.

This script NEVER writes Supabase and NEVER changes a production pricing authority.
PkmnPrices sold rows do not expose raw-card condition, so sold prices are NOT
treated as Near Mint prices or as Set Value inputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from backend.db.clients.supabase_client import create_service_role_client
from backend.pricing_pipeline.pkmnprices_client import PkmnPricesClient
from backend.pricing_pipeline.pkmnprices_credentials import load_pkmnprices_credentials
from backend.pricing_pipeline.pkmnprices_sold import normalize_sold_listing

ROOT = Path(__file__).resolve().parents[2]
F1 = ROOT / "backend/artifacts/index_fair_value/index_fair_value_f1_dataset.json"
F2 = ROOT / "backend/artifacts/index_fair_value/index_fair_value_f2_oof_predictions.csv"
F2R = ROOT / "backend/artifacts/index_fair_value/index_fair_value_f2r_target_blind_predictions.csv"
OUT = ROOT / "backend/artifacts/index_fair_value/sold_signal_pilot_v1"
EXPECTED_F1_FINGERPRINT = "0e7b04f1119ce525fbe387b50b523ac580aa7a14c758e5d16487a334969825d9"
VERSION = "index_fair_value_sold_signal_pilot_v1"
SEED = 20260929
BANDS = [
    (-math.inf, 5, "under_5"),
    (5, 10, "5_to_under_10"),
    (10, 25, "10_to_under_25"),
    (25, 50, "25_to_under_50"),
    (50, 100, "50_to_under_100"),
    (100, 250, "100_to_under_250"),
    (250, math.inf, "250_plus"),
]


def _hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def _band(value: float) -> str:
    return next(label for lo, hi, label in BANDS if lo <= value < hi)


def _paged(factory: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        page = list(factory().range(start, start + 999).execute().data or [])
        rows.extend(page)
        if len(page) < 1000:
            return rows
        start += 1000


def _load_frozen() -> pd.DataFrame:
    payload = json.loads(F1.read_text(encoding="utf-8"))
    if payload["manifest"]["datasetFingerprint"] != EXPECTED_F1_FINGERPRINT:
        raise RuntimeError("SOLD_SIGNAL_PILOT_F1_FINGERPRINT_DRIFT")
    rows = [row for row in payload["rows"] if row.get("eligible_v1_strict")]
    df = pd.DataFrame(rows)
    df["price"] = df["target_market_price_usd"].astype(float)
    df["price_band"] = df["price"].map(_band)

    f2 = pd.read_csv(F2)
    structural = (
        f2[f2["model"] == "ModelC"][["canonical_card_id", "predicted_price"]]
        .rename(columns={"predicted_price": "structural_price"})
    )
    if structural["canonical_card_id"].duplicated().any():
        raise RuntimeError("SOLD_SIGNAL_PILOT_DUPLICATE_STRUCTURAL_ROWS")
    df = df.merge(structural, on="canonical_card_id", validate="one_to_one")

    f2r = pd.read_csv(F2R)
    market = (
        f2r[f2r["method"] == "R1_local_residual_10"][
            ["canonical_card_id", "predicted_price"]
        ].rename(columns={"predicted_price": "market_anchored_price"})
    )
    if market["canonical_card_id"].duplicated().any():
        raise RuntimeError("SOLD_SIGNAL_PILOT_DUPLICATE_MARKET_ROWS")
    return df.merge(market, on="canonical_card_id", validate="one_to_one")


def _variant_product_ids(db: Any, variant_ids: list[str]) -> dict[str, str]:
    rows = _paged(
        lambda: db.table("card_variant_external_identities")
        .select("card_variant_id,provider,external_product_id")
        .eq("provider", "tcgplayer")
        .in_("card_variant_id", variant_ids)
        .order("card_variant_id")
    )
    grouped: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        value = str(row.get("external_product_id") or "").strip()
        if value:
            grouped[str(row["card_variant_id"])].add(value)
    return {vid: next(iter(values)) for vid, values in grouped.items() if len(values) == 1}


def _variant_rows(db: Any, variant_ids: list[str]) -> dict[str, dict[str, Any]]:
    rows = _paged(
        lambda: db.table("card_variants")
        .select("id,edition,printing_type,special_type")
        .in_("id", variant_ids)
        .order("id")
    )
    return {str(row["id"]): dict(row) for row in rows}


def _deterministic_sample(
    df: pd.DataFrame, product_by_variant: dict[str, str], per_band: int
) -> pd.DataFrame:
    eligible = df[df["card_variant_id"].astype(str).isin(product_by_variant)].copy()
    eligible["tcgplayer_product_id"] = eligible["card_variant_id"].astype(str).map(product_by_variant)
    eligible["sample_key"] = eligible["canonical_card_id"].map(
        lambda value: hashlib.sha256(f"{SEED}:{value}".encode()).hexdigest()
    )
    picks = []
    for label in [x[2] for x in BANDS]:
        group = eligible[eligible["price_band"] == label].sort_values(
            ["sample_key", "canonical_card_id"]
        )
        picks.append(group.head(max(0, per_band)))
    return pd.concat(picks, ignore_index=True) if picks else eligible.head(0)


def _median(values: list[float]) -> float | None:
    return float(statistics.median(values)) if values else None


def _mad(values: list[float]) -> float | None:
    if not values:
        return None
    med = statistics.median(values)
    return float(statistics.median(abs(x - med) for x in values))


def _aggregate(
    rows: list[dict[str, Any]], target: dict[str, Any], cutoff: date
) -> dict[str, Any]:
    exact = [
        row for row in rows
        if row.get("fair_value_signal_eligible")
        and date.fromisoformat(str(row["sold_at"])[:10]) <= cutoff
    ]
    exact.sort(key=lambda row: (str(row["sold_at"]), int(row["provider_listing_id"])))
    prices = [float(row["price"]) for row in exact]
    sold_dates = [date.fromisoformat(str(row["sold_at"])[:10]) for row in exact]
    recent = lambda days: sum((cutoff - sold).days <= days for sold in sold_dates)
    last_sale_age = min(((cutoff - sold).days for sold in sold_dates), default=None)
    median = _median(prices)
    p25 = float(np.percentile(prices, 25)) if prices else None
    p75 = float(np.percentile(prices, 75)) if prices else None
    trend = None
    if len(exact) >= 4:
        first = [float(row["price"]) for row in exact[: max(2, len(exact)//3)]]
        last = [float(row["price"]) for row in exact[-max(2, len(exact)//3):]]
        a, b = _median(first), _median(last)
        trend = (b / a - 1.0) if a and b else None
    return {
        "canonical_card_id": target["canonical_card_id"],
        "card_variant_id": target["card_variant_id"],
        "root_set_id": target["root_set_id"],
        "set_name": target["set_name"],
        "card_name": target["card_name"],
        "price_band": target["price_band"],
        "target_nm_market_price": float(target["price"]),
        "structural_price": float(target["structural_price"]),
        "market_anchored_price": float(target["market_anchored_price"]),
        "sold_rows_returned": len(rows),
        "eligible_sold_count": len(exact),
        "sold_30d": recent(30),
        "sold_90d": recent(90),
        "sold_180d": recent(180),
        "last_sale_age_days": last_sale_age,
        "sold_median": median,
        "sold_mad": _mad(prices),
        "sold_iqr": (p75 - p25) if p25 is not None else None,
        "sold_min": min(prices) if prices else None,
        "sold_max": max(prices) if prices else None,
        "sold_trend_fraction": trend,
        "sold_median_to_nm_ratio": (median / float(target["price"])) if median else None,
        "condition_equivalence_assumed": False,
    }


def _metrics(actual: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    pred = np.maximum(pred, 0.01)
    ape = np.abs(pred - actual) / actual
    tss = np.sum((actual - actual.mean()) ** 2)
    rho = spearmanr(actual, pred).statistic if len(actual) > 2 else np.nan
    return {
        "n": int(len(actual)),
        "mae": float(mean_absolute_error(actual, pred)),
        "mdape": float(np.median(ape) * 100),
        "within30Pct": float(np.mean(ape <= 0.30) * 100),
        "r2Dollars": float(1 - np.sum((pred - actual) ** 2) / tss) if tss else float("nan"),
        "spearman": float(rho) if not np.isnan(rho) else float("nan"),
    }


FEATURES = [
    "sold_30d", "sold_90d", "sold_180d", "last_sale_age_days",
    "sold_median_to_nm_ratio", "sold_mad", "sold_iqr", "sold_trend_fraction",
]


def _grouped_correction(frame: pd.DataFrame, baseline_col: str) -> tuple[np.ndarray, dict[str, Any]]:
    usable = frame[frame["eligible_sold_count"] >= 3].copy()
    if usable["root_set_id"].nunique() < 3 or len(usable) < 20:
        return np.array([]), {"status": "INSUFFICIENT_SAMPLE", "n": len(usable)}
    X = usable[FEATURES].astype(float)
    y = np.log(usable["target_nm_market_price"].astype(float)) - np.log(
        usable[baseline_col].astype(float)
    )
    groups = usable["root_set_id"].astype(str)
    splits = min(5, groups.nunique())
    gkf = GroupKFold(n_splits=splits)
    pred_residual = np.zeros(len(usable))
    for train, test in gkf.split(X, y, groups):
        model = Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("ridge", Ridge(alpha=10.0)),
        ])
        model.fit(X.iloc[train], y.iloc[train])
        pred_residual[test] = model.predict(X.iloc[test])
    predicted = usable[baseline_col].astype(float).to_numpy() * np.exp(pred_residual)
    return predicted, {
        "status": "EVALUATED",
        "n": len(usable),
        "rows": usable.index.tolist(),
        "baseline": _metrics(
            usable["target_nm_market_price"].astype(float).to_numpy(),
            usable[baseline_col].astype(float).to_numpy(),
        ),
        "plusSoldSignals": _metrics(
            usable["target_nm_market_price"].astype(float).to_numpy(), predicted
        ),
    }


def run(*, per_band: int, max_sold_per_card: int, credit_cap: int, cutoff: date) -> dict[str, Any]:
    db = create_service_role_client()
    frozen = _load_frozen()
    variant_ids = sorted({str(v) for v in frozen["card_variant_id"].dropna()})
    products = _variant_product_ids(db, variant_ids)
    variants = _variant_rows(db, variant_ids)
    sample = _deterministic_sample(frozen, products, per_band)
    if sample.empty:
        raise RuntimeError("SOLD_SIGNAL_PILOT_SAMPLE_EMPTY")

    creds = load_pkmnprices_credentials(allow_frontend_fallback=False)
    provider = PkmnPricesClient(
        creds.api_key, min_request_interval=1.05, max_retries=2, timeout=30
    )
    aggregates = []
    failures = []
    for raw in sample.to_dict("records"):
        if provider.credits_charged >= credit_cap:
            failures.append({"canonical_card_id": raw["canonical_card_id"], "reason": "CREDIT_CAP"})
            break
        try:
            cards = provider.cards_by_tcgplayer_id(raw["tcgplayer_product_id"], per_page=5)
            matches = [
                card for card in cards
                if str(card.get("tcg_player_id") or "") == str(raw["tcgplayer_product_id"])
            ]
            if len(matches) != 1:
                raise RuntimeError(f"provider_card_identity_count={len(matches)}")
            provider_id = matches[0]["id"]
            remaining = max(0, credit_cap - provider.credits_charged)
            collection = provider.ebay_sold_collection(
                provider_id,
                graded=False,
                max_items=min(max_sold_per_card, remaining),
            )
            target_variant = variants[str(raw["card_variant_id"])]
            normalized = [
                normalize_sold_listing(
                    row,
                    provider_card_id=provider_id,
                    canonical_card_id=raw["canonical_card_id"],
                    internal_variants=[target_variant],
                    collected_at=datetime.now(timezone.utc).isoformat(),
                )
                for row in collection["rows"]
            ]
            aggregates.append(_aggregate(normalized, raw, cutoff))
        except Exception as exc:
            failures.append({
                "canonical_card_id": raw["canonical_card_id"],
                "reason": type(exc).__name__,
                "detail": str(exc)[:160],
            })

    frame = pd.DataFrame(aggregates)
    structural_pred, structural = _grouped_correction(frame, "structural_price") if not frame.empty else (np.array([]), {"status":"NO_ROWS"})
    market_pred, market = _grouped_correction(frame, "market_anchored_price") if not frame.empty else (np.array([]), {"status":"NO_ROWS"})
    if len(structural_pred):
        rows = frame[frame["eligible_sold_count"] >= 3].copy()
        rows["structural_plus_sold"] = structural_pred
        rows["market_plus_sold"] = market_pred
    else:
        rows = frame

    manifest = {
        "version": VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cutoff_date": cutoff.isoformat(),
        "research_only": True,
        "production_authority_changed": False,
        "condition_equivalence_assumed": False,
        "f1_fingerprint": EXPECTED_F1_FINGERPRINT,
        "sample_seed": SEED,
        "per_band_target": per_band,
        "max_sold_per_card": max_sold_per_card,
        "credit_cap": credit_cap,
        "provider_credits_used": provider.credits_charged,
        "provider_credit_limit": provider.credits_limit,
        "sample_rows": len(sample),
        "completed_rows": len(frame),
        "failures": failures,
        "sample_by_band": sample["price_band"].value_counts().sort_index().to_dict(),
        "eligible_3plus_by_band": (
            frame[frame["eligible_sold_count"] >= 3]["price_band"].value_counts().sort_index().to_dict()
            if not frame.empty else {}
        ),
        "structural_information_gain": structural,
        "market_anchored_information_gain": market,
        "interpretation": (
            "Cross-sectional information-gain pilot only. Backfilled sold rows were ingested after "
            "their historical sale dates, so this is not forward-time validation. Sold raw-card "
            "condition is unknown and no Near Mint equivalence is assumed."
        ),
    }
    manifest["fingerprint"] = _hash({k:v for k,v in manifest.items() if k!="generated_at"})

    OUT.mkdir(parents=True, exist_ok=True)
    rows.to_csv(OUT / "sample_features.csv", index=False)
    (OUT / "pilot_report.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True, default=str))
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-band", type=int, default=40)
    parser.add_argument("--max-sold-per-card", type=int, default=20)
    parser.add_argument("--credit-cap", type=int, default=6000)
    parser.add_argument("--cutoff-date", type=date.fromisoformat, default=date(2026, 9, 28))
    args = parser.parse_args()
    report = run(
        per_band=max(1, args.per_band),
        max_sold_per_card=max(1, min(args.max_sold_per_card, 20)),
        credit_cap=max(100, args.credit_cap),
        cutoff=args.cutoff_date,
    )
    return 0 if report["completed_rows"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
