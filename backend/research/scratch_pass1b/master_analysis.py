import json, os, math, itertools
import numpy as np
import pandas as pd
from scipy import stats

DOCS = r"d:\EVRCalculator\docs\research"
SB = r"d:\EVRCalculator\backend\research\scratch_pass1b"

primary = json.load(open(os.path.join(DOCS, "overall_rip_accessibility_primary_cohort.json")))
product_cohort = json.load(open(os.path.join(DOCS, "overall_rip_accessibility_product_cohort.json")))["products"]
state_a = json.load(open(os.path.join(SB, "phase7c_state_a_accessibility.json")))
enriched_summary = json.load(open(os.path.join(SB, "phase7b_fully_enriched_run_summary.json")))
loose_pack_all = json.load(open(os.path.join(SB, "phase7b_sealed_product_loose_pack_all.json")))

RESULTS = {}

# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------

def a_score(a_raw, k):
    return 100.0 * a_raw / (a_raw + k)

def compute_overall(fin, coll, a_raw, k, aw, fin_w=None):
    # fin_w default = 90 - aw - 10(collector fixed) ... spec: Collector fixed 10%, financial = 90%-aw
    coll_w = 0.10
    if fin_w is None:
        fin_w = 0.90 - aw
    return fin_w*fin + aw*a_score(a_raw, k) + coll_w*coll

def hc_and_araw(prices, probs):
    squares = [p*p for p in prices]
    total = math.fsum(squares)
    if total <= 0:
        return None, None
    hc = [s/total for s in squares]
    a_raw = math.fsum(w*pr for w, pr in zip(hc, probs))
    return hc, a_raw

def n_hc_from_hc(hc):
    tot = math.fsum(w*w for w in hc)
    return 1.0/tot if tot > 0 else None

def pair_metrics(df, score_col, control_col="overall_rip_v10_score", fin_col="financial_rip_v4_score"):
    """All-pairs diagnostics for an n-row cohort comparing score_col ranking to control_col."""
    n = len(df)
    rows = df.reset_index(drop=True)
    sp, sp_p = stats.spearmanr(rows[score_col], rows[control_col])
    kt, kt_p = stats.kendalltau(rows[score_col], rows[control_col])

    rank_new = rows[score_col].rank(ascending=False, method="average")
    rank_ctrl = rows[control_col].rank(ascending=False, method="average")
    movement = (rank_new - rank_ctrl).abs()
    mean_abs_move = movement.mean()
    max_move = movement.max()

    top5_ctrl = set(rows.nlargest(5, control_col).index)
    top5_new = set(rows.nlargest(5, score_col).index)
    top5_overlap = len(top5_ctrl & top5_new)

    top10_ctrl = set(rows.nlargest(min(10, n), control_col).index)
    top10_new = set(rows.nlargest(min(10, n), score_col).index)
    top10_overlap = len(top10_ctrl & top10_new)

    close_fin_pairs = 0
    close_reversals = 0
    clear_overrides = 0
    max_fin_gap_overturned = 0.0
    for i, j in itertools.combinations(range(n), 2):
        fa, fb = rows.loc[i, fin_col], rows.loc[j, fin_col]
        ca, cb = rows.loc[i, control_col], rows.loc[j, control_col]
        na, nb = rows.loc[i, score_col], rows.loc[j, score_col]
        gap = abs(fa - fb)
        ctrl_order = (ca > cb)
        new_order = (na > nb)
        reversed_ = (ctrl_order != new_order) and (ca != cb) and (na != nb)
        if gap <= 2:
            close_fin_pairs += 1
            if reversed_:
                close_reversals += 1
        if gap >= 10 and reversed_:
            clear_overrides += 1
            max_fin_gap_overturned = max(max_fin_gap_overturned, gap)

    close_reversal_rate = close_reversals/close_fin_pairs if close_fin_pairs else None

    return {
        "n": n,
        "spearman": sp, "spearman_p": sp_p,
        "kendall_tau": kt, "kendall_p": kt_p,
        "mean_abs_rank_movement": float(mean_abs_move),
        "max_rank_movement": float(max_move),
        "top5_overlap": top5_overlap,
        "top10_overlap": top10_overlap,
        "close_financial_pair_count": close_fin_pairs,
        "close_reversal_count": close_reversals,
        "close_reversal_rate": close_reversal_rate,
        "clear_financial_overrides": clear_overrides,
        "max_financial_gap_overturned": max_fin_gap_overturned,
    }

