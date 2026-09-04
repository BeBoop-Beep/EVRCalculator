import json, os, itertools
import numpy as np
import pandas as pd
from scipy import stats

D = r"d:\EVRCalculator\backend\research\scratch_pass1a_supplement"
DOCS = r"d:\EVRCalculator\docs\research"
df = pd.DataFrame(json.load(open(os.path.join(D, "product_cohort_raw.json"))))
primary = json.load(open(os.path.join(DOCS, "overall_rip_accessibility_primary_cohort.json")))
primary_by_set = {p["set_id"]: p for p in primary}
results = json.load(open(os.path.join(D,"results_part3.json")))

budgets = [25,50,100,200,500]
budget_results = {}
budget_within_set = {}

for budget in budgets:
    agree=0; disagree=0; comparable=0
    fam_agree = {}
    disagree_examples = []
    within_agree=0; within_disagree=0; within_comparable=0
    for set_id, g in df.groupby("set_id"):
        pv = primary_by_set[set_id]["per_variant"]
        HC = np.array(pv["HC"]); p = np.array(pv["modeled_probability"])
        rows=[]
        for _, row in g.iterrows():
            price = row["product_market_cost"]
            pack_eq = row["pack_equivalent_used"]
            q = int(budget // price)
            if q < 1:
                continue
            packs = q*pack_eq
            o_budget = float((HC*(1-(1-p)**packs)).sum())
            rows.append({"sealed_product_id": row["sealed_product_id"], "family": row["product_family"],
                         "ECE_raw": row["ECE_raw"], "o_budget": o_budget, "q": q, "packs": packs, "price": price})
        if len(rows) < 2:
            continue
        rdf = pd.DataFrame(rows)
        for i,j in itertools.combinations(range(len(rdf)),2):
            a,b = rdf.iloc[i], rdf.iloc[j]
            comparable += 1
            ece_order = a["ECE_raw"] > b["ECE_raw"]
            ob_order = a["o_budget"] > b["o_budget"]
            same = (ece_order == ob_order)
            fam_key = tuple(sorted([a["family"], b["family"]]))
            same_family = a["family"]==b["family"]
            if same:
                agree += 1
            else:
                disagree += 1
                disagree_examples.append({"set_id": set_id, "product_a": a["sealed_product_id"], "family_a": a["family"],
                                           "product_b": b["sealed_product_id"], "family_b": b["family"],
                                           "ece_a": a["ECE_raw"], "ece_b": b["ECE_raw"],
                                           "o_budget_a": a["o_budget"], "o_budget_b": b["o_budget"],
                                           "q_a": int(a["q"]), "q_b": int(b["q"]), "price_a": a["price"], "price_b": b["price"]})
            key = "same_family" if same_family else "cross_family"
            fam_agree.setdefault(key, [0,0])
            fam_agree[key][0 if same else 1][0] if False else None
            if same:
                fam_agree[key][0]+=1
            else:
                fam_agree[key][1]+=1
            if not same_family:
                within_comparable += 1
                if same: within_agree+=1
                else: within_disagree+=1
    budget_results[budget] = {
        "comparable_pairs": comparable, "agree": agree, "disagree": disagree,
        "agreement_rate": agree/comparable if comparable else None,
        "by_pairtype": fam_agree,
    }
    budget_within_set[budget] = {
        "cross_format_same_set_pairs": within_comparable, "agree": within_agree, "disagree": within_disagree,
        "agreement_rate": within_agree/within_comparable if within_comparable else None,
    }
    with open(os.path.join(D, f"budget_disagree_{budget}.json"),"w") as f:
        json.dump(disagree_examples[:15], f, indent=2, default=str)
    print(budget, budget_results[budget]["agreement_rate"], "cross-format same-set:", budget_within_set[budget])

results["section7_budget_validation"] = budget_results
results["section7_within_set_cross_format"] = budget_within_set

with open(os.path.join(D,"results_final.json"),"w") as f:
    json.dump(results, f, indent=2, default=str)
