"""Pass 1B Phase 8: temporal replay using genuine second Accessibility state.

State 1 = Pass 1A frozen primary cohort (Accessibility run ~2026-09-02, paired
Financial/Collector run ~2026-08-27, offset 1.0-5.4 days -- FROZEN, unchanged).

State 2 = a genuine SECOND Accessibility-capable state found live in Phase 7:
the OLDEST live pull_rates run per set (~2026-08-28), paired with the closest
available Financial/Collector-enriched simulation_sealed_product_results run
(~2026-08-27, the last one on record for these sets) -- offset well under 24h
for every set, tighter than State 1's own internal offset.
"""
import json, sys, itertools
sys.path.insert(0, r"d:\EVRCalculator")
from backend.db.clients.supabase_client import supabase
from scipy.stats import spearmanr, kendalltau

sys.path.insert(0, r"d:\EVRCalculator\backend\research\scratch_pass1b")
from common import a_raw_from_variants, a_score, overall_candidate, K_ANCHORS

with open("phase7_run_dates_result.json") as f:
    run_dates = json.load(f)
with open("phase7_financial_runs_result.json") as f:
    financial_runs = json.load(f)

# pick State 2 accessibility run = oldest run per set
state2_accessibility_run = {}
state2_accessibility_run_date = {}
for sid, info in run_dates.items():
    runs = info["runs_sorted_newest_first"]
    oldest = min(runs, key=lambda r: r["max_created_at"])
    state2_accessibility_run[sid] = oldest["run_id"]
    state2_accessibility_run_date[sid] = oldest["max_created_at"]

# pick State 2 financial/collector run = latest available (08-27), nearest to accessibility run
state2_financial_run = {}
state2_financial_date = {}
for sid, rows in financial_runs.items():
    latest = rows[-1]
    state2_financial_run[sid] = latest["calculation_run_id"]
    state2_financial_date[sid] = latest["created_at"]

# fetch full per-variant rows for state2 accessibility runs
set_ids = list(state2_accessibility_run.keys())
per_variant_state2 = {}
for sid in set_ids:
    rid = state2_accessibility_run[sid]
    r = (supabase.table("simulation_card_variant_pull_rates")
         .select("card_variant_id,price_used,modeled_probability")
         .eq("set_id", sid).eq("calculation_run_id", rid).gt("pull_count", 0)
         .order("card_variant_id").execute())
    rows = r.data or []
    per_variant_state2[sid] = rows

# fetch financial/collector product rows for state2 (loose_booster_pack only, matching primary cohort scope)
product_rows_state2 = {}
for sid in set_ids:
    rid = state2_financial_run[sid]
    r = (supabase.table("simulation_sealed_product_results")
         .select("sealed_product_id,product_market_cost,financial_rip_v4_score,"
                 "collector_appeal_score,overall_rip_v10_score,expected_value,p95_value,p99_value")
         .eq("set_id", sid).eq("calculation_run_id", rid).eq("product_family", "loose_booster_pack")
         .execute())
    rows = r.data or []
    product_rows_state2[sid] = rows[0] if rows else None

# offsets
offsets = {}
from dateutil import parser as dtparser
for sid in set_ids:
    d1 = dtparser.isoparse(state2_accessibility_run_date[sid])
    d2 = dtparser.isoparse(state2_financial_date[sid])
    offsets[sid] = abs((d1 - d2).total_seconds()) / 86400.0

usable_sets = [sid for sid in set_ids if product_rows_state2[sid] is not None and len(per_variant_state2[sid]) > 0]
print("usable sets for State 2:", len(usable_sets), "of", len(set_ids))
print("offsets (days):", {sid: round(o, 3) for sid, o in offsets.items()})

# compute A_raw for state2
a_raw_state2 = {}
for sid in usable_sets:
    prices = [row["price_used"] for row in per_variant_state2[sid]]
    probs = [row["modeled_probability"] for row in per_variant_state2[sid]]
    araw, _ = a_raw_from_variants(prices, probs)
    a_raw_state2[sid] = araw

financial_state2 = {sid: product_rows_state2[sid]["financial_rip_v4_score"] for sid in usable_sets}
collector_state2 = {sid: product_rows_state2[sid]["collector_appeal_score"] for sid in usable_sets}
v10_state2 = {sid: product_rows_state2[sid]["overall_rip_v10_score"] for sid in usable_sets}

