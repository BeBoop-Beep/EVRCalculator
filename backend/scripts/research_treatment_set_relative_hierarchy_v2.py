"""Set-relative Treatment hierarchy V2 on the frozen broad independent expansion.

Research only. No production writes.

Frozen design:
  y = theta_set(high) - theta_set(low)
      + beta_scarcity * log(p_low / p_high)
      + beta_artist * artist_delta/100

Double Rare is the reference inside each included Set. Ultra Rare and SIR receive
Set-specific latent log levels. Scarcity and Artist coefficients are shared.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MODEL_RUN_ID = "e282f26e-2136-4105-b0a3-f0974c4d9d70"
MODEL_VERSION = "pokemon_collector_appeal_v7_expanded_price_blind_v1"
MODEL_AS_OF_DATE = "2026-09-11"
SEED = 20261002
BOOTSTRAP_DRAWS = 2000
MIN_VALID_BOOTSTRAP_DRAWS = 1900

DOUBLE = "Double Rare"
ULTRA = "Ultra Rare"
SIR = "Special Illustration Rare"

PRIOR_PANEL_FINGERPRINT = "173e42718a23b90294876d0ee576e484f9392bfdfe60b97df26fb13b0add93d8"
FRESH_TARGET_FINGERPRINT = "28b344ca8ea95ba8fbc9fa947cdb28a1a3d83408482572084ee83e1cf992563d"

PRIOR_EXPECTED_BY_SET = {
    "Perfect Order": 4,
    "Phantasmal Flames": 4,
    "Obsidian Flames": 4,
    "Scarlet and Violet 151": 4,
    "Twilight Masquerade": 4,
}
FRESH_EXPECTED_BY_SET = {
    "Pitch Black": 4,
    "Destined Rivals": 8,
    "Surging Sparks": 7,
    "Black Bolt": 6,
    "Journey Together": 6,
    "Scarlet and Violet Base Set": 6,
    "Temporal Forces": 6,
    "White Flare": 6,
    "Shrouded Fable": 4,
    "Stellar Crown": 3,
}
FROZEN_SET_ORDER = [
    "Perfect Order",
    "Phantasmal Flames",
    "Pitch Black",
    "Obsidian Flames",
    "Scarlet and Violet 151",
    "Twilight Masquerade",
    "Destined Rivals",
    "Surging Sparks",
    "Black Bolt",
    "Journey Together",
    "Scarlet and Violet Base Set",
    "Temporal Forces",
    "White Flare",
    "Shrouded Fable",
    "Stellar Crown",
]
EXPECTED_ERA_BY_SET = {
    "Perfect Order": "Mega Evolution",
    "Phantasmal Flames": "Mega Evolution",
    "Pitch Black": "Mega Evolution",
    "Obsidian Flames": "Scarlet and Violet",
    "Scarlet and Violet 151": "Scarlet and Violet",
    "Twilight Masquerade": "Scarlet and Violet",
    "Destined Rivals": "Scarlet and Violet",
    "Surging Sparks": "Scarlet and Violet",
    "Black Bolt": "Scarlet and Violet",
    "Journey Together": "Scarlet and Violet",
    "Scarlet and Violet Base Set": "Scarlet and Violet",
    "Temporal Forces": "Scarlet and Violet",
    "White Flare": "Scarlet and Violet",
    "Shrouded Fable": "Scarlet and Violet",
    "Stellar Crown": "Scarlet and Violet",
}


def stable_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _chunks(values: list[str], size: int = 100):
    for start in range(0, len(values), size):
        yield values[start:start + size]


def load_controls(db: Any, card_ids: list[str]) -> dict[str, dict[str, float]]:
    rows: list[dict[str, Any]] = []
    for chunk in _chunks(card_ids):
        rows.extend(
            db.table("pokemon_card_collector_appeal_scores")
            .select(
                "pokemon_canonical_card_id,subject_baseline_score,"
                "artist_recognition_score,playability_score,"
                "collector_card_appeal_score,price_input_excluded,"
                "treatment_input_excluded"
            )
            .eq("model_run_id", MODEL_RUN_ID)
            .in_("pokemon_canonical_card_id", chunk)
            .execute().data
            or []
        )
    if len(rows) != len(card_ids):
        raise RuntimeError(
            f"frozen control coverage mismatch expected={len(card_ids)} got={len(rows)}"
        )
    out: dict[str, dict[str, float]] = {}
    for row in rows:
        cid = str(row["pokemon_canonical_card_id"])
        if row.get("price_input_excluded") is not True:
            raise RuntimeError(f"control row uses price input card={cid}")
        if row.get("treatment_input_excluded") is not True:
            raise RuntimeError(f"control row uses Treatment input card={cid}")
        out[cid] = {
            "subject": float(row["subject_baseline_score"]),
            "artist": 0.0 if row.get("artist_recognition_score") is None else float(row["artist_recognition_score"]),
            "playability": 0.0 if row.get("playability_score") is None else float(row["playability_score"]),
            "collector": float(row["collector_card_appeal_score"]),
        }
    return out


def _ready_keys(panel: dict[str, Any]) -> set[tuple[str, str]]:
    return {
        (str(row["set_name"]), str(row["subject_key"]))
        for row in panel.get("triad_results", [])
        if row.get("ready")
    }


def _target_triads(panel: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in (panel.get("target") or {}).get("triads", [])]


def _ready_triads(panel: dict[str, Any]) -> list[dict[str, Any]]:
    keys = _ready_keys(panel)
    return [
        row for row in _target_triads(panel)
        if (str(row["set_name"]), str(row["subject_key"])) in keys
    ]


def control_eligible_fresh_triads(
    panel: dict[str, Any],
    controls: dict[str, dict[str, float]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Apply the preregistered exact Subject/Playability match rule to ready fresh triads.

    This is an eligibility gate, not a fitted outcome: no price direction or
    magnitude is consulted. Artist remains an allowed nuisance delta.
    """
    eligible: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    for triad in _ready_triads(panel):
        by_rarity = {str(card["rarity"]): card for card in triad["cards"]}
        if set(by_rarity) != {DOUBLE, ULTRA, SIR}:
            raise RuntimeError(
                f"unexpected fresh triad treatments {triad['set_name']} {triad['subject_key']}"
            )
        card_ids = [str(by_rarity[rarity]["canonical_card_id"]) for rarity in (DOUBLE, ULTRA, SIR)]
        missing = [cid for cid in card_ids if cid not in controls]
        if missing:
            raise RuntimeError(
                f"fresh control coverage mismatch {triad['set_name']} "
                f"{triad['subject_key']} missing={missing}"
            )

        subject_values = [controls[cid]["subject"] for cid in card_ids]
        playability_values = [controls[cid]["playability"] for cid in card_ids]
        reasons: list[str] = []
        if max(subject_values) - min(subject_values) > 1e-9:
            reasons.append("SUBJECT_CONTROL_MISMATCH")
        if max(playability_values) - min(playability_values) > 1e-9:
            reasons.append("PLAYABILITY_CONTROL_MISMATCH")

        if reasons:
            exclusions.append({
                "set_name": str(triad["set_name"]),
                "era_name": str(triad["era_name"]),
                "subject_key": str(triad["subject_key"]),
                "reasons": reasons,
                "controls_by_treatment": {
                    rarity: {
                        "card_id": str(by_rarity[rarity]["canonical_card_id"]),
                        "subject": controls[str(by_rarity[rarity]["canonical_card_id"])]["subject"],
                        "playability": controls[str(by_rarity[rarity]["canonical_card_id"])]["playability"],
                    }
                    for rarity in (DOUBLE, ULTRA, SIR)
                },
            })
        else:
            eligible.append(triad)
    return eligible, exclusions


