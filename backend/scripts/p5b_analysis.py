"""P5B.3/P5B.4/P5B.6: characterize the TCGplayer vs eBayActiveAsk relationship from the paired dataset.

Diagnostics only. Neither source is treated as ground truth.
"""
from __future__ import annotations

import json
import math
import random
import statistics
from collections import Counter, defaultdict
from typing import Any

from backend.scripts import p5b_dataset as ds

OUT = ds.OUT
VINTAGE_ERAS = {"Base/WOTC", "Neo", "Gym", "E-Card", "EX", "POP", "NP", "Diamond and Pearl", "Platinum", "HeartGold and SoulSilver"}
OLD_ERAS = {"Base/WOTC", "Neo", "Gym", "E-Card", "EX", "POP", "NP"}


def bootstrap_median_ci(values: list[float], iters: int = 4000, seed: int = 20260920) -> list[float] | None:
    if len(values) < 5:
        return None
    rng = random.Random(seed)
    meds = sorted(statistics.median(rng.choices(values, k=len(values))) for _ in range(iters))
    return [meds[int(iters * .025)], meds[int(iters * .975)]]


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ratios = [r["ebay_to_tcg_ratio"] for r in rows]
    if not ratios:
        return {"n": 0}
    abs_pct = [abs(r["percentage_difference"]) for r in rows]
    s = ds.ratio_stats(ratios)
    s["log_ratio_mean_exp"] = math.exp(statistics.fmean(math.log(x) for x in ratios))
    s["median_abs_pct_diff"] = statistics.median(abs_pct)
    s["abs_pct_p90"] = ds.ratio_stats(abs_pct).get("p90")
    s["ratio_median_ci95"] = bootstrap_median_ci(ratios)
    s["weighted_ratio_by_tcg_value"] = sum(r["ebay_price"] for r in rows) / sum(r["tcgplayer_price"] for r in rows)
    return s


