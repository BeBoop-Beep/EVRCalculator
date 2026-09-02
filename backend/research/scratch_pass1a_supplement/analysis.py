import json, os
import numpy as np
import pandas as pd
from scipy import stats

D = r"d:\EVRCalculator\backend\research\scratch_pass1a_supplement"
DOCS = r"d:\EVRCalculator\docs\research"

df = pd.DataFrame(json.load(open(os.path.join(D, "product_cohort_raw.json"))))
df["price_efficiency"] = 1.0 / df["effective_pack_cost"]

results = {}

# --- Section 2: set invariance check ---
inv = df.groupby("set_id")["A_raw"].nunique()
mismatches = int((inv > 1).sum())
results["set_invariance"] = {
    "sets_checked": int(inv.shape[0]),
    "products_checked": int(len(df)),
    "mismatches": mismatches
}
print("Set invariance mismatches:", mismatches)

# --- Section 3: ECE correlation matrix ---
def srho(a, b):
    m = df[[a,b]].dropna()
    if len(m) < 3:
        return None, None, len(m)
    rho, p = stats.spearmanr(m[a], m[b])
    return float(rho), float(p), len(m)

targets = ["financial_rip_v4_score","overall_rip_v10_score","A_raw","price_efficiency",
           "effective_pack_cost","ev_over_cost","p95_over_cost","p99_over_cost",
           "collector_appeal_v5_score","pack_equivalent_used","product_market_cost",
           "true_win_frequency","typical_retention","loss_resilience","realistic_upside",
           "jackpot_upside","base_economic_efficiency"]
corr = {}
for t in targets:
    rho, p, n = srho("ECE_raw", t)
    corr[t] = {"rho": rho, "p": p, "n": n}
results["ece_correlation_matrix"] = corr
print(json.dumps(corr, indent=2))

# partials controlling for effective_pack_cost via rank residualization
def partial_rho(x, y, controls):
    cols = [x, y] + controls
    m = df[cols].dropna()
    rx = m[x].rank()
    ry = m[y].rank()
    X = m[controls].rank()
    X = np.column_stack([np.ones(len(X))] + [X[c].values for c in controls])
    bx, *_ = np.linalg.lstsq(X, rx.values, rcond=None)
    by, *_ = np.linalg.lstsq(X, ry.values, rcond=None)
    resx = rx.values - X@bx
    resy = ry.values - X@by
    rho, p = stats.spearmanr(resx, resy)
    return float(rho), float(p), len(m)

p1 = partial_rho("financial_rip_v4_score","ECE_raw", ["effective_pack_cost"])
p2 = partial_rho("ev_over_cost","ECE_raw", ["effective_pack_cost"])
results["partials_vs_cost"] = {"financial_given_cost": p1, "ev_over_cost_given_cost": p2}
print("partial financial|cost:", p1)
print("partial ev/cost|cost:", p2)

# --- residual test: regress rank(ECE) on rank(Financial), rank(A_raw) ---
m = df[["ECE_raw","financial_rip_v4_score","A_raw"]].dropna()
rE = m["ECE_raw"].rank().values
rF = m["financial_rip_v4_score"].rank().values
rA = m["A_raw"].rank().values
X = np.column_stack([np.ones(len(m)), rF, rA])
beta, *_ = np.linalg.lstsq(X, rE, rcond=None)
pred = X@beta
resid = rE - pred
ss_res = np.sum(resid**2)
ss_tot = np.sum((rE-rE.mean())**2)
r2 = 1 - ss_res/ss_tot
rho_pred_actual, p_pred = stats.spearmanr(pred, rE)
rho_resid_price, p_resid_price = stats.spearmanr(resid, df.loc[m.index,"price_efficiency"].rank())
results["residual_regression"] = {
    "n": len(m), "R2": float(r2),
    "spearman_pred_actual": float(rho_pred_actual),
    "residual_std": float(resid.std()),
    "residual_vs_price_rank_rho": float(rho_resid_price), "p": float(p_resid_price)
}
print("R2:", r2, "pred~actual rho:", rho_pred_actual, "resid vs price rho:", rho_resid_price)

# key partial: ECE vs PriceEfficiency | Financial + Accessibility
def partial_rho2(x, y, controls, data):
    cols = [x, y] + controls
    m = data[cols].dropna()
    rx = m[x].rank(); ry = m[y].rank()
    Xc = m[controls].rank()
    Xd = np.column_stack([np.ones(len(Xc))] + [Xc[c].values for c in controls])
    bx, *_ = np.linalg.lstsq(Xd, rx.values, rcond=None)
    by, *_ = np.linalg.lstsq(Xd, ry.values, rcond=None)
    resx = rx.values - Xd@bx
    resy = ry.values - Xd@by
    rho, p = stats.spearmanr(resx, resy)
    return float(rho), float(p), len(m)

key = partial_rho2("ECE_raw","price_efficiency", ["financial_rip_v4_score","A_raw"], df)
results["key_residual_test_ece_vs_price_given_financial_accessibility"] = {"rho": key[0], "p": key[1], "n": key[2]}
print("KEY TEST rho(ECE, price | Financial, Accessibility) =", key)

with open(os.path.join(D,"results_part1.json"),"w") as f:
    json.dump(results, f, indent=2, default=str)
