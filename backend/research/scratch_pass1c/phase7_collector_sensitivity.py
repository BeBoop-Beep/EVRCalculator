"""Pass 1C Phase 7: Collector Appeal weight sensitivity on the frozen 22-set
primary cohort. Accessibility weight held at the Pass 1C-selected 4% (k=0.002).
Reads only frozen JSON already written by Pass 1A/1B. No DB touched."""
import json, itertools, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scratch_pass1b"))
from scipy.stats import spearmanr, kendalltau
from common import load_primary_cohort, a_raw_from_variants, a_score

cohort = load_primary_cohort()
set_ids = [row["set_id"] for row in cohort]
financial = {row["set_id"]: row["financial_rip_v4_score"] for row in cohort}
collector = {row["set_id"]: row["collector_appeal_v5_score"] for row in cohort}
v10 = {row["set_id"]: row["overall_rip_v10_score"] for row in cohort}

K = 0.002
AW = 4.0  # fixed, Pass 1C selection

a_raw = {}
for row in cohort:
    pv = row["per_variant"]
    araw, _hc = a_raw_from_variants(pv["price_used"], pv["modeled_probability"])
    a_raw[row["set_id"]] = araw
a_scores = {sid: a_score(a_raw[sid], K) for sid in set_ids}


def candidate(cw_pct):
    fw_pct = 100.0 - AW - cw_pct
    return {
        sid: (fw_pct / 100.0) * financial[sid] + (cw_pct / 100.0) * collector[sid]
        + (AW / 100.0) * a_scores[sid]
        for sid in set_ids
    }


def diagnostics(cand_scores):
    ids = set_ids
    cand = [cand_scores[i] for i in ids]
    ctrl = [v10[i] for i in ids]
    rho, _ = spearmanr(cand, ctrl)
    tau, _ = kendalltau(cand, ctrl)
    cand_rank = {sid: r for r, sid in enumerate(sorted(ids, key=lambda i: -cand_scores[i]), start=1)}
    ctrl_rank = {sid: r for r, sid in enumerate(sorted(ids, key=lambda i: -v10[i]), start=1)}
    top5_ctrl = {sid for sid, r in ctrl_rank.items() if r <= 5}
    top5_cand = {sid for sid, r in cand_rank.items() if r <= 5}
    top10_ctrl = {sid for sid, r in ctrl_rank.items() if r <= 10}
    top10_cand = {sid for sid, r in cand_rank.items() if r <= 10}

    close_pairs = close_reversals = 0
    clear_pairs = clear_flips = 0
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
            clear_pairs += 1
            fin_order = fa > fb
            if fin_order != cand_order:
                clear_flips += 1
                max_gap_overturned = max(max_gap_overturned, gap)
    return {
        "spearman": rho, "kendall": tau,
        "top5_overlap": len(top5_ctrl & top5_cand),
        "top10_overlap": len(top10_ctrl & top10_cand),
        "close_pairs": close_pairs, "close_reversals": close_reversals,
        "close_reversal_rate": (close_reversals / close_pairs if close_pairs else 0.0),
        "clear_pairs": clear_pairs, "clear_flips": clear_flips,
        "max_financial_gap_overturned": max_gap_overturned,
        "same_set_reversals": 0,  # 1 product/set cohort, impossible by construction
    }


results = {}
for cw in [5.0, 7.5, 10.0, 11.0, 12.5, 15.0]:
    fw = 100.0 - AW - cw
    d = diagnostics(candidate(cw))
    results[str(cw)] = {"collector_weight_pct": cw, "financial_weight_pct": fw, **d}

out = {"accessibility_weight_pct_fixed": AW, "k_fixed": K, "results": results}
print(json.dumps(out, indent=2, default=float))
with open(Path(__file__).resolve().parent / "phase7_collector_sensitivity_result.json", "w") as f:
    json.dump(out, f, indent=2, default=float)
