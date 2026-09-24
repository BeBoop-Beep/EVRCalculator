"""Freeze and replay P4 active-ask evidence without touching canonical prices."""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from backend.scripts.ebay_english_price_eligibility_v1 import VERSION as ELIGIBILITY_VERSION, fingerprint as eligibility_fingerprint

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "backend/artifacts/pricing"
VERSION = "ebay_active_ask_lower3_seller_median_v1"
RUN_ID = "97cff77b2a1c4b3e9c5d9cfc862d1c8c"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def estimate(target, rows, market_date, run_id):
    eligible = {}
    for row in rows:
        if row.get("state") != "ENGLISH_PRICE_ELIGIBLE" or not row.get("seller_key_sha256"):
            continue
        if row.get("landed_ask_usd") is None or Decimal(row["landed_ask_usd"]) <= 0:
            continue
        item = row["item_id"]
        old = eligible.get(item)
        if old is None or (Decimal(row["landed_ask_usd"]), row["seller_key_sha256"]) < (Decimal(old["landed_ask_usd"]), old["seller_key_sha256"]):
            eligible[item] = row
    sellers = {}
    for row in eligible.values():
        key = row["seller_key_sha256"]
        old = sellers.get(key)
        if old is None or (Decimal(row["landed_ask_usd"]), row["item_id"]) < (Decimal(old["landed_ask_usd"]), old["item_id"]):
            sellers[key] = row
    selected = sorted(sellers.values(), key=lambda r: (Decimal(r["landed_ask_usd"]), r["item_id"]))
    depth = "SUFFICIENT" if len(selected) >= 5 else "THIN" if len(selected) >= 3 else "INSUFFICIENT"
    provenance = [{"evidence_row_id": None, "listing_item_id": r["item_id"],
                   "seller_key_sha256": r["seller_key_sha256"], "landed_ask_usd": r["landed_ask_usd"]}
                  for r in sorted(eligible.values(), key=lambda r: r["item_id"])]
    selected_asks = [str(Decimal(r["landed_ask_usd"]).quantize(Decimal(".01"))) for r in selected[:3]]
    result = {"pricing_run_id": run_id, "canonical_card_id": target["canonical_card_id"],
              "card_variant_id": target.get("card_variant_id"), "condition_id": None,
              "market_date": market_date, "source": "eBayActiveAsk", "evidence_kind": "active_ask",
              "estimator_version": VERSION, "eligibility_policy_version": ELIGIBILITY_VERSION,
              "eligible_listing_count": len(eligible), "distinct_seller_count": len(selected),
              "landed_ask_min": selected_asks[0] if selected_asks else None,
              "landed_ask_max": str(max(Decimal(r["landed_ask_usd"]) for r in selected)) if selected else None,
              "selected_ask_1": selected_asks[0] if len(selected_asks) > 0 else None,
              "selected_ask_2": selected_asks[1] if len(selected_asks) > 1 else None,
              "selected_ask_3": selected_asks[2] if len(selected_asks) > 2 else None,
              "estimated_price": selected_asks[1] if depth == "SUFFICIENT" and target.get("card_variant_id") else None,
              "depth_state": depth, "input_evidence_fingerprint": digest(provenance),
              "contributing_evidence": provenance, "tcgplayer_reference": target.get("tcgplayer_market_price"),
              "price_band": target.get("price_band")}
    result["estimator_fingerprint"] = digest({k: v for k, v in result.items() if k not in ("tcgplayer_reference", "price_band")})
    return result


def replay(run_id=RUN_ID):
    capture = json.loads((OUT / f"ebay_p4a_{run_id}.json").read_text(encoding="utf-8"))
    by_card = defaultdict(list)
    for suffix in (".decisions.jsonl", ".extension.decisions.jsonl"):
        for line in (OUT / f"ebay_p4a_{run_id}{suffix}").read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                by_card[row["target_id"]].append(row)
    rows = [estimate(t, by_card[t["canonical_card_id"]], capture["market_date"], run_id) for t in capture["targets"]]
    result = {"estimator_version": VERSION, "eligibility_fingerprint": eligibility_fingerprint(),
              "source_run": run_id, "market_date": capture["market_date"],
              "depth_counts": dict(Counter(r["depth_state"] for r in rows)), "rows": rows}
    result["fingerprint"] = digest(result)
    return result


if __name__ == "__main__":
    data = replay()
    (OUT / f"ebay_p4c_{RUN_ID}.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"fingerprint": data["fingerprint"], "depth_counts": data["depth_counts"],
                      "numeric_estimates": sum(r["estimated_price"] is not None for r in data["rows"])}, indent=2))
