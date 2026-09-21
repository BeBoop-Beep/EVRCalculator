"""P5B.7/P5B.11/P5B.12: evaluate candidate merge policies and gap-fill on the paired development cohort.

Development evidence only. No production writes; neither source is treated as ground truth.
"""
from __future__ import annotations

import json
import math
import statistics
from collections import Counter
from datetime import date
from typing import Any

from backend.scripts import p5b_dataset as ds
from backend.scripts import pokemon_multi_source_card_price_v1 as pol

OUT = ds.OUT
NM_CONDITION_ID = "4f8d1181-670e-4aea-937c-4d98d2e531a6"


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    if n == 0:
        return [0.0, 1.0]
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [(c - m) / d, (c + m) / d]


def to_inputs(row: dict[str, Any]):
    tcg = None
    if row["tcgplayer_price"] is not None and row["card_variant_id"]:
        tcg = {"canonical_card_id": row["canonical_card_id"], "card_variant_id": row["card_variant_id"],
               "market_price": row["tcgplayer_price"], "captured_at": row["tcgplayer_observed_date"]}
    ebay = {"canonical_card_id": row["canonical_card_id"], "card_variant_id": row["card_variant_id"],
            "estimated_price": row["ebay_price"], "depth_state": row["ebay_depth_state"],
            "estimator_version": row["ebay_estimator_version"], "distinct_seller_count": row["ebay_distinct_seller_count"],
            "eligible_listing_count": row["ebay_eligible_listing_count"], "market_date": row["ebay_market_date"],
            "estimator_fingerprint": row["ebay_estimator_fingerprint"]}
    return tcg, ebay