# ---------------------------------------------------------------
# Build primary dataframe (n=22)
# ---------------------------------------------------------------
prim_rows = []
for p in primary:
    prim_rows.append({
        "set_id": p["set_id"],
        "A_raw": p["A_raw"],
        "financial_rip_v4_score": p["financial_rip_v4_score"],
        "collector_appeal_v5_score": p["collector_appeal_v5_score"],
        "overall_rip_v10_score": p["overall_rip_v10_score"],
    })
df22 = pd.DataFrame(prim_rows)

K_VALUES = [0.0005, 0.001, 0.002, 0.004, 0.008]
WEIGHTS = [0.0, 0.02, 0.04, 0.06, 0.08, 0.10]

# ---------------------------------------------------------------
# PHASE 1 + 2: transform x weight grid
# ---------------------------------------------------------------
grid = {}
for k in K_VALUES:
    grid[str(k)] = {}
    for w in WEIGHTS:
        df = df22.copy()
        df["candidate"] = df.apply(lambda r: compute_overall(r["financial_rip_v4_score"], r["collector_appeal_v5_score"], r["A_raw"], k, w), axis=1)
        m = pair_metrics(df, "candidate")
        # same-set reversal check: set-level cohort = 1 product/set -> "same-set" reversal impossible by construction
        m["same_set_reversal_by_construction_zero"] = True
        grid[str(k)][str(w)] = m
RESULTS["phase1_2_grid"] = grid

gates = {}
for w in WEIGHTS:
    spearmans = [grid[str(k)][str(w)]["spearman"] for k in K_VALUES]
    overrides = [grid[str(k)][str(w)]["clear_financial_overrides"] for k in K_VALUES]
    fin_gaps = [grid[str(k)][str(w)]["max_financial_gap_overturned"] for k in K_VALUES]
    top5 = [grid[str(k)][str(w)]["top5_overlap"] for k in K_VALUES]
    close_rates = [grid[str(k)][str(w)]["close_reversal_rate"] for k in K_VALUES if grid[str(k)][str(w)]["close_reversal_rate"] is not None]
    gates[str(w)] = {
        "min_spearman": min(spearmans),
        "max_clear_overrides": max(overrides),
        "max_financial_gap_overturned": max(fin_gaps),
        "min_top5_overlap": min(top5),
        "close_reversal_rate_range": [min(close_rates), max(close_rates)] if close_rates else None,
        "passes_hard_gates_all_k": (max(overrides)==0 and min(spearmans)>=0.98 and (5-min(top5))<=1),
    }
RESULTS["phase2_transform_robustness"] = gates

# ---------------------------------------------------------------
# PHASE 3: Core K reconstruction
# ---------------------------------------------------------------
def compute_core_k(card_values, product_market_cost, random_pack_count, multiple=3.0):
    if product_market_cost is None or random_pack_count in (None, 0):
        return None
    pack_cost = product_market_cost/random_pack_count
    floor = multiple*pack_cost
    core = sum(1 for v in card_values if v is not None and v >= floor)
    return core, pack_cost, floor

# Use per-set primary per_variant price arrays as the eligible card-value roster proxy
# (documented assumption: same drawable/eligible card roster per set regardless of product SKU).
primary_by_set = {p["set_id"]: p for p in primary}

core_k_rows = []
for prod in product_cohort:
    sid = prod["set_id"]
    pv = primary_by_set.get(sid, {}).get("per_variant")
    if pv is None:
        continue
    card_values = pv["price_used"]
    rpc = prod.get("random_pack_count")
    pmc = prod.get("product_market_cost")
    res = compute_core_k(card_values, pmc, rpc)
    if res is None:
        continue
    core, pack_cost, floor = res
    core_k_rows.append({
        "sealed_product_id": prod["sealed_product_id"],
        "set_id": sid,
        "product_family": prod["product_family"],
        "core_k": core,
        "pack_equivalent_cost": pack_cost,
        "A_raw": prod["A_raw"],
        "financial_rip_v4_score": prod["financial_rip_v4_score"],
        "effective_pack_cost": prod["effective_pack_cost"],
    })
