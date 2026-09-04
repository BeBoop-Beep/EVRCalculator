import json, os
import pandas as pd, numpy as np
from scipy.stats import spearmanr, pearsonr

D = r"d:\EVRCalculator\backend\research\scratch_pass1a"
cohort = pd.DataFrame(json.load(open(os.path.join(D,"cohort_final_v2.json"))))
variant_store = json.load(open(os.path.join(D,"variant_store.json")))
n = len(cohort)
print("n =", n)

def srho(x,y):
    r,p = spearmanr(cohort[x], cohort[y])
    return round(float(r),4), round(float(p),4)
def prho(x,y):
    r,p = pearsonr(cohort[x], cohort[y])
    return round(float(r),4), round(float(p),4)

results = {"n": n}

# Section 3: redundancy matrix vs A_raw
targets_s3 = ["financial_rip_v4_score","true_win_frequency","typical_retention","loss_resilience",
              "realistic_upside","jackpot_upside","base_economic_efficiency",
              "ev_over_cost","p95_over_cost","p99_over_cost","collector_appeal_score",
              "chase_depth","pack_count","product_market_cost_B","effective_pack_cost"]
sec3 = {}
for t in targets_s3:
    s = srho("A_raw", t)
    p = prho("A_raw", t)
    sec3[t] = {"spearman": s, "pearson": p}
results["section3_redundancy_vs_A_raw"] = sec3
print("SECTION 3"); [print(k,v) for k,v in sec3.items()]

# Section 4: ECE correlations
targets_s4 = ["financial_rip_v4_score","overall_rip_v10_score","ev_over_cost","p95_over_cost","p99_over_cost",
              "product_market_cost_B","effective_pack_cost","pack_count","A_raw","collector_appeal_score",
              "true_win_frequency","typical_retention","loss_resilience","realistic_upside","jackpot_upside","base_economic_efficiency"]
sec4 = {}
for t in targets_s4:
    sec4[t] = {"spearman": srho("ECE_raw", t)}
results["section4_ece_correlations"] = sec4
print("\nSECTION 4"); [print(k,v) for k,v in sec4.items()]

def rank(s):
    return pd.Series(s).rank()

def partial_rho(x,y,z):
    rx, ry, rz = rank(cohort[x]), rank(cohort[y]), rank(cohort[z])
    rxy = spearmanr(rx,ry)[0]
    rxz = spearmanr(rx,rz)[0]
    ryz = spearmanr(ry,rz)[0]
    return float((rxy - rxz*ryz)/np.sqrt((1-rxz**2)*(1-ryz**2)))

pr_financial = partial_rho("financial_rip_v4_score","ECE_raw","effective_pack_cost")
pr_evcost = partial_rho("ev_over_cost","ECE_raw","effective_pack_cost")
results["section4_partials"] = {
    "rho_Financial_ECE_given_effpackcost": round(pr_financial,4),
    "rho_EVcost_ECE_given_effpackcost": round(pr_evcost,4),
}
print("\nPartials:", results["section4_partials"])

json.dump(results, open(os.path.join(D,"partial_results.json"),"w"), indent=2)
print("saved partial_results.json")
