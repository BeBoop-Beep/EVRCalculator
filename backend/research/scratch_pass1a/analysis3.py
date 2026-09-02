import json, os
import pandas as pd, numpy as np
from scipy.stats import spearmanr
import statsmodels.api as sm

D = r"d:\EVRCalculator\backend\research\scratch_pass1a"
cohort = pd.DataFrame(json.load(open(os.path.join(D,"cohort_with_candidates.json"))))
results = json.load(open(os.path.join(D,"partial_results.json")))
n = len(cohort)

def rank(s): return pd.Series(s).rank().values

rE = rank(cohort.ECE_raw)
rF = rank(cohort.financial_rip_v4_score)
rA = rank(cohort.A_raw)
rP = rank(cohort.price_efficiency)

X = sm.add_constant(np.column_stack([rF, rA]))
model_ece = sm.OLS(rE, X).fit()
pred_ece_rank = model_ece.predict(X)
r2 = model_ece.rsquared
resid_ece = rE - pred_ece_rank
spearman_pred_actual = spearmanr(pred_ece_rank, rE)[0]

model_price = sm.OLS(rP, X).fit()
resid_price = rP - model_price.predict(X)

partial_corr_2ctrl = spearmanr(resid_ece, resid_price)[0]
resid_disp = float(np.std(resid_ece))
resid_corr_with_priceeff = spearmanr(resid_ece, rP)[0]

results["section6_residual_test"] = {
    "OLS_ECE_rank_on_Financial_Accessibility_R2": round(float(r2),4),
    "spearman_predicted_vs_actual_ECE_rank": round(float(spearman_pred_actual),4),
    "residual_dispersion_std": round(resid_disp,4),
    "residual_correlation_with_PriceEfficiency_rank": round(float(resid_corr_with_priceeff),4),
    "partial_corr_ECE_PriceEfficiency_given_Financial_and_Accessibility": round(float(partial_corr_2ctrl),4),
    "note": "prior_lost_run_reported_0.9264_for_this_partial_correlation",
}
print(results["section6_residual_test"])

json.dump(results, open(os.path.join(D,"partial_results.json"),"w"), indent=2)
