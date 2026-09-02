"""Pass 1B Phase 1-2: transform x weight grid + transform robustness summary.

Reads the frozen Pass 1A primary cohort (22 sets, one loose_booster_pack
product per set) and does NOT touch the DB. Financial RIP V4 total and
Overall RIP V10 are taken verbatim from the frozen file (not recomputed).
"""
import json, itertools
from scipy.stats import spearmanr, kendalltau
from common import load_primary_cohort, a_raw_from_variants, a_score, overall_candidate, \
    K_ANCHORS, WEIGHTS_PCT, DOCS

cohort = load_primary_cohort()
n = len(cohort)
set_ids = [row["set_id"] for row in cohort]

financial = {row["set_id"]: row["financial_rip_v4_score"] for row in cohort}
collector = {row["set_id"]: row["collector_appeal_v5_score"] for row in cohort}
v10 = {row["set_id"]: row["overall_rip_v10_score"] for row in cohort}
a_raw_frozen = {row["set_id"]: row["A_raw"] for row in cohort}

# Recompute A_raw numerically from the frozen per-variant arrays as a parity check
a_raw_recomputed = {}
for row in cohort:
    pv = row["per_variant"]
    prices = pv["price_used"]
    probs = pv["modeled_probability"]
    araw, hc = a_raw_from_variants(prices, probs)
    a_raw_recomputed[row["set_id"]] = araw

parity = {sid: abs(a_raw_recomputed[sid] - a_raw_frozen[sid]) for sid in set_ids}
worst_parity = max(parity.values())


def diagnostics(candidate_scores):
    """candidate_scores: dict set_id -> score. Compare vs v10 control."""
    ids = set_ids
    cand = [candidate_scores[i] for i in ids]
    ctrl = [v10[i] for i in ids]
    rho, p_rho = spearmanr(cand, ctrl)
    tau, p_tau = kendalltau(cand, ctrl)

    cand_rank = {sid: r for r, sid in enumerate(sorted(ids, key=lambda i: -candidate_scores[i]), start=1)}
    ctrl_rank = {sid: r for r, sid in enumerate(sorted(ids, key=lambda i: -v10[i]), start=1)}
    movements = [abs(cand_rank[sid] - ctrl_rank[sid]) for sid in ids]
    mean_abs_move = sum(movements) / len(movements)
    max_move = max(movements)

    top5_ctrl = {sid for sid, r in ctrl_rank.items() if r <= 5}
    top5_cand = {sid for sid, r in cand_rank.items() if r <= 5}
    top10_ctrl = {sid for sid, r in ctrl_rank.items() if r <= 10}
    top10_cand = {sid for sid, r in cand_rank.items() if r <= 10}
    top5_overlap = len(top5_ctrl & top5_cand)
    top10_overlap = len(top10_ctrl & top10_cand)

    # pairwise diagnostics
    close_pairs = 0
    close_reversals = 0
    clear_override_pairs = 0
    clear_overrides_flipped = 0
    max_gap_overturned = 0.0
    for a, b in itertools.combinations(ids, 2):
        fa, fb = financial[a], financial[b]
        gap = abs(fa - fb)
        ctrl_order = ctrl_rank[a] < ctrl_rank[b]  # True if a ranked above b under V10
        cand_order = cand_rank[a] < cand_rank[b]
        if gap <= 2:
            close_pairs += 1
            if ctrl_order != cand_order:
                close_reversals += 1
        if gap >= 10:
            clear_override_pairs += 1
            # financial says the higher-F one should rank above; does candidate flip that?
            fin_order = fa > fb  # True if a has higher financial than b
            cand_a_above_b = cand_order
            if fin_order != cand_a_above_b:
                clear_overrides_flipped += 1
                max_gap_overturned = max(max_gap_overturned, gap)

    close_rate = close_reversals / close_pairs if close_pairs else 0.0

    return {
        "spearman": rho, "spearman_p": p_rho,
        "kendall": tau, "kendall_p": p_tau,
        "mean_abs_rank_movement": mean_abs_move,
        "max_rank_movement": max_move,
        "top5_overlap": top5_overlap,
        "top10_overlap": top10_overlap,
        "close_financial_pair_count": close_pairs,
        "close_reversal_count": close_reversals,
        "close_reversal_rate": close_rate,
        "clear_override_pair_count": clear_override_pairs,
        "clear_overrides_flipped": clear_overrides_flipped,
        "max_financial_gap_overturned": max_gap_overturned,
        "same_set_reversals": 0,  # by construction: 1 product per set in this cohort
        "same_set_winner_changes": 0,
    }


grid = {}
for k in K_ANCHORS:
    a_scores = {sid: a_score(a_raw_recomputed[sid], k) for sid in set_ids}
    for w in WEIGHTS_PCT:
        cand_scores = {sid: overall_candidate(financial[sid], collector[sid], a_scores[sid], w)
                       for sid in set_ids}
        d = diagnostics(cand_scores)
        grid[f"k={k}_w={w}"] = {"k": k, "weight_pct": w, **d}

# Hard gates check for Phase 1 (identity of weight=0 should be == V10 exactly, sanity check)
w0_any_k = grid[f"k={K_ANCHORS[0]}_w=0"]

# PHASE 2: transform robustness summary for w in {4,6,8,10}
phase2 = {}
for w in [4, 6, 8, 10]:
    rows = [grid[f"k={k}_w={w}"] for k in K_ANCHORS]
    phase2[str(w)] = {
        "min_spearman": min(r["spearman"] for r in rows),
        "max_clear_overrides": max(r["clear_overrides_flipped"] for r in rows),
        "max_financial_gap_overturned": max(r["max_financial_gap_overturned"] for r in rows),
        "min_top5_overlap": min(r["top5_overlap"] for r in rows),
        "close_reversal_rate_min": min(r["close_reversal_rate"] for r in rows),
        "close_reversal_rate_max": max(r["close_reversal_rate"] for r in rows),
    }

hard_gates = {}
for key, row in grid.items():
    hard_gates[key] = {
        "gate_clear_overrides_zero": row["clear_overrides_flipped"] == 0,
        "gate_spearman_ge_098": row["spearman"] >= 0.98,
        "gate_top5_turnover_le_1": (5 - row["top5_overlap"]) <= 1,
        "passes_all": (row["clear_overrides_flipped"] == 0 and row["spearman"] >= 0.98
                       and (5 - row["top5_overlap"]) <= 1),
    }

out = {
    "n_sets": n,
    "worst_a_raw_parity_delta_vs_frozen": worst_parity,
    "grid": grid,
    "hard_gates": hard_gates,
    "phase2_transform_robustness_w4_6_8_10": phase2,
}
with open(DOCS.parent.parent / "backend" / "research" / "scratch_pass1b" / "phase1_2_grid_result.json", "w") as f:
    json.dump(out, f, indent=2, default=float)

print("worst A_raw parity delta vs frozen:", worst_parity)
print("Hard-gate PASS weights (any k):")
for key, hg in hard_gates.items():
    if hg["passes_all"]:
        print(" ", key)
print()
print("Phase 2 summary:")
for w, s in phase2.items():
    print(w, s)
