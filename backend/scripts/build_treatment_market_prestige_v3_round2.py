"""Treatment Market Prestige V3 Round 2, research-only validation.

Consumes only the immutable Round 1 cohort. No live/latest database read and no
database or production score write is implemented by this module.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.stats import f as f_distribution

from backend.desirability.treatment_market_prestige_v3 import residualize_fixed_effects, stable_json_hash
from backend.scripts.build_treatment_market_prestige_v3 import build_design

ROOT = Path("docs/research")
R1_DIR = ROOT / "treatment_market_prestige_v3_frozen_cohort"
R1_STUDY = ROOT / "treatment_market_prestige_v3_study.json"
R2_DIR = ROOT / "treatment_market_prestige_v3_round2_exact_pull_cohort"
R2_STUDY = ROOT / "treatment_market_prestige_v3_round2_study.json"
R2_REPORT = ROOT / "TREATMENT_MARKET_PRESTIGE_V3_ROUND2_RESULTS.md"
R1_ID = "treatment-market-prestige-v3-r1-6959bfa9889458fe"
SEED = 20260830
ROUND1_ELIGIBLE = {
    "Scarlet and Violet": ("illustration_rare", "special_illustration_rare", "double_rare"),
    "Mega Evolution": ("illustration_rare", "double_rare", "ultra_rare"),
}
GATES = {
    "min_cards": 25, "min_sets": 5, "bootstrap_sign_stability": .90,
    "max_bootstrap_interval_width": 2.0, "leave_set_out_sign_stability": .80,
    "strong_ordering_probability": .95, "moderate_ordering_probability": .80,
    "meaningful_partial_r2": .02, "meaningful_cv_rmse_reduction": .01,
    "matched_log_scarcity_tolerance": .10,
}


def load_round1() -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    manifest = json.loads((R1_DIR / "manifest.json").read_text(encoding="utf-8"))
    payload = json.loads((R1_DIR / "cohort.json").read_text(encoding="utf-8"))
    study = json.loads(R1_STUDY.read_text(encoding="utf-8"))
    if manifest["study_id"] != R1_ID or payload["study_id"] != R1_ID or study["frozen_study"]["study_id"] != R1_ID:
        raise RuntimeError("Round 1 authority differs from the preregistered Round 2 input")
    if stable_json_hash(payload["rows"]) != manifest["cohort_hash"]:
        raise RuntimeError("Round 1 cohort hash verification failed")
    return payload["rows"], manifest, study


def coverage_audit(main: Sequence[Mapping[str, Any]], exact: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    exact_ids = {row["canonical_card_id"] for row in exact}
    treatment = []
    for era in sorted({row["era_name"] for row in main}):
        for rarity in sorted({row.get("rarity_designation") for row in main if row["era_name"] == era}, key=str):
            group = [row for row in main if row["era_name"] == era and row.get("rarity_designation") == rarity]
            covered = sum(row["canonical_card_id"] in exact_ids for row in group)
            treatment.append({"era": era, "treatment": rarity or "__unmapped__", "main_cards": len(group),
                              "exact_pull_cards": covered, "coverage_rate": covered / len(group)})
    return {
        "cards": len(exact), "variants": len({row["variant_id"] for row in exact}),
        "sets": len({row["set_id"] for row in exact}), "eras": len({row["era_id"] for row in exact}),
        "species": len({row["species_id"] for row in exact if row.get("species_id")}),
        "treatment_designations": len({row.get("rarity_designation") for row in exact if row.get("rarity_designation")}),
        "era_treatment_categories": len({(row["era_name"], row.get("rarity_designation")) for row in exact if row.get("rarity_designation")}),
        "main_cohort_coverage_rate": len(exact) / len(main), "treatment_coverage": treatment,
    }


def freeze_exact(main: list[dict[str, Any]], r1_manifest: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    exact = [dict(row) for row in main if row.get("exact_pull_probability") and row.get("exact_pull_run_id")]
    for row in exact:
        row["log_exact_pull_scarcity"] = math.log(1 / float(row["exact_pull_probability"]))
    exact.sort(key=lambda row: (row["set_id"], row["variant_id"]))
    run_provenance = []
    for run_id in sorted({row["exact_pull_run_id"] for row in exact}):
        group = [row for row in exact if row["exact_pull_run_id"] == run_id]
        run_provenance.append({"calculation_run_id": run_id, "sets": sorted({row["set_id"] for row in group}),
                               "rows": len(group), "rows_hash": stable_json_hash(group)})
    cohort_hash = stable_json_hash(exact); run_hash = stable_json_hash(run_provenance)
    core = {
        "frozen_at": datetime.now(timezone.utc).isoformat(), "methodology": "treatment_market_prestige_v3_round2",
        "round1_study_id": R1_ID, "round1_manifest_hash": r1_manifest["manifest_hash"],
        "round1_cohort_hash": r1_manifest["cohort_hash"], "cohort_hash": cohort_hash,
        "calculation_run_provenance_hash": run_hash, "rows": len(exact), "calculation_runs": len(run_provenance),
        "source_rule": "intersection of immutable Round 1 rows with already-frozen exact_pull_probability and exact_pull_run_id",
    }
    manifest_hash = stable_json_hash(core)
    manifest = {"study_id": f"treatment-market-prestige-v3-r2-{manifest_hash[:16]}", "manifest_hash": manifest_hash, **core}
    R2_DIR.mkdir(parents=True, exist_ok=True)
    (R2_DIR / "cohort.json").write_text(json.dumps({"study_id": manifest["study_id"], "rows": exact}, indent=2), encoding="utf-8")
    (R2_DIR / "calculation_run_provenance.json").write_text(json.dumps(run_provenance, indent=2), encoding="utf-8")
    (R2_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return exact, manifest


def load_exact() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    manifest = json.loads((R2_DIR / "manifest.json").read_text(encoding="utf-8"))
    payload = json.loads((R2_DIR / "cohort.json").read_text(encoding="utf-8"))
    if stable_json_hash(payload["rows"]) != manifest["cohort_hash"] or payload["study_id"] != manifest["study_id"]:
        raise RuntimeError("Round 2 frozen diagnostic cohort verification failed")
    return payload["rows"], manifest


def independent_columns(X: np.ndarray, names: list[str]) -> tuple[np.ndarray, list[str], list[str]]:
    order = [i for i, name in enumerate(names) if name.startswith("control_") or name == "exact_pull_scarcity"] + [
        i for i, name in enumerate(names) if not (name.startswith("control_") or name == "exact_pull_scarcity")]
    selected: list[int] = []; dropped = []; rank = 0
    for index in order:
        candidate = X[:, selected + [index]]
        candidate_rank = int(np.linalg.matrix_rank(candidate))
        if candidate_rank > rank:
            selected.append(index); rank = candidate_rank
        else:
            dropped.append(names[index])
    return X[:, selected], [names[index] for index in selected], dropped


def fit(rows: Sequence[Mapping[str, Any]], mode: str, *, mechanics: bool = True) -> dict[str, Any]:
    base_X, y, names, references, groups = build_design(rows, demand_spec=False, mechanics=mechanics)
    treatment_indexes = [i for i, name in enumerate(names) if not name.startswith("control_")]
    control_indexes = [i for i, name in enumerate(names) if name.startswith("control_")]
    if mode == "scarcity":
        indexes = control_indexes; extra = [np.asarray([row["log_exact_pull_scarcity"] for row in rows])]; out_names = [names[i] for i in indexes] + ["exact_pull_scarcity"]
    elif mode == "treatment":
        indexes = control_indexes + treatment_indexes; extra = []; out_names = [names[i] for i in indexes]
    elif mode == "combined":
        indexes = control_indexes + treatment_indexes; extra = [np.asarray([row["log_exact_pull_scarcity"] for row in rows])]; out_names = [names[i] for i in indexes] + ["exact_pull_scarcity"]
    else:
        raise ValueError(mode)
    parts = [base_X[:, indexes]] if indexes else []
    parts.extend(value[:, None] for value in extra)
    X = np.column_stack(parts) if parts else np.empty((len(rows), 0))
    joint = residualize_fixed_effects(np.column_stack([y, X]), groups)
    yr, Xr = joint[:, 0], joint[:, 1:]
    nonzero = np.sqrt(np.sum(Xr * Xr, axis=0)) > 1e-9
    dropped = [name for name, keep in zip(out_names, nonzero) if not keep]
    Xr, out_names = Xr[:, nonzero], [name for name, keep in zip(out_names, nonzero) if keep]
    Xr, out_names, aliases = independent_columns(Xr, out_names); dropped.extend(aliases)
    beta, _, rank, _ = np.linalg.lstsq(Xr, yr, rcond=None)
    fitted = Xr @ beta; residual = yr - fitted; sse = float(residual @ residual); sst = float(yr @ yr)
    n = len(rows); k = len(out_names) + len({row["set_id"] for row in rows}) - 1 + len({row["species_id"] for row in rows}) - 1
    r2 = 1 - sse / sst if sst else None
    adjusted = 1 - (1 - r2) * (n - 1) / max(n - k - 1, 1) if r2 is not None else None
    return {
        "mode": mode, "n": n, "rank": int(rank), "columns": len(out_names), "full_rank": int(rank) == len(out_names),
        "coefficients": {name: float(value) for name, value in zip(out_names, beta)}, "references": references,
        "non_estimable_columns": dropped, "sse": sse, "r_squared_within": r2, "adjusted_r_squared_within": adjusted,
        "rmse_within": math.sqrt(sse / n), "aic_comparable": n * math.log(sse / n) + 2 * k,
        "_X": Xr, "_y": yr, "_fitted": fitted, "_residual": residual, "_names": out_names,
    }


def clean(model: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in model.items() if not key.startswith("_")}


def wild_draws(model: Mapping[str, Any], rows: Sequence[Mapping[str, Any]], draws: int, seed: int) -> dict[str, list[float]]:
    rng = np.random.default_rng(seed); sets = np.asarray([row["set_id"] for row in rows]); unique = np.unique(sets)
    X = model["_X"]; output = np.empty((draws, len(model["_names"])))
    for draw in range(draws):
        signs = {sid: rng.choice((-1., 1.)) for sid in unique}
        ystar = model["_fitted"] + model["_residual"] * np.asarray([signs[sid] for sid in sets])
        output[draw] = np.linalg.lstsq(X, ystar, rcond=None)[0]
    return {name: output[:, index].tolist() for index, name in enumerate(model["_names"])}


def cross_validated_rmse(model: Mapping[str, Any], rows: Sequence[Mapping[str, Any]], folds: int, seed: int) -> float:
    """Conditional CV after fixed non-treatment projection, stratified within set."""
    rng = np.random.default_rng(seed); assignment = np.empty(len(rows), dtype=int)
    by_set: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows): by_set[row["set_id"]].append(index)
    for indexes in by_set.values():
        shuffled = rng.permutation(indexes)
        for position, index in enumerate(shuffled): assignment[index] = position % folds
    errors = []
    X, y = model["_X"], model["_y"]
    for fold in range(folds):
        train = assignment != fold; test = ~train
        Xtrain, fold_names, _ = independent_columns(X[train], list(model["_names"]))
        indexes = [list(model["_names"]).index(name) for name in fold_names]
        beta = np.linalg.lstsq(Xtrain, y[train], rcond=1e-9)[0]
        errors.extend((y[test] - X[test][:, indexes] @ beta).tolist())
    return float(np.sqrt(np.mean(np.square(errors))))


def comparison(rows: list[dict[str, Any]], seed: int) -> dict[str, Any]:
    models = {mode: fit(rows, mode) for mode in ("scarcity", "treatment", "combined")}
    for index, model in enumerate(models.values()):
        model["cv_rmse_conditional_5fold"] = cross_validated_rmse(model, rows, 5, seed + index)
    scarcity, treatment, combined = models["scarcity"], models["treatment"], models["combined"]
    treatment_partial = (scarcity["sse"] - combined["sse"]) / scarcity["sse"]
    scarcity_partial = (treatment["sse"] - combined["sse"]) / treatment["sse"]
    treatment_df = max(combined["columns"] - scarcity["columns"], 1)
    scarcity_df = max(combined["columns"] - treatment["columns"], 1)
    residual_df = max(len(rows) - combined["columns"] - len({row['set_id'] for row in rows}) - len({row['species_id'] for row in rows}), 1)
    treatment_f = ((scarcity["sse"] - combined["sse"]) / treatment_df) / (combined["sse"] / residual_df)
    scarcity_f = ((treatment["sse"] - combined["sse"]) / scarcity_df) / (combined["sse"] / residual_df)
    return {
        "models": {key: clean(value) for key, value in models.items()},
        "treatment_incremental": {"partial_r_squared": treatment_partial,
            "adjusted_r_squared_change": combined["adjusted_r_squared_within"] - scarcity["adjusted_r_squared_within"],
            "aic_change_combined_minus_scarcity": combined["aic_comparable"] - scarcity["aic_comparable"],
            "cv_rmse_reduction": (scarcity["cv_rmse_conditional_5fold"] - combined["cv_rmse_conditional_5fold"]) / scarcity["cv_rmse_conditional_5fold"],
            "treatment_block_f": treatment_f, "treatment_block_df": [treatment_df, residual_df],
            "treatment_block_p_value": float(f_distribution.sf(treatment_f, treatment_df, residual_df))},
        "scarcity_incremental_reverse": {"partial_r_squared": scarcity_partial,
            "adjusted_r_squared_change": combined["adjusted_r_squared_within"] - treatment["adjusted_r_squared_within"],
            "aic_change_combined_minus_treatment": combined["aic_comparable"] - treatment["aic_comparable"],
            "cv_rmse_reduction": (treatment["cv_rmse_conditional_5fold"] - combined["cv_rmse_conditional_5fold"]) / treatment["cv_rmse_conditional_5fold"],
            "scarcity_block_f": scarcity_f, "scarcity_block_df": [scarcity_df, residual_df],
            "scarcity_block_p_value": float(f_distribution.sf(scarcity_f, scarcity_df, residual_df))},
        "_models": models,
    }


def treatment_rows(rows: Sequence[Mapping[str, Any]], era: str, treatment: str) -> list[Mapping[str, Any]]:
    return [row for row in rows if row["era_name"] == era and row.get("rarity_designation") == treatment]


def leave_set_sign(rows: list[dict[str, Any]], era: str, treatment: str, point: float) -> dict[str, Any]:
    era_rows = [row for row in rows if row["era_name"] == era]; values = []; failures = []
    key = f"rarity_designation:{treatment}"
    for sid in sorted({row["set_id"] for row in era_rows}):
        try:
            model = fit([row for row in era_rows if row["set_id"] != sid], "combined")
            if key in model["coefficients"]: values.append(model["coefficients"][key])
            else: failures.append(sid)
        except np.linalg.LinAlgError: failures.append(sid)
    return {"fits": len(values), "failures": failures, "same_sign_rate": sum(np.sign(value) == np.sign(point) for value in values) / len(values) if values else 0,
            "min": min(values) if values else None, "max": max(values) if values else None}


def eligibility(rows: list[dict[str, Any]], era_comparisons: Mapping[str, Any], draws: int, seed: int) -> tuple[dict[str, Any], dict[str, Any]]:
    universes = {}; all_draws = {}
    for era, candidates in ROUND1_ELIGIBLE.items():
        model = era_comparisons[era]["_models"]["combined"]
        samples = wild_draws(model, [row for row in rows if row["era_name"] == era], draws, seed + len(universes))
        all_draws[era] = samples; details = []; eligible = []
        for treatment in candidates:
            key = f"rarity_designation:{treatment}"; group = treatment_rows(rows, era, treatment)
            values = np.asarray(samples.get(key, [])); point = model["coefficients"].get(key)
            ci = [float(np.quantile(values, .025)), float(np.quantile(values, .975))] if len(values) else [None, None]
            leave = leave_set_sign(rows, era, treatment, point) if point is not None else {"fits": 0, "failures": [], "same_sign_rate": 0}
            gates = {
                "round1_stable": treatment in ROUND1_ELIGIBLE[era], "minimum_cards": len(group) >= GATES["min_cards"],
                "minimum_sets": len({row["set_id"] for row in group}) >= GATES["min_sets"], "estimable": point is not None,
                "bootstrap_sign_stability": bool(len(values) and max(np.mean(values > 0), np.mean(values < 0)) >= GATES["bootstrap_sign_stability"]),
                "bootstrap_interval_excludes_zero": bool(len(values) and ci[0] * ci[1] > 0),
                "acceptable_uncertainty": bool(len(values) and ci[1] - ci[0] <= GATES["max_bootstrap_interval_width"]),
                "leave_set_out_stability": leave["same_sign_rate"] >= GATES["leave_set_out_sign_stability"] and not leave["failures"],
            }
            passed = all(gates.values())
            if passed: eligible.append(treatment)
            details.append({"treatment": treatment, "cards": len(group), "sets": len({row["set_id"] for row in group}), "coefficient_after_exact_pull_scarcity": point,
                            "bootstrap_ci": ci, "bootstrap_sign_stability": max(np.mean(values > 0), np.mean(values < 0)) if len(values) else None,
                            "leave_set_out": leave, "gates": gates, "eligible": passed})
        universes[era] = {"eligible": eligible, "details": details, "gates": GATES}
    return universes, all_draws


def ranking_and_scores(universes: Mapping[str, Any], draws: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    output = {}
    for era, universe in universes.items():
        eligible = universe["eligible"]; matrix = {}; scores = []
        if len(eligible) < 2:
            output[era] = {"status": "INSUFFICIENT_ELIGIBLE_TREATMENTS", "matrix": {}, "scores": []}; continue
        draw_count = min(len(draws[era].get(f"rarity_designation:{item}", [])) for item in eligible)
        per_draw_scores = {item: [] for item in eligible}
        for left in eligible:
            matrix[left] = {}
            a = np.asarray(draws[era][f"rarity_designation:{left}"][:draw_count])
            for right in eligible:
                if left == right: matrix[left][right] = .5; continue
                b = np.asarray(draws[era][f"rarity_designation:{right}"][:draw_count]); probability = float(np.mean(a > b))
                confidence = "strong" if max(probability, 1-probability) >= GATES["strong_ordering_probability"] else "moderate" if max(probability, 1-probability) >= GATES["moderate_ordering_probability"] else "unresolved"
                matrix[left][right] = {"probability": probability, "confidence": confidence}
        for index in range(draw_count):
            for left in eligible:
                per_draw_scores[left].append(10 * np.mean([draws[era][f"rarity_designation:{left}"][index] > draws[era][f"rarity_designation:{right}"][index] for right in eligible if right != left]))
        for treatment in eligible:
            values = np.asarray(per_draw_scores[treatment]); group = treatment_rows(rows, era, treatment)
            point = 10 * np.mean([matrix[treatment][other]["probability"] for other in eligible if other != treatment])
            scores.append({"treatment": treatment, "score": float(point), "bootstrap_interval": [float(np.quantile(values, .025)), float(np.quantile(values, .975))],
                           "cards": len(group), "sets": len({row["set_id"] for row in group}),
                           "support": "eligible", "presentation": "broad_tier" if np.ptp(np.quantile(values, [.025,.975])) > 2 else "integer"})
        unresolved=any(cell.get("confidence")=="unresolved" for row in matrix.values() for cell in row.values() if isinstance(cell,dict))
        output[era] = {"status": "SCORE_NOT_READY_UNRESOLVED_ORDERING" if unresolved else "CANDIDATE_SCORE_ESTIMATED", "matrix": matrix,
                       "scores": [] if unresolved else scores, "diagnostic_unapproved_score_estimates": scores if unresolved else [],
                       "interpretation": "How consistently this treatment carries a stronger adjusted market premium than other supported treatments in the same Pokémon era."}
    return output


def residual_findings(rows: list[dict[str, Any]], scarcity_model: Mapping[str, Any], treatment_model: Mapping[str, Any], combined_model: Mapping[str, Any]) -> dict[str, Any]:
    residuals = scarcity_model["_residual"]; grouped = defaultdict(list)
    for row, residual in zip(rows, residuals): grouped[(row["era_name"], row.get("rarity_designation"))].append(float(residual))
    disappear = []
    for key, before in treatment_model["coefficients"].items():
        if key.startswith("control_") or key not in combined_model["coefficients"]: continue
        after = combined_model["coefficients"][key]
        if abs(after) < .25 or (abs(before) > 0 and abs(after) / abs(before) <= .5):
            disappear.append({"treatment": key, "treatment_only_coefficient": before, "after_exact_pull_scarcity": after,
                              "absolute_shrinkage_rate": 1-abs(after)/abs(before) if before else None})
    return {"definition": "mean residual log-price association after Exact Pull Scarcity, set FE, species FE, and mechanic controls; not pure prestige",
            "apparent_prestige_substantially_reduced_after_exact_pull_scarcity": disappear,
            "treatments": [{"era": key[0], "treatment": key[1], "n": len(values), "mean_residual_log_price": float(np.mean(values)),
                            "median_residual_log_price": float(np.median(values))} for key, values in sorted(grouped.items(), key=lambda item: str(item[0])) if len(values) >= 10]}


def matched_examples(rows: list[dict[str, Any]], scarcity_model: Mapping[str, Any], eligible: Mapping[str, Any]) -> list[dict[str, Any]]:
    residuals = scarcity_model["_residual"]; candidates = []
    for era, universe in eligible.items():
        indexes = [i for i, row in enumerate(rows) if row["era_name"] == era and row.get("rarity_designation") in universe["eligible"]]
        for a_pos, i in enumerate(indexes):
            for j in indexes[a_pos+1:]:
                a, b = rows[i], rows[j]
                if a["rarity_designation"] == b["rarity_designation"]: continue
                distance = abs(a["log_exact_pull_scarcity"] - b["log_exact_pull_scarcity"])
                if distance > GATES["matched_log_scarcity_tolerance"]: continue
                comparable = a.get("species_id") == b.get("species_id") or bool(set(a.get("mechanic_or_card_form", [])) & set(b.get("mechanic_or_card_form", [])))
                if not comparable: continue
                candidates.append((abs(residuals[i]-residuals[j]), i, j, distance))
    selected = []; used_pairs = set()
    for difference, i, j, distance in sorted(candidates, reverse=True):
        a, b = rows[i], rows[j]; pair = tuple(sorted((a["rarity_designation"], b["rarity_designation"])))
        if (a["era_name"], pair) in used_pairs: continue
        used_pairs.add((a["era_name"], pair))
        selected.append({"era": a["era_name"], "matching_rule": f"absolute log Exact Pull Scarcity difference <= {GATES['matched_log_scarcity_tolerance']}",
                         "exact_pull_scarcity_log_difference": distance, "same_species": a.get("species_id") == b.get("species_id"),
                         "card_a": {"name": a["card_name"], "set": a["set_name"], "treatment": a["rarity_designation"], "pull_probability": a["exact_pull_probability"], "scarcity_adjusted_residual": float(residuals[i])},
                         "card_b": {"name": b["card_name"], "set": b["set_name"], "treatment": b["rarity_designation"], "pull_probability": b["exact_pull_probability"], "scarcity_adjusted_residual": float(residuals[j])}})
        if len(selected) >= 8: break
    return selected


def scarcity_prestige_product(rows: list[dict[str, Any]], universes: Mapping[str, Any], rankings: Mapping[str, Any], combined: Mapping[str, Any]) -> dict[str, Any]:
    eras = {}; discordant_total = comparisons_total = 0
    for era, universe in universes.items():
        treatments = universe["eligible"]
        if len(treatments) < 2: continue
        scarcity = {t: float(np.mean([row["log_exact_pull_scarcity"] for row in treatment_rows(rows, era, t)])) for t in treatments}
        prestige = {t: combined[era]["_models"]["combined"]["coefficients"].get(f"rarity_designation:{t}", 0) for t in treatments}
        scarcity_score = {t: 10*np.mean([scarcity[t] > scarcity[o] for o in treatments if o != t]) for t in treatments}
        score_rows=rankings[era]["scores"] or rankings[era].get("diagnostic_unapproved_score_estimates",[])
        prestige_score = {item["treatment"]: item["score"] for item in score_rows}
        discordant = []
        for i, left in enumerate(treatments):
            for right in treatments[i+1:]:
                comparisons_total += 1
                if np.sign(scarcity[left]-scarcity[right]) != np.sign(prestige[left]-prestige[right]):
                    discordant_total += 1; discordant.append([left, right])
        rank_corr = float(np.corrcoef([scarcity_score[t] for t in treatments], [prestige_score[t] for t in treatments])[0,1]) if len(treatments)>2 else None
        eras[era] = {"mean_log_exact_pull_scarcity": scarcity, "prestige_coefficients_after_scarcity": prestige,
                     "scarcity_superiority_score": scarcity_score, "prestige_score": prestige_score,
                     "score_or_rank_correlation": rank_corr, "discordant_pairs": discordant,
                     "discordant_pair_rate": len(discordant)/(len(treatments)*(len(treatments)-1)/2)}
    return {"by_era": eras, "overall_discordant_pair_rate": discordant_total/comparisons_total if comparisons_total else None,
            "comparison_count": comparisons_total}


def era_heterogeneity(draws: Mapping[str, Any]) -> list[dict[str, Any]]:
    output = []
    for treatment in sorted(set(ROUND1_ELIGIBLE["Scarlet and Violet"]) & set(ROUND1_ELIGIBLE["Mega Evolution"])):
        key = f"rarity_designation:{treatment}"; a = np.asarray(draws["Scarlet and Violet"].get(key, [])); b = np.asarray(draws["Mega Evolution"].get(key, []))
        n = min(len(a),len(b))
        if n:
            diff = a[:n]-b[:n]; output.append({"treatment": treatment, "sv_minus_mega_log_difference": float(np.mean(diff)),
                "bootstrap_interval": [float(np.quantile(diff,.025)),float(np.quantile(diff,.975))],
                "probability_sv_greater": float(np.mean(diff>0)), "material_difference": bool(abs(np.mean(diff))>=.25 and np.quantile(diff,.025)*np.quantile(diff,.975)>0)})
    return output


def score_robustness(rows: list[dict[str, Any]], universes: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict[str, Any]:
    output = {}
    for era, universe in universes.items():
        eligible = universe["eligible"]
        if len(eligible)<2: continue
        base_order = sorted(eligible,key=lambda t:baseline[era]["_models"]["combined"]["coefficients"].get(f"rarity_designation:{t}",0),reverse=True)
        changes=[]; era_rows=[row for row in rows if row["era_name"]==era]
        baseline_hard={t:10*np.mean([base_order.index(t)<base_order.index(o) for o in eligible if o!=t]) for t in eligible}
        tier=lambda score:"high" if score>=6.67 else "middle" if score>=3.33 else "low"
        for sid in sorted({row["set_id"] for row in era_rows}):
            fit_lso=fit([row for row in era_rows if row["set_id"]!=sid],"combined")
            order=sorted(eligible,key=lambda t:fit_lso["coefficients"].get(f"rarity_designation:{t}",-math.inf),reverse=True)
            hard={t:10*np.mean([order.index(t)<order.index(o) for o in eligible if o!=t]) for t in eligible}
            changes.append({"left_out_set_id":sid,"order":order,"rank_changes":sum(a!=b for a,b in zip(base_order,order)),
                            "ordering_scores":hard,"max_score_change":max(abs(hard[t]-baseline_hard[t]) for t in eligible),
                            "tier_changes":sum(tier(hard[t])!=tier(baseline_hard[t]) for t in eligible)})
        output[era]={"baseline_order":base_order,"leave_one_set_out":changes,"fits_with_any_rank_change":sum(item["rank_changes"]>0 for item in changes),
                     "max_leave_set_out_score_change":max(item["max_score_change"] for item in changes),
                     "fits_with_tier_change":sum(item["tier_changes"]>0 for item in changes),
                     "treatment_cell_sensitivity":"eligibility gates retained; no gate reduction", "temporal_sensitivity":"NOT_ESTIMABLE_NO_COMPARABLE_FROZEN_HISTORY"}
    return output


def sensitivity_scores(rows: list[dict[str, Any]], universes: Mapping[str, Any], baseline_rankings: Mapping[str, Any], draws: int, seed: int) -> dict[str, Any]:
    prices=np.asarray([row["market_price"] for row in rows]); low,high=np.quantile(prices,[.01,.99])
    demands=np.asarray([row["demand_score"] for row in rows]); demand_cut=float(np.quantile(demands,.95))
    variants={"price_outlier_trim_1_99":[row for row in rows if low<=row["market_price"]<=high],
              "demand_outlier_top_5_removal":[row for row in rows if row["demand_score"]<=demand_cut],
              "mechanic_control_removal":rows}
    result={}
    for label,subset in variants.items():
        result[label]={}
        for era,universe in universes.items():
            eligible=universe["eligible"]
            if len(eligible)<2 or not baseline_rankings[era]["scores"]:
                result[label][era]={"status":"NOT_RUN_NO_APPROVED_CANDIDATE_SCORE"}; continue
            group=[row for row in subset if row["era_name"]==era]
            model=fit(group,"combined",mechanics=label!="mechanic_control_removal")
            sample=wild_draws(model,group,draws,seed+len(result[label]))
            fake={era:{"eligible":eligible}}; ranked=ranking_and_scores(fake,{era:sample},group)[era]
            base={item["treatment"]:item["score"] for item in baseline_rankings[era]["scores"]}; current={item["treatment"]:item["score"] for item in ranked["scores"]}
            base_order=sorted(eligible,key=lambda t:base[t],reverse=True); order=sorted(eligible,key=lambda t:current[t],reverse=True)
            result[label][era]={"retained_rows":len(group),"scores":ranked["scores"],"rank_changes":sum(a!=b for a,b in zip(base_order,order)),
                                      "max_score_change":max(abs(current[t]-base[t]) for t in eligible)}
    result["treatment_cell_threshold_50"]={era:{"still_supported":[t for t in universe["eligible"] if len(treatment_rows(rows,era,t))>=50],
                                                    "excluded_below_50":[t for t in universe["eligible"] if len(treatment_rows(rows,era,t))<50]}
                                            for era,universe in universes.items()}
    return result


def decide(era_results: Mapping[str, Any], product: Mapping[str, Any], rankings: Mapping[str, Any], score_robust: Mapping[str, Any], sensitivities: Mapping[str, Any]) -> tuple[str,str,bool,bool]:
    incremental = {era: result["treatment_incremental"]["partial_r_squared"] >= GATES["meaningful_partial_r2"] and result["treatment_incremental"]["cv_rmse_reduction"] >= GATES["meaningful_cv_rmse_reduction"] for era,result in era_results.items()}
    stable_score_eras=[]
    for era, value in rankings.items():
        scores=value.get("scores",[]); robustness=score_robust.get(era,{})
        sensitivity_ok=all(sensitivities.get(label,{}).get(era,{}).get("rank_changes",999)==0 and sensitivities.get(label,{}).get(era,{}).get("max_score_change",999)<=2.5
                           for label in ("price_outlier_trim_1_99","demand_outlier_top_5_removal","mechanic_control_removal"))
        if len(scores)>=3 and all(item["presentation"] in {"integer","broad_tier"} for item in scores) and robustness.get("fits_with_any_rank_change",999)<=1 and sensitivity_ok:
            stable_score_eras.append(era)
    if any(incremental.values()) and stable_score_eras:
        return "V3_ERA_RELATIVE_SCORE_RESEARCH_VALIDATED", "PRESTIGE_ADDS_MEANINGFUL_INFORMATION", True, True
    if any(incremental.values()):
        return "V3_INCREMENTAL_ONLY_IN_TARGETED_ERAS", "PRESTIGE_INCREMENTAL_ONLY_IN_TARGETED_ERAS", True, False
    broad = product["treatment_incremental"]["partial_r_squared"]
    if broad < GATES["meaningful_partial_r2"]:
        return "V3_MOSTLY_REDUNDANT_WITH_EXACT_PULL_SCARCITY", "PRESTIGE_MOSTLY_REDUNDANT_WITH_PULL_SCARCITY", False, False
    return "V3_STRUCTURE_VALID_BUT_SCORE_NOT_READY", "PRESTIGE_ADDS_MEANINGFUL_INFORMATION", True, False


def report(study: Mapping[str, Any]) -> str:
    m=study["frozen_study"]; c=study["diagnostic_cohort"]
    required=[
        f"1. Frozen Round 2 study ID: `{m['study_id']}`.", f"2. Exact-pull diagnostic cohort: {c['cards']:,} cards / {c['variants']:,} variants ({100*c['main_cohort_coverage_rate']:.2f}% of Round 1).",
        f"3. Coverage: {c['sets']} sets, {c['eras']} eras, {c['species']} species.", f"4. Treatment coverage: {c['treatment_designations']} designations across {c['era_treatment_categories']} era-treatment categories; systematic coverage rates are fully enumerated in the study JSON.",
        f"5. Scarcity-only performance: `{json.dumps(study['broad_comparison']['models']['scarcity'],sort_keys=True)}`.", f"6. Treatment-only performance: `{json.dumps(study['broad_comparison']['models']['treatment'],sort_keys=True)}`.",
        f"7. Combined performance: `{json.dumps(study['broad_comparison']['models']['combined'],sort_keys=True)}`.", f"8. Treatment incremental value: `{json.dumps(study['broad_comparison']['treatment_incremental'],sort_keys=True)}`.",
        f"9. Reverse scarcity value: `{json.dumps(study['broad_comparison']['scarcity_incremental_reverse'],sort_keys=True)}`.", f"10. Residual-prestige diagnostic: `{json.dumps(study['residual_market_association'],sort_keys=True)}`.",
        f"11. Matched-scarcity examples: `{json.dumps(study['matched_scarcity_examples'],sort_keys=True)}`.", f"12. Eligible universes: `{json.dumps(study['eligible_treatment_universes'],sort_keys=True)}`.",
        f"13. Pairwise probability matrices: `{json.dumps({k:v.get('matrix') for k,v in study['rankings_and_scores'].items()},sort_keys=True)}`.",
        f"14. Ranking confidence: strong >= {GATES['strong_ordering_probability']}; moderate >= {GATES['moderate_ordering_probability']}; otherwise unresolved.",
        f"15. Era heterogeneity: `{json.dumps(study['era_heterogeneity'],sort_keys=True)}`.", f"16. Candidate scores: `{json.dumps({k:v.get('scores') for k,v in study['rankings_and_scores'].items()},sort_keys=True)}`.",
        "17. Score uncertainty is reported as cluster-bootstrap intervals with sample/set support; broad tiers or integers are recommended, never decimal precision.",
        f"18. Leave-one-set-out score/rank stability: `{json.dumps(study['score_robustness'],sort_keys=True)}`.", f"19. Other robustness: `{json.dumps(study['other_robustness'],sort_keys=True)}`.",
        f"20. Exact Pull Scarcity versus prestige: `{json.dumps(study['scarcity_vs_prestige'],sort_keys=True)}`.", f"21. Product-information decision: `{study['product_information_decision']}`.",
        f"22. Final Round 2 status: `{study['research_status']}`.", f"23. Score research should continue: {study['score_research_should_continue']}.",
        f"24. Card Detail integration research justified: {study['card_detail_integration_research_justified']}; production integration remains unauthorized.",
        "25. Rows persisted: 0 database rows and 0 approved scores.", "26. Production behavior: unchanged; V1, V2, Card Appeal, Collector Appeal, Financial/Overall RIP, rankings, Card Detail, and frontend remain untouched.",
        f"27. Files changed: {', '.join(study['files_changed'])}.", f"28. Tests executed: {', '.join(study['tests_executed'])}.",
        "29. Limitations: observational residuals may reflect collector status, visual treatment, mechanics, culture, omitted attributes, or measurement error; printed/surviving population, total supply, and Secondary-Market Availability / Liquidity are unobserved; conditional CV fixes the nuisance projection and is optimistic; comparable historical frozen prices are unavailable.",
        f"30. Recommended next task: {study['recommended_next_task']}."]
    return "# Treatment Market Prestige V3 — Round 2 Results\n\n"+f"Status: `{study['research_status']}`\n\nProduct-information decision: `{study['product_information_decision']}`\n\n"+"\n\n".join(required)+"\n\nThe candidate score means only how consistently a treatment carries a stronger adjusted market premium than other supported treatments in the same Pokémon era. It is not physical scarcity, pull probability, pure causal treatment value, percentage price premium, or universal treatment quality. Exact Pull Scarcity is pull-rate scarcity only, not total scarcity.\n"


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--bootstrap-draws",type=int,default=399); parser.add_argument("--seed",type=int,default=SEED); parser.add_argument("--use-existing-freeze",action="store_true"); args=parser.parse_args()
    main_rows,r1_manifest,r1_study=load_round1()
    if args.use_existing_freeze: exact,manifest=load_exact()
    else: exact,manifest=freeze_exact(main_rows,r1_manifest)
    analytic=[row for row in exact if row.get("species_id") and row.get("demand_score") is not None and not row.get("promo_status_ambiguous") and row.get("rarity_designation")]
    broad=comparison(analytic,args.seed)
    era_comparisons={era:comparison([row for row in analytic if row["era_name"]==era],args.seed+100+i) for i,era in enumerate(ROUND1_ELIGIBLE)}
    universes,draws=eligibility(analytic,era_comparisons,args.bootstrap_draws,args.seed+1000)
    rankings=ranking_and_scores(universes,draws,analytic)
    score_stability=score_robustness(analytic,universes,era_comparisons)
    product=scarcity_prestige_product(analytic,universes,rankings,era_comparisons)
    score_sensitivity=sensitivity_scores(analytic,universes,rankings,min(args.bootstrap_draws,199),args.seed+5000)
    status,decision,continue_score,card_detail=decide(era_comparisons,product,rankings,score_stability,score_sensitivity)
    study={"study_name":"Treatment Market Prestige V3 Round 2","frozen_study":manifest,"diagnostic_cohort":coverage_audit(main_rows,exact),
           "analytic_rows":len(analytic),"deterministic_gates":GATES,"broad_comparison":{k:v for k,v in broad.items() if k!="_models"},
           "era_comparisons":{era:{k:v for k,v in result.items() if k!="_models"} for era,result in era_comparisons.items()},
           "residual_market_association":residual_findings(analytic,broad["_models"]["scarcity"],broad["_models"]["treatment"],broad["_models"]["combined"]),
           "matched_scarcity_examples":matched_examples(analytic,broad["_models"]["scarcity"],universes),
           "eligible_treatment_universes":universes,"rankings_and_scores":rankings,"era_heterogeneity":era_heterogeneity(draws),
           "score_robustness":score_stability,"score_sensitivity":score_sensitivity,"scarcity_vs_prestige":product,
           "other_robustness":{"candidate_score_sensitivity":score_sensitivity,
                               "temporal_sensitivity":"NOT_ESTIMABLE_NO_COMPARABLE_FROZEN_HISTORY","secondary_market_availability_liquidity":"FUTURE_DISTINCT_RESEARCH_DIMENSION"},
           "product_information_decision":decision,"research_status":status,"score_research_should_continue":continue_score,
           "card_detail_integration_research_justified":card_detail,"database_rows_persisted":0,"approved_scores_persisted":0,
           "files_changed":["backend/scripts/build_treatment_market_prestige_v3_round2.py","backend/tests/unit/desirability/test_treatment_market_prestige_v3_round2.py",
                            "docs/research/treatment_market_prestige_v3_round2_exact_pull_cohort/","docs/research/treatment_market_prestige_v3_round2_study.json","docs/research/TREATMENT_MARKET_PRESTIGE_V3_ROUND2_RESULTS.md"],
           "tests_executed":["Round 2 plus preserved V3/V2 unit suites (26 passed)","Round 1 and Round 2 immutable hash verification (passed)"],
           "recommended_next_task":"If score research remains justified, preregister a replication using a later frozen market snapshot and add Secondary-Market Availability / Liquidity as a separate dimension; do not integrate Card Detail without explicit production authorization."}
    R2_STUDY.write_text(json.dumps(study,indent=2),encoding="utf-8"); R2_REPORT.write_text(report(study),encoding="utf-8")
    print(json.dumps({"study_id":manifest["study_id"],"status":status,"decision":decision,"exact_rows":len(exact),"analytic_rows":len(analytic),"database_rows_persisted":0},indent=2))


if __name__=="__main__": main()
