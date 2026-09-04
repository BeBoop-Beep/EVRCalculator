"""Pass 1B Phase 3: Historical Core K numerical reconstruction + shock instability.

Uses the exact production formula module backend/desirability/chase_core_k.py
(CORE_K_V1_VERSION = 'chase_core_k_v1_stage5c_3x_pack_equivalent_cost') as the
byte-identical contract -- not re-derived from memory. This is READ-ONLY use of
a pure function; nothing is written back to production/DB/migrations.
"""
import json, sys
from pathlib import Path
from scipy.stats import spearmanr

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from backend.desirability.chase_core_k import compute_core_k, CORE_K_V1_VERSION  # noqa: E402
from common import load_primary_cohort, load_product_cohort, a_raw_from_variants, DOCS  # noqa: E402

primary = load_primary_cohort()
products = load_product_cohort()["products"]

card_values_by_set = {row["set_id"]: row["per_variant"]["price_used"] for row in primary}
a_raw_by_set = {}
for row in primary:
    araw, _ = a_raw_from_variants(row["per_variant"]["price_used"], row["per_variant"]["modeled_probability"])
    a_raw_by_set[row["set_id"]] = araw

matched = []
for p in products:
    sid = p["set_id"]
    if sid not in card_values_by_set:
        continue
    result = compute_core_k(card_values=card_values_by_set[sid],
                            product_market_cost=p["product_market_cost"],
                            random_pack_count=p["random_pack_count"])
    if result["status"] != "ready":
        continue
    matched.append({
        "sealed_product_id": p["sealed_product_id"], "set_id": sid,
        "product_family": p["product_family"],
        "core_k": result["coreK"], "extended_k": result["extendedK"],
        "pack_equivalent_cost": result["packEquivalentCost"],
        "financial_rip_v4_score": p["financial_rip_v4_score"],
        "a_raw": a_raw_by_set[sid],
        "effective_pack_cost": p["effective_pack_cost"],
    })

print("version identity:", CORE_K_V1_VERSION)
print("products evaluated (matched, ready status):", len(matched), "of", len(products))

core_k = [m["core_k"] for m in matched]
a_raw = [m["a_raw"] for m in matched]
fin = [m["financial_rip_v4_score"] for m in matched]
peq = [m["pack_equivalent_cost"] for m in matched]

rho_a, p_a = spearmanr(core_k, a_raw)
rho_f, p_f = spearmanr(core_k, fin)
rho_p, p_p = spearmanr(core_k, peq)

baseline = {
    "n_products": len(matched),
    "core_k_vs_accessibility_a_raw": {"spearman": rho_a, "p": p_a},
    "core_k_vs_financial_rip_v4": {"spearman": rho_f, "p": p_f},
    "core_k_vs_effective_pack_cost": {"spearman": rho_p, "p": p_p},
    "core_k_distribution": {"min": min(core_k), "max": max(core_k),
                            "mean": sum(core_k) / len(core_k),
                            "n_zero": sum(1 for k in core_k if k == 0)},
}
print(json.dumps(baseline, indent=2, default=float))

# ---- shocks ----
def run_card_price_shock(pct):
    changed = 0
    deltas = []
    for m in matched:
        sid = m["set_id"]
        base_vals = card_values_by_set[sid]
        shocked_vals = [v * (1 + pct / 100.0) for v in base_vals]
        p = next(pp for pp in products if pp["sealed_product_id"] == m["sealed_product_id"])
        base_result = compute_core_k(card_values=base_vals, product_market_cost=p["product_market_cost"],
                                     random_pack_count=p["random_pack_count"])
        shocked_result = compute_core_k(card_values=shocked_vals, product_market_cost=p["product_market_cost"],
                                        random_pack_count=p["random_pack_count"])
        dk = shocked_result["coreK"] - base_result["coreK"]
        if dk != 0:
            changed += 1
        deltas.append(abs(dk))
    return {
        "products_evaluated": len(matched),
        "products_changed": changed,
        "share_changed": changed / len(matched),
        "mean_abs_delta_k": sum(deltas) / len(deltas),
        "max_abs_delta_k": max(deltas),
    }


def run_product_price_shock(pct):
    changed = 0
    deltas = []
    for m in matched:
        sid = m["set_id"]
        base_vals = card_values_by_set[sid]
        p = next(pp for pp in products if pp["sealed_product_id"] == m["sealed_product_id"])
        base_result = compute_core_k(card_values=base_vals, product_market_cost=p["product_market_cost"],
                                     random_pack_count=p["random_pack_count"])
        shocked_cost = p["product_market_cost"] * (1 + pct / 100.0)
        shocked_result = compute_core_k(card_values=base_vals, product_market_cost=shocked_cost,
                                        random_pack_count=p["random_pack_count"])
        dk = shocked_result["coreK"] - base_result["coreK"]
        if dk != 0:
            changed += 1
        deltas.append(abs(dk))
    return {
        "products_evaluated": len(matched),
        "products_changed": changed,
        "share_changed": changed / len(matched),
        "mean_abs_delta_k": sum(deltas) / len(deltas),
        "max_abs_delta_k": max(deltas),
    }


shock_pcts = [-20, -10, -5, -2, 2, 5, 10, 20]
card_shocks = {str(pct): run_card_price_shock(pct) for pct in shock_pcts}
product_shocks = {str(pct): run_product_price_shock(pct) for pct in shock_pcts}

print("\n=== card price shocks ===")
print(json.dumps(card_shocks, indent=2, default=float))
print("\n=== product price shocks ===")
print(json.dumps(product_shocks, indent=2, default=float))

out = {
    "version_identity": CORE_K_V1_VERSION,
    "baseline": baseline,
    "card_price_shocks": card_shocks,
    "product_price_shocks": product_shocks,
    "note": "Core K counts drawable cards crossing a hard 3x pack-equivalent-cost "
            "threshold -- an integer step function, unlike Accessibility's continuous "
            "A_raw. Non-zero share_changed at even small (+-2%) shocks with zero A_raw "
            "sensitivity (Phase 5/6) at the same magnitudes quantifies exactly this "
            "discontinuity gap.",
}
with open("phase3_core_k_result.json", "w") as f:
    json.dump(out, f, indent=2, default=float)
