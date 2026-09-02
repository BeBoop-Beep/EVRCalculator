"""Pass 1B Phase 9: Leave-one-set-out (LOSO) on the frozen 22-set primary cohort."""
import json, itertools
from scipy.stats import spearmanr
from common import load_primary_cohort, a_raw_from_variants, a_score, overall_candidate, DOCS, K_ANCHORS

cohort = load_primary_cohort()
set_ids = [row["set_id"] for row in cohort]
financial = {row["set_id"]: row["financial_rip_v4_score"] for row in cohort}
collector = {row["set_id"]: row["collector_appeal_v5_score"] for row in cohort}
v10 = {row["set_id"]: row["overall_rip_v10_score"] for row in cohort}
a_raw = {}
for row in cohort:
    araw, _ = a_raw_from_variants(row["per_variant"]["price_used"], row["per_variant"]["modeled_probability"])
    a_raw[row["set_id"]] = araw

K_DEFAULT = 0.002  # primary anchor for the headline LOSO table
WEIGHTS = [4, 6, 8, 10]


def diagnostics_on_subset(ids, cand_scores):
    ctrl_rank = {sid: r for r, sid in enumerate(sorted(ids, key=lambda i: -v10[i]), start=1)}
    cand_rank = {sid: r for r, sid in enumerate(sorted(ids, key=lambda i: -cand_scores[i]), start=1)}
    cand = [cand_scores[i] for i in ids]
    ctrl = [v10[i] for i in ids]
    rho, _ = spearmanr(cand, ctrl)
    top5_ctrl = {sid for sid, r in ctrl_rank.items() if r <= 5}
    top5_cand = {sid for sid, r in cand_rank.items() if r <= 5}
    top5_overlap = len(top5_ctrl & top5_cand)

    close_pairs = 0
    close_reversals = 0
    clear_override_pairs = 0
    clear_overrides_flipped = 0
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
    return {"spearman": rho, "top5_overlap": top5_overlap, "close_reversal_rate": close_rate,
            "clear_overrides_flipped": clear_overrides_flipped,
            "max_financial_gap_overturned": max_gap_overturned}


results = {}
for w in WEIGHTS:
    a_scores_full = {sid: a_score(a_raw[sid], K_DEFAULT) for sid in set_ids}
    per_omit = {}
    for omit in set_ids:
        remaining = [sid for sid in set_ids if sid != omit]
        cand_scores = {sid: overall_candidate(financial[sid], collector[sid], a_scores_full[sid], w)
                       for sid in remaining}
        per_omit[omit] = diagnostics_on_subset(remaining, cand_scores)
    spearmans = {o: d["spearman"] for o, d in per_omit.items()}
    worst_set = min(spearmans, key=lambda o: spearmans[o])
    results[str(w)] = {
        "min_spearman": min(spearmans.values()),
        "max_spearman": max(spearmans.values()),
        "worst_omitted_set": worst_set,
        "min_top5_overlap": min(d["top5_overlap"] for d in per_omit.values()),
        "max_clear_overrides": max(d["clear_overrides_flipped"] for d in per_omit.values()),
        "max_financial_gap_overturned": max(d["max_financial_gap_overturned"] for d in per_omit.values()),
        "close_reversal_rate_min": min(d["close_reversal_rate"] for d in per_omit.values()),
        "close_reversal_rate_max": max(d["close_reversal_rate"] for d in per_omit.values()),
        "meets_min_spearman_ge_098": min(spearmans.values()) >= 0.98,
        "per_omitted_set_spearman": spearmans,
    }

# Robustness sweep: same LOSO computation across ALL k anchors, to check whether
# the k=0.002 finding above is k-specific or holds across the transform grid.
loso_by_k = {}
for k in K_ANCHORS:
    a_scores_k = {sid: a_score(a_raw[sid], k) for sid in set_ids}
    per_w = {}
    for w in WEIGHTS:
        spearmans = {}
        for omit in set_ids:
            remaining = [sid for sid in set_ids if sid != omit]
            cand_scores = {sid: overall_candidate(financial[sid], collector[sid], a_scores_k[sid], w)
                           for sid in remaining}
            d = diagnostics_on_subset(remaining, cand_scores)
            spearmans[omit] = d["spearman"]
        per_w[str(w)] = {
            "min_spearman": min(spearmans.values()),
            "worst_omitted_set": min(spearmans, key=lambda o: spearmans[o]),
            "meets_min_spearman_ge_098": min(spearmans.values()) >= 0.98,
        }
    loso_by_k[str(k)] = per_w

with open("phase9_loso_result.json", "w") as f:
    json.dump({"headline_k_0.002": results, "loso_by_k_sweep": loso_by_k}, f, indent=2, default=float)

for w, r in results.items():
    print(w, "min_spearman=", r["min_spearman"], "worst_set=", r["worst_omitted_set"],
          "meets>=0.98:", r["meets_min_spearman_ge_098"])

print("\n=== LOSO by-k sweep (does min-Spearman>=0.98 hold at every k anchor?) ===")
for k, per_w in loso_by_k.items():
    for w, r in per_w.items():
        print(f"k={k} w={w}: min_spearman={r['min_spearman']:.4f} meets>=0.98={r['meets_min_spearman_ge_098']}")