def analyze() -> dict[str, Any]:
    rows = ds.build_rows()
    paired = [r for r in rows if ds.is_paired(r)]
    result: dict[str, Any] = {
        "targets": len(rows), "cohort_counts": dict(Counter(r["cohort"] for r in rows)),
        "depth_counts": dict(Counter(r["ebay_depth_state"] for r in rows)),
        "tcg_status_counts": dict(Counter(r["tcg_status"] for r in rows)),
        "target_band_counts": dict(Counter(r["price_band"] for r in rows)),
        "target_era_counts": dict(Counter(r["era"] for r in rows)),
        "target_structure_counts": dict(Counter(r["structure"] for r in rows)),
        "sufficient_by_band": {b: [sum(1 for r in rows if r["price_band"] == b and r["ebay_depth_state"] == "SUFFICIENT"),
                                   sum(1 for r in rows if r["price_band"] == b)] for b in sorted({r["price_band"] for r in rows})},
        "sufficient_by_tcg_status": {b: [sum(1 for r in rows if r["tcg_status"] == b and r["ebay_depth_state"] == "SUFFICIENT"),
                                         sum(1 for r in rows if r["tcg_status"] == b)] for b in sorted({r["tcg_status"] for r in rows})},
        "paired_sufficient": len(paired),
        "overall": summarize(paired),
    }
    seg: dict[str, Any] = {}
    seg["price_band"] = {b: summarize([r for r in paired if r["price_band"] == b]) for b in sorted({r["price_band"] for r in paired})}
    seg["price_band_coarse"] = {
        "lt5": summarize([r for r in paired if r["tcgplayer_price"] < 5]),
        "5_to_20": summarize([r for r in paired if 5 <= r["tcgplayer_price"] < 20]),
        "20_plus": summarize([r for r in paired if r["tcgplayer_price"] >= 20])}
    seg["era_group"] = {"pre_2007_vintage": summarize([r for r in paired if r["era"] in OLD_ERAS]),
                        "modern": summarize([r for r in paired if r["era"] not in OLD_ERAS])}
    seg["structure"] = {k: summarize([r for r in paired if r["structure"] == k]) for k in sorted({r["structure"] for r in paired})}
    seg["tcg_freshness"] = {k: summarize([r for r in paired if r["tcg_status"] == k]) for k in sorted({r["tcg_status"] for r in paired})}
    result["segments"] = seg
    # shipping diagnostic: how much of the ratio is landed shipping (diagnostic only; estimator is frozen)
    ship = []
    for r in paired:
        ship_usd = r.get("median_shipping_usd")
        if ship_usd is not None:
            ship.append({"band": r["price_band"], "tcg": r["tcgplayer_price"], "ratio": r["ebay_to_tcg_ratio"],
                         "ratio_ex_median_shipping": max(r["ebay_price"] - ship_usd, 0) / r["tcgplayer_price"]})
    result["shipping_diagnostic"] = {
        "lt5_median_ratio_landed": statistics.median(x["ratio"] for x in ship if x["tcg"] < 5),
        "lt5_median_ratio_ex_ship": statistics.median(x["ratio_ex_median_shipping"] for x in ship if x["tcg"] < 5),
        "ge5_median_ratio_landed": statistics.median(x["ratio"] for x in ship if x["tcg"] >= 5),
        "ge5_median_ratio_ex_ship": statistics.median(x["ratio_ex_median_shipping"] for x in ship if x["tcg"] >= 5)}
    # thin-market noise: low-three median from THIN (3-4 sellers) vs SUFFICIENT rows, diagnostic only
    thin, suff = [], []
    for r in rows:
        asks = r["ebay_selected_asks"]
        if asks[1] is None or not r["tcgplayer_price"] or r["tcgplayer_price"] <= 0 or r["card_variant_id"] is None:
            continue
        ratio = float(asks[1]) / r["tcgplayer_price"]
        (thin if r["ebay_depth_state"] == "THIN" else suff if r["ebay_depth_state"] == "SUFFICIENT" else []).append(math.log(ratio))
    result["thin_vs_sufficient_log_ratio"] = {
        "thin_n": len(thin), "thin_sd": statistics.pstdev(thin) if len(thin) > 1 else None,
        "thin_median_ratio": math.exp(statistics.median(thin)) if thin else None,
        "sufficient_n": len(suff), "sufficient_sd": statistics.pstdev(suff) if len(suff) > 1 else None,
        "sufficient_median_ratio": math.exp(statistics.median(suff)) if suff else None}
    # estimator sensitivity
    sens = [r["sensitivity"] for r in paired if "drop_lowest_seller" in r["sensitivity"]]
    sens_all = [r["sensitivity"] for r in rows if "drop_lowest_seller" in r["sensitivity"]]
    def _agg(sl):
        drop_low = [s["drop_lowest_seller"]["rel"] for s in sl if s["drop_lowest_seller"]["rel"] is not None]
        return {
            "n": len(sl),
            "drop_lowest_seller_downgraded": sum(s["drop_lowest_seller"]["depth"] != "SUFFICIENT" for s in sl),
            "drop_lowest_seller_rel_median": statistics.median(drop_low) if drop_low else None,
            "drop_lowest_seller_rel_max": max(drop_low) if drop_low else None,
            "drop_any_listing_downgrade_share": statistics.fmean(s["drop_any_one_listing"]["downgraded"] / s["drop_any_one_listing"]["n"] for s in sl) if sl else None,
            "cards_with_any_listing_drop_downgrade": sum(s["drop_any_one_listing"]["downgraded"] > 0 for s in sl),
            "drop_any_seller_max_rel_median": statistics.median([s["drop_any_one_seller"]["max_rel"] for s in sl if s["drop_any_one_seller"]["max_rel"] is not None] or [0]),
            "drop_any_seller_max_rel_max": max([s["drop_any_one_seller"]["max_rel"] for s in sl if s["drop_any_one_seller"]["max_rel"] is not None] or [0]),
            "drop_contrib_ask_max_rel_max": max([s["drop_one_contributing_ask"]["max_rel"] for s in sl if s["drop_one_contributing_ask"]["max_rel"] is not None] or [0]),
            "alt_tie_order_matches": sum(bool(s.get("alt_tie_order_matches")) for s in sl),
            "sellers_exactly_5": sum(s["seller_count"] == 5 for s in sl)}
    result["sensitivity"] = _agg(sens_all)
    result["sensitivity_paired_only"] = _agg(sens)
    result["paired_rows"] = [{k: v for k, v in r.items() if k != "sensitivity"} for r in paired]
    return result


def main() -> None:
    result = analyze()
    (OUT / "p5b_analysis_summary.json").write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    slim = {k: v for k, v in result.items() if k != "paired_rows"}
    print(json.dumps(slim, indent=1, default=str))


if __name__ == "__main__":
    main()