with open("phase8_state2_raw.json", "w") as f:
    json.dump({
        "usable_sets": usable_sets,
        "accessibility_run_by_set": state2_accessibility_run,
        "accessibility_run_date_by_set": state2_accessibility_run_date,
        "financial_run_by_set": state2_financial_run,
        "financial_run_date_by_set": state2_financial_date,
        "offset_days_by_set": offsets,
        "a_raw_state2": a_raw_state2,
        "financial_state2": financial_state2,
        "collector_state2": collector_state2,
        "v10_state2": v10_state2,
    }, f, indent=2, default=str)


def diagnostics(cand_scores, ctrl_scores, financial, ids):
    cand = [cand_scores[i] for i in ids]
    ctrl = [ctrl_scores[i] for i in ids]
    rho, p_rho = spearmanr(cand, ctrl)
    tau, p_tau = kendalltau(cand, ctrl)
    ctrl_rank = {sid: r for r, sid in enumerate(sorted(ids, key=lambda i: -ctrl_scores[i]), start=1)}
    cand_rank = {sid: r for r, sid in enumerate(sorted(ids, key=lambda i: -cand_scores[i]), start=1)}
    top5_ctrl = {sid for sid, r in ctrl_rank.items() if r <= 5}
    top5_cand = {sid for sid, r in cand_rank.items() if r <= 5}
    top10_ctrl = {sid for sid, r in ctrl_rank.items() if r <= 10}
    top10_cand = {sid for sid, r in cand_rank.items() if r <= 10}
    close_pairs = close_reversals = clear_override_pairs = clear_overrides_flipped = 0
    max_gap_overturned = 0.0
    for a, b in itertools.combinations(ids, 2):
        fa, fb = financial[a], financial[b]
        gap = abs(fa - fb)
        ctrl_order = ctrl_rank[a] < ctrl_rank[b]
        cand_order = cand_rank[a] < cand_rank[b]
        if gap <= 2:
            close_pairs += 1
            if ctrl_order != cand_order:
                close_reversals += 1
        if gap >= 10:
            clear_override_pairs += 1
            fin_order = fa > fb
            if fin_order != cand_order:
                clear_overrides_flipped += 1
                max_gap_overturned = max(max_gap_overturned, gap)
    close_rate = close_reversals / close_pairs if close_pairs else 0.0
    return {
        "spearman": rho, "kendall": tau,
        "top5_overlap": len(top5_ctrl & top5_cand), "top10_overlap": len(top10_ctrl & top10_cand),
        "close_reversal_rate": close_rate, "clear_overrides_flipped": clear_overrides_flipped,
        "max_financial_gap_overturned": max_gap_overturned,
    }


K_DEFAULT = 0.002
results = {}
for w in [4, 6, 8]:
    a_scores = {sid: a_score(a_raw_state2[sid], K_DEFAULT) for sid in usable_sets}
    cand = {sid: overall_candidate(financial_state2[sid], collector_state2[sid], a_scores[sid], w)
            for sid in usable_sets}
    results[str(w)] = diagnostics(cand, v10_state2, financial_state2, usable_sets)

summary = {
    "state2_set_count": len(usable_sets),
    "state2_accessibility_market_dates_range": [min(state2_accessibility_run_date[s] for s in usable_sets),
                                                 max(state2_accessibility_run_date[s] for s in usable_sets)],
    "state2_financial_market_dates_range": [min(state2_financial_date[s] for s in usable_sets),
                                             max(state2_financial_date[s] for s in usable_sets)],
    "state2_offset_days_max": max(offsets[s] for s in usable_sets),
    "state2_offset_days_median": sorted(offsets[s] for s in usable_sets)[len(usable_sets) // 2],
    "a_raw_min": min(a_raw_state2.values()), "a_raw_median": sorted(a_raw_state2.values())[len(usable_sets) // 2],
    "a_raw_max": max(a_raw_state2.values()),
    "candidate_diagnostics_k0.002": results,
}
with open("phase8_temporal_replay_result.json", "w") as f:
    json.dump(summary, f, indent=2, default=str)
print(json.dumps(summary, indent=2, default=str))
