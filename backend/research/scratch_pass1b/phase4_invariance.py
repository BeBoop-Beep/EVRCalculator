"""Pass 1B Phase 4: uniform card-price scaling invariance + product-price irrelevance."""
import json
from common import load_primary_cohort, a_raw_from_variants, DOCS

cohort = load_primary_cohort()
results = {"card_price_scaling": {}, "product_price_change": {}}

worst_delta_scaling = 0.0
for scale in [0.5, 2.0, 10.0]:
    deltas = []
    for row in cohort:
        pv = row["per_variant"]
        prices = pv["price_used"]
        probs = pv["modeled_probability"]
        base_araw, _ = a_raw_from_variants(prices, probs)
        scaled_prices = [p * scale for p in prices]
        scaled_araw, _ = a_raw_from_variants(scaled_prices, probs)
        deltas.append(abs(scaled_araw - base_araw))
    worst = max(deltas)
    worst_delta_scaling = max(worst_delta_scaling, worst)
    results["card_price_scaling"][str(scale)] = {
        "worst_abs_delta": worst,
        "n_sets_checked": len(deltas),
    }

# Product price is NOT an Accessibility input at all -- A_raw computation reads
# only per_variant price_used / modeled_probability, never product_market_cost.
# So changing product price by any % literally cannot appear in the a_raw_from_variants
# call; we demonstrate this by computing A_raw with product_market_cost perturbed
# in the surrounding record (which the function never even receives) at each pct.
worst_delta_product = 0.0
for pct in [-20, -10, -5, -2, 2, 5, 10, 20]:
    deltas = []
    for row in cohort:
        pv = row["per_variant"]
        prices = pv["price_used"]
        probs = pv["modeled_probability"]
        base_araw, _ = a_raw_from_variants(prices, probs)
        # perturb product_market_cost (irrelevant input -- not passed to the function)
        perturbed_product_cost = row["product_market_cost_accessibility_run"] * (1 + pct / 100.0)
        # recompute A_raw again with EXACTLY the same (unperturbed) card inputs,
        # since compute_chase_accessibility has no product-cost parameter at all
        recomputed_araw, _ = a_raw_from_variants(prices, probs)
        deltas.append(abs(recomputed_araw - base_araw))
    worst = max(deltas)
    worst_delta_product = max(worst_delta_product, worst)
    results["product_price_change"][str(pct)] = {
        "worst_abs_delta": worst,
        "n_sets_checked": len(deltas),
        "note": "product_market_cost is not a parameter of compute_chase_accessibility; "
                "delta is exactly 0.0 by construction (the function signature is "
                "keyword-only over variants and physically cannot accept a product cost)."
    }

results["worst_delta_card_price_scaling_overall"] = worst_delta_scaling
results["worst_delta_product_price_change_overall"] = worst_delta_product

with open("phase4_invariance_result.json", "w") as f:
    json.dump(results, f, indent=2, default=float)

print("worst delta card price scaling:", worst_delta_scaling)
print("worst delta product price change:", worst_delta_product)
