import json, os, itertools
import numpy as np
import pandas as pd
from scipy import stats

D = r"d:\EVRCalculator\backend\research\scratch_pass1a_supplement"
df = pd.DataFrame(json.load(open(os.path.join(D, "product_cohort_raw.json"))))
df["price_efficiency"] = 1.0/df["effective_pack_cost"]

results = json.load(open(os.path.join(D,"results_part1.json")))

# --- Section 4: same-set price placebo ---
same_set_pairs = 0
ece_v10_reversals = 0
price_v10_reversals = 0
shared = 0
ece_only = 0
price_only_flag = 0
identical_ranking = True
divergent_examples = []
ece_reversal_examples = []

for set_id, g in df.groupby("set_id"):
    g = g.reset_index(drop=True)
    n = len(g)
    if n < 2:
        continue
    # check ECE ranking == price_efficiency ranking within set (since A_raw constant)
    r_ece = g["ECE_raw"].rank().tolist()
    r_price = g["price_efficiency"].rank().tolist()
    if r_ece != r_price:
        identical_ranking = False
    for i, j in itertools.combinations(range(n), 2):
        same_set_pairs += 1
        a, b = g.iloc[i], g.iloc[j]
        # order by V10
        v10_order = a["overall_rip_v10_score"] > b["overall_rip_v10_score"]
        ece_order = a["ECE_raw"] > b["ECE_raw"]
        price_order = a["price_efficiency"] > b["price_efficiency"]
        ece_rev = (ece_order != v10_order)
        price_rev = (price_order != v10_order)
        if ece_rev:
            ece_v10_reversals += 1
            cheaper_won = None
            winner = a["sealed_product_id"] if ece_order else b["sealed_product_id"]
            cheaper = a["sealed_product_id"] if a["effective_pack_cost"] < b["effective_pack_cost"] else b["sealed_product_id"]
            ece_reversal_examples.append({
                "set_id": set_id,
                "product_a": a["sealed_product_id"], "product_a_family": a["product_family"],
                "product_b": b["sealed_product_id"], "product_b_family": b["product_family"],
                "financial_a": a["financial_rip_v4_score"], "financial_b": b["financial_rip_v4_score"],
                "financial_gap": abs(a["financial_rip_v4_score"]-b["financial_rip_v4_score"]),
                "eff_cost_a": a["effective_pack_cost"], "eff_cost_b": b["effective_pack_cost"],
                "ece_a": a["ECE_raw"], "ece_b": b["ECE_raw"],
                "ece_winner": winner,
                "cheaper_product": cheaper,
                "cheaper_won": winner == cheaper,
            })
        if price_rev:
            price_v10_reversals += 1
        if ece_rev and price_rev:
            shared += 1
        if ece_rev and not price_rev:
            ece_only += 1
        if price_rev and not ece_rev:
            price_only_flag += 1

agreement_rate = 1 - (ece_v10_reversals/same_set_pairs) if same_set_pairs else None
cheaper_won_count = sum(1 for e in ece_reversal_examples if e["cheaper_won"])

results["same_set_placebo"] = {
    "same_set_pairs": same_set_pairs,
    "ece_within_set_ranking_identical_to_price_ranking_every_set": identical_ranking,
    "ece_vs_v10_reversals": ece_v10_reversals,
    "price_vs_v10_reversals": price_v10_reversals,
    "shared_reversals": shared,
    "ece_only_reversals": ece_only,
    "price_only_reversals": price_only_flag,
    "agreement_rate_ece_vs_v10": agreement_rate,
    "ece_reversals_where_cheaper_effective_cost_product_won": cheaper_won_count,
    "ece_reversals_total": len(ece_reversal_examples),
}
with open(os.path.join(D,"ece_reversal_examples.json"),"w") as f:
    json.dump(ece_reversal_examples, f, indent=2, default=str)

print("same_set_pairs:", same_set_pairs)
print("identical ranking to price (all sets)?", identical_ranking)
print("ece_v10_reversals:", ece_v10_reversals, "price_v10_reversals:", price_v10_reversals,
      "shared:", shared, "ece_only:", ece_only, "price_only:", price_only_flag)
print("agreement rate:", agreement_rate)
print("cheaper won in ece reversals:", cheaper_won_count, "/", len(ece_reversal_examples))

with open(os.path.join(D,"results_part2.json"),"w") as f:
    json.dump(results, f, indent=2, default=str)
