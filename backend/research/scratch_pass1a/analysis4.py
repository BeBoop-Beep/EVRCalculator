import json, os
import pandas as pd, numpy as np
from scipy.stats import spearmanr

D = r"d:\EVRCalculator\backend\research\scratch_pass1a"
cohort = pd.DataFrame(json.load(open(os.path.join(D,"cohort_with_candidates.json"))))
variant_store = json.load(open(os.path.join(D,"variant_store.json")))
results = json.load(open(os.path.join(D,"partial_results.json")))
n = len(cohort)

# Section 7: negative control sum(HC*V*p)/cost
neg_control = []
for _, row in cohort.iterrows():
    s = row.set_id
    vs = variant_store[s]
    hc = np.array(vs["HC"]); v = np.array(vs["price_used"]); p = np.array(vs["modeled_probability"])
    val = float(np.sum(hc*v*p)) / row.effective_pack_cost
    neg_control.append(val)
cohort["neg_control_value_heavy"] = neg_control

def srho(a,b):
    r,p = spearmanr(a,b); return round(float(r),4), round(float(p),4)

results["section7_negative_control"] = {
    "rho_negcontrol_p99_over_cost": srho(cohort.neg_control_value_heavy, cohort.p99_over_cost),
    "rho_negcontrol_jackpot_upside": srho(cohort.neg_control_value_heavy, cohort.jackpot_upside),
    "rho_negcontrol_financial_rip_v4": srho(cohort.neg_control_value_heavy, cohort.financial_rip_v4_score),
}
print(results["section7_negative_control"])

# Section 8: budget validation
budgets = [25,50,100,200,500]
sec8 = {}
for budget in budgets:
    comparable = []
    for _, row in cohort.iterrows():
        s = row.set_id
        price = row.product_market_cost_B  # per-pack price, pack_count=1 => per unit price
        q = int(budget // price)
        if q < 1:
            continue
        vs = variant_store[s]
        hc = np.array(vs["HC"]); p = np.array(vs["modeled_probability"])
        packs = q * row.pack_count
        o_budget = float(np.sum(hc * (1 - (1-p)**packs)))
        comparable.append({"set_id": s, "q": q, "packs": packs, "O_budget": o_budget,
                            "ECE_raw": row.ECE_raw, "product_price": price})
    df = pd.DataFrame(comparable)
    n_comp = len(df)
    agree = 0; disagree = 0; examples = []
    for i in range(n_comp):
        for j in range(i+1, n_comp):
            e1,e2 = df.ECE_raw.iloc[i], df.ECE_raw.iloc[j]
            o1,o2 = df.O_budget.iloc[i], df.O_budget.iloc[j]
            ece_order = e1>e2
            o_order = o1>o2
            if ece_order == o_order:
                agree += 1
            else:
                disagree += 1
                if len(examples) < 3:
                    examples.append({
                        "set_A": df.set_id.iloc[i], "set_B": df.set_id.iloc[j],
                        "ECE_A": e1, "ECE_B": e2, "O_budget_A": o1, "O_budget_B": o2,
                        "q_A": int(df.q.iloc[i]), "q_B": int(df.q.iloc[j]),
                        "price_A": df.product_price.iloc[i], "price_B": df.product_price.iloc[j],
                    })
    sec8[str(budget)] = {
        "n_comparable_products": n_comp,
        "pairs_total": n_comp*(n_comp-1)//2,
        "pairs_agree": agree,
        "pairs_disagree": disagree,
        "disagreement_examples": examples,
    }
    print(budget, sec8[str(budget)]["n_comparable_products"], "agree", agree, "disagree", disagree)

results["section8_budget_validation"] = sec8
json.dump(results, open(os.path.join(D,"partial_results.json"),"w"), indent=2)
cohort.to_json(os.path.join(D,"cohort_with_negcontrol.json"), orient="records", indent=2)
print("done")
