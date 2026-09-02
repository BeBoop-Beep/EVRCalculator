"""Pass 1B Phase 10: project the SET-level 6% Accessibility candidate onto the
frozen 138-product cohort and report rank movement by product family."""
import json
from collections import defaultdict
from common import load_primary_cohort, load_product_cohort, a_raw_from_variants, a_score, overall_candidate, DOCS

primary = load_primary_cohort()
products = load_product_cohort()["products"]

# set-level A_raw recomputed from frozen per-variant arrays (Accessibility is
# constant per set, independent of which product in that set we're looking at)
a_raw_by_set = {}
for row in primary:
    araw, _ = a_raw_from_variants(row["per_variant"]["price_used"], row["per_variant"]["modeled_probability"])
    a_raw_by_set[row["set_id"]] = araw

K_DEFAULT = 0.002
W = 6

a_score_by_set = {sid: a_score(araw, K_DEFAULT) for sid, araw in a_raw_by_set.items()}

# V10 control rank vs candidate rank, over the WHOLE 138-product cohort (not
# just loose_booster_pack -- Phase 10 asks about family movement across all 8 families).
rows = []
for p in products:
    sid = p["set_id"]
    if sid not in a_score_by_set:
        continue  # product's set is not in the 22-set Accessibility-supported primary cohort
    financial = p["financial_rip_v4_score"]
    collector = p["collector_appeal_v5_score"]
    v10 = p["overall_rip_v10_score"]
    cand = overall_candidate(financial, collector, a_score_by_set[sid], W)
    rows.append({
        "sealed_product_id": p["sealed_product_id"], "set_id": sid,
        "product_family": p["product_family"], "product_name": p["product_name"],
        "v10": v10, "candidate": cand,
    })

n_matched = len(rows)
n_excluded = len(products) - n_matched

ctrl_rank = {r["sealed_product_id"]: i + 1 for i, r in
             enumerate(sorted(rows, key=lambda r: -r["v10"]))}
cand_rank = {r["sealed_product_id"]: i + 1 for i, r in
             enumerate(sorted(rows, key=lambda r: -r["candidate"]))}

for r in rows:
    r["ctrl_rank"] = ctrl_rank[r["sealed_product_id"]]
    r["cand_rank"] = cand_rank[r["sealed_product_id"]]
    r["movement"] = r["cand_rank"] - r["ctrl_rank"]  # negative = riser, positive = faller

by_family = defaultdict(list)
for r in rows:
    by_family[r["product_family"]].append(r)

family_summary = {}
for fam, items in by_family.items():
    moves = [it["movement"] for it in items]
    abs_moves = [abs(m) for m in moves]
    risers = sum(1 for m in moves if m < 0)
    fallers = sum(1 for m in moves if m > 0)
    unchanged = sum(1 for m in moves if m == 0)
    family_summary[fam] = {
        "n": len(items),
        "avg_rank_movement_abs": sum(abs_moves) / len(abs_moves),
        "median_rank_movement_abs": sorted(abs_moves)[len(abs_moves) // 2],
        "avg_signed_movement": sum(moves) / len(moves),
        "risers": risers, "fallers": fallers, "unchanged": unchanged,
    }

# same-set Accessibility reversals: since A_raw/A_score is CONSTANT per set,
# it cannot by itself reorder two products within the same set (their relative
# candidate ordering is driven entirely by Financial+Collector, unchanged
# relative order vs V10 within a set UNLESS Financial/Collector weight also
# changed -- but only the split changed, not their own values, so within-set
# ordering by (Financial, Collector) alone is preserved iff the weights on
# F and C are applied uniformly, which they are). Verify directly:
same_set_reversals = 0
by_set = defaultdict(list)
for r in rows:
    by_set[r["set_id"]].append(r)
for sid, items in by_set.items():
    if len(items) < 2:
        continue
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i], items[j]
            v10_order = a["v10"] > b["v10"]
            cand_order = a["candidate"] > b["candidate"]
            if v10_order != cand_order:
                same_set_reversals += 1

out = {
    "weight_tested_pct": W, "k_used": K_DEFAULT,
    "n_products_total_cohort": len(products),
    "n_products_matched_to_accessibility_supported_sets": n_matched,
    "n_products_excluded_set_not_in_primary_cohort": n_excluded,
    "family_summary": family_summary,
    "same_set_accessibility_reversals": same_set_reversals,
    "same_set_reversals_note": "Must be 0 by construction: A_raw/A_score is set-constant, "
                                "so within a set every product's candidate score shifts by the "
                                "exact same additive/multiplicative amount relative to V10 and "
                                "relative product ordering (by Financial+Collector) cannot flip.",
}

with open("phase10_family_movement_result.json", "w") as f:
    json.dump(out, f, indent=2, default=float)

print("n matched:", n_matched, "excluded:", n_excluded)
print("same_set_accessibility_reversals:", same_set_reversals)
print(json.dumps(family_summary, indent=2, default=float))
