"""P5B.2/P5B.4: paired TCGplayer/eBayActiveAsk analysis dataset and estimator-sensitivity diagnostics.

Reads retained P4/P5B capture artifacts.  The eBay estimate is computed by the FROZEN P4C function
`freeze_ebay_active_ask_v1.estimate` unchanged; sensitivity diagnostics only call it on perturbed inputs.
"""
from __future__ import annotations

import gzip
import json
import statistics
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

from backend.scripts.freeze_ebay_active_ask_v1 import VERSION as EBAY_ESTIMATOR_VERSION, estimate
from backend.scripts import p5b_cohort_builder as cb

OUT = cb.OUT
P4_RUN = "97cff77b2a1c4b3e9c5d9cfc862d1c8c"


def load_decisions(run_id: str) -> dict[str, list[dict[str, Any]]]:
    by_card: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for suffix in (".decisions.jsonl", ".extension.decisions.jsonl"):
        path = OUT / f"ebay_p4a_{run_id}{suffix}"
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    by_card[row["target_id"]].append(row)
    return by_card


def run_ids() -> list[tuple[str, str]]:
    """(label, run_id) for P4 and every recorded P5B batch."""
    runs = [("p4", P4_RUN)]
    for path in sorted(OUT.glob("p5b_batch*_run.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        runs.append((f"p5b_batch{data['batch']}", data["run_id"]))
    return runs


def load_universe(market_date: str = "2026-09-20") -> dict[str, dict[str, Any]]:
    rows = json.load(gzip.open(OUT / f"p5b_universe_{market_date}.json.gz", "rt"))["rows"]
    return {r["canonical_card_id"]: r for r in rows}


def _band_of(value):
    return cb.price_band(value)


def ratio_stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0}
    ordered = sorted(values)

    def q(p):
        return ordered[min(len(ordered) - 1, max(0, round((len(ordered) - 1) * p)))]
    return {"n": len(values), "median": statistics.median(values), "mean": statistics.fmean(values),
            "p25": q(.25), "p75": q(.75), "p90": q(.90), "min": ordered[0], "max": ordered[-1]}


def sensitivity(rows: list[dict[str, Any]], target: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    """Perturb the eligible input set and re-run the frozen estimator (P5B.4; does not retune P4C)."""
    eligible = [r for r in rows if r.get("state") == "ENGLISH_PRICE_ELIGIBLE" and r.get("landed_ask_usd") is not None
                and r.get("seller_key_sha256") and Decimal(r["landed_ask_usd"]) > 0]
    base_price = base.get("estimated_price")
    out: dict[str, Any] = {"base_depth": base["depth_state"], "base_price": base_price}
    if base["depth_state"] != "SUFFICIENT" or base_price is None:
        return out
    base_d = Decimal(base_price)
    # cheapest per seller ordering
    by_seller: dict[str, dict[str, Any]] = {}
    for r in eligible:
        old = by_seller.get(r["seller_key_sha256"])
        if old is None or (Decimal(r["landed_ask_usd"]), r["item_id"]) < (Decimal(old["landed_ask_usd"]), old["item_id"]):
            by_seller[r["seller_key_sha256"]] = r
    ordered = sorted(by_seller.values(), key=lambda r: (Decimal(r["landed_ask_usd"]), r["item_id"]))

    def rerun(drop_items: set[str]):
        kept = [r for r in rows if r["item_id"] not in drop_items]
        return estimate(target, kept, "2000-01-01", "sens")

    def rel(res):
        # price movement of the frozen lower-three median, measured even when the perturbation
        # downgrades depth (selected_ask_2 exists for >=3 sellers); depth is reported separately.
        if res["selected_ask_2"] is None:
            return None
        return float(abs(Decimal(res["selected_ask_2"]) / base_d - 1))

    # (a) drop lowest seller, (b) drop each of the three contributing asks, (c) drop every single seller
    a = rerun({ordered[0]["item_id"]})
    b = [rerun({ordered[i]["item_id"]}) for i in range(3)]
    c = [rerun({s["item_id"]}) for s in ordered]
    # (d) one listing disappearing: remove one item; a same-seller cheaper-than-next item may substitute
    d = [rerun({r["item_id"]}) for r in eligible]

    def summarize(results):
        rels = [rel(x) for x in results]
        return {"n": len(results), "downgraded": sum(x["depth_state"] != "SUFFICIENT" for x in results),
                "max_rel": max([v for v in rels if v is not None], default=None)}
    out.update({"drop_lowest_seller": {"depth": a["depth_state"], "rel": rel(a)},
                "drop_one_contributing_ask": summarize(b),
                "drop_any_one_seller": summarize(c), "drop_any_one_listing": summarize(d),
                "seller_count": len(ordered),
                "ask_spread_max_over_min": float(Decimal(ordered[-1]["landed_ask_usd"]) / Decimal(ordered[0]["landed_ask_usd"]))})
    # (e) alternative ordering: ties broken in reverse item-id order must give the same price
    alt = sorted(by_seller.values(), key=lambda r: (Decimal(r["landed_ask_usd"]), r["item_id"][::-1]))[:3]
    out["alt_tie_order_price"] = str(Decimal(alt[1]["landed_ask_usd"]).quantize(Decimal(".01")))
    out["alt_tie_order_matches"] = out["alt_tie_order_price"] == base_price
    return out


def build_rows(market_date: str = "2026-09-20") -> list[dict[str, Any]]:
    universe = load_universe(market_date)
    rows_out: list[dict[str, Any]] = []
    p4_manifest = json.loads((OUT / "ebay_daily_pricing_targets_2026-09-19.json").read_text(encoding="utf-8"))
    p4_dates = {c["canonical_card_id"]: c.get("tcgplayer_captured_at") for c in p4_manifest["cards"]}
    resolution_path = OUT / "p5b_missing_variant_resolution.json"
    resolved_variants = {k: v["chosen_variant_id"] for k, v in json.loads(
        resolution_path.read_text(encoding="utf-8"))["cards"].items()} if resolution_path.exists() else {}
    for label, run_id in run_ids():
        capture = json.loads((OUT / f"ebay_p4a_{run_id}.json").read_text(encoding="utf-8"))
        decisions = load_decisions(run_id)
        run_date = capture["market_date"]
        for target in capture["targets"]:
            cid = target["canonical_card_id"]
            uni = universe.get(cid, {})
            if target.get("card_variant_id") is None and target.get("tcgplayer_market_price") is None and resolved_variants.get(cid):
                # Missing-TCG card: attach the resolver-ranked default variant so eBay evidence can be paired to an exact variant.
                target = {**target, "card_variant_id": resolved_variants[cid]}
            est = estimate(target, decisions.get(cid, []), run_date, run_id)
            tcg = target.get("tcgplayer_market_price")
            tcg_date = None
            age = None
            if label == "p4":
                tcg_date = p4_dates.get(cid)  # P4 manifest carries its own 2026-09-19 observed date
            else:
                tcg_date = uni.get("tcgplayer_captured_at")
            if tcg_date:
                age = (date.fromisoformat(run_date) - date.fromisoformat(str(tcg_date)[:10])).days
            ebay = float(est["estimated_price"]) if est["estimated_price"] is not None else None
            row = {
                "cohort": label, "run_id": run_id, "canonical_card_id": cid,
                "card_variant_id": target.get("card_variant_id"), "condition": "Near Mint",
                "set_id": target.get("set_id"), "set": uni.get("set_name"), "era": uni.get("era"),
                "rarity": uni.get("rarity"), "structure": uni.get("structure"), "catalog_role": uni.get("catalog_role"),
                "opening_eligible": uni.get("opening_eligible"), "set_value_eligible": uni.get("set_value_eligible"),
                "tcgplayer_price": tcg, "tcgplayer_observed_date": tcg_date, "tcgplayer_age_days": age,
                "tcg_status": cb.tcg_status(age, tcg) if tcg is not None else "missing",
                "ebay_price": ebay, "ebay_market_date": run_date, "ebay_age_days": 0,
                "ebay_eligible_listing_count": est["eligible_listing_count"],
                "ebay_distinct_seller_count": est["distinct_seller_count"], "ebay_depth_state": est["depth_state"],
                "ebay_estimator_version": est["estimator_version"],
                "ebay_selected_asks": [est["selected_ask_1"], est["selected_ask_2"], est["selected_ask_3"]],
                "ebay_input_fingerprint": est["input_evidence_fingerprint"],
                "ebay_estimator_fingerprint": est["estimator_fingerprint"],
                "stratum": (target.get("stratum") or ("p4_" + str(target.get("price_band")))),
                "price_band": _band_of(tcg),
            }
            if ebay is not None and tcg is not None and tcg > 0:
                row["absolute_difference"] = ebay - tcg
                row["percentage_difference"] = (ebay - tcg) / tcg
                row["ebay_to_tcg_ratio"] = ebay / tcg
            row["sensitivity"] = sensitivity(decisions.get(cid, []), target, est)
            # shipping diagnostic on the three selected asks (not part of the estimator)
            rows_ok = [r for r in decisions.get(cid, []) if r.get("state") == "ENGLISH_PRICE_ELIGIBLE"
                       and r.get("landed_ask_usd") is not None and r.get("shipping_price_usd") is not None]
            if rows_ok:
                row["median_shipping_usd"] = statistics.median(float(r["shipping_price_usd"]) for r in rows_ok)
            rows_out.append(row)
    return rows_out


def is_paired(row: dict[str, Any]) -> bool:
    return (row["ebay_depth_state"] == "SUFFICIENT" and row["card_variant_id"] is not None
            and row["ebay_price"] is not None and row["tcgplayer_price"] not in (None, 0)
            and row["tcgplayer_price"] > 0)


def main() -> None:
    rows = build_rows()
    path = OUT / "p5b_paired_dataset.json"
    path.write_text(json.dumps({"estimator": EBAY_ESTIMATOR_VERSION, "rows": rows}, indent=2) + "\n", encoding="utf-8")
    paired = [r for r in rows if is_paired(r)]
    print(json.dumps({"rows": len(rows), "paired_sufficient": len(paired)}, indent=2))


if __name__ == "__main__":
    main()
