import json, os
D = r"d:\EVRCalculator\backend\research\scratch_pass1a"
OUT = r"d:\EVRCalculator\docs\research"

cohort = json.load(open(os.path.join(D,"cohort_with_negcontrol.json")))
variant_store = json.load(open(os.path.join(D,"variant_store.json")))
results = json.load(open(os.path.join(D,"partial_results.json")))

primary = []
for row in cohort:
    s = row["set_id"]
    primary.append({
        "set_id": s,
        "calculation_run_id_accessibility": row["run_A_accessibility"],
        "market_date_accessibility_run_created_at": row["date_A"],
        "calculation_run_id_financial_collector": row["run_B_financial_collector"],
        "market_date_financial_collector_run_created_at": row["date_B"],
        "offset_days": row["offset_days"],
        "product_market_cost_accessibility_run": row["product_market_cost_A"],
        "product_market_cost_financial_run": row["product_market_cost_B"],
        "pack_count": row["pack_count"],
        "A_raw": row["A_raw"],
        "chase_depth_N_HC": row["chase_depth"],
        "n_priced_variants": row["n_priced_variants"],
        "financial_rip_v4_score": row["financial_rip_v4_score"],
        "financial_rip_v4_components": {
            "true_win_frequency": row["true_win_frequency"],
            "typical_retention": row["typical_retention"],
            "loss_resilience": row["loss_resilience"],
            "realistic_upside": row["realistic_upside"],
            "jackpot_upside": row["jackpot_upside"],
            "base_economic_efficiency": row["base_economic_efficiency"],
        },
        "collector_appeal_v5_score": row["collector_appeal_score"],
        "overall_rip_v10_score": row["overall_rip_v10_score"],
        "expected_value": row["expected_value"],
        "p95_value": row["p95_value"],
        "p99_value": row["p99_value"],
        "total_value_to_cost_ratio": row["total_value_to_cost_ratio"],
        "effective_pack_cost": row["effective_pack_cost"],
        "ECE_raw": row["ECE_raw"],
        "per_variant": variant_store[s],
    })

with open(os.path.join(OUT, "overall_rip_accessibility_primary_cohort.json"), "w") as f:
    json.dump(primary, f, indent=2)
print("wrote primary cohort,", len(primary), "sets")

pr_all = json.load(open(os.path.join(D,"pull_rates_all.json")))
sp_all = json.load(open(os.path.join(D,"sealed_product_results_all.json")))

chase_accessibility_note = (
    "Migration 077 (pokemon_set_chase_accessibility_snapshot_latest) exists in the repo "
    "(backend/db/migrations/077_create_pokemon_set_chase_accessibility_snapshot.sql) and "
    "CHASE_ACCESSIBILITY_V1_IMPLEMENTATION.md describes it as fully implemented with a live read path, "
    "but a live query against the current Supabase project (SUPABASE_URL in backend/.env) returns "
    "PGRST205 (table not found in schema cache). The table does not exist on this environment. "
    "Accessibility values in this pass were NOT read from that snapshot table. Instead A_raw was "
    "independently reconstructed using the exact published formula "
    "(HC_i = V_i^2 / sum(V_j^2), A_raw = sum(HC_i * modeled_probability_i)) directly from "
    "simulation_card_variant_pull_rates (pull_count > 0 filter), the same fields "
    "load_drawable_variants() reads in backend/db/services/chase_accessibility_service.py. This is a "
    "read-only, math-identical reconstruction, not a new metric, but the published/persisted "
    "Accessibility surface itself could not be independently cross-checked against a stored row."
)

coherence_note = (
    "No single calculation_run_id carries both (a) simulation_card_variant_pull_rates rows (needed for "
    "Accessibility) and (b) a finalized simulation_sealed_product_results row with BOTH "
    "collector_appeal_score and overall_rip_v10_score non-null (needed for Financial RIP V4 total, "
    "Collector Appeal V5, and the Overall RIP V10 control) for the same product. The pipeline "
    "continuously re-simulates (fresh runs land in simulation_card_variant_pull_rates roughly every few "
    "hours per set) while Collector Appeal/Overall RIP V10 enrichment is a separate downstream "
    "finalization pass that lags behind and was last completed around 2026-08-27 for this cohort. For "
    "all 22 sets the two runs are between 1.0 and 5.4 days apart, and product_market_cost differs by "
    "well under 2% between the two runs, so the two runs describe materially the same market state even "
    "though they are not the same calculation_run_id. This mirrors, at a similar order of magnitude, the "
    "mismatch documented in the prior OVERALL_RIP_ACCESSIBILITY_ARCHITECTURE_CLOSURE pass (there: 4-day "
    "offset, 123/138 products across 20 sets). Because this looks like a structural property of the "
    "pipeline cadence rather than a one-off gap, the strongest reproducible cohort pairs, per set, the "
    "LATEST run with pull-rate rows to the LATEST run with full Financial+Collector+Overall enrichment."
)

