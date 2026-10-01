"""Treatment Hierarchy V2 modern-pilot estimator (research only).

Consumes the immutable Treatment Panel Recovery V2 artifact and read-only
production authorities.  No provider calls and no database writes.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence

import numpy as np
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.scripts.research_treatment_panel_recovery_v2 import (
    DEFAULT_MANIFEST,
    ROUND23_LADDERS,
    _build_targets,
    load_json,
    resolve_sample,
    stable_hash,
)

MODEL_VERSION = "treatment_hierarchy_v2_modern_pilot_v1"
SIMULATION_MARKET_DATE = "2026-09-29"
BOOTSTRAP_DRAWS = 2000
SEED = 20261001
MAX_SENSITIVITY_DRIFT = 0.50
MAX_INFLUENCE_DRIFT = 0.50
MIN_SIGN_STABILITY = 0.80
MIN_TEMPORAL_SPEARMAN = 0.60

DEFAULT_HISTORY = ROOT / "backend/artifacts/treatment_panel_recovery_v2_input/history.json"
DEFAULT_RECOVERY_SUMMARY = ROOT / "backend/artifacts/treatment_panel_recovery_v2_input/summary.json"
DEFAULT_OUTPUT = ROOT / "backend/artifacts/treatment_hierarchy_v2"


def norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().casefold()).strip("_")


def reference_treatment(family: str) -> str:
    values = family.split(" <> ")
    for preferred in ("common", "uncommon", "double_rare"):
        if preferred in values:
            return preferred
    return values[0]


def _paged(query_factory):
    rows, start = [], 0
    while True:
        part = query_factory().range(start, start + 999).execute().data or []
        rows.extend(part)
        if len(part) < 1000:
            return rows
        start += 1000


def _pull_authority(client: Any, variant_ids: Sequence[str]) -> dict[str, dict[str, Any]]:
    runs = _paged(
        lambda: client.table("calculation_runs")
        .select("id,target_id")
        .eq("market_date", SIMULATION_MARKET_DATE)
        .eq("target_type", "set")
    )
    run_ids = [str(x["id"]) for x in runs]
    rows = []
    for start in range(0, len(variant_ids), 100):
        chunk = list(variant_ids[start:start + 100])
        rows.extend(
            client.table("simulation_card_variant_pull_rates")
            .select(
                "card_variant_id,calculation_run_id,modeled_probability,"
                "effective_pull_rate,status,model_version"
            )
            .in_("card_variant_id", chunk)
            .in_("calculation_run_id", run_ids)
            .execute()
            .data
            or []
        )
    by_variant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("status") == "modeled" and float(row.get("modeled_probability") or 0) > 0:
            by_variant[str(row["card_variant_id"])].append(dict(row))
    out = {}
    for vid in variant_ids:
        matches = by_variant.get(str(vid), [])
        if len(matches) != 1:
            raise RuntimeError(f"exact pull authority count={len(matches)} for variant={vid}")
        if matches[0].get("model_version") != "exact_variant_pull_frequency_v1":
            raise RuntimeError(f"exact pull model drift for variant={vid}")
        out[str(vid)] = matches[0]
    return out


def _collector_controls(client: Any, card_ids: Sequence[str]) -> tuple[str, dict[str, dict[str, Any]]]:
    current = (
        client.table("pokemon_collector_appeal_current")
        .select("model_run_id,model_version")
        .eq("scope", "pokemon")
        .single()
        .execute()
        .data
    )
    if not current:
        raise RuntimeError("current Collector authority unavailable")
    rows = []
    for start in range(0, len(card_ids), 100):
        chunk = list(card_ids[start:start + 100])
        rows.extend(
            client.table("pokemon_card_collector_appeal_scores")
            .select(
                "pokemon_canonical_card_id,subject_baseline_score,"
                "artist_recognition_score,playability_score"
            )
            .eq("model_run_id", current["model_run_id"])
            .in_("pokemon_canonical_card_id", chunk)
            .execute()
            .data
            or []
        )
    out = {str(x["pokemon_canonical_card_id"]): dict(x) for x in rows}
    if set(out) != set(card_ids):
        raise RuntimeError("Collector control coverage is not complete")
    if any(out[cid].get("subject_baseline_score") is None for cid in card_ids):
        raise RuntimeError("Subject control coverage is not complete")
    return str(current["model_version"]), out


def _card_context(
    sample: Sequence[Mapping[str, Any]],
    targets: Sequence[Mapping[str, Any]],
    pull: Mapping[str, Mapping[str, Any]],
    controls: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    membership = {}
    for row in sample:
        for card_id in row["cardIds"]:
            cid = str(card_id)
            if cid in membership:
                raise RuntimeError(f"pilot card appears in multiple frozen identities: {cid}")
            membership[cid] = {
                "identity": str(row["identity"]),
                "set": str(row["set"]),
                "era": str(row["era"]),
                "family": str(row["family"]),
                "tier": int(row["tier"]),
            }
    result = {}
    for target in targets:
        cid = str(target["canonical_card_id"])
        base = membership.get(cid)
        if not base:
            continue
        treatment = norm(target.get("rarity"))
        if treatment not in base["family"].split(" <> "):
            raise RuntimeError(
                f"treatment identity drift card={cid} rarity={treatment} family={base['family']}"
            )
        vid = str(target["selected_variant_id"])
        p = float(pull[vid]["modeled_probability"])
        ctl = controls[cid]
        result[cid] = {
            **base,
            "cardId": cid,
            "cardName": target.get("card_name"),
            "rarity": target.get("rarity"),
            "treatment": treatment,
            "selectedVariantId": vid,
            "modeledProbability": p,
            "scarcity": -math.log(p),
            "subject": float(ctl["subject_baseline_score"]),
            "artist": None if ctl.get("artist_recognition_score") is None else float(ctl["artist_recognition_score"]),
            "playability": None if ctl.get("playability_score") is None else float(ctl["playability_score"]),
        }
    if set(result) != set(membership):
        raise RuntimeError("card context did not cover the frozen pilot")
    return result


def _shared_dates(row: Mapping[str, Any], history: Mapping[str, Sequence[Mapping[str, Any]]]) -> list[str]:
    sets = [{str(x["date"]) for x in history[str(cid)]} for cid in row["cardIds"]]
    return sorted(set.intersection(*sets))


def _fold_dates(
    sample: Sequence[Mapping[str, Any]],
    history: Mapping[str, Sequence[Mapping[str, Any]]],
    fold: str,
) -> dict[str, set[str]]:
    out = {}
    for row in sample:
        shared = _shared_dates(row, history)
        if len(shared) < 90:
            raise RuntimeError(f"recovered panel lost readiness: {row['identity']} dates={len(shared)}")
        mid = len(shared) // 2
        if fold == "full":
            chosen = shared
        elif fold == "early":
            chosen = shared[: mid + 1]
        elif fold == "late":
            chosen = shared[mid + 1 :]
        else:
            raise ValueError(fold)
        out[str(row["identity"])] = set(chosen)
    return out


def _mean_centered_log_prices(
    sample: Sequence[Mapping[str, Any]],
    history: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    fold: str,
) -> dict[str, float]:
    dates_by_identity = _fold_dates(sample, history, fold)
    result = {}
    for row in sample:
        identity = str(row["identity"])
        chosen = dates_by_identity[identity]
        by_card = {
            str(cid): {str(x["date"]): float(x["avg"]) for x in history[str(cid)]}
            for cid in row["cardIds"]
        }
        accum: dict[str, list[float]] = {str(cid): [] for cid in row["cardIds"]}
        for day in sorted(chosen):
            logs = {cid: math.log(values[day]) for cid, values in by_card.items()}
            center = float(np.mean(list(logs.values())))
            for cid, value in logs.items():
                accum[cid].append(value - center)
        for cid, values in accum.items():
            if not values:
                raise RuntimeError(f"no {fold} values for {identity}/{cid}")
            result[cid] = float(np.mean(values))
    return result


def _treatment_columns(card_ctx: Mapping[str, Mapping[str, Any]]) -> list[str]:
    groups: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in card_ctx.values():
        groups[(row["set"], row["family"])].add(row["treatment"])
    cols = []
    for (set_name, family), treatments in sorted(groups.items()):
        ref = reference_treatment(family)
        if ref not in treatments:
            raise RuntimeError(f"reference treatment {ref} missing for {set_name}/{family}")
        for treatment in sorted(treatments - {ref}):
            cols.append(f"{set_name}|{family}|{treatment}")
    return cols


def _raw_feature(card: Mapping[str, Any], column: str) -> float:
    if column == "scarcity":
        return float(card["scarcity"])
    if column == "artist":
        return 0.0 if card["artist"] is None else float(card["artist"]) / 100.0
    if column == "artist_missing":
        return float(card["artist"] is None)
    if column == "playability":
        return 0.0 if card["playability"] is None else float(card["playability"]) / 100.0
    if column == "playability_missing":
        return float(card["playability"] is None)
    set_name, family, treatment = column.split("|", 2)
    return float(
        card["set"] == set_name
        and card["family"] == family
        and card["treatment"] == treatment
    )


def _centered_matrix(
    card_ctx: Mapping[str, Mapping[str, Any]],
    y_by_card: Mapping[str, float],
    columns: Sequence[str],
) -> tuple[list[str], np.ndarray, np.ndarray, list[str]]:
    card_ids = sorted(card_ctx)
    identities = [str(card_ctx[cid]["identity"]) for cid in card_ids]
    X = np.asarray(
        [[_raw_feature(card_ctx[cid], column) for column in columns] for cid in card_ids],
        dtype=float,
    )
    y = np.asarray([float(y_by_card[cid]) for cid in card_ids], dtype=float)
    for identity in sorted(set(identities)):
        idx = [i for i, value in enumerate(identities) if value == identity]
        X[idx, :] -= np.mean(X[idx, :], axis=0)
        y[idx] -= float(np.mean(y[idx]))
    keep = [j for j in range(X.shape[1]) if np.max(np.abs(X[:, j])) > 1e-12]
    X = X[:, keep]
    kept_columns = [columns[j] for j in keep]
    return card_ids, X, y, kept_columns


def _fit(X: np.ndarray, y: np.ndarray, columns: Sequence[str]) -> dict[str, Any]:
    rank = int(np.linalg.matrix_rank(X))
    singular = np.linalg.svd(X, compute_uv=False)
    nonzero = singular[singular > 1e-12]
    condition = float(nonzero.max() / nonzero.min()) if len(nonzero) else math.inf
    if rank != len(columns):
        return {
            "estimable": False,
            "rank": rank,
            "columns": len(columns),
            "conditionNumber": condition,
            "coefficients": {},
        }
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    pred = X @ beta
    residual = y - pred
    return {
        "estimable": True,
        "rank": rank,
        "columns": len(columns),
        "conditionNumber": condition,
        "coefficients": {column: float(value) for column, value in zip(columns, beta)},
        "residualRmse": float(math.sqrt(np.mean(residual ** 2))),
    }


def _model(
    card_ctx: Mapping[str, Mapping[str, Any]],
    y_by_card: Mapping[str, float],
    treatment_cols: Sequence[str],
    *,
    scarcity: bool,
    sensitivity: str | None = None,
) -> dict[str, Any]:
    columns = list(treatment_cols)
    if scarcity:
        columns.append("scarcity")
    if sensitivity == "artist":
        columns += ["artist", "artist_missing"]
    elif sensitivity == "playability":
        columns += ["playability", "playability_missing"]
    card_ids, X, y, kept = _centered_matrix(card_ctx, y_by_card, columns)
    fit = _fit(X, y, kept)
    fit["rowCount"] = len(card_ids)
    fit["requestedColumns"] = columns
    fit["keptColumns"] = kept
    return fit


def _rankdata(values: Sequence[float]) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    order = np.argsort(arr, kind="mergesort")
    ranks = np.empty(len(arr), dtype=float)
    i = 0
    while i < len(arr):
        j = i + 1
        while j < len(arr) and arr[order[j]] == arr[order[i]]:
            j += 1
        rank = (i + j - 1) / 2.0 + 1.0
        ranks[order[i:j]] = rank
        i = j
    return ranks


def spearman(a: Sequence[float], b: Sequence[float]) -> float | None:
    if len(a) < 2 or len(b) != len(a):
        return None
    ra, rb = _rankdata(a), _rankdata(b)
    if np.std(ra) == 0 or np.std(rb) == 0:
        return None
    return float(np.corrcoef(ra, rb)[0, 1])


def _bootstrap(
    card_ctx: Mapping[str, Mapping[str, Any]],
    y_by_card: Mapping[str, float],
    treatment_cols: Sequence[str],
) -> dict[str, Any]:
    card_ids, X, y, columns = _centered_matrix(
        card_ctx, y_by_card, list(treatment_cols) + ["scarcity"]
    )
    if int(np.linalg.matrix_rank(X)) != len(columns):
        return {"estimable": False, "drawsRequested": BOOTSTRAP_DRAWS, "drawsValid": 0}
    identity_by_row = [str(card_ctx[cid]["identity"]) for cid in card_ids]
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for card in card_ctx.values():
        key = (str(card["set"]), str(card["family"]))
        identity = str(card["identity"])
        if identity not in groups[key]:
            groups[key].append(identity)
    rows_by_identity: dict[str, list[int]] = defaultdict(list)
    for idx, identity in enumerate(identity_by_row):
        rows_by_identity[identity].append(idx)

    rng = np.random.default_rng(SEED)
    values: dict[str, list[float]] = {c: [] for c in treatment_cols}
    valid = 0
    for _ in range(BOOTSTRAP_DRAWS):
        idx: list[int] = []
        for identities in groups.values():
            selected = rng.choice(identities, size=len(identities), replace=True)
            for identity in selected:
                idx.extend(rows_by_identity[str(identity)])
        xb, yb = X[idx, :], y[idx]
        if int(np.linalg.matrix_rank(xb)) != len(columns):
            continue
        beta, *_ = np.linalg.lstsq(xb, yb, rcond=None)
        coefs = dict(zip(columns, beta))
        for column in treatment_cols:
            values[column].append(float(coefs[column]))
        valid += 1
    return {
        "estimable": valid > 0,
        "drawsRequested": BOOTSTRAP_DRAWS,
        "drawsValid": valid,
        "coefficients": {
            column: {
                "ci95": [
                    float(np.percentile(vals, 2.5)),
                    float(np.percentile(vals, 97.5)),
                ] if vals else [None, None],
                "signStabilityPositive": float(np.mean(np.asarray(vals) > 0)) if vals else None,
                "signStabilityNegative": float(np.mean(np.asarray(vals) < 0)) if vals else None,
                "stddev": float(np.std(vals)) if vals else None,
            }
            for column, vals in values.items()
        },
    }


def _subset_fit(
    card_ctx: Mapping[str, Mapping[str, Any]],
    y_by_card: Mapping[str, float],
    treatment_cols: Sequence[str],
    excluded_identity: str,
) -> dict[str, Any]:
    subset = {
        cid: row for cid, row in card_ctx.items()
        if str(row["identity"]) != str(excluded_identity)
    }
    y = {cid: y_by_card[cid] for cid in subset}
    return _model(subset, y, treatment_cols, scarcity=True)


def _influence(
    card_ctx: Mapping[str, Mapping[str, Any]],
    y_by_card: Mapping[str, float],
    treatment_cols: Sequence[str],
    point: Mapping[str, float],
) -> dict[str, Any]:
    identities = sorted({str(x["identity"]) for x in card_ctx.values()})
    drift: dict[str, list[dict[str, Any]]] = {c: [] for c in treatment_cols}
    for identity in identities:
        fit = _subset_fit(card_ctx, y_by_card, treatment_cols, identity)
        if not fit.get("estimable"):
            for column in treatment_cols:
                drift[column].append({"identity": identity, "estimable": False, "drift": None})
            continue
        for column in treatment_cols:
            value = fit["coefficients"].get(column)
            drift[column].append({
                "identity": identity,
                "estimable": value is not None,
                "drift": None if value is None else abs(float(value) - float(point[column])),
            })
    return {
        column: {
            "maximumAbsoluteDrift": max(
                (x["drift"] for x in rows if x["drift"] is not None),
                default=None,
            ),
            "nonEstimableLeaveOuts": sum(x["drift"] is None for x in rows),
            "details": rows,
        }
        for column, rows in drift.items()
    }


def _control_invariant(
    card_ctx: Mapping[str, Mapping[str, Any]],
    column: str,
    treatment_column: str,
) -> bool:
    set_name, family, _ = treatment_column.split("|", 2)
    identities = sorted({
        str(row["identity"])
        for row in card_ctx.values()
        if row["set"] == set_name and row["family"] == family
    })
    for identity in identities:
        vals = []
        for row in card_ctx.values():
            if str(row["identity"]) != identity:
                continue
            value = row[column]
            vals.append(("missing",) if value is None else ("value", round(float(value), 12)))
        if len(set(vals)) > 1:
            return False
    return True


def _effect_report(
    treatment_cols: Sequence[str],
    package: Mapping[str, Any],
    pure: Mapping[str, Any],
    early: Mapping[str, Any],
    late: Mapping[str, Any],
    bootstrap: Mapping[str, Any],
    influence: Mapping[str, Any],
    artist: Mapping[str, Any],
    playability: Mapping[str, Any],
    card_ctx: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    out = {}
    for column in treatment_cols:
        p = float(pure["coefficients"][column])
        pkg = float(package["coefficients"][column])
        boot = bootstrap["coefficients"][column]
        sign_stability = (
            boot["signStabilityPositive"] if p > 0 else boot["signStabilityNegative"]
        )
        artist_value = artist.get("coefficients", {}).get(column) if artist.get("estimable") else None
        play_value = playability.get("coefficients", {}).get(column) if playability.get("estimable") else None
        artist_invariant = _control_invariant(card_ctx, "artist", column)
        play_invariant = _control_invariant(card_ctx, "playability", column)
        artist_drift = None if artist_value is None else abs(float(artist_value) - p)
        play_drift = None if play_value is None else abs(float(play_value) - p)
        artist_gate = artist_invariant or (artist_drift is not None and artist_drift <= MAX_SENSITIVITY_DRIFT)
        play_gate = play_invariant or (play_drift is not None and play_drift <= MAX_SENSITIVITY_DRIFT)
        early_value = early["coefficients"].get(column)
        late_value = late["coefficients"].get(column)
        temporal_sign = (
            early_value is not None
            and late_value is not None
            and float(early_value) != 0
            and float(late_value) != 0
            and math.copysign(1, float(early_value)) == math.copysign(1, float(late_value))
        )
        inf = influence[column]
        supported = (
            sign_stability is not None
            and sign_stability >= MIN_SIGN_STABILITY
            and inf["maximumAbsoluteDrift"] is not None
            and inf["maximumAbsoluteDrift"] <= MAX_INFLUENCE_DRIFT
            and inf["nonEstimableLeaveOuts"] == 0
            and temporal_sign
            and artist_gate
            and play_gate
        )
        out[column] = {
            "packageLogEffect": pkg,
            "pureTreatmentLogEffect": p,
            "pureTreatmentMultiplier": math.exp(p),
            "pureTreatmentPctVsReference": (math.exp(p) - 1.0) * 100.0,
            "scarcityAdjustmentLogPoints": pkg - p,
            "bootstrap": boot,
            "bootstrapSignStability": sign_stability,
            "influence": inf,
            "earlyLogEffect": early_value,
            "lateLogEffect": late_value,
            "temporalSameSign": temporal_sign,
            "artistSensitivity": {
                "estimable": artist_value is not None,
                "invariantWithinMatchedIdentities": artist_invariant,
                "logEffect": artist_value,
                "absoluteDrift": artist_drift,
                "passes": artist_gate,
            },
            "playabilitySensitivity": {
                "estimable": play_value is not None,
                "invariantWithinMatchedIdentities": play_invariant,
                "logEffect": play_value,
                "absoluteDrift": play_drift,
                "passes": play_gate,
            },
            "supported": supported,
        }
    return out


def _group_decisions(effect_report: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[tuple[str, Mapping[str, Any]]]] = defaultdict(list)
    for column, result in effect_report.items():
        set_name, family, treatment = column.split("|", 2)
        grouped[(set_name, family)].append((treatment, result))
    return [
        {
            "set": set_name,
            "family": family,
            "effects": [t for t, _ in sorted(items)],
            "passes": all(bool(result["supported"]) for _, result in items),
        }
        for (set_name, family), items in sorted(grouped.items())
    ]


def _era_pool(
    groups: Sequence[Mapping[str, Any]],
    effects: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    passing = {(g["set"], g["family"]) for g in groups if g["passes"]}
    by: dict[tuple[str, str], list[tuple[str, Mapping[str, Any]]]] = defaultdict(list)
    for column, result in effects.items():
        set_name, family, treatment = column.split("|", 2)
        if (set_name, family) in passing:
            by[(family, treatment)].append((set_name, result))
    out = []
    for (family, treatment), rows in sorted(by.items()):
        if len(rows) < 2:
            continue
        direct = np.asarray([float(r["pureTreatmentLogEffect"]) for _, r in rows])
        variances = np.asarray([
            float(r["bootstrap"]["stddev"] or 0) ** 2 for _, r in rows
        ])
        between = float(np.var(direct, ddof=1)) if len(direct) > 1 else 0.0
        tau2 = max(0.0, between - float(np.mean(variances)))
        mean = float(np.mean(direct))
        pooled = []
        for (set_name, result), value, variance in zip(rows, direct, variances):
            weight = tau2 / (tau2 + variance) if (tau2 + variance) > 0 else 0.0
            posterior = float(weight * value + (1.0 - weight) * mean)
            pooled.append({
                "set": set_name,
                "directLogEffect": float(value),
                "measurementVariance": float(variance),
                "directWeight": float(weight),
                "pooledLogEffect": posterior,
                "pooledMultiplier": math.exp(posterior),
            })
        out.append({
            "era": "Scarlet and Violet",
            "family": family,
            "treatment": treatment,
            "setCount": len(rows),
            "eraMeanLogEffect": mean,
            "betweenSetVarianceTau2": tau2,
            "sets": pooled,
        })
    return out


def run(
    client: Any,
    *,
    history_path: Path,
    recovery_summary_path: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    history = load_json(history_path)
    recovery = load_json(recovery_summary_path)
    manifest = load_json(manifest_path)
    if recovery.get("providerCreditsUsed") != 3521:
        raise RuntimeError("recovery artifact provenance drift")
    sample = resolve_sample(manifest, load_json(ROUND23_LADDERS))
    targets, target_meta = _build_targets(client, sample)
    if target_meta["targetBuildFailures"]:
        raise RuntimeError(f"target build drift: {target_meta['targetBuildFailures']}")
    variant_ids = [str(x["selected_variant_id"]) for x in targets]
    pull = _pull_authority(client, variant_ids)
    card_ids = sorted({str(x["canonical_card_id"]) for x in targets})
    collector_version, controls = _collector_controls(client, card_ids)
    card_ctx = _card_context(sample, targets, pull, controls)
    treatment_cols = _treatment_columns(card_ctx)
    if len(treatment_cols) != 10:
        raise RuntimeError(f"expected 10 treatment coefficients, found {len(treatment_cols)}")

    y_full = _mean_centered_log_prices(sample, history, fold="full")
    y_early = _mean_centered_log_prices(sample, history, fold="early")
    y_late = _mean_centered_log_prices(sample, history, fold="late")

    package = _model(card_ctx, y_full, treatment_cols, scarcity=False)
    pure = _model(card_ctx, y_full, treatment_cols, scarcity=True)
    early = _model(card_ctx, y_early, treatment_cols, scarcity=True)
    late = _model(card_ctx, y_late, treatment_cols, scarcity=True)
    if not package["estimable"]:
        raise RuntimeError("TREATMENT_PACKAGE_RANK_DEFICIENT")
    if not pure["estimable"]:
        return {
            "decisionToken": "TREATMENT_HIERARCHY_V2_SCARCITY_CONFOUNDED",
            "package": package,
            "pure": pure,
            "databaseWrites": 0,
            "providerCalls": 0,
        }
    if not early["estimable"] or not late["estimable"]:
        raise RuntimeError("temporal fold estimator rank deficient")

    artist = _model(card_ctx, y_full, treatment_cols, scarcity=True, sensitivity="artist")
    playability = _model(
        card_ctx, y_full, treatment_cols, scarcity=True, sensitivity="playability"
    )
    bootstrap = _bootstrap(card_ctx, y_full, treatment_cols)
    if not bootstrap.get("estimable"):
        raise RuntimeError("bootstrap could not estimate PURE_TREATMENT")
    influence = _influence(
        card_ctx, y_full, treatment_cols, pure["coefficients"]
    )
    effects = _effect_report(
        treatment_cols,
        package,
        pure,
        early,
        late,
        bootstrap,
        influence,
        artist,
        playability,
        card_ctx,
    )
    early_values = [float(early["coefficients"][c]) for c in treatment_cols]
    late_values = [float(late["coefficients"][c]) for c in treatment_cols]
    temporal_rho = spearman(early_values, late_values)
    groups = _group_decisions(effects)
    passing_groups = [g for g in groups if g["passes"]]
    era_pools = _era_pool(groups, effects) if temporal_rho is not None and temporal_rho >= MIN_TEMPORAL_SPEARMAN else []

    family_sets: dict[str, set[str]] = defaultdict(set)
    for group in passing_groups:
        family_sets[group["family"]].add(group["set"])
    era_supported_families = {
        family: sorted(sets)
        for family, sets in family_sets.items()
        if len(sets) >= 2
    }

    if temporal_rho is None or temporal_rho < MIN_TEMPORAL_SPEARMAN:
        decision = "TREATMENT_HIERARCHY_V2_DIAGNOSTIC_ONLY"
    elif era_supported_families:
        decision = "TREATMENT_HIERARCHY_V2_SV_ERA_SUPPORTED"
    elif passing_groups:
        decision = "TREATMENT_HIERARCHY_V2_SET_LOCAL_ONLY"
    else:
        decision = "TREATMENT_HIERARCHY_V2_DIAGNOSTIC_ONLY"

    return {
        "modelVersion": MODEL_VERSION,
        "decisionToken": decision,
        "collectorControlVersion": collector_version,
        "recoveryProvenance": {
            "workflowRunId": 36913676646,
            "artifactId": 11190000187,
            "artifactDigest": "sha256:e1cafb46732bf40932c8095b8f8266b05d256d2fdaa5761afc0fe1078be86233",
            "historyFingerprint": stable_hash(history),
        },
        "counts": {
            "cards": len(card_ctx),
            "identities": len({x["identity"] for x in card_ctx.values()}),
            "sets": len({x["set"] for x in card_ctx.values()}),
            "treatmentCoefficients": len(treatment_cols),
            "artistCoveredCards": sum(x["artist"] is not None for x in card_ctx.values()),
            "playabilityCoveredCards": sum(x["playability"] is not None for x in card_ctx.values()),
        },
        "package": package,
        "pure": pure,
        "artistSensitivity": artist,
        "playabilitySensitivity": playability,
        "bootstrap": bootstrap,
        "temporal": {
            "early": early,
            "late": late,
            "coefficientSpearman": temporal_rho,
            "minimumRequiredSpearman": MIN_TEMPORAL_SPEARMAN,
            "passesGlobalGate": temporal_rho is not None and temporal_rho >= MIN_TEMPORAL_SPEARMAN,
        },
        "effects": effects,
        "setFamilyDecisions": groups,
        "passingSetFamilyCount": len(passing_groups),
        "eraSupportedFamilies": era_supported_families,
        "eraPools": era_pools,
        "crossEraStatus": "NOT_REACHED_SINGLE_AUTHORIZED_ERA",
        "sourcePolicy": {
            "priceUsedAsOutcomeOnly": True,
            "currentPriceInputToFutureTreatmentScore": False,
            "exactPullScarcityControlled": True,
            "subjectControlledByMatchedIdentityDateEffects": True,
        },
        "databaseWrites": 0,
        "providerCalls": 0,
        "collectorMutation": False,
        "overallRipMutation": False,
    }


def render(report: Mapping[str, Any]) -> str:
    lines = [
        "# Treatment Hierarchy V2 — Modern Pilot Results",
        "",
        f"Decision: `{report['decisionToken']}`",
        "",
        "## Core results",
        "",
        f"- Cards: {report['counts']['cards']}",
        f"- Matched identities: {report['counts']['identities']}",
        f"- Sets: {report['counts']['sets']}",
        f"- Set-specific treatment coefficients: {report['counts']['treatmentCoefficients']}",
        f"- PURE_TREATMENT condition number: {report['pure'].get('conditionNumber')}",
        f"- Temporal early/late coefficient Spearman: {report['temporal']['coefficientSpearman']}",
        f"- Passing Set/family groups: {report['passingSetFamilyCount']}",
        f"- Era-supported families: {json.dumps(report['eraSupportedFamilies'], sort_keys=True)}",
        "",
        "## Set-specific effects",
        "",
        "| Set / family / treatment | Package log | Pure log | Pure % vs ref | Scarcity removed | Sign stability | Max influence | Early/Late same sign | Supported |",
        "|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for column, row in sorted(report["effects"].items()):
        lines.append(
            f"| {column} | {row['packageLogEffect']:.4f} | "
            f"{row['pureTreatmentLogEffect']:.4f} | "
            f"{row['pureTreatmentPctVsReference']:.1f}% | "
            f"{row['scarcityAdjustmentLogPoints']:.4f} | "
            f"{row['bootstrapSignStability']:.3f} | "
            f"{row['influence']['maximumAbsoluteDrift'] if row['influence']['maximumAbsoluteDrift'] is not None else 'NA'} | "
            f"{row['temporalSameSign']} | {row['supported']} |"
        )
    lines += [
        "",
        "## Interpretation boundary",
        "",
        "Price is the research outcome used to learn a frozen treatment association. "
        "No live/current price is authorized as an input to a future Treatment score.",
        "",
        "This pilot authorizes no production change. Cross-era Treatment remains not reached.",
        "",
        "## Safety",
        "",
        "- Production database writes: 0",
        "- Provider calls in this fit: 0",
        "- Collector Appeal mutation: none",
        "- Overall RIP mutation: none",
    ]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", type=Path, default=DEFAULT_HISTORY)
    parser.add_argument("--recovery-summary", type=Path, default=DEFAULT_RECOVERY_SUMMARY)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    load_dotenv(ROOT / "backend/.env", override=False)
    from backend.db.clients.supabase_client import create_service_role_client

    report = run(
        create_service_role_client(),
        history_path=args.history,
        recovery_summary_path=args.recovery_summary,
        manifest_path=args.manifest,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "results.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "FINAL_REPORT.md").write_text(render(report), encoding="utf-8")
    (args.output_dir / "decision.json").write_text(
        json.dumps(
            {
                "decisionToken": report["decisionToken"],
                "passingSetFamilyCount": report.get("passingSetFamilyCount", 0),
                "eraSupportedFamilies": report.get("eraSupportedFamilies", {}),
                "crossEraStatus": report.get("crossEraStatus"),
                "databaseWrites": report.get("databaseWrites", 0),
                "providerCalls": report.get("providerCalls", 0),
                "collectorMutation": report.get("collectorMutation", False),
                "overallRipMutation": report.get("overallRipMutation", False),
            },
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "decisionToken": report["decisionToken"],
        "counts": report.get("counts"),
        "temporalSpearman": report.get("temporal", {}).get("coefficientSpearman"),
        "passingSetFamilyCount": report.get("passingSetFamilyCount"),
        "eraSupportedFamilies": report.get("eraSupportedFamilies"),
        "databaseWrites": report.get("databaseWrites"),
        "providerCalls": report.get("providerCalls"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
