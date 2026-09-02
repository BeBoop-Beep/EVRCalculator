"""Pass 1B Phase 5-6: independent deterministic per-card price / pull-probability shocks."""
import json, random, itertools
from scipy.stats import spearmanr
from common import load_primary_cohort, a_raw_from_variants, a_score, overall_candidate, DOCS

cohort = load_primary_cohort()
set_ids = [row["set_id"] for row in cohort]
financial = {row["set_id"]: row["financial_rip_v4_score"] for row in cohort}
collector = {row["set_id"]: row["collector_appeal_v5_score"] for row in cohort}
v10 = {row["set_id"]: row["overall_rip_v10_score"] for row in cohort}

ctrl_rank = {sid: r for r, sid in enumerate(sorted(set_ids, key=lambda i: -v10[i]), start=1)}
top5_ctrl = {sid for sid, r in ctrl_rank.items() if r <= 5}
top10_ctrl = {sid for sid, r in ctrl_rank.items() if r <= 10}

MAGNITUDES = [0.02, 0.05, 0.10]
SEEDS_PER_MAGNITUDE = 12
# Deterministic seed scheme: seed = int(magnitude*1000)*100 + seed_index
# e.g. magnitude 0.02 -> base 200, seeds 200..211 ; 0.05 -> base 500 ; 0.10 -> base 1000
WEIGHTS_TO_TEST = [4, 6, 8]
K_DEFAULT = 0.002  # median-ish anchor for shock scoring; k not the object under test here


def diagnostics_for_candidate(cand_scores):
    ids = set_ids
    cand = [cand_scores[i] for i in ids]
    ctrl = [v10[i] for i in ids]
    rho, _ = spearmanr(cand, ctrl)
    cand_rank = {sid: r for r, sid in enumerate(sorted(ids, key=lambda i: -cand_scores[i]), start=1)}
    top5_cand = {sid for sid, r in cand_rank.items() if r <= 5}
    top10_cand = {sid for sid, r in cand_rank.items() if r <= 10}
    top5_overlap = len(top5_ctrl & top5_cand)
    top10_overlap = len(top10_ctrl & top10_cand)

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
    return {
        "spearman": rho, "top5_overlap": top5_overlap, "top10_overlap": top10_overlap,
        "close_reversal_rate": close_rate, "clear_overrides_flipped": clear_overrides_flipped,
        "max_financial_gap_overturned": max_gap_overturned,
    }


def run_phase(kind):
    """kind: 'card_price' or 'pull_probability'"""
    out = {}
    for mag in MAGNITUDES:
        base_seed = int(round(mag * 1000)) * 100
        seed_results = []
        a_raw_deltas = []
        for s in range(SEEDS_PER_MAGNITUDE):
            seed = base_seed + s
            rng = random.Random(seed)
            a_raw_by_set = {}
            for row in cohort:
                pv = row["per_variant"]
                prices = list(pv["price_used"])
                probs = list(pv["modeled_probability"])
                base_araw, _ = a_raw_from_variants(prices, probs)
                if kind == "card_price":
                    new_prices = [p * (1 + rng.uniform(-mag, mag)) for p in prices]
                    new_probs = probs
                else:
                    new_probs = []
                    for p in probs:
                        pert = p * (1 + rng.uniform(-mag, mag))
                        pert = min(1.0, max(0.0, pert))
                        new_probs.append(pert)
                    new_prices = prices
                new_araw, _ = a_raw_from_variants(new_prices, new_probs)
                a_raw_by_set[row["set_id"]] = new_araw
                a_raw_deltas.append(abs(new_araw - base_araw))

            per_weight = {}
            for w in WEIGHTS_TO_TEST:
                a_scores = {sid: a_score(a_raw_by_set[sid], K_DEFAULT) for sid in set_ids}
                cand_scores = {sid: overall_candidate(financial[sid], collector[sid], a_scores[sid], w)
                               for sid in set_ids}
                per_weight[w] = diagnostics_for_candidate(cand_scores)
            seed_results.append({"seed": seed, "per_weight": per_weight})

        worst_per_weight = {}
        for w in WEIGHTS_TO_TEST:
            rows = [sr["per_weight"][w] for sr in seed_results]
            worst_per_weight[str(w)] = {
                "worst_spearman": min(r["spearman"] for r in rows),
                "worst_top5_overlap": min(r["top5_overlap"] for r in rows),
                "worst_top10_overlap": min(r["top10_overlap"] for r in rows),
                "worst_close_reversal_rate": max(r["close_reversal_rate"] for r in rows),
                "max_clear_overrides": max(r["clear_overrides_flipped"] for r in rows),
                "max_financial_gap_overturned": max(r["max_financial_gap_overturned"] for r in rows),
            }
        out[str(mag)] = {
            "seeds_tested": SEEDS_PER_MAGNITUDE,
            "base_seed": base_seed,
            "worst_per_weight": worst_per_weight,
            "raw_a_raw_abs_delta_median": sorted(a_raw_deltas)[len(a_raw_deltas) // 2],
            "raw_a_raw_abs_delta_max": max(a_raw_deltas),
        }
    return out


phase5 = run_phase("card_price")
phase6 = run_phase("pull_probability")

with open("phase5_6_shocks_result.json", "w") as f:
    json.dump({"phase5_card_price_shocks": phase5, "phase6_pull_probability_shocks": phase6},
               f, indent=2, default=float)

print("=== Phase 5: card price shocks ===")
print(json.dumps(phase5, indent=2, default=float))
print("=== Phase 6: pull probability shocks ===")
print(json.dumps(phase6, indent=2, default=float))
