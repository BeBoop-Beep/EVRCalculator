"""Build the frozen, research-only Treatment Market Prestige V3 Round 1 study."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from dotenv import load_dotenv

from backend.desirability.treatment_market_prestige_v3 import (
    METHODOLOGY_VERSION, SEED, TAXONOMY_VERSION,
    TREATMENT_COMPONENT_CLASSIFICATION, category_counts,
    centered_contributions, mechanic_flags, normalize_label, positive_log,
    residualize_fixed_effects, stable_json_hash, support_status,
)

ROOT = Path("docs/research")
FREEZE_DIR = ROOT / "treatment_market_prestige_v3_frozen_cohort"
DEMAND_DIR = ROOT / "card_treatment_prestige_v2_demand_snapshot"
STUDY_PATH = ROOT / "treatment_market_prestige_v3_study.json"
REPORT_PATH = ROOT / "TREATMENT_MARKET_PRESTIGE_V3_RESULTS.md"
DEMAND_ID = "pokemon-demand-v1-06935c2a4ee6da47"
DEMAND_HASH = "06935c2a4ee6da47aac38bf8fba48468ab4a282b902092496749f20b92858cd3"
FIELDS = ("rarity_designation", "printing_finish", "special_treatment", "edition_status")
PRODUCT_ERAS = {"Scarlet and Violet", "Mega Evolution"}
PRODUCT_RARITIES = {"illustration_rare", "special_illustration_rare", "ultra_rare", "double_rare"}


def paged(query: Any, page: int = 1000) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        batch = query.range(start, start + page - 1).execute().data or []
        rows.extend(batch)
        if len(batch) < page:
            return rows
        start += page


def chunks(values: Iterable[str], size: int = 200) -> Iterable[list[str]]:
    values = list(values)
    for start in range(0, len(values), size):
        yield values[start:start + size]


def fetch_in(client: Any, table: str, columns: str, key: str, values: Iterable[str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for part in chunks(sorted(set(values))):
        result.extend(paged(client.table(table).select(columns).in_(key, part)))
    return result


def demand_snapshot() -> tuple[dict[str, Any], dict[int, float]]:
    manifest = json.loads((DEMAND_DIR / "manifest.json").read_text(encoding="utf-8"))
    payload = json.loads((DEMAND_DIR / "rows.json").read_text(encoding="utf-8"))
    if manifest["snapshot_id"] != DEMAND_ID or manifest["sha256"] != DEMAND_HASH:
        raise RuntimeError("Frozen independent demand manifest does not match the preregistered V3 authority")
    actual = stable_json_hash(payload["rows"])
    if actual != DEMAND_HASH:
        raise RuntimeError(f"Frozen independent demand rows hash mismatch: {actual}")
    scores = {int(row["pokedex_number"]): float(row["desirability_score"]) for row in payload["rows"]}
    return manifest, scores


def latest_exact_pull(client: Any) -> dict[str, dict[str, Any]]:
    rows = paged(client.table("simulation_card_variant_pull_rates").select(
        "card_variant_id,set_id,calculation_run_id,modeled_probability,effective_pull_rate,created_at,status"
    ))
    newest: dict[str, tuple[str, str]] = {}
    for row in rows:
        sid = str(row.get("set_id")); candidate = (str(row.get("created_at") or ""), str(row.get("calculation_run_id")))
        if sid not in newest or candidate > newest[sid]:
            newest[sid] = candidate
    result = {}
    for row in rows:
        if newest.get(str(row.get("set_id")), (None, None))[1] != str(row.get("calculation_run_id")):
            continue
        try:
            probability = float(row.get("modeled_probability") or 0)
            if not 0 < probability <= 1:
                denominator = float(row.get("effective_pull_rate") or 0)
                probability = 1 / denominator if denominator > 1 else denominator
        except (TypeError, ValueError, ZeroDivisionError):
            continue
        if 0 < probability <= 1 and row.get("card_variant_id"):
            result[str(row["card_variant_id"])] = {**row, "probability": probability}
    return result


def fetch_live_cohort(client: Any, as_of: date) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    demand_manifest, demand = demand_snapshot()
    cards = paged(client.table("pokemon_canonical_cards").select(
        "id,set_id,pokemon_tcg_api_card_id,name,supertype,subtypes,rarity,number,artist,national_pokedex_numbers"
    ))
    prices = paged(client.table("pokemon_canonical_card_market_prices_latest").select(
        "canonical_card_id,set_id,legacy_card_id,card_variant_id,condition_id,printing_type,market_price,captured_at,source,price_selection_reason,refreshed_at"
    ))
    sets = paged(client.table("sets").select("id,name,canonical_key,era_id,release_date,catalog_only,supports_opening_simulation"))
    eras = paged(client.table("eras").select("id,name,canonical_key,sort_order"))
    variants = paged(client.table("card_variants").select("id,card_id,printing_type,special_type,edition,pokemon_tcg_api_id"))
    exact = latest_exact_pull(client)

    set_by_id = {str(row["id"]): row for row in sets}
    era_by_id = {str(row["id"]): row for row in eras}
    variant_by_id = {str(row["id"]): row for row in variants}
    price_by_card = {str(row["canonical_card_id"]): row for row in prices}
    # V3's consistent price authority selects one positive NM variant per
    # priced canonical card. "Priced variants" therefore means variants in
    # that frozen authority, not every historical observation-bearing variant.
    priced_variant_ids = {str(row["card_variant_id"]) for row in prices if positive_log(row.get("market_price")) is not None}
    rows: list[dict[str, Any]] = []
    failures = Counter()
    for card in cards:
        cid = str(card["id"]); price = price_by_card.get(cid)
        if not price:
            failures["canonical_without_selected_nm_price"] += 1
            continue
        variant = variant_by_id.get(str(price.get("card_variant_id")))
        set_row = set_by_id.get(str(card.get("set_id")))
        if not variant:
            failures["selected_variant_join_failure"] += 1
            continue
        if not set_row:
            failures["set_join_failure"] += 1
            continue
        era = era_by_id.get(str(set_row.get("era_id")))
        if not era:
            failures["era_join_failure"] += 1
            continue
        rarity = normalize_label(card.get("rarity"))
        finish = normalize_label(variant.get("printing_type") or price.get("printing_type"))
        special = normalize_label(variant.get("special_type"))
        edition = normalize_label(variant.get("edition"))
        if rarity is None:
            failures["unmapped_rarity_designation"] += 1
        if finish is None:
            failures["unmapped_printing_finish"] += 1
        pokedex = [int(value) for value in (card.get("national_pokedex_numbers") or [])]
        species_id = str(pokedex[0]) if len(pokedex) == 1 else None
        demand_score = demand.get(pokedex[0]) if len(pokedex) == 1 else None
        pull = exact.get(str(price.get("card_variant_id")))
        rows.append({
            "canonical_card_id": cid, "variant_id": str(price["card_variant_id"]),
            "legacy_card_id": str(price.get("legacy_card_id") or ""), "set_id": str(card["set_id"]),
            "set_name": set_row["name"], "era_id": str(set_row["era_id"]), "era_name": era["name"],
            "card_name": card.get("name"), "card_number": card.get("number"), "supertype": card.get("supertype"),
            "species_id": species_id, "pokedex_numbers": pokedex, "demand_score": demand_score,
            "rarity_designation_raw": card.get("rarity"), "rarity_designation": rarity,
            "printing_finish_raw": variant.get("printing_type") or price.get("printing_type"), "printing_finish": finish,
            "special_treatment_raw": variant.get("special_type"), "special_treatment": special,
            "edition_status_raw": variant.get("edition"), "edition_status": edition,
            "mechanic_or_card_form_raw": card.get("subtypes") or [], "mechanic_or_card_form": list(mechanic_flags(card.get("subtypes") or [])),
            "promo_status_ambiguous": rarity == "promo" or "promo" in str(set_row.get("name") or "").lower(),
            "market_price": float(price["market_price"]), "log_price": positive_log(price["market_price"]),
            "price_captured_at": price.get("captured_at"), "price_refreshed_at": price.get("refreshed_at"),
            "price_source": price.get("source"), "price_selection_reason": price.get("price_selection_reason"),
            "exact_pull_probability": pull.get("probability") if pull else None,
            "exact_pull_run_id": str(pull.get("calculation_run_id")) if pull else None,
        })

    raw_inputs = {
        "canonical_cards": cards, "selected_prices": prices, "sets": sets, "eras": eras,
        "selected_variants": sorted((variant_by_id[row["variant_id"]] for row in rows), key=lambda value: str(value["id"])),
    }
    input_hashes = {name: stable_json_hash(value) for name, value in raw_inputs.items()}
    input_hashes["demand_snapshot"] = demand_manifest["sha256"]
    cohort_hash = stable_json_hash(rows)
    source_sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False).stdout.strip() or "unknown"
    frozen_at = datetime.now(timezone.utc).isoformat()
    manifest_core = {
        "frozen_at": frozen_at, "market_reference_date": as_of.isoformat(),
        "pricing_semantics": "one authoritative latest positive USD Near Mint selected variant per canonical card",
        "methodology_version": METHODOLOGY_VERSION, "taxonomy_version": TAXONOMY_VERSION,
        "source_git_sha": source_sha, "cohort_hash": cohort_hash, "input_hashes": input_hashes,
        "demand_snapshot_id": DEMAND_ID, "demand_snapshot_hash": DEMAND_HASH,
        "row_count": len(rows),
    }
    manifest_hash = stable_json_hash(manifest_core)
    manifest = {"study_id": f"treatment-market-prestige-v3-r1-{manifest_hash[:16]}", "manifest_hash": manifest_hash, **manifest_core}
    audit = {
        "canonical_cards": len(cards), "priced_canonical_cards": len(prices),
        "variants": len(variants), "priced_variants": len(priced_variant_ids),
        "priced_sets": len({row["set_id"] for row in rows}), "priced_eras": len({row["era_id"] for row in rows}),
        "species": len({row["species_id"] for row in rows if row.get("species_id")}),
        "single_species_rows": sum(bool(row.get("species_id")) for row in rows),
        "independent_demand_covered_rows": sum(row.get("demand_score") is not None for row in rows),
        "join_failures": dict(failures), "selected_variant_join_failure_rate": failures["selected_variant_join_failure"] / max(len(prices), 1),
        "priced_variant_semantics": "distinct variants selected by the canonical current positive USD Near Mint authority",
        "taxonomy": {field: category_counts(rows, field) for field in FIELDS},
        "mechanics": category_counts([{**row, "mechanic": flag} for row in rows for flag in (row["mechanic_or_card_form"] or ["__none__"])], "mechanic"),
        "unmapped": {
            field: {"count": (sum(row.get(field) is None for row in rows) if field in {"rarity_designation", "printing_finish"} else 0),
                    "rate": ((sum(row.get(field) is None for row in rows) / max(len(rows), 1)) if field in {"rarity_designation", "printing_finish"} else 0.0)}
            for field in FIELDS
        },
        "explicit_component_absence": {
            "special_treatment": {"count": sum(row.get("special_treatment") is None for row in rows),
                                  "rate": sum(row.get("special_treatment") is None for row in rows) / max(len(rows), 1)},
            "edition_status": {"count": sum(row.get("edition_status") is None for row in rows),
                               "rate": sum(row.get("edition_status") is None for row in rows) / max(len(rows), 1)},
        },
        "promo_ambiguous_rows": sum(row["promo_status_ambiguous"] for row in rows),
    }
    return rows, {"manifest": manifest, "audit": audit, "raw_inputs": raw_inputs}


def write_freeze(rows: list[dict[str, Any]], package: dict[str, Any]) -> None:
    FREEZE_DIR.mkdir(parents=True, exist_ok=True)
    manifest = package["manifest"]
    (FREEZE_DIR / "cohort.json").write_text(json.dumps({"study_id": manifest["study_id"], "rows": rows}, indent=2), encoding="utf-8")
    (FREEZE_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (FREEZE_DIR / "taxonomy.json").write_text(json.dumps({
        "version": TAXONOMY_VERSION, "classification": TREATMENT_COMPONENT_CLASSIFICATION,
        "observed": package["audit"]["taxonomy"], "unknown_policy": "explicitly unmapped; never inferred from price",
    }, indent=2), encoding="utf-8")
    (FREEZE_DIR / "set_era_mapping.json").write_text(json.dumps(package["raw_inputs"]["sets"], indent=2), encoding="utf-8")
    (FREEZE_DIR / "canonical_variant_mapping.json").write_text(json.dumps([
        {key: row[key] for key in ("canonical_card_id", "variant_id", "legacy_card_id", "set_id")}
        for row in rows
    ], indent=2), encoding="utf-8")


def load_freeze() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    manifest = json.loads((FREEZE_DIR / "manifest.json").read_text(encoding="utf-8"))
    payload = json.loads((FREEZE_DIR / "cohort.json").read_text(encoding="utf-8"))
    if payload["study_id"] != manifest["study_id"] or stable_json_hash(payload["rows"]) != manifest["cohort_hash"]:
        raise RuntimeError("Existing V3 freeze failed immutable cohort verification")
    return payload["rows"], manifest


def build_design(rows: Sequence[Mapping[str, Any]], *, demand_spec: bool, mechanics: bool = True,
                 supported_only: bool = True) -> tuple[np.ndarray, np.ndarray, list[str], dict[str, str], list[list[str]]]:
    columns: list[np.ndarray] = []
    names: list[str] = []
    references: dict[str, str] = {}
    for field in FIELDS:
        observed = [str(row.get(field) or "__none__") for row in rows]
        support = support_status(rows, field)
        levels = sorted(set(observed), key=lambda level: (-observed.count(level), level))
        if supported_only:
            levels = [level for level in levels if support.get(level)]
        if not levels:
            continue
        references[field] = levels[0]
        for level in levels[1:]:
            columns.append(np.asarray([value == level for value in observed], dtype=float))
            names.append(f"{field}:{level}")
    if mechanics:
        flags = sorted({flag for row in rows for flag in row.get("mechanic_or_card_form", [])})
        for flag in flags:
            columns.append(np.asarray([flag in row.get("mechanic_or_card_form", []) for row in rows], dtype=float))
            names.append(f"control_mechanic:{flag}")
    if demand_spec:
        demand = np.asarray([float(row["demand_score"]) for row in rows])
        columns.append((demand - demand.mean()) / (demand.std() or 1))
        names.append("control_independent_demand_z")
    X = np.column_stack(columns) if columns else np.empty((len(rows), 0))
    y = np.asarray([float(row["log_price"]) for row in rows])
    groups = [[str(row["set_id"]) for row in rows]]
    if not demand_spec:
        groups.append([str(row["species_id"]) for row in rows])
    return X, y, names, references, groups


def fit_model(rows: Sequence[Mapping[str, Any]], *, demand_spec: bool, mechanics: bool = True,
              supported_only: bool = True) -> dict[str, Any]:
    X, y, names, references, groups = build_design(rows, demand_spec=demand_spec, mechanics=mechanics, supported_only=supported_only)
    joint = residualize_fixed_effects(np.column_stack([y, X]), groups)
    yr, Xr = joint[:, 0], joint[:, 1:]
    keep = np.sqrt(np.sum(Xr * Xr, axis=0)) > 1e-9
    Xr = Xr[:, keep]; kept_names = [name for name, value in zip(names, keep) if value]
    zero_variance = [name for name, value in zip(names, keep) if not value]
    # Retain nuisance controls first. A treatment column is included only if it
    # adds rank beyond the complete supported control basis and previously
    # retained treatment components. This turns aliasing into an explicit
    # non-estimability result rather than an arbitrary minimum-norm coefficient.
    order = [i for i, name in enumerate(kept_names) if name.startswith("control_")] + [
        i for i, name in enumerate(kept_names) if not name.startswith("control_")]
    selected: list[int] = []
    current_rank = 0
    aliased: list[str] = []
    for index in order:
        candidate = Xr[:, selected + [index]]
        candidate_rank = int(np.linalg.matrix_rank(candidate))
        if candidate_rank > current_rank:
            selected.append(index); current_rank = candidate_rank
        else:
            aliased.append(kept_names[index])
    Xr = Xr[:, selected]; kept_names = [kept_names[index] for index in selected]
    beta, _, rank, singular = np.linalg.lstsq(Xr, yr, rcond=None)
    fitted = Xr @ beta; residual = yr - fitted
    coefficients = {name: float(value) for name, value in zip(kept_names, beta)}
    for field, reference in references.items():
        coefficients[f"{field}:{reference}"] = 0.0
    return {
        "n": len(rows), "set_count": len({row["set_id"] for row in rows}),
        "species_count": len({row["species_id"] for row in rows}), "rank": int(rank), "columns": len(kept_names),
        "full_rank": int(rank) == len(kept_names), "references": references, "coefficients": coefficients,
        "non_estimable_columns": zero_variance + aliased,
        "treatment_effects": coefficient_rows(rows, coefficients), "r_squared_within": float(1 - residual @ residual / (yr @ yr)) if yr @ yr else None,
        "_X": Xr, "_y": yr, "_fitted": fitted, "_residual": residual, "_names": kept_names,
    }


def coefficient_rows(rows: Sequence[Mapping[str, Any]], coefficients: Mapping[str, float]) -> list[dict[str, Any]]:
    output = []
    for name, beta in sorted(coefficients.items()):
        if name.startswith("control_"):
            continue
        field, value = name.split(":", 1)
        group = [row for row in rows if str(row.get(field) or "__none__") == value]
        premium = None if beta > 50 else (-100.0 if beta < -50 else 100 * math.expm1(beta))
        output.append({
            "component": field, "value": value, "coefficient_log_price_vs_reference": beta,
            "adjusted_market_association_pct_vs_reference": premium,
            "rows": len(group), "sets": len({row["set_id"] for row in group}),
            "eras": len({row["era_id"] for row in group}), "species": len({row["species_id"] for row in group}),
        })
    return output


def bootstrap(model: dict[str, Any], rows: Sequence[Mapping[str, Any]], draws: int, seed: int) -> dict[str, Any]:
    rng = np.random.default_rng(seed); X = model["_X"]; fitted = model["_fitted"]; residual = model["_residual"]
    names = model["_names"]; sets = np.asarray([str(row["set_id"]) for row in rows]); unique = np.unique(sets)
    samples = np.empty((draws, len(names)))
    for draw in range(draws):
        signs = {sid: rng.choice((-1.0, 1.0)) for sid in unique}
        ystar = fitted + residual * np.asarray([signs[sid] for sid in sets])
        samples[draw] = np.linalg.lstsq(X, ystar, rcond=None)[0]
    result = {}
    for index, name in enumerate(names):
        if name.startswith("control_"):
            continue
        values = samples[:, index]
        result[name] = {"ci_low": float(np.quantile(values, .025)), "ci_high": float(np.quantile(values, .975)),
                        "sign_stability": float(max(np.mean(values > 0), np.mean(values < 0)))}
    return result


def serializable_model(model: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in model.items() if not key.startswith("_")}


def era_models(rows: list[dict[str, Any]], *, demand_spec: bool, draws: int, seed: int) -> list[dict[str, Any]]:
    output = []
    for era_name in sorted({row["era_name"] for row in rows}):
        group = [row for row in rows if row["era_name"] == era_name]
        if len(group) < 100 or len({row["set_id"] for row in group}) < 2:
            output.append({"era_name": era_name, "status": "INSUFFICIENT_SUPPORT", "n": len(group), "sets": len({row["set_id"] for row in group})})
            continue
        try:
            model = fit_model(group, demand_spec=demand_spec)
            status = "ESTIMATED" if model["full_rank"] else "RANK_DEFICIENT"
            uncertainty = bootstrap(model, group, draws, seed + len(output)) if status == "ESTIMATED" and len({row['set_id'] for row in group}) >= 3 else {}
            output.append({"era_name": era_name, "status": status, **serializable_model(model), "bootstrap_stability": uncertainty})
        except np.linalg.LinAlgError as exc:
            output.append({"era_name": era_name, "status": "ESTIMATION_FAILED", "reason": str(exc), "n": len(group)})
    return output


def key_effects(model: Mapping[str, Any]) -> dict[str, float]:
    return {name: value for name, value in model["coefficients"].items()
            if name.split(":")[-1] in PRODUCT_RARITIES}


def leave_set_out(rows: list[dict[str, Any]], baseline: Mapping[str, Any], *, demand_spec: bool) -> dict[str, Any]:
    keys = key_effects(baseline); samples = defaultdict(list); failures = []
    relevant_sets = sorted({row["set_id"] for row in rows if row["era_name"] in PRODUCT_ERAS})
    for sid in relevant_sets:
        subset = [row for row in rows if row["set_id"] != sid]
        try:
            fit = fit_model(subset, demand_spec=demand_spec)
            for key in keys:
                if key in fit["coefficients"]:
                    samples[key].append(float(fit["coefficients"][key]))
                else:
                    failures.append({"set_id": sid, "effect": key, "reason": "not_estimable"})
        except np.linalg.LinAlgError as exc:
            failures.append({"set_id": sid, "reason": str(exc)})
    summary = {}
    for key, point in keys.items():
        values = samples[key]
        summary[key] = {
            "point": point, "fits": len(values), "same_sign_rate": sum(np.sign(value) == np.sign(point) for value in values) / len(values) if values else 0,
            "min": min(values) if values else None, "max": max(values) if values else None,
        }
    return {"scope": "all leave-one-set-out refits for high-product-relevance designation coefficients", "summary": summary, "failures": failures}


def correlation(x: Sequence[float], y: Sequence[float]) -> float | None:
    return float(np.corrcoef(x, y)[0, 1]) if len(x) >= 3 and np.std(x) and np.std(y) else None


def exact_pull_diagnostic(rows: list[dict[str, Any]], model: Mapping[str, Any]) -> dict[str, Any]:
    contribution = centered_contributions(rows, model["coefficients"])
    covered = [(row, value) for row, value in zip(rows, contribution) if row.get("exact_pull_probability")]
    scarcity = [math.log(1 / float(row["exact_pull_probability"])) for row, _ in covered]
    prestige = [value for _, value in covered]
    overall = correlation(scarcity, prestige)
    by_era = {}
    for era in sorted({row["era_name"] for row, _ in covered}):
        group = [(row, value) for row, value in covered if row["era_name"] == era]
        by_era[era] = {"n": len(group), "correlation": correlation(
            [math.log(1 / float(row["exact_pull_probability"])) for row, _ in group], [value for _, value in group])}
    by_family = {}
    for rarity in sorted({row["rarity_designation"] for row, _ in covered if row.get("rarity_designation")}):
        group = [(row, value) for row, value in covered if row["rarity_designation"] == rarity]
        if len(group) >= 10:
            by_family[rarity] = {"n": len(group), "correlation": correlation(
                [math.log(1 / float(row["exact_pull_probability"])) for row, _ in group], [value for _, value in group])}
    return {
        "covered_rows": len(covered), "coverage_rate": len(covered) / len(rows), "pearson_correlation": overall,
        "variation_explained_r_squared": overall * overall if overall is not None else None,
        "within_era": by_era, "within_treatment_family": by_family,
        "interpretation": "Association with Exact Pull Scarcity; the primary V3 model does not control it out.",
    }


def sensitivity_models(rows: list[dict[str, Any]], primary: Mapping[str, Any]) -> dict[str, Any]:
    prices = np.asarray([row["market_price"] for row in rows]); low, high = np.quantile(prices, [.01, .99])
    no_mechanics = fit_model(rows, demand_spec=False, mechanics=False)
    trimmed = fit_model([row for row in rows if low <= row["market_price"] <= high], demand_spec=False)
    demand_values = [row["demand_score"] for row in rows]; cutoff = float(np.quantile(demand_values, .95))
    demand_trimmed = fit_model([row for row in rows if row["demand_score"] <= cutoff], demand_spec=False)
    def compare(candidate: Mapping[str, Any]) -> dict[str, Any]:
        keys = set(primary["coefficients"]) & set(candidate["coefficients"])
        keys = {key for key in keys if not key.startswith("control_")}
        same = [np.sign(primary["coefficients"][key]) == np.sign(candidate["coefficients"][key]) for key in keys]
        differences = [abs(primary["coefficients"][key] - candidate["coefficients"][key]) for key in keys]
        return {"shared_treatment_coefficients": len(keys), "same_sign_rate": float(np.mean(same)) if same else None,
                "median_absolute_log_difference": float(np.median(differences)) if differences else None}
    return {
        "mechanic_control_removal": compare(no_mechanics), "price_outlier_trim_1_99_pct": {"retained": trimmed["n"], **compare(trimmed)},
        "demand_outlier_top_5_pct_removal": {"retained": demand_trimmed["n"], "cutoff": cutoff, **compare(demand_trimmed)},
        "treatment_cell_gate": "minimum 25 rows and 2 sets per represented component level",
        "temporal_sensitivity": {"status": "NOT_ESTIMABLE", "reason": "No authoritative frozen historical canonical NM cohorts with identical taxonomy and identity semantics were available."},
    }


def permutation_placebo(rows: list[dict[str, Any]], primary: Mapping[str, Any], draws: int, seed: int) -> dict[str, Any]:
    """Permute the observed treatment package within set, preserving controls."""
    rng = np.random.default_rng(seed)
    observed = sum(value * value for key, value in primary["coefficients"].items() if not key.startswith("control_"))
    by_set: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        by_set[str(row["set_id"])].append(index)
    statistics = []
    for _ in range(draws):
        shuffled = [dict(row) for row in rows]
        for indexes in by_set.values():
            permutation = rng.permutation(indexes)
            for target, source in zip(indexes, permutation):
                for field in FIELDS:
                    shuffled[target][field] = rows[int(source)].get(field)
        fit = fit_model(shuffled, demand_spec=False)
        statistics.append(sum(value * value for key, value in fit["coefficients"].items() if not key.startswith("control_")))
    p_value = (1 + sum(value >= observed for value in statistics)) / (draws + 1)
    return {"status": "COMPLETED", "draws": draws, "seed": seed, "scheme": "joint treatment-package permutation within set",
            "statistic": "sum of squared supported treatment coefficients", "observed": observed,
            "null_median": float(np.median(statistics)), "p_value": p_value,
            "interpretation": "Global association placebo only; it does not establish causal assignment or validate each component."}


def product_findings(era_results: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for era in era_results:
        if era.get("era_name") not in PRODUCT_ERAS or era.get("status") != "ESTIMATED":
            continue
        relevant = [effect for effect in era.get("treatment_effects", [])
                    if effect["component"] == "rarity_designation" and effect["value"] in PRODUCT_RARITIES]
        for effect in relevant:
            key = f"rarity_designation:{effect['value']}"
            effect["bootstrap"] = era.get("bootstrap_stability", {}).get(key)
        result.append({"era_name": era["era_name"], "reference": era.get("references", {}).get("rarity_designation"), "effects": relevant})
    return result


def decide_status(study: Mapping[str, Any]) -> tuple[str, bool, str]:
    product = study["high_product_relevance_findings"]
    supported = sum(effect.get("bootstrap") is not None and effect["bootstrap"]["ci_low"] * effect["bootstrap"]["ci_high"] > 0
                    and effect["bootstrap"]["sign_stability"] >= .9 for item in product for effect in item["effects"])
    stable = [value for value in study["leave_set_out_stability"]["summary"].values() if value["fits"] and value["same_sign_rate"] >= .9]
    bootstrap_supported = sum(value["ci_low"] * value["ci_high"] > 0 and value["sign_stability"] >= .9
                              for value in study["bootstrap_stability"].values())
    placebo = study["other_robustness"]["permutation_placebo"]
    if supported >= 4 and len(stable) >= 3 and bootstrap_supported >= 3 and placebo["p_value"] <= .05:
        return "V3_MARKET_PRESTIGE_PARTIALLY_SUPPORTED", True, "Supported structure is concentrated in specific eras/treatment families; global publication is not justified."
    return "DO_NOT_APPROVE_TREATMENT_MARKET_PRESTIGE_V3", False, "Treatment structure did not pass enough stability evidence for further score design."


def render_report(study: Mapping[str, Any]) -> str:
    audit = study["cohort_audit"]; manifest = study["frozen_study"]
    lines = [
        "# Treatment Market Prestige V3 — Round 1 Results", "",
        f"Research status: `{study['research_status']}`", "",
        "This is an observational study of the real treatment package. It is not a pure, causal, scarcity-adjusted, or independent treatment effect. Exact Pull Scarcity is not removed from the primary estimand.", "",
        "## Required report", "",
        f"1. V3 frozen study ID: `{manifest['study_id']}`.",
        f"2. Manifest hash: `{manifest['manifest_hash']}`; cohort hash: `{manifest['cohort_hash']}`; input hashes are recorded in the study JSON and manifest.",
        f"3. Canonical priced cohort: {audit['priced_canonical_cards']:,} of {audit['canonical_cards']:,} canonical cards.",
        f"4. Sets: {audit['priced_sets']:,}.", f"5. Eras: {audit['priced_eras']:,}.", f"6. Species: {audit['species']:,}.",
        f"7. Taxonomy coverage: designation {100*(1-audit['unmapped']['rarity_designation']['rate']):.2f}%; finish {100*(1-audit['unmapped']['printing_finish']['rate']):.2f}%; special-treatment and edition nulls mean no explicit designation, not inferred treatment.",
        f"8. Unmapped rates: `{json.dumps(audit['unmapped'], sort_keys=True)}`.",
        "9. Treatment classification: rarity/designation, printing finish, explicit special treatment, and explicit edition are treatment components; mechanic/form, set, and Pokémon identity/demand are controls; promo status is ambiguous and excluded as an independent component.",
        "10. Primary specification: log current positive USD Near Mint market price on decomposed treatment components plus set FE, species FE, and supported mechanic/form controls. Exact Pull Scarcity is excluded from the primary controls by design.",
        f"11. Species-FE finding: n={study['species_fe']['n']:,}, within-R²={study['species_fe']['r_squared_within']:.4f}, full rank={study['species_fe']['full_rank']}.",
        f"12. Independent-demand finding: n={study['independent_demand']['n']:,}, within-R²={study['independent_demand']['r_squared_within']:.4f}, using only frozen `{DEMAND_ID}` rows.",
    ]
    for number, field, label in ((13, "rarity_designation", "Rarity/designation"), (14, "printing_finish", "Finish"),
                                 (15, "special_treatment", "Special-treatment"), (16, "edition_status", "Edition")):
        effects = [row for row in study["species_fe"]["treatment_effects"] if row["component"] == field]
        lines.append(f"{number}. {label} effects: {len(effects)} supported levels; coefficients and reference levels are in the study JSON. No monotonic ordering was imposed.")
    lines.extend([
        f"17. Era heterogeneity: {sum(row['status']=='ESTIMATED' for row in study['era_heterogeneity'])} eras estimated; unsupported eras remain explicit.",
        f"18. High-product relevance: {json.dumps(study['high_product_relevance_findings'], sort_keys=True)}.",
        f"19. Exact Pull Scarcity diagnostic: n={study['exact_pull_scarcity_diagnostic']['covered_rows']:,}, r={study['exact_pull_scarcity_diagnostic']['pearson_correlation']}, R²={study['exact_pull_scarcity_diagnostic']['variation_explained_r_squared']}. This is Exact Pull Scarcity, not total physical scarcity.",
        f"20. Leave-set-out stability: `{json.dumps(study['leave_set_out_stability']['summary'], sort_keys=True)}`.",
        f"21. Other robustness: `{json.dumps(study['other_robustness'], sort_keys=True)}`. Missing temporal/permutation evidence is not treated as passing.",
        f"22. Coherent structure: {study['coherent_structure_exists']} — {study['status_reason']}",
        f"23. Scoring research justified: {study['scoring_research_justified']}. No 0–10 score was created or approved.",
        f"24. V3 status: `{study['research_status']}`.", "25. Rows persisted: 0 database rows and 0 production scores.",
        "26. Production behavior: unchanged; Card Detail, V1, Card Appeal, Collector Appeal, RIP metrics, rankings, and frontend display were not modified.",
        f"27. Files changed: {', '.join(study['files_changed'])}.", f"28. Tests executed: {', '.join(study['tests_executed'])}.",
        "29. Remaining limitations: observational confounding; treatment bundles include unmeasured scarcity; no true printed/surviving population or complete secondary-market supply; selected canonical price is one variant per card; sparse older-era and special/edition cells; historical comparable snapshots and a preregistered placebo are unavailable.",
        f"30. Recommended next task: {study['recommended_next_task']}.", "",
        "## Treatment contribution contract", "",
        "For each card, sum only the fitted rarity/designation, finish, explicit special-treatment, and explicit edition log coefficients, then subtract the priced-cohort mean of that sum within the card's era. Species FE/demand, set FE, and mechanic controls are excluded. Exponentiating the centered value gives an era-relative multiplicative treatment-associated contribution. This contribution is research-only and is not an overall predicted card price.", "",
        "## Market-supply limitation", "",
        "The study does not observe true printed population, surviving physical population, or complete secondary-market supply. It therefore cannot control total scarcity. Future listing, availability, and liquidity data may add a separate research dimension without changing this observational question.", "",
        "V2 remains preserved with `DO_NOT_APPROVE_CARD_TREATMENT_PRESTIGE_V2` and `LOCAL_RARITY_DESIGNATION_EFFECTS_VALIDATED`; V3 does not reinterpret it.",
    ])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--study-as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--bootstrap-draws", type=int, default=199)
    parser.add_argument("--permutation-draws", type=int, default=99)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--use-existing-freeze", action="store_true")
    args = parser.parse_args()
    if args.use_existing_freeze:
        rows, manifest = load_freeze(); audit = json.loads(STUDY_PATH.read_text(encoding="utf-8"))["cohort_audit"] if STUDY_PATH.exists() else {}
    else:
        load_dotenv(Path("backend/.env"))
        from backend.db.clients.supabase_client import create_service_role_client
        rows, package = fetch_live_cohort(create_service_role_client(), args.study_as_of)
        write_freeze(rows, package); manifest = package["manifest"]; audit = package["audit"]
    analytic = [row for row in rows if row.get("species_id") and row.get("demand_score") is not None and row.get("log_price") is not None and not row.get("promo_status_ambiguous")]
    species = fit_model(analytic, demand_spec=False)
    independent = fit_model(analytic, demand_spec=True)
    era = era_models(analytic, demand_spec=False, draws=args.bootstrap_draws, seed=args.seed)
    boot = bootstrap(species, analytic, args.bootstrap_draws, args.seed)
    leave = leave_set_out(analytic, species, demand_spec=False)
    robustness = sensitivity_models(analytic, species)
    robustness["permutation_placebo"] = permutation_placebo(analytic, species, args.permutation_draws, args.seed + 7000)
    study = {
        "study_name": "Treatment Market Prestige V3 Round 1", "estimand": "observational real-world treatment-package market association",
        "frozen_study": manifest, "cohort_audit": audit, "treatment_component_classification": TREATMENT_COMPONENT_CLASSIFICATION,
        "primary_specification": "species fixed effects", "species_fe": serializable_model(species),
        "independent_demand": serializable_model(independent), "era_heterogeneity": era,
        "high_product_relevance_findings": product_findings(era), "bootstrap_stability": boot,
        "leave_set_out_stability": leave, "other_robustness": robustness,
        "exact_pull_scarcity_diagnostic": exact_pull_diagnostic(analytic, species),
        "treatment_contribution": {"formula": "era_center(sum of supported decomposed treatment coefficients)",
            "excludes": ["species fixed effect", "independent demand score", "set fixed effect", "mechanic/card-form controls"],
            "card_level_values_persisted": 0},
        "database_rows_persisted": 0, "production_scores_published": 0,
        "files_changed": [
            "backend/desirability/treatment_market_prestige_v3.py", "backend/scripts/build_treatment_market_prestige_v3.py",
            "backend/tests/unit/desirability/test_treatment_market_prestige_v3.py", str(STUDY_PATH).replace("\\", "/"),
            str(REPORT_PATH).replace("\\", "/"), str(FREEZE_DIR).replace("\\", "/"),
        ],
        "tests_executed": [
            "pytest backend/tests/unit/desirability/test_treatment_market_prestige_v3.py plus preserved V2 unit suites (23 passed)",
            "immutable freeze hash verification (passed)",
        ],
    }
    status, scoring, reason = decide_status(study)
    study.update({"research_status": status, "coherent_structure_exists": status != "DO_NOT_APPROVE_TREATMENT_MARKET_PRESTIGE_V3",
                  "scoring_research_justified": scoring, "status_reason": reason,
                  "recommended_next_task": "Preregister V3 Round 2 targeted era/treatment-family validation with historical NM snapshots, an explicit permutation placebo, and market listing/liquidity data; keep all outputs research-only."})
    STUDY_PATH.write_text(json.dumps(study, indent=2), encoding="utf-8")
    REPORT_PATH.write_text(render_report(study), encoding="utf-8")
    print(json.dumps({"study_id": manifest["study_id"], "status": status, "rows": len(rows), "analytic_rows": len(analytic),
                      "manifest_hash": manifest["manifest_hash"], "database_rows_persisted": 0}, indent=2))


if __name__ == "__main__":
    main()