core_df = pd.DataFrame(core_k_rows)

sp_ck_acc = stats.spearmanr(core_df["core_k"], core_df["A_raw"])
sp_ck_fin = stats.spearmanr(core_df["core_k"], core_df["financial_rip_v4_score"])
sp_ck_cost = stats.spearmanr(core_df["core_k"], core_df["effective_pack_cost"])

RESULTS["phase3_core_k_baseline"] = {
    "n_products": len(core_df),
    "core_k_value_counts": core_df["core_k"].value_counts().to_dict(),
    "spearman_core_k_vs_accessibility": {"rho": sp_ck_acc.statistic, "p": sp_ck_acc.pvalue},
    "spearman_core_k_vs_financial": {"rho": sp_ck_fin.statistic, "p": sp_ck_fin.pvalue},
    "spearman_core_k_vs_effective_pack_cost": {"rho": sp_ck_cost.statistic, "p": sp_ck_cost.pvalue},
}

# Core K shocks: card-price and product-price uniform pct shocks
shock_pcts = [-0.20, -0.10, -0.05, -0.02, 0.02, 0.05, 0.10, 0.20]

def core_k_card_shock(pct):
    changed = 0
    deltas = []
    evaluated = 0
    for prod in product_cohort:
        sid = prod["set_id"]
        pv = primary_by_set.get(sid, {}).get("per_variant")
        if pv is None:
            continue
        card_values = pv["price_used"]
        rpc = prod.get("random_pack_count"); pmc = prod.get("product_market_cost")
        base = compute_core_k(card_values, pmc, rpc)
        shocked_values = [v*(1+pct) if v is not None else v for v in card_values]
        shocked = compute_core_k(shocked_values, pmc, rpc)  # product price unaffected by card shock
        if base is None or shocked is None:
            continue
        evaluated += 1
        d = shocked[0]-base[0]
        deltas.append(d)
        if d != 0:
            changed += 1
    return evaluated, changed, deltas

def core_k_product_shock(pct):
    changed = 0
    deltas = []
    evaluated = 0
    for prod in product_cohort:
        sid = prod["set_id"]
        pv = primary_by_set.get(sid, {}).get("per_variant")
        if pv is None:
            continue
        card_values = pv["price_used"]
        rpc = prod.get("random_pack_count"); pmc = prod.get("product_market_cost")
        base = compute_core_k(card_values, pmc, rpc)
        shocked_pmc = pmc*(1+pct) if pmc is not None else pmc
        shocked = compute_core_k(card_values, shocked_pmc, rpc)
        if base is None or shocked is None:
            continue
        evaluated += 1
        d = shocked[0]-base[0]
        deltas.append(d)
        if d != 0:
            changed += 1
    return evaluated, changed, deltas

core_k_card_shocks = {}
core_k_product_shocks = {}
for pct in shock_pcts:
    ev, ch, deltas = core_k_card_shock(pct)
    core_k_card_shocks[str(pct)] = {
        "products_evaluated": ev, "products_changed": ch,
        "share_changed": ch/ev if ev else None,
        "mean_abs_delta_k": float(np.mean(np.abs(deltas))) if deltas else None,
        "max_abs_delta_k": float(np.max(np.abs(deltas))) if deltas else None,
    }
    ev2, ch2, deltas2 = core_k_product_shock(pct)
    core_k_product_shocks[str(pct)] = {
        "products_evaluated": ev2, "products_changed": ch2,
        "share_changed": ch2/ev2 if ev2 else None,
        "mean_abs_delta_k": float(np.mean(np.abs(deltas2))) if deltas2 else None,
        "max_abs_delta_k": float(np.max(np.abs(deltas2))) if deltas2 else None,
    }
RESULTS["phase3_core_k_card_price_shocks"] = core_k_card_shocks
RESULTS["phase3_core_k_product_price_shocks"] = core_k_product_shocks