def validate_prior_panel(panel: dict[str, Any]) -> list[dict[str, Any]]:
    if panel.get("status") not in {"COMPLETE", "PARTIAL"}:
        raise RuntimeError("prior replication panel status invalid")
    if int(panel.get("production_writes") or 0) != 0:
        raise RuntimeError("prior replication panel reports production writes")
    if str((panel.get("target") or {}).get("fingerprint") or "") != PRIOR_PANEL_FINGERPRINT:
        raise RuntimeError("prior replication panel fingerprint drift")
    if not (panel.get("coverage") or {}).get("coverage_pass"):
        raise RuntimeError("prior replication coverage gate did not pass")

    triads = _ready_triads(panel)
    counts: dict[str, int] = defaultdict(int)
    for triad in triads:
        counts[str(triad["set_name"])] += 1
    if len(triads) != 20 or dict(counts) != PRIOR_EXPECTED_BY_SET:
        raise RuntimeError(f"prior ready-triad cohort drift: count={len(triads)} by_set={dict(counts)}")
    return triads


def fresh_coverage(
    panel: dict[str, Any],
    controls: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    target = panel.get("target") or {}
    if int(panel.get("production_writes") or 0) != 0:
        return {"pass": False, "reason": "production_writes_nonzero"}
    if str(target.get("fingerprint") or "") != FRESH_TARGET_FINGERPRINT:
        return {"pass": False, "reason": "fresh_target_fingerprint_drift"}
    if int(target.get("triad_count") or 0) != 56 or int(target.get("card_count") or 0) != 168:
        return {"pass": False, "reason": "fresh_target_size_drift"}
    if dict(target.get("by_set") or {}) != FRESH_EXPECTED_BY_SET:
        return {"pass": False, "reason": "fresh_target_set_counts_drift"}

    history_ready = _ready_triads(panel)
    if controls is None:
        ready = history_ready
        control_exclusions: list[dict[str, Any]] = []
    else:
        ready, control_exclusions = control_eligible_fresh_triads(panel, controls)

    ready_by_set: dict[str, int] = defaultdict(int)
    for triad in ready:
        ready_by_set[str(triad["set_name"])] += 1

    panels = panel.get("panels") or {}
    fresh_cards_returned = sum(
        bool((panels.get(str(card["canonical_card_id"])) or {}).get("history"))
        for triad in _target_triads(panel)
        for card in triad["cards"]
    )
    qualifying_sv_sets = sum(
        ready_by_set.get(set_name, 0) >= 3
        for set_name in FRESH_EXPECTED_BY_SET
        if EXPECTED_ERA_BY_SET[set_name] == "Scarlet and Violet"
    )
    computed = {
        "history_ready_triads": len(history_ready),
        "ready_triads": len(ready),
        "control_eligible_ready_triads": len(ready),
        "control_exclusions": control_exclusions,
        "ready_by_set": dict(ready_by_set),
        "pitch_black_ready": ready_by_set.get("Pitch Black", 0),
        "qualifying_sv_sets": qualifying_sv_sets,
        "fresh_cards_returned": fresh_cards_returned,
    }
    computed["pass"] = (
        computed["ready_triads"] >= 45
        and computed["pitch_black_ready"] >= 3
        and computed["qualifying_sv_sets"] >= 7
        and computed["fresh_cards_returned"] >= 120
    )
    computed["reason"] = "coverage_gate_passed" if computed["pass"] else "coverage_gate_failed"
    return computed


def _history(panel: dict[str, Any], card_id: str) -> dict[str, float]:
    rows = panel["panels"][card_id]["history"]
    return {str(row["date"]): float(row["price"]) for row in rows}


def _pair_row(
    *,
    panel: dict[str, Any],
    source: str,
    set_name: str,
    era_name: str,
    subject_key: str,
    high: dict[str, Any],
    low: dict[str, Any],
    controls: dict[str, dict[str, float]],
) -> dict[str, Any]:
    high_id = str(high["canonical_card_id"])
    low_id = str(low["canonical_card_id"])
    high_hist = _history(panel, high_id)
    low_hist = _history(panel, low_id)
    shared = sorted(set(high_hist) & set(low_hist))
    if len(shared) < 30:
        raise RuntimeError(f"edge below frozen history gate {set_name} {subject_key}")
    ratios = [math.log(high_hist[day] / low_hist[day]) for day in shared]
    hc = controls[high_id]
    lc = controls[low_id]
    subject_delta = hc["subject"] - lc["subject"]
    playability_delta = hc["playability"] - lc["playability"]
    if abs(subject_delta) > 1e-9:
        raise RuntimeError(f"subject control mismatch {set_name} {subject_key}")
    if abs(playability_delta) > 1e-9:
        raise RuntimeError(f"playability control mismatch {set_name} {subject_key}")
    cut = len(shared) // 2
    if cut <= 0 or cut >= len(shared):
        raise RuntimeError(f"temporal split unavailable {set_name} {subject_key}")
    return {
        "cluster_key": f"{source}|{set_name}|{subject_key}",
        "source": source,
        "set_name": set_name,
        "era_name": era_name,
        "subject_key": subject_key,
        "high_treatment": str(high["rarity"]),
        "low_treatment": str(low["rarity"]),
        "high_card_id": high_id,
        "low_card_id": low_id,
        "shared_dates": len(shared),
        "first_date": shared[0],
        "last_date": shared[-1],
        "mean_log_ratio": float(np.mean(ratios)),
        "early_mean_log_ratio": float(np.mean(ratios[:cut])),
        "late_mean_log_ratio": float(np.mean(ratios[cut:])),
        "scarcity_log_ratio": math.log(
            float(low["modeled_probability"]) / float(high["modeled_probability"])
        ),
        "artist_delta": hc["artist"] - lc["artist"],
        "subject_delta": subject_delta,
        "playability_delta": playability_delta,
    }


def build_combined_edges(
    prior_panel: dict[str, Any],
    fresh_panel: dict[str, Any],
    controls: dict[str, dict[str, float]],
) -> tuple[list[dict[str, Any]], list[str], dict[str, str], dict[str, int]]:
    prior_triads = validate_prior_panel(prior_panel)
    fresh_triads, _ = control_eligible_fresh_triads(fresh_panel, controls)

    combined: list[tuple[str, dict[str, Any], dict[str, Any]]] = [
        ("prior", prior_panel, triad) for triad in prior_triads
    ] + [
        ("fresh", fresh_panel, triad) for triad in fresh_triads
    ]

    observed_era: dict[str, str] = {}
    ready_by_set: dict[str, int] = defaultdict(int)
    edges: list[dict[str, Any]] = []
    for source, panel, triad in combined:
        set_name = str(triad["set_name"])
        era_name = str(triad["era_name"])
        subject_key = str(triad["subject_key"])
        expected_era = EXPECTED_ERA_BY_SET.get(set_name)
        if expected_era != era_name:
            raise RuntimeError(f"era drift set={set_name} expected={expected_era} got={era_name}")
        if set_name in observed_era and observed_era[set_name] != era_name:
            raise RuntimeError(f"inconsistent era for set={set_name}")
        observed_era[set_name] = era_name
        ready_by_set[set_name] += 1

        by_rarity = {str(card["rarity"]): card for card in triad["cards"]}
        if set(by_rarity) != {DOUBLE, ULTRA, SIR}:
            raise RuntimeError(f"unexpected triad treatments {set_name} {subject_key}")
        edges.extend([
            _pair_row(
                panel=panel, source=source, set_name=set_name, era_name=era_name,
                subject_key=subject_key, high=by_rarity[ULTRA], low=by_rarity[DOUBLE],
                controls=controls,
            ),
            _pair_row(
                panel=panel, source=source, set_name=set_name, era_name=era_name,
                subject_key=subject_key, high=by_rarity[SIR], low=by_rarity[DOUBLE],
                controls=controls,
            ),
            _pair_row(
                panel=panel, source=source, set_name=set_name, era_name=era_name,
                subject_key=subject_key, high=by_rarity[SIR], low=by_rarity[ULTRA],
                controls=controls,
            ),
        ])

    set_order = [name for name in FROZEN_SET_ORDER if ready_by_set.get(name, 0) > 0]
    if set(set_order) != set(ready_by_set):
        raise RuntimeError(f"unexpected included Set(s): {sorted(set(ready_by_set) - set(set_order))}")
    if len(edges) != 3 * sum(ready_by_set.values()):
        raise RuntimeError("edge count mismatch")
    return edges, set_order, observed_era, dict(ready_by_set)


def _level_col_index(set_order: list[str], set_name: str, treatment: str) -> int | None:
    base = set_order.index(set_name) * 2
    if treatment == ULTRA:
        return base
    if treatment == SIR:
        return base + 1
    if treatment == DOUBLE:
        return None
    raise RuntimeError(f"unsupported treatment {treatment}")


def design(
    rows: list[dict[str, Any]],
    set_order: list[str],
    outcome_key: str = "mean_log_ratio",
) -> tuple[np.ndarray, np.ndarray]:
    X = []
    y = []
    width = len(set_order) * 2 + 2
    for row in rows:
        vector = [0.0] * width
        high_idx = _level_col_index(set_order, str(row["set_name"]), str(row["high_treatment"]))
        low_idx = _level_col_index(set_order, str(row["set_name"]), str(row["low_treatment"]))
        if high_idx is not None:
            vector[high_idx] += 1.0
        if low_idx is not None:
            vector[low_idx] -= 1.0
        vector[-2] = float(row["scarcity_log_ratio"])
        vector[-1] = float(row["artist_delta"]) / 100.0
        X.append(vector)
        y.append(float(row[outcome_key]))
    return np.array(X, dtype=float), np.array(y, dtype=float)


def fit(
    rows: list[dict[str, Any]],
    set_order: list[str],
    outcome_key: str = "mean_log_ratio",
) -> tuple[np.ndarray, int, float]:
    X, y = design(rows, set_order, outcome_key)
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    return beta, int(np.linalg.matrix_rank(X)), float(np.linalg.cond(X))


def set_levels(beta: np.ndarray, set_order: list[str]) -> dict[str, dict[str, float]]:
    return {
        set_name: {
            DOUBLE: 0.0,
            ULTRA: float(beta[2 * i]),
            SIR: float(beta[2 * i + 1]),
        }
        for i, set_name in enumerate(set_order)
    }


def summarize_levels(
    levels_by_set: dict[str, dict[str, float]],
    set_order: list[str],
    era_by_set: dict[str, str],
) -> dict[str, Any]:
    sets: list[dict[str, Any]] = []
    for set_name in set_order:
        levels = levels_by_set[set_name]
        sets.append({
            "set_name": set_name,
            "era_name": era_by_set[set_name],
            "ultra_vs_double_log": levels[ULTRA],
            "ultra_vs_double_multiplier": math.exp(levels[ULTRA]),
            "sir_vs_double_log": levels[SIR],
            "sir_vs_double_multiplier": math.exp(levels[SIR]),
            "sir_vs_ultra_log": levels[SIR] - levels[ULTRA],
            "sir_vs_ultra_multiplier": math.exp(levels[SIR] - levels[ULTRA]),
        })
    eras: list[dict[str, Any]] = []
    for era_name in ("Mega Evolution", "Scarlet and Violet"):
        names = [name for name in set_order if era_by_set[name] == era_name]
        if not names:
            raise RuntimeError(f"era missing from combined fit: {era_name}")
        ur = float(np.mean([levels_by_set[name][ULTRA] for name in names]))
        sir = float(np.mean([levels_by_set[name][SIR] for name in names]))
        eras.append({
            "era_name": era_name,
            "set_count": len(names),
            "ultra_vs_double_log": ur,
            "ultra_vs_double_multiplier": math.exp(ur),
            "sir_vs_double_log": sir,
            "sir_vs_double_multiplier": math.exp(sir),
            "sir_vs_ultra_log": sir - ur,
            "sir_vs_ultra_multiplier": math.exp(sir - ur),
        })
    return {"sets": sets, "eras": eras}


def _metric_vector(
    levels_by_set: dict[str, dict[str, float]],
    beta: np.ndarray,
    set_order: list[str],
    era_by_set: dict[str, str],
) -> dict[str, float]:
    out: dict[str, float] = {}
    for set_name in set_order:
        levels = levels_by_set[set_name]
        out[f"set::{set_name}::ur_dr"] = levels[ULTRA]
        out[f"set::{set_name}::sir_dr"] = levels[SIR]
        out[f"set::{set_name}::sir_ur"] = levels[SIR] - levels[ULTRA]
    for era_name in ("Mega Evolution", "Scarlet and Violet"):
        names = [name for name in set_order if era_by_set[name] == era_name]
        ur = float(np.mean([levels_by_set[name][ULTRA] for name in names]))
        sir = float(np.mean([levels_by_set[name][SIR] for name in names]))
        out[f"era::{era_name}::ur_dr"] = ur
        out[f"era::{era_name}::sir_dr"] = sir
        out[f"era::{era_name}::sir_ur"] = sir - ur
    out["beta::scarcity"] = float(beta[-2])
    out["beta::artist"] = float(beta[-1])
    return out


def _era_row(summary_rows: list[dict[str, Any]], era: str) -> dict[str, Any]:
    return next(row for row in summary_rows if row["era_name"] == era)


def estimate(
    prior_panel: dict[str, Any],
    fresh_panel: dict[str, Any],
    controls: dict[str, dict[str, float]],
) -> dict[str, Any]:
    history_coverage = fresh_coverage(fresh_panel)
    if not history_coverage["pass"]:
        return {
            "study_id": "set_relative_treatment_hierarchy_v2_broad_expansion",
            "decision_token": "SET_RELATIVE_TREATMENT_V2_INSUFFICIENT_EXPANSION_COVERAGE",
            "status": "research_only",
            "fresh_coverage": history_coverage,
            "production_writes": 0,
        }

    coverage = fresh_coverage(fresh_panel, controls)
    if not coverage["pass"]:
        return {
            "study_id": "set_relative_treatment_hierarchy_v2_broad_expansion",
            "decision_token": "SET_RELATIVE_TREATMENT_V2_INSUFFICIENT_EXPANSION_COVERAGE",
            "status": "research_only",
            "fresh_coverage": coverage,
            "production_writes": 0,
        }

    edges, set_order, era_by_set, ready_by_set = build_combined_edges(
        prior_panel, fresh_panel, controls
    )
    expected_rank = len(set_order) * 2 + 2
    beta, rank, condition = fit(edges, set_order)
    levels = set_levels(beta, set_order)
    summary = summarize_levels(levels, set_order, era_by_set)

    early_beta, early_rank, early_condition = fit(edges, set_order, "early_mean_log_ratio")
    late_beta, late_rank, late_condition = fit(edges, set_order, "late_mean_log_ratio")
    early_summary = summarize_levels(set_levels(early_beta, set_order), set_order, era_by_set)
    late_summary = summarize_levels(set_levels(late_beta, set_order), set_order, era_by_set)

    by_set_cluster: dict[str, list[str]] = defaultdict(list)
    by_cluster: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in edges:
        cluster = str(row["cluster_key"])
        set_name = str(row["set_name"])
        if cluster not in by_set_cluster[set_name]:
            by_set_cluster[set_name].append(cluster)
        by_cluster[cluster].append(row)

    rng = np.random.default_rng(SEED)
    boot_metrics: list[dict[str, float]] = []
    invalid_bootstrap_draws = 0
    for _ in range(BOOTSTRAP_DRAWS):
        sample: list[dict[str, Any]] = []
        for set_name in set_order:
            clusters = sorted(by_set_cluster[set_name])
            sampled = rng.choice(clusters, size=len(clusters), replace=True)
            for cluster in sampled:
                sample.extend(by_cluster[str(cluster)])
        b, r, _ = fit(sample, set_order)
        if r < expected_rank:
            invalid_bootstrap_draws += 1
            continue
        boot_metrics.append(_metric_vector(set_levels(b, set_order), b, set_order, era_by_set))

    if len(boot_metrics) < MIN_VALID_BOOTSTRAP_DRAWS:
        raise RuntimeError(
            f"insufficient valid stratified bootstrap draws {len(boot_metrics)} "
            f"of {BOOTSTRAP_DRAWS}"
        )

    metric_keys = sorted(boot_metrics[0])
    ci: dict[str, list[float]] = {}
    for key in metric_keys:
        vals = np.array([row[key] for row in boot_metrics], dtype=float)
        bounds = np.percentile(vals, [2.5, 50, 97.5])
        ci[key] = [float(bounds[0]), float(bounds[1]), float(bounds[2])]

    loo: list[dict[str, Any]] = []
    for dropped in sorted(by_cluster):
        sample = [row for row in edges if str(row["cluster_key"]) != dropped]
        b, r, c = fit(sample, set_order)
        complete = r == expected_rank
        metrics = _metric_vector(set_levels(b, set_order), b, set_order, era_by_set)
        loo.append({
            "dropped_cluster": dropped,
            "rank": r,
            "condition_number": c,
            "complete_rank": complete,
            "metrics": metrics,
        })

    set_sir_dr_positive = [row["sir_vs_double_log"] > 0 for row in summary["sets"]]
    set_sir_ur_positive = [row["sir_vs_ultra_log"] > 0 for row in summary["sets"]]
    share_sir_dr = sum(set_sir_dr_positive) / len(set_sir_dr_positive)
    share_sir_ur = sum(set_sir_ur_positive) / len(set_sir_ur_positive)

    gates: dict[str, bool] = {
        "full_design_complete_rank": rank == expected_rank,
        "condition_le_30": condition <= 30,
        "scarcity_positive_ci": beta[-2] > 0 and ci["beta::scarcity"][0] > 0,
    }
    temporal_rank_complete = early_rank == expected_rank and late_rank == expected_rank
    for era in ("Mega Evolution", "Scarlet and Violet"):
        point = _era_row(summary["eras"], era)
        early = _era_row(early_summary["eras"], era)
        late = _era_row(late_summary["eras"], era)
        gates[f"{era}_sir_double_point_positive"] = point["sir_vs_double_log"] > 0
        gates[f"{era}_sir_ultra_point_positive"] = point["sir_vs_ultra_log"] > 0
        gates[f"{era}_sir_double_ci_positive"] = ci[f"era::{era}::sir_dr"][0] > 0
        gates[f"{era}_sir_ultra_ci_positive"] = ci[f"era::{era}::sir_ur"][0] > 0
        gates[f"{era}_temporal_sir_double_positive"] = (
            temporal_rank_complete
            and early["sir_vs_double_log"] > 0
            and late["sir_vs_double_log"] > 0
        )
        gates[f"{era}_temporal_sir_ultra_positive"] = (
            temporal_rank_complete
            and early["sir_vs_ultra_log"] > 0
            and late["sir_vs_ultra_log"] > 0
        )
        gates[f"{era}_loo_sir_double_positive"] = all(
            row["complete_rank"] and row["metrics"][f"era::{era}::sir_dr"] > 0
            for row in loo
        )
        gates[f"{era}_loo_sir_ultra_positive"] = all(
            row["complete_rank"] and row["metrics"][f"era::{era}::sir_ur"] > 0
            for row in loo
        )
    gates["sets_sir_double_positive_share_ge_70pct"] = share_sir_dr >= 0.70
    gates["sets_sir_ultra_positive_share_ge_70pct"] = share_sir_ur >= 0.70

    passed = all(gates.values())

    set_rows = []
    for row in summary["sets"]:
        set_name = row["set_name"]
        set_rows.append({
            **row,
            "ready_triads": ready_by_set[set_name],
            "ultra_vs_double_ci95": [
                math.exp(ci[f"set::{set_name}::ur_dr"][0]),
                math.exp(ci[f"set::{set_name}::ur_dr"][2]),
            ],
            "sir_vs_double_ci95": [
                math.exp(ci[f"set::{set_name}::sir_dr"][0]),
                math.exp(ci[f"set::{set_name}::sir_dr"][2]),
            ],
            "sir_vs_ultra_ci95": [
                math.exp(ci[f"set::{set_name}::sir_ur"][0]),
                math.exp(ci[f"set::{set_name}::sir_ur"][2]),
            ],
        })

    era_rows = []
    for row in summary["eras"]:
        era = row["era_name"]
        era_rows.append({
            **row,
            "ultra_vs_double_ci95": [
                math.exp(ci[f"era::{era}::ur_dr"][0]),
                math.exp(ci[f"era::{era}::ur_dr"][2]),
            ],
            "sir_vs_double_ci95": [
                math.exp(ci[f"era::{era}::sir_dr"][0]),
                math.exp(ci[f"era::{era}::sir_dr"][2]),
            ],
            "sir_vs_ultra_ci95": [
                math.exp(ci[f"era::{era}::sir_ur"][0]),
                math.exp(ci[f"era::{era}::sir_ur"][2]),
            ],
        })

    controls_payload = {
        "model_run_id": MODEL_RUN_ID,
        "model_version": MODEL_VERSION,
        "as_of_date": MODEL_AS_OF_DATE,
        "cards": [{"card_id": cid, **controls[cid]} for cid in sorted(controls)],
    }

    return {
        "study_id": "set_relative_treatment_hierarchy_v2_broad_expansion",
        "decision_token": (
            "SET_RELATIVE_TREATMENT_HIERARCHY_V2_SUPPORTED_FOR_EXPANSION"
            if passed
            else "SET_RELATIVE_TREATMENT_HIERARCHY_V2_NOT_SUPPORTED"
        ),
        "status": "research_only",
        "formula": {
            "model": "theta_set(high)-theta_set(low)+shared_scarcity*log(p_low/p_high)+artist_delta/100",
            "reference": "Double Rare=0 independently inside every included Set",
            "bootstrap": "2000 deterministic Set-stratified whole-triad resamples",
            "bootstrap_seed": SEED,
            "temporal": "chronological median split within each edge",
            "influence": "leave one whole Set+subject triad out",
        },
        "inputs": {
            "prior_panel_fingerprint": PRIOR_PANEL_FINGERPRINT,
            "fresh_panel_fingerprint": FRESH_TARGET_FINGERPRINT,
            "control_fingerprint": stable_hash(controls_payload),
            "prior_ready_triads": 20,
            "fresh_ready_triads": coverage["ready_triads"],
            "combined_ready_triads": sum(ready_by_set.values()),
            "combined_edges": len(edges),
            "included_sets": len(set_order),
            "set_order": set_order,
            "ready_by_set": ready_by_set,
            "collector_model_run_id": MODEL_RUN_ID,
        },
        "fresh_coverage": coverage,
        "fit": {
            "expected_rank": expected_rank,
            "rank": rank,
            "condition_number": condition,
            "scarcity_beta": float(beta[-2]),
            "scarcity_beta_ci95": [ci["beta::scarcity"][0], ci["beta::scarcity"][2]],
            "artist_beta_per_100": float(beta[-1]),
            "artist_beta_ci95": [ci["beta::artist"][0], ci["beta::artist"][2]],
            "bootstrap_valid_draws": len(boot_metrics),
            "bootstrap_invalid_draws": invalid_bootstrap_draws,
            "early_rank": early_rank,
            "early_condition_number": early_condition,
            "late_rank": late_rank,
            "late_condition_number": late_condition,
        },
        "sets": set_rows,
        "eras": era_rows,
        "set_positive_shares": {
            "sir_vs_double": share_sir_dr,
            "sir_vs_ultra": share_sir_ur,
        },
        "temporal": {"early": early_summary, "late": late_summary},
        "leave_one_triad_out": loo,
        "gates": gates,
        "production_writes": 0,
    }


def render(result: dict[str, Any]) -> str:
    lines = [
        "# Set-Relative Treatment Hierarchy V2 — Broad Independent Expansion",
        "",
        f"Decision token: \`{result['decision_token']}\`",
        "",
    ]
    if result["decision_token"] == "SET_RELATIVE_TREATMENT_V2_INSUFFICIENT_EXPANSION_COVERAGE":
        c = result["fresh_coverage"]
        lines += [
            "## Coverage stop",
            "",
            f"- Ready fresh triads: **{c.get('ready_triads', 0)} / 56**",
            f"- Pitch Black ready: **{c.get('pitch_black_ready', 0)}**",
            f"- Qualifying Scarlet & Violet Sets: **{c.get('qualifying_sv_sets', 0)} / 9**",
            f"- Fresh cards with usable history: **{c.get('fresh_cards_returned', 0)} / 168**",
            "",
            "The preregistered expansion coverage gate did not pass, so the combined Set-relative model was not fit.",
            "",
            "Production writes: **ZERO**.",
            "",
        ]
        return "\n".join(lines)

    lines += [
        "## Shared nuisance coefficients",
        "",
        f"- Scarcity beta: **{result['fit']['scarcity_beta']:.3f}** "
        f"(95% {result['fit']['scarcity_beta_ci95'][0]:.3f}–{result['fit']['scarcity_beta_ci95'][1]:.3f})",
        f"- Artist beta / 100 points: **{result['fit']['artist_beta_per_100']:.3f}**",
        f"- Design rank: **{result['fit']['rank']} / {result['fit']['expected_rank']}**; "
        f"condition number: **{result['fit']['condition_number']:.2f}**",
        f"- Combined ready triads: **{result['inputs']['combined_ready_triads']}** across "
        f"**{result['inputs']['included_sets']} Sets**",
        "",
        "## Set-specific Treatment levels",
        "",
        "| Era | Set | Ready triads | Ultra/Double | SIR/Double | SIR/Ultra |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in result["sets"]:
        lines.append(
            f"| {row['era_name']} | {row['set_name']} | {row['ready_triads']} | "
            f"{row['ultra_vs_double_multiplier']:.2f}x | "
            f"{row['sir_vs_double_multiplier']:.2f}x | "
            f"{row['sir_vs_ultra_multiplier']:.2f}x |"
        )
    lines += ["", "## Era summaries", ""]
    for row in result["eras"]:
        lines.append(
            f"- **{row['era_name']}** ({row['set_count']} Sets) — "
            f"Ultra/Double {row['ultra_vs_double_multiplier']:.2f}x; "
            f"SIR/Double {row['sir_vs_double_multiplier']:.2f}x; "
            f"SIR/Ultra {row['sir_vs_ultra_multiplier']:.2f}x"
        )
    lines += [
        "",
        "## Individual-Set sign shares",
        "",
        f"- SIR > Double Rare: **{100*result['set_positive_shares']['sir_vs_double']:.1f}%**",
        f"- SIR > Ultra Rare: **{100*result['set_positive_shares']['sir_vs_ultra']:.1f}%**",
        "",
        "## Frozen gates",
        "",
    ]
    for key, value in result["gates"].items():
        lines.append(f"- {key}: **{'PASS' if value else 'FAIL'}**")
    lines += [
        "",
        "Ultra Rare vs Double Rare remains descriptive by preregistration and is not required to have one universal ordering.",
        "",
        "Production writes: **ZERO**.",
        "",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prior-panel", type=Path, required=True)
    parser.add_argument("--fresh-panel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)

    prior_panel = json.loads(args.prior_panel.read_text(encoding="utf-8"))
    fresh_panel = json.loads(args.fresh_panel.read_text(encoding="utf-8"))

    coverage = fresh_coverage(fresh_panel)
    controls: dict[str, dict[str, float]] = {}
    if coverage["pass"]:
        prior_triads = validate_prior_panel(prior_panel)
        fresh_triads = _ready_triads(fresh_panel)
        card_ids = sorted({
            str(card["canonical_card_id"])
            for triad in prior_triads + fresh_triads
            for card in triad["cards"]
        })
        load_dotenv(ROOT / "backend/.env", override=False)
        from backend.db.clients.supabase_client import supabase
        controls = load_controls(supabase, card_ids)

    result = estimate(prior_panel, fresh_panel, controls)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(render(result), encoding="utf-8")
    printable = {k: v for k, v in result.items() if k != "leave_one_triad_out"}
    print(json.dumps(printable, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