collector_version_seen = None
overall_v10_version_seen = None
for r in sp_all:
    if r.get("collector_appeal_version") and collector_version_seen is None:
        collector_version_seen = r["collector_appeal_version"]
    if r.get("overall_rip_v10_version") and overall_v10_version_seen is None:
        overall_v10_version_seen = r["overall_rip_v10_version"]
    if collector_version_seen and overall_v10_version_seen:
        break

authority = {
    "pass": "OVERALL_RIP_ACCESSIBILITY_PASS_1A_ECE",
    "start_head": "26bec1c5183164f5d8bde0be9571836183b1f455",
    "head_at_artifact_write_time": "8affebfb587a6b8e207dca42b627a168528dc619",
    "branch": "fix/public-rankings-entitlement-regression-2",
    "critical_finding_chase_accessibility_persistence_not_live": chase_accessibility_note,
    "coherence_limitation": coherence_note,
    "product_family_scope": "loose_booster_pack only (pack_count == 1 uniformly, so effective_pack_cost == product_market_cost; avoids conflating booster_box/ETB pack-equivalent conversions into this pass)",
    "primary_cohort_set_count": len(primary),
    "primary_cohort_set_ids": [r["set_id"] for r in primary],
    "temporal_replication_cohort_identified": (
        "The 2026-08-27 17:00-18:30 UTC batch of simulation_sealed_product_results rows (the run_B "
        "values in primary_cohort.json, same 22 sets) is a usable, already-identified temporal "
        "replication cohort with its own Financial RIP V4 / Collector Appeal V5 / Overall RIP V10 "
        "authority. It was not independently re-analyzed in this pass because no separate "
        "simulation_card_variant_pull_rates snapshot from that same window remains queryable: only 64 "
        "distinct calculation_run_ids remain live in simulation_card_variant_pull_rates against 261 "
        "distinct runs in simulation_sealed_product_results, meaning older runs' pull-rate rows appear "
        "pruned once a set is re-simulated. A Pass 1B temporal replication should snapshot pull_rates "
        "immediately when a run completes rather than relying on retroactive lookup."
    ),
    "financial_rip_v4_version_seen": "financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5 (matches backend/calculations/evr/financial_rip_v4_config.py FINANCIAL_RIP_V4_VERSION)",
    "collector_appeal_version_seen": collector_version_seen,
    "overall_rip_v10_version_seen": overall_v10_version_seen,
    "probability_authority_used": "modeled_probability (simulation_card_variant_pull_rates.modeled_probability) exclusively; effective_pull_rate was pulled for reference only and never used as a probability",
    "row_counts": {
        "simulation_card_variant_pull_rates_total_rows_pulled": len(pr_all),
        "simulation_sealed_product_results_total_rows_pulled": len(sp_all),
        "distinct_calculation_run_ids_in_pull_rates": len(set(r["calculation_run_id"] for r in pr_all)),
        "distinct_calculation_run_ids_in_sealed_product_results": len(set(r["calculation_run_id"] for r in sp_all)),
        "loose_booster_pack_rows": sum(1 for r in sp_all if r.get("product_family") == "loose_booster_pack"),
    },
    "exclusions": (
        "Non-loose_booster_pack families (elite_trainer_box, pokemon_center_elite_trainer_box, "
        "booster_bundle, booster_box, sleeved_booster_pack, half_booster_box, enhanced_booster_box) "
        "excluded from this pass's primary cohort to avoid mixing pack-equivalent conversions into the "
        "effective_pack_cost denominator; a Pass 1B could extend using random_pack_count for those "
        "families, which is populated separately from pack_count."
    ),
    "supported_set_cohort_overall": (
        "1558 simulation_sealed_product_results rows span 261 distinct calculation_run_ids; "
        "239 of those rows are loose_booster_pack across 22 distinct set_ids with a run present in "
        "simulation_card_variant_pull_rates; all 22 also have a (different, ~5.4-day-earlier) run with "
        "full Collector Appeal + Overall RIP V10 enrichment, giving the 22-set primary cohort used here."
    ),
}

with open(os.path.join(OUT, "overall_rip_accessibility_authority.json"), "w") as f:
    json.dump(authority, f, indent=2)
print("wrote authority.json")
print("collector_version_seen:", collector_version_seen)
print("overall_v10_version_seen:", overall_v10_version_seen)
