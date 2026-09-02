import json, os, itertools
import numpy as np
import pandas as pd
from scipy import stats

D = r"d:\EVRCalculator\backend\research\scratch_pass1a_supplement"
df = pd.DataFrame(json.load(open(os.path.join(D, "product_cohort_raw.json"))))
df["price_efficiency"] = 1.0/df["effective_pack_cost"]
results = json.load(open(os.path.join(D,"results_part2.json")))

# --- Section 5: Overall_ECE diagnostic blend ---
df["ece_pctrank"] = df["ECE_raw"].rank(pct=True)*100
df["overall_ece_diag"] = 0.84*df["financial_rip_v4_score"] + 0.10*df["collector_appeal_v5_score"] + 0.06*df["ece_pctrank"]

reversal_examples = json.load(open(os.path.join(D,"ece_reversal_examples.json")))
big_gap = [e for e in reversal_examples if e["financial_gap"] >= 10]
max_gap = max((e["financial_gap"] for e in reversal_examples), default=0)
# same-set max gap is same set here since all reversal_examples are same-set already
max_same_set_gap = max_gap

# close-pair reversal rate: |financial_gap| < 5 among reversal candidates -> fraction of ALL same-set pairs with gap<5 that reversed
all_pairs_gap = []
for set_id, g in df.groupby("set_id"):
    g = g.reset_index(drop=True)
    n = len(g)
    for i,j in itertools.combinations(range(n),2):
        a,b = g.iloc[i], g.iloc[j]
        gap = abs(a["financial_rip_v4_score"]-b["financial_rip_v4_score"])
        v10_order = a["overall_rip_v10_score"] > b["overall_rip_v10_score"]
        ece_order = a["ECE_raw"] > b["ECE_raw"]
        all_pairs_gap.append({"gap": gap, "reversed": ece_order != v10_order})
apg = pd.DataFrame(all_pairs_gap)
close = apg[apg["gap"] < 5]
close_reversal_rate = float(close["reversed"].mean()) if len(close) else None

results["section5_financial_gap_protection"] = {
    "count_large_gap_overrides_ge10": len(big_gap),
    "max_financial_gap_overturned": float(max_gap),
    "max_same_set_financial_gap_overturned": float(max_same_set_gap),
    "close_pair_gap_lt5_count": int(len(close)),
    "close_pair_reversal_rate": close_reversal_rate,
}
print("big gap overrides (>=10):", len(big_gap), "max gap:", max_gap, "close-pair reversal rate:", close_reversal_rate)

# --- Section 6: family bias ---
fam_rows = []
for fam, g in df.groupby("product_family"):
    n = len(g)
    avg_price = g["product_market_cost"].mean()
    avg_eff = g["effective_pack_cost"].mean()
    avg_ece = g["ECE_raw"].mean()
    # rank movement under diag blend vs V10 (rank within full cohort)
    df["rank_v10"] = df["overall_rip_v10_score"].rank(ascending=False)
    df["rank_diag"] = df["overall_ece_diag"].rank(ascending=False)
    move = (df.loc[g.index,"rank_v10"] - df.loc[g.index,"rank_diag"])  # positive = riser (better rank = lower number, so v10_rank - diag_rank >0 means diag rank is better/lower -> riser)
    risers = int((move > 0).sum())
    fallers = int((move < 0).sum())
    # same-set reversal wins/losses for this family (from reversal_examples where product in family beat/lost due to ECE)
    wins = 0; losses = 0
    for e in reversal_examples:
        if e["product_a_family"] == fam and e["ece_winner"] == e["product_a"]:
            wins += 1
        if e["product_b_family"] == fam and e["ece_winner"] == e["product_b"]:
            wins += 1
        if e["product_a_family"] == fam and e["ece_winner"] != e["product_a"]:
            losses += 1
        if e["product_b_family"] == fam and e["ece_winner"] != e["product_b"]:
            losses += 1
    fam_rows.append({
        "family": fam, "n": n, "avg_product_price": float(avg_price), "avg_effective_pack_cost": float(avg_eff),
        "avg_ece": float(avg_ece), "avg_rank_movement": float(move.mean()),
        "risers": risers, "fallers": fallers, "same_set_reversal_wins": wins, "same_set_reversal_losses": losses,
    })
fam_df = pd.DataFrame(fam_rows).sort_values("avg_effective_pack_cost")
print(fam_df.to_string())
results["section6_family_bias"] = fam_rows

with open(os.path.join(D,"results_part3.json"),"w") as f:
    json.dump(results, f, indent=2, default=str)
