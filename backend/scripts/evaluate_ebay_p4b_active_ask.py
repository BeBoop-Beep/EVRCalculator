"""Reproducible, unpublished development of seller-diverse active-ask estimates."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.scripts.ebay_english_price_eligibility_v1 import VERSION as ELIGIBILITY_VERSION, fingerprint as eligibility_fingerprint

OUT = Path(__file__).resolve().parents[2] / "backend/artifacts/pricing"
VERSION = "ebay_active_ask_lowest_three_seller_median_candidate_v1"


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _median(values: list[Decimal]) -> Decimal | None:
    return Decimal(str(statistics.median(values))) if values else None


def _q1(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * .25)]


def evaluate_card(target: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [row for row in rows if row.get("state") == "ENGLISH_PRICE_ELIGIBLE"
                and row.get("landed_ask_usd") is not None]
    # One cheapest executable ask per seller prevents prolific sellers from dominating.
    by_seller: dict[str, dict[str, Any]] = {}
    for row in eligible:
        key = row.get("seller_key_sha256") or f"unknown:{row['item_id']}"
        old = by_seller.get(key)
        if old is None or (Decimal(row["landed_ask_usd"]), row["item_id"]) < (Decimal(old["landed_ask_usd"]), old["item_id"]):
            by_seller[key] = row
    seller_rows = sorted(by_seller.values(), key=lambda row: (Decimal(row["landed_ask_usd"]), row["item_id"]))
    asks = [Decimal(row["landed_ask_usd"]) for row in seller_rows]
    all_asks = [Decimal(row["landed_ask_usd"]) for row in eligible]
    n = len(asks)
    low3 = _median(asks[:3]) if n >= 3 else None
    low5 = _median(asks[:5]) if n >= 5 else None
    lower_half = _median(asks[:max(3, math.ceil(n / 2))]) if n >= 3 else None
    leave_one_out = [_median((asks[:i] + asks[i + 1:])[:3]) for i in range(n)] if n >= 4 else []
    max_loo = max(abs(float(x / low3 - 1)) for x in leave_one_out) if low3 and leave_one_out else None
    drop_high = _median(asks[:-1][:3]) if n >= 4 else None
    depth = "SUFFICIENT" if n >= 5 and max_loo is not None and max_loo <= .25 else ("THIN" if n >= 3 else "INSUFFICIENT")
    benchmark = target.get("tcgplayer_market_price")
    ratio = float(low3 / Decimal(str(benchmark))) if low3 is not None and benchmark and benchmark > 0 else None
    source_inputs = [{"listing_item_id": row["item_id"], "seller_key_sha256": row.get("seller_key_sha256"),
                      "landed_ask_usd": row["landed_ask_usd"]} for row in seller_rows]
    provenance = {"estimator_version": VERSION, "eligibility_version": ELIGIBILITY_VERSION,
                  "eligibility_fingerprint": eligibility_fingerprint(),
                  "canonical_card_id": target["canonical_card_id"],
                  "card_variant_id": target.get("card_variant_id"), "inputs": source_inputs}
    return {
        "canonical_card_id": target["canonical_card_id"], "card_variant_id": target.get("card_variant_id"),
        "era_id": target.get("era_id"), "price_band": target.get("price_band"),
        "tcgplayer_market_price": benchmark, "eligible_listing_count": len(eligible), "seller_count": n,
        "landed_ask_min": str(min(asks)) if asks else None, "landed_ask_max": str(max(asks)) if asks else None,
        "dispersion_max_over_min": float(max(asks) / min(asks)) if asks and min(asks) > 0 else None,
        "depth_state": depth,
        "candidates": {"lowest": str(min(asks)) if asks else None,
                       "low3_seller_median": str(low3) if low3 is not None else None,
                       "low5_seller_median": str(low5) if low5 is not None else None,
                       "seller_lower_quartile": str(_q1(asks)) if asks else None,
                       "trimmed_lower_half_median": str(lower_half) if lower_half is not None else None,
                       "all_listing_median": str(_median(all_asks)) if all_asks else None,
                       "all_seller_median": str(_median(asks)) if asks else None},
        "max_leave_one_seller_out_relative_change": max_loo,
        "drop_highest_relative_change": abs(float(drop_high / low3 - 1)) if low3 and drop_high else None,
        "ebay_over_tcgplayer_ratio": ratio,
        "absolute_percentage_difference": abs(ratio - 1) if ratio is not None else None,
        "source_estimate_usd": str(low3) if depth == "SUFFICIENT" and target.get("card_variant_id") else None,
        "provenance": provenance, "calculation_fingerprint": _hash(provenance),
    }


def evaluate(run_id: str) -> dict[str, Any]:
    capture = json.loads((OUT / f"ebay_p4a_{run_id}.json").read_text(encoding="utf-8"))
    extension_path = OUT / f"ebay_p4a_{run_id}.extension.json"
    extension = json.loads(extension_path.read_text(encoding="utf-8")) if extension_path.exists() else None
    decisions = []
    for suffix in (".decisions.jsonl", ".extension.decisions.jsonl"):
        path = OUT / f"ebay_p4a_{run_id}{suffix}"
        if path.exists():
            decisions.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    by_card = defaultdict(list)
    for row in decisions:
        by_card[row["target_id"]].append(row)
    cards = [evaluate_card(target, by_card[target["canonical_card_id"]]) for target in capture["targets"]]
    publishable = [row for row in cards if row["source_estimate_usd"] is not None]
    ratios = [row["ebay_over_tcgplayer_ratio"] for row in cards if row["ebay_over_tcgplayer_ratio"] is not None and row["depth_state"] == "SUFFICIENT"]
    result = {"classification": "DEVELOPMENT_NOT_PUBLISHED", "source_name": "eBayActiveAsk",
              "estimator_version": VERSION, "eligibility_version": ELIGIBILITY_VERSION,
              "run_id": run_id, "market_date": capture["market_date"],
              "request_count": capture["requests_attempted"] + (extension or {}).get("requests_attempted", 0),
              "target_count": len(cards), "detail_decision_count": len(decisions),
              "state_counts": dict(Counter(row["state"] for row in decisions)),
              "depth_counts": dict(Counter(row["depth_state"] for row in cards)),
              "resolved_variant_sufficient_count": len(publishable),
              "tcg_benchmark_ratio_median": statistics.median(ratios) if ratios else None,
              "tcg_benchmark_ratio_min": min(ratios) if ratios else None,
              "tcg_benchmark_ratio_max": max(ratios) if ratios else None,
              "cards": cards}
    result["fingerprint"] = _hash(result)
    (OUT / f"ebay_p4b_{run_id}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    result = evaluate(args.run_id)
    print(json.dumps({key: result[key] for key in ("run_id", "request_count", "target_count",
        "depth_counts", "resolved_variant_sufficient_count", "tcg_benchmark_ratio_median", "fingerprint")}, indent=2))