print("PHASE 3 done")

# ---------------------------------------------------------------
# PHASE 4: uniform accessibility invariance
# ---------------------------------------------------------------
card_scale_factors = [0.5, 2.0, 10.0]
worst_delta_card_scale = 0.0
for p in primary:
    pv = p["per_variant"]
    prices = pv["price_used"]; probs = pv["modeled_probability"]
    base_hc, base_araw = hc_and_araw(prices, probs)
    for f in card_scale_factors:
        scaled = [v*f for v in prices]
        hc2, araw2 = hc_and_araw(scaled, probs)
        worst_delta_card_scale = max(worst_delta_card_scale, abs(araw2-base_araw))
RESULTS["phase4_card_scale_invariance"] = {
    "factors_tested": card_scale_factors,
    "worst_abs_delta_A_raw": worst_delta_card_scale,
}

# product price changes: A_raw has zero dependency on product price by construction (not an input at all)
RESULTS["phase4_product_price_invariance"] = {
    "pcts_tested": shock_pcts,
    "observed_delta_A_raw": 0.0,
    "note": "product_market_cost is not read anywhere in compute_chase_accessibility(); A_raw is algebraically and mechanically independent of it.",
}
print("PHASE 4 done")

# ---------------------------------------------------------------
# PHASE 5: independent card-price shocks
# ---------------------------------------------------------------
def make_seeds(base_seed, n=12):
    return [base_seed*1000 + i for i in range(n)]

card_shock_mags = [0.02, 0.05, 0.10]
SEEDS_PER_MAG = 12
phase5_results = {}
raw_stability = {"median_abs_change": {}, "max_abs_change": {}}

for mag in card_shock_mags:
    seeds = make_seeds(int(mag*1000), SEEDS_PER_MAG)
    worst_by_weight = {w: {"spearman": 1.0, "top5": 5, "top10": 10, "close_reversal_rate": 0.0, "clear_overrides": 0, "max_fin_gap_overturned": 0.0} for w in [0.04,0.06,0.08]}
    all_araw_deltas = []
    for seed in seeds:
        rng = np.random.default_rng(seed)
        rows = []
        for p in primary:
            pv = p["per_variant"]
            prices = np.array(pv["price_used"], dtype=float)
            probs = pv["modeled_probability"]
            perturb = rng.uniform(-mag, mag, size=len(prices))
            shocked_prices = prices * (1+perturb)
            shocked_prices = np.clip(shocked_prices, 1e-6, None)
            hc2, araw2 = hc_and_araw(list(shocked_prices), probs)
            all_araw_deltas.append(araw2 - p["A_raw"])
            rows.append({
                "set_id": p["set_id"], "A_raw": araw2,
                "financial_rip_v4_score": p["financial_rip_v4_score"],
                "collector_appeal_v5_score": p["collector_appeal_v5_score"],
                "overall_rip_v10_score": p["overall_rip_v10_score"],
            })
        dfx = pd.DataFrame(rows)
        for w in [0.04,0.06,0.08]:
            dfx["candidate"] = dfx.apply(lambda r: compute_overall(r["financial_rip_v4_score"], r["collector_appeal_v5_score"], r["A_raw"], 0.002, w), axis=1)
            m = pair_metrics(dfx, "candidate")
            wb = worst_by_weight[w]
            wb["spearman"] = min(wb["spearman"], m["spearman"])
            wb["top5"] = min(wb["top5"], m["top5_overlap"])
            wb["top10"] = min(wb["top10"], m["top10_overlap"])
            wb["close_reversal_rate"] = max(wb["close_reversal_rate"], m["close_reversal_rate"] or 0.0)
            wb["clear_overrides"] = max(wb["clear_overrides"], m["clear_financial_overrides"])
            wb["max_fin_gap_overturned"] = max(wb["max_fin_gap_overturned"], m["max_financial_gap_overturned"])
    phase5_results[str(mag)] = {"worst_by_weight": worst_by_weight,
                                  "seeds_used": seeds}
    raw_stability["median_abs_change"][str(mag)] = float(np.median(np.abs(all_araw_deltas)))
    raw_stability["max_abs_change"][str(mag)] = float(np.max(np.abs(all_araw_deltas)))