def evaluate() -> dict[str, Any]:
    rows = ds.build_rows()
    decisions = []
    for r in rows:
        tcg, ebay = to_inputs(r)
        d = pol.decide(tcg, ebay, date.fromisoformat(r["ebay_market_date"]), NM_CONDITION_ID)
        d["_row"] = r
        decisions.append(d)
    out: dict[str, Any] = {"policy": pol.POLICY_VERSION, "policy_fingerprint": pol.POLICY_FINGERPRINT,
                           "cohort_size": len(rows)}
    out["v1_decision_state_counts"] = dict(Counter(d["decision_state"] for d in decisions))
    out["v1_agreement_counts_all"] = dict(Counter(d["source_agreement_state"] for d in decisions))
    out["v1_freshness_counts"] = dict(Counter(d["tcgplayer_freshness_state"] for d in decisions))
    both = [d for d in decisions if d["tcgplayer_price"] and d["source_agreement_state"] != "SINGLE_SOURCE_ONLY"]
    out["paired_agreement_counts"] = dict(Counter(d["source_agreement_state"] for d in both))
    out["paired_by_freshness_agreement"] = {
        f: dict(Counter(d["source_agreement_state"] for d in both if d["tcgplayer_freshness_state"] == f))
        for f in sorted({d["tcgplayer_freshness_state"] for d in both})}
    out["paired_by_band_agreement"] = {
        b: dict(Counter(d["source_agreement_state"] for d in both if d["_row"]["price_band"] == b))
        for b in sorted({d["_row"]["price_band"] for d in both})}
    out["severe_or_moderate_rows"] = [
        {"canonical": d["canonical_card_id"][:8], "band": d["_row"]["price_band"], "era": d["_row"]["era"],
         "rarity": d["_row"]["rarity"], "set": d["_row"]["set"], "tcg": d["tcgplayer_price"], "ebay": d["ebay_price"],
         "diff_pct": d["source_difference_pct"], "state": d["source_agreement_state"],
         "freshness": d["tcgplayer_freshness_state"]} for d in both if d["source_agreement_state"] != "AGREE"]
    # ---- Policy A: TCG primary / eBay gap fill (stale TCG retained as-is: A does not remove existing prices)
    def sel_A(d):
        if d["tcgplayer_price"]:
            return "TCGPLAYER", d["tcgplayer_price"]
        if d["decision_state"] == "EBAY_ACTIVE_ASK_FALLBACK":
            return "EBAY_ACTIVE_ASK", d["ebay_price"]
        return None, None
    # ---- Policy B: A + stale/aging TCG replaced by sufficient eBay unless SEVERE disagreement
    def sel_B(d):
        s, p = sel_A(d)
        if d["tcgplayer_freshness_state"] in ("AGING", "STALE") and d["ebay_price"] and d["ebay_depth_state"] == "SUFFICIENT":
            if d["source_agreement_state"] in ("AGREE", "MODERATE_DISAGREEMENT"):
                return "EBAY_ACTIVE_ASK", d["ebay_price"]
        return s, p
    priced_now = sum(1 for d in decisions if d["tcgplayer_price"])
    A = [sel_A(d) for d in decisions]
    B = [sel_B(d) for d in decisions]
    out["baseline_priced"] = priced_now
    out["policy_A"] = {"priced": sum(1 for s, _ in A if s), "ebay_selected": sum(1 for s, _ in A if s == "EBAY_ACTIVE_ASK"),
                       "existing_prices_changed": 0}
    b_changes = [(d, sel) for d, sel in zip(decisions, B) if sel[0] == "EBAY_ACTIVE_ASK" and d["tcgplayer_price"]]
    out["policy_B"] = {"priced": sum(1 for s, _ in B if s), "ebay_selected": sum(1 for s, _ in B if s == "EBAY_ACTIVE_ASK"),
                       "existing_prices_replaced": len(b_changes),
                       "stale_or_aging_with_sufficient_ebay": sum(1 for d in decisions if d["tcgplayer_freshness_state"] in ("AGING", "STALE") and d["ebay_depth_state"] == "SUFFICIENT" and d["ebay_price"]),
                       "stale_candidates": [{"canonical": d["canonical_card_id"][:8], "tcg": d["tcgplayer_price"], "tcg_age_days": d["tcgplayer_age_days"],
                                             "ebay": d["ebay_price"], "diff_pct": d["source_difference_pct"], "agreement": d["source_agreement_state"]}
                                            for d in decisions if d["tcgplayer_freshness_state"] in ("AGING", "STALE") and d["ebay_depth_state"] == "SUFFICIENT" and d["ebay_price"]]}
    fresh_suff_agree = [d for d in decisions if d["tcgplayer_freshness_state"] == "FRESH" and d["ebay_price"] and d["source_agreement_state"] == "AGREE"]
    out["policy_C"] = {"eligible_fresh_sufficient_agree_rows": len(fresh_suff_agree),
                       "paired_rows_total": len(both), "min_paired_for_calibration_gate": 30,
                       "gate_met": len(both) >= 30, "weights_evaluated": False}
    paired = [r for r in rows if ds.is_paired(r)]
    lt5 = [r["ebay_to_tcg_ratio"] for r in paired if r["tcgplayer_price"] < 5]
    ge5 = [r["ebay_to_tcg_ratio"] for r in paired if r["tcgplayer_price"] >= 5]
    out["policy_D"] = {"paired_n": len(paired), "gate_n_ge_30": len(paired) >= 30,
                       "lt5_median": statistics.median(lt5), "ge5_median": statistics.median(ge5),
                       "lt5_iqr": [ds.ratio_stats(lt5)["p25"], ds.ratio_stats(lt5)["p75"]],
                       "ge5_iqr": [ds.ratio_stats(ge5)["p25"], ds.ratio_stats(ge5)["p75"]],
                       "stable_across_bands": False, "implemented": False}
    # ---- gap fill on sampled missing-TCG cards
    missing = [d for d in decisions if d["tcgplayer_freshness_state"] == "MISSING"]
    with_variant = [d for d in missing if d["card_variant_id"]]
    recovered = [d for d in missing if d["decision_state"] == "EBAY_ACTIVE_ASK_FALLBACK"]
    thin = [d for d in with_variant if d["ebay_depth_state"] == "THIN"]
    none = [d for d in with_variant if d["ebay_depth_state"] == "INSUFFICIENT"]
    n = len(with_variant)
    out["gap_fill_sample"] = {"missing_sampled": len(missing), "with_resolved_variant": n,
                              "recovered_sufficient": len(recovered), "thin_only": len(thin), "no_evidence": len(none),
                              "recovery_rate": len(recovered) / n if n else None, "recovery_wilson95": wilson(len(recovered), n),
                              "recovered_rows": [{"canonical": d["canonical_card_id"][:8], "variant": d["card_variant_id"][:8], "ebay_price": d["ebay_price"],
                                                  "sellers": d["ebay_seller_count"], "set": d["_row"]["set"], "rarity": d["_row"]["rarity"]} for d in recovered],
                              "unrecovered_by_set": dict(Counter(d["_row"]["set"] for d in with_variant if d not in recovered)),
                              "sampled_by_set": dict(Counter(d["_row"]["set"] for d in missing))}
    gap = json.loads((OUT / "p5b_gap_universe_2026-09-20.json").read_text(encoding="utf-8"))
    resolvable = sum(t["n"] for t in gap["totals"] if t["has_variant"])
    lo, hi = wilson(len(recovered), n)
    out["gap_fill_projection"] = {"missing_main_promo_total": sum(t["n"] for t in gap["totals"]), "identity_unresolved": sum(t["n"] for t in gap["totals"] if not t["has_variant"]),
                                  "resolvable": resolvable, "expected_recoverable_point": round(resolvable * len(recovered) / n) if n else None,
                                  "expected_recoverable_95": [round(resolvable * lo), round(resolvable * hi)],
                                  "caveat": "sample of 21 resolvable cards, dominated by low-supply strata; extrapolation is indicative only"}
    # ---- shadow rows (persistable grain) fingerprint / idempotency
    persisted = [{k: v for k, v in d.items() if k != "_row"} for d in decisions if d["card_variant_id"]]
    persisted_sorted = sorted(persisted, key=lambda x: (x["canonical_card_id"], x["market_date"]))
    out["shadow_rows_persistable"] = len(persisted_sorted)
    out["shadow_rows_fingerprint"] = pol.digest(persisted_sorted)
    (OUT / "p5b_shadow_authority_cohort_rows.json").write_text(json.dumps(persisted_sorted, indent=1) + "\n", encoding="utf-8")
    # ---- high-value disagreements
    out["high_value_paired"] = [{"canonical": d["canonical_card_id"][:8], "tcg": d["tcgplayer_price"], "ebay": d["ebay_price"],
                                 "diff_pct": d["source_difference_pct"], "state": d["source_agreement_state"], "set": d["_row"]["set"], "rarity": d["_row"]["rarity"]}
                                for d in both if float(d["tcgplayer_price"]) >= 50]
    return out


def main() -> None:
    out = evaluate()
    (OUT / "p5b_policy_evaluation.json").write_text(json.dumps(out, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
