import json, os
import pandas as pd, numpy as np
from scipy.stats import spearmanr, pearsonr
from numpy.polynomial import polynomial as P

D = r"d:\EVRCalculator\backend\research\scratch_pass1a"
cohort = pd.DataFrame(json.load(open(os.path.join(D,"cohort_final_v2.json"))))
variant_store = json.load(open(os.path.join(D,"variant_store.json")))
n = len(cohort)
results = json.load(open(os.path.join(D,"partial_results.json")))

def srho(a,b):
    r,p = spearmanr(a,b); return round(float(r),4), round(float(p),4)

# Section 5: price placebo
rho_ece_price = srho(cohort.ECE_raw, cohort.price_efficiency)
rho_ece_access = srho(cohort.ECE_raw, cohort.A_raw)
rho_price_financial = srho(cohort.price_efficiency, cohort.financial_rip_v4_score)
rho_price_access = srho(cohort.price_efficiency, cohort.A_raw)
results["section5_placebo_correlations"] = {
    "rho_ECE_PriceEfficiency": rho_ece_price,
    "rho_ECE_Accessibility": rho_ece_access,
    "rho_PriceEfficiency_Financial": rho_price_financial,
    "rho_PriceEfficiency_Accessibility": rho_price_access,
}
print(results["section5_placebo_correlations"])

def pct_rank(s):
    return s.rank(pct=True)*100.0

cohort["ECE_pctrank"] = pct_rank(cohort.ECE_raw)
cohort["Price_pctrank"] = pct_rank(cohort.price_efficiency)
cohort["Financial_pctrank"] = pct_rank(cohort.financial_rip_v4_score)  # already 0-100-ish ranked scale but use consistent transform
cohort["Collector_pctrank"] = pct_rank(cohort.collector_appeal_score)

cohort["Overall_ECE"] = 0.84*cohort.financial_rip_v4_score + 0.06*cohort.ECE_pctrank + 0.10*cohort.collector_appeal_score
cohort["Overall_Price"] = 0.84*cohort.financial_rip_v4_score + 0.06*cohort.Price_pctrank + 0.10*cohort.collector_appeal_score

# rank comparisons vs V10 control
def ranks_desc(s):
    return s.rank(ascending=False, method="min")

r_v10 = ranks_desc(cohort.overall_rip_v10_score)
r_ece = ranks_desc(cohort.Overall_ECE)
r_price = ranks_desc(cohort.Overall_Price)

def reversal_count(rank_a, rank_b):
    # count pairs whose relative order differs
    cnt = 0
    idx = cohort.index.tolist()
    for i in range(len(idx)):
        for j in range(i+1, len(idx)):
            a1,a2 = rank_a[idx[i]], rank_a[idx[j]]
            b1,b2 = rank_b[idx[i]], rank_b[idx[j]]
            if (a1-a2)*(b1-b2) < 0:
                cnt += 1
    return cnt

total_pairs = n*(n-1)//2
rev_ece = reversal_count(r_v10, r_ece)
rev_price = reversal_count(r_v10, r_price)
# shared reversals: pairs reversed by BOTH
def reversal_set(rank_a, rank_b):
    idx = cohort.index.tolist()
    s=set()
    for i in range(len(idx)):
        for j in range(i+1, len(idx)):
            a1,a2 = rank_a[idx[i]], rank_a[idx[j]]
            b1,b2 = rank_b[idx[i]], rank_b[idx[j]]
            if (a1-a2)*(b1-b2) < 0:
                s.add((idx[i],idx[j]))
    return s
set_ece = reversal_set(r_v10, r_ece)
set_price = reversal_set(r_v10, r_price)
shared = set_ece & set_price

results["section5_candidate_vs_v10"] = {
    "total_pairs": total_pairs,
    "reversals_Overall_ECE_vs_V10": rev_ece,
    "reversals_Overall_Price_vs_V10": rev_price,
    "shared_reversals_both_candidates": len(shared),
    "transform_used": "percentile_rank_0_100_for_ECE_and_PriceEfficiency_only_financial_and_collector_used_as_is_native_0_100_scale",
}
print(results["section5_candidate_vs_v10"])

# Controlled pair tests
TOL = 0.05
# (A) near-equal effective cost pairs -> does ECE ordering follow Accessibility ordering
pairsA = []
for i in range(n):
    for j in range(i+1,n):
        c1,c2 = cohort.effective_pack_cost.iloc[i], cohort.effective_pack_cost.iloc[j]
        if abs(c1-c2)/max(c1,c2) <= TOL:
            a1,a2 = cohort.A_raw.iloc[i], cohort.A_raw.iloc[j]
            e1,e2 = cohort.ECE_raw.iloc[i], cohort.ECE_raw.iloc[j]
            agree = (a1>a2) == (e1>e2)
            pairsA.append(agree)
pairsB = []
for i in range(n):
    for j in range(i+1,n):
        a1,a2 = cohort.A_raw.iloc[i], cohort.A_raw.iloc[j]
        if a2==0: continue
        if abs(a1-a2)/max(abs(a1),abs(a2)) <= TOL:
            c1,c2 = cohort.effective_pack_cost.iloc[i], cohort.effective_pack_cost.iloc[j]
            e1,e2 = cohort.ECE_raw.iloc[i], cohort.ECE_raw.iloc[j]
            follows_cheaper = (c1<c2) == (e1>e2)
            pairsB.append(follows_cheaper)

results["section5_controlled_pairs"] = {
    "tolerance": TOL,
    "testA_near_equal_cost_pairs_n": len(pairsA),
    "testA_ECE_follows_Accessibility_ordering_count": int(sum(pairsA)),
    "testB_near_equal_accessibility_pairs_n": len(pairsB),
    "testB_ECE_follows_cheaper_cost_count": int(sum(pairsB)),
}
print(results["section5_controlled_pairs"])

json.dump(results, open(os.path.join(D,"partial_results.json"),"w"), indent=2)
cohort.to_json(os.path.join(D,"cohort_with_candidates.json"), orient="records", indent=2)
print("saved")