RESULTS["phase5_card_price_shocks"] = phase5_results
RESULTS["phase5_raw_accessibility_stability"] = raw_stability
print("PHASE 5 done")

# ---------------------------------------------------------------
# PHASE 6: independent pull-probability shocks
# ---------------------------------------------------------------
prob_shock_mags = [0.02, 0.05, 0.10]
phase6_results = {}
raw_stability6 = {"median_abs_change": {}, "max_abs_change": {}}
for mag in prob_shock_mags:
    seeds = make_seeds(int(mag*1000)+7, SEEDS_PER_MAG)
    worst_by_weight = {w: {"spearman": 1.0, "top5": 5, "top10": 10, "close_reversal_rate": 0.0, "clear_overrides": 0, "max_fin_gap_overturned": 0.0} for w in [0.04,0.06,0.08]}
    all_araw_deltas = []
    for seed in seeds:
        rng = np.random.default_rng(seed)
        rows = []
        for p in primary:
            pv = p["per_variant"]
            prices = pv["price_used"]
            probs = np.array(pv["modeled_probability"], dtype=float)
            perturb = rng.uniform(-mag, mag, size=len(probs))
            shocked_probs = np.clip(probs*(1+perturb), 0.0, 1.0)
            hc2, araw2 = hc_and_araw(prices, list(shocked_probs))
            all_araw_deltas.append(araw2 - p["A_raw"])
            rows.append({
                "set_id": p["set_id"], "A_raw": araw2,
                "financial_rip_v4_score": p["financial_rip_v4_score"],
                "collector_appeal_v5_score": p["collector_appeal_v5_score"],
                "overall_rip_v10_score": p["overall_rip_v10_score"],
            })
        dfx = pd.DataFrame(rows)
        for w in [0.04,0.06,0.08]:
            dfx["candidate"] = dfx.apply(lambda r: compute_overall(r["financial_rip_v4_score"], r["collector_appeal_v5_score"], r["A_raw"], 0.002, w), axis=1)
            m = pair_metrics(dfx, "candidate")
            wb = worst_by_weight[w]
            wb["spearman"] = min(wb["spearman"], m["spearman"])
            wb["top5"] = min(wb["top5"], m["top5_overlap"])
            wb["top10"] = min(wb["top10"], m["top10_overlap"])
            wb["close_reversal_rate"] = max(wb["close_reversal_rate"], m["close_reversal_rate"] or 0.0)
            wb["clear_overrides"] = max(wb["clear_overrides"], m["clear_financial_overrides"])
            wb["max_fin_gap_overturned"] = max(wb["max_fin_gap_overturned"], m["max_financial_gap_overturned"])
    phase6_results[str(mag)] = {"worst_by_weight": worst_by_weight, "seeds_used": seeds}
    raw_stability6["median_abs_change"][str(mag)] = float(np.median(np.abs(all_araw_deltas)))
    raw_stability6["max_abs_change"][str(mag)] = float(np.max(np.abs(all_araw_deltas)))
RESULTS["phase6_pull_probability_shocks"] = phase6_results
RESULTS["phase6_raw_accessibility_stability"] = raw_stability6
print("PHASE 6 done")

# ---------------------------------------------------------------
# PHASE 9: LOSO
# ---------------------------------------------------------------
loso_results = {}
for w in [0.04, 0.06, 0.08, 0.10]:
    df = df22.copy()
    df["candidate"] = df.apply(lambda r: compute_overall(r["financial_rip_v4_score"], r["collector_appeal_v5_score"], r["A_raw"], 0.002, w), axis=1)
    per_set = {}
    for omit_sid in df["set_id"]:
        sub = df[df["set_id"] != omit_sid]
        m = pair_metrics(sub, "candidate")
        per_set[omit_sid] = m
    spearmans = {sid: m["spearman"] for sid, m in per_set.items()}
    min_sid = min(spearmans, key=spearmans.get)
    loso_results[str(w)] = {
        "min_spearman": min(spearmans.values()),
        "max_spearman": max(spearmans.values()),
        "worst_omitted_set": min_sid,
        "min_top5_overlap": min(m["top5_overlap"] for m in per_set.values()),
        "max_clear_overrides": max(m["clear_financial_overrides"] for m in per_set.values()),
        "max_financial_gap_overturned": max(m["max_financial_gap_overturned"] for m in per_set.values()),
        "close_reversal_rate_range": [min(m["close_reversal_rate"] or 0 for m in per_set.values()),
                                       max(m["close_reversal_rate"] or 0 for m in per_set.values())],
        "passes_min_0_98": min(spearmans.values()) >= 0.98,
    }
RESULTS["phase9_loso"] = loso_results
print("PHASE 9 done")

# ---------------------------------------------------------------
# PHASE 10: product family movement (6% candidate)
# ---------------------------------------------------------------
pdf = pd.DataFrame(product_cohort)
pdf["candidate_6pct"] = pdf.apply(lambda r: compute_overall(r["financial_rip_v4_score"], r["collector_appeal_v5_score"], r["A_raw"], 0.002, 0.06), axis=1)
pdf["rank_v10"] = pdf["overall_rip_v10_score"].rank(ascending=False, method="average")
pdf["rank_cand"] = pdf["candidate_6pct"].rank(ascending=False, method="average")
pdf["movement"] = pdf["rank_cand"] - pdf["rank_v10"]

family_stats = {}
for fam, g in pdf.groupby("product_family"):
    family_stats[fam] = {
        "n": len(g),
        "avg_rank_movement": float(g["movement"].mean()),
        "median_rank_movement": float(g["movement"].median()),
        "risers": int((g["movement"] < 0).sum()),
        "fallers": int((g["movement"] > 0).sum()),
    }
RESULTS["phase10_family_movement"] = family_stats

# same-set reversal check (should be 0: A_raw constant per set)
same_set_reversals = 0
same_set_pairs = 0
for sid, g in pdf.groupby("set_id"):
    g = g.reset_index(drop=True)
    n = len(g)
    for i, j in itertools.combinations(range(n), 2):
        # accessibility-attributable reversal: does adding accessibility change relative order vs (Financial+Collector only, no accessibility)?
        # Since A_raw is constant within set, candidate ordering within a set == ordering by (fin*fw + coll*cw) alone -> never flips vs itself
        same_set_pairs += 1
        # check whether V10 order flips vs candidate order (both real, not accessibility-isolated)
        pass
# Direct same-set accessibility-attributable reversal: compare candidate order (has accessibility) vs a
# "no-accessibility" comparator using only Financial(0.84/0.90 scaled)+Collector(0.10) i.e w=0 case, restricted to same set
pdf["baseline_0pct"] = pdf.apply(lambda r: compute_overall(r["financial_rip_v4_score"], r["collector_appeal_v5_score"], r["A_raw"], 0.002, 0.0), axis=1)
accessibility_attributable_reversals = 0
for sid, g in pdf.groupby("set_id"):
    g = g.reset_index(drop=True)
    n = len(g)
    for i, j in itertools.combinations(range(n), 2):
        a6 = g.loc[i,"candidate_6pct"] > g.loc[j,"candidate_6pct"]
        a0 = g.loc[i,"baseline_0pct"] > g.loc[j,"baseline_0pct"]
        if a6 != a0 and g.loc[i,"candidate_6pct"]!=g.loc[j,"candidate_6pct"] and g.loc[i,"baseline_0pct"]!=g.loc[j,"baseline_0pct"]:
            accessibility_attributable_reversals += 1
RESULTS["phase10_same_set_accessibility_attributable_reversals"] = {
    "count": accessibility_attributable_reversals,
    "total_same_set_pairs": same_set_pairs,
    "expected_zero_because": "A_raw is a constant per set_id (broadcast), so within a set the accessibility term never changes relative order vs a 0%-accessibility baseline built the same way.",
}
print("PHASE 10 done")

with open(os.path.join(SB, "results_master.json"), "w") as f:
    json.dump(RESULTS, f, default=str, indent=2)
print("ALL DONE, results_master.json written")
