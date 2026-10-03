"""Set-relative Treatment hierarchy follow-up on the independent replication panel.

Research only. No production writes.

Frozen design:
  y = theta_set(high) - theta_set(low)
      + beta_scarcity * log(p_low / p_high)
      + beta_artist * artist_delta/100

Double Rare is the reference inside each Set. Ultra Rare and SIR receive
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

DOUBLE = "Double Rare"
ULTRA = "Ultra Rare"
SIR = "Special Illustration Rare"

EXPECTED_SET_ORDER = [
    "Perfect Order",
    "Phantasmal Flames",
    "Obsidian Flames",
    "Scarlet and Violet 151",
    "Twilight Masquerade",
]
ERA_BY_SET = {
    "Perfect Order": "Mega Evolution",
    "Phantasmal Flames": "Mega Evolution",
    "Obsidian Flames": "Scarlet and Violet",
    "Scarlet and Violet 151": "Scarlet and Violet",
    "Twilight Masquerade": "Scarlet and Violet",
}
SET_LEVELS = ("ultra", "sir")


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


def _ready_triads(panel: dict[str, Any]) -> list[dict[str, Any]]:
    ready_keys = {
        (str(row["set_name"]), str(row["subject_key"]))
        for row in panel.get("triad_results", [])
        if row.get("ready")
    }
    triads = [
        dict(row)
        for row in panel["target"]["triads"]
        if (str(row["set_name"]), str(row["subject_key"])) in ready_keys
    ]
    if len(triads) != 20:
        raise RuntimeError(f"expected 20 ready triads, got {len(triads)}")
    counts = defaultdict(int)
    for triad in triads:
        counts[str(triad["set_name"])] += 1
    expected = {name: 4 for name in EXPECTED_SET_ORDER}
    if dict(counts) != expected:
        raise RuntimeError(f"unexpected ready-triad Set counts: {dict(counts)}")
    return triads


def _history(panel: dict[str, Any], card_id: str) -> dict[str, float]:
    rows = panel["panels"][card_id]["history"]
    return {str(row["date"]): float(row["price"]) for row in rows}


def _pair_row(
    *,
    panel: dict[str, Any],
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
    return {
        "cluster_key": f"{set_name}|{subject_key}",
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


def build_edges(panel: dict[str, Any], controls: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
    if panel.get("status") not in {"COMPLETE", "PARTIAL"}:
        raise RuntimeError("replication panel status invalid")
    if int(panel.get("production_writes") or 0) != 0:
        raise RuntimeError("replication panel reports production writes")
    if not (panel.get("coverage") or {}).get("coverage_pass"):
        raise RuntimeError("replication coverage gate did not pass")

    edges: list[dict[str, Any]] = []
    for triad in _ready_triads(panel):
        set_name = str(triad["set_name"])
        era_name = str(triad["era_name"])
        subject_key = str(triad["subject_key"])
        cards = list(triad["cards"])
        by_rarity = {str(card["rarity"]): card for card in cards}
        if set(by_rarity) != {DOUBLE, ULTRA, SIR}:
            raise RuntimeError(f"unexpected triad treatments {set_name} {subject_key}")
        edges.append(
            _pair_row(
                panel=panel, set_name=set_name, era_name=era_name, subject_key=subject_key,
                high=by_rarity[ULTRA], low=by_rarity[DOUBLE], controls=controls,
            )
        )
        edges.append(
            _pair_row(
                panel=panel, set_name=set_name, era_name=era_name, subject_key=subject_key,
                high=by_rarity[SIR], low=by_rarity[DOUBLE], controls=controls,
            )
        )
        edges.append(
            _pair_row(
                panel=panel, set_name=set_name, era_name=era_name, subject_key=subject_key,
                high=by_rarity[SIR], low=by_rarity[ULTRA], controls=controls,
            )
        )
    if len(edges) != 60:
        raise RuntimeError(f"expected 60 edges, got {len(edges)}")
    return edges


def _level_col_index(set_name: str, treatment: str) -> int | None:
    base = EXPECTED_SET_ORDER.index(set_name) * 2
    if treatment == ULTRA:
        return base
    if treatment == SIR:
        return base + 1
    if treatment == DOUBLE:
        return None
    raise RuntimeError(f"unsupported treatment {treatment}")


def design(rows: list[dict[str, Any]], outcome_key: str = "mean_log_ratio") -> tuple[np.ndarray, np.ndarray]:
    X = []
    y = []
    for row in rows:
        vector = [0.0] * (len(EXPECTED_SET_ORDER) * 2 + 2)
        high_idx = _level_col_index(str(row["set_name"]), str(row["high_treatment"]))
        low_idx = _level_col_index(str(row["set_name"]), str(row["low_treatment"]))
        if high_idx is not None:
            vector[high_idx] += 1.0
        if low_idx is not None:
            vector[low_idx] -= 1.0
        vector[-2] = float(row["scarcity_log_ratio"])
        vector[-1] = float(row["artist_delta"]) / 100.0
        X.append(vector)
        y.append(float(row[outcome_key]))
    return np.array(X, dtype=float), np.array(y, dtype=float)


def fit(rows: list[dict[str, Any]], outcome_key: str = "mean_log_ratio") -> tuple[np.ndarray, int, float]:
    X, y = design(rows, outcome_key)
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    return beta, int(np.linalg.matrix_rank(X)), float(np.linalg.cond(X))


def set_levels(beta: np.ndarray) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for i, set_name in enumerate(EXPECTED_SET_ORDER):
        out[set_name] = {
            DOUBLE: 0.0,
            ULTRA: float(beta[2 * i]),
            SIR: float(beta[2 * i + 1]),
        }
    return out


def contrast(levels: dict[str, float], high: str, low: str) -> float:
    return levels[high] - levels[low]


def summarize_levels(levels_by_set: dict[str, dict[str, float]]) -> dict[str, Any]:
    sets: list[dict[str, Any]] = []
    for set_name in EXPECTED_SET_ORDER:
        levels = levels_by_set[set_name]
        sets.append(
            {
                "set_name": set_name,
                "era_name": ERA_BY_SET[set_name],
                "ultra_vs_double_log": levels[ULTRA],
                "ultra_vs_double_multiplier": math.exp(levels[ULTRA]),
                "sir_vs_double_log": levels[SIR],
                "sir_vs_double_multiplier": math.exp(levels[SIR]),
                "sir_vs_ultra_log": levels[SIR] - levels[ULTRA],
                "sir_vs_ultra_multiplier": math.exp(levels[SIR] - levels[ULTRA]),
            }
        )
    eras: list[dict[str, Any]] = []
    for era_name in ("Mega Evolution", "Scarlet and Violet"):
        names = [name for name in EXPECTED_SET_ORDER if ERA_BY_SET[name] == era_name]
        ur = float(np.mean([levels_by_set[name][ULTRA] for name in names]))
        sir = float(np.mean([levels_by_set[name][SIR] for name in names]))
        eras.append(
            {
                "era_name": era_name,
                "set_count": len(names),
                "ultra_vs_double_log": ur,
                "ultra_vs_double_multiplier": math.exp(ur),
                "sir_vs_double_log": sir,
                "sir_vs_double_multiplier": math.exp(sir),
                "sir_vs_ultra_log": sir - ur,
                "sir_vs_ultra_multiplier": math.exp(sir - ur),
            }
        )
    return {"sets": sets, "eras": eras}


def _metric_vector(levels_by_set: dict[str, dict[str, float]], beta: np.ndarray) -> dict[str, float]:
    out: dict[str, float] = {}
    for set_name in EXPECTED_SET_ORDER:
        levels = levels_by_set[set_name]
        out[f"set::{set_name}::ur_dr"] = levels[ULTRA]
        out[f"set::{set_name}::sir_dr"] = levels[SIR]
        out[f"set::{set_name}::sir_ur"] = levels[SIR] - levels[ULTRA]
    for era_name in ("Mega Evolution", "Scarlet and Violet"):
        names = [name for name in EXPECTED_SET_ORDER if ERA_BY_SET[name] == era_name]
        ur = float(np.mean([levels_by_set[name][ULTRA] for name in names]))
        sir = float(np.mean([levels_by_set[name][SIR] for name in names]))
        out[f"era::{era_name}::ur_dr"] = ur
        out[f"era::{era_name}::sir_dr"] = sir
        out[f"era::{era_name}::sir_ur"] = sir - ur
    out["beta::scarcity"] = float(beta[-2])
    out["beta::artist"] = float(beta[-1])
    return out


def estimate(panel: dict[str, Any], controls: dict[str, dict[str, float]]) -> dict[str, Any]:
    edges = build_edges(panel, controls)
    beta, rank, condition = fit(edges)
    levels = set_levels(beta)
    summary = summarize_levels(levels)

    early_beta, early_rank, _ = fit(edges, "early_mean_log_ratio")
    late_beta, late_rank, _ = fit(edges, "late_mean_log_ratio")
    if early_rank != 12 or late_rank != 12:
        raise RuntimeError("temporal design rank deficient")
    early_summary = summarize_levels(set_levels(early_beta))
    late_summary = summarize_levels(set_levels(late_beta))

    by_set_cluster: dict[str, list[str]] = defaultdict(list)
    by_cluster: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in edges:
        cluster = str(row["cluster_key"])
        if cluster not in by_set_cluster[str(row["set_name"])]:
            by_set_cluster[str(row["set_name"])].append(cluster)
        by_cluster[cluster].append(row)

    rng = np.random.default_rng(SEED)
    boot_metrics: list[dict[str, float]] = []
    valid = 0
    for _ in range(BOOTSTRAP_DRAWS):
        sample: list[dict[str, Any]] = []
        for set_name in EXPECTED_SET_ORDER:
            clusters = sorted(by_set_cluster[set_name])
            sampled = rng.choice(clusters, size=len(clusters), replace=True)
            for cluster in sampled:
                sample.extend(by_cluster[str(cluster)])
        b, r, _ = fit(sample)
        if r < 12:
            continue
        valid += 1
        boot_metrics.append(_metric_vector(set_levels(b), b))
    if valid < 1900:
        raise RuntimeError(f"insufficient valid stratified bootstrap draws {valid}")

    metric_keys = sorted(boot_metrics[0])
    ci: dict[str, list[float]] = {}
    for key in metric_keys:
        vals = np.array([row[key] for row in boot_metrics], dtype=float)
        bounds = np.percentile(vals, [2.5, 50, 97.5])
        ci[key] = [float(bounds[0]), float(bounds[1]), float(bounds[2])]

    loo: list[dict[str, Any]] = []
    clusters = sorted(by_cluster)
    for dropped in clusters:
        sample = [row for row in edges if str(row["cluster_key"]) != dropped]
        b, r, _ = fit(sample)
        if r < 12:
            raise RuntimeError(f"leave-one-triad rank deficient {dropped}")
        loo.append({"dropped_cluster": dropped, "metrics": _metric_vector(set_levels(b), b)})

    def era_row(summary_rows: list[dict[str, Any]], era: str) -> dict[str, Any]:
        return next(row for row in summary_rows if row["era_name"] == era)

    gates: dict[str, bool] = {
        "rank12": rank == 12,
        "condition_le_30": condition <= 30,
        "scarcity_positive_ci": beta[-2] > 0 and ci["beta::scarcity"][0] > 0,
        "all_sets_sir_gt_double": all(row["sir_vs_double_log"] > 0 for row in summary["sets"]),
        "all_sets_sir_gt_ultra": all(row["sir_vs_ultra_log"] > 0 for row in summary["sets"]),
    }
    for era in ("Mega Evolution", "Scarlet and Violet"):
        gates[f"{era}_sir_double_positive_ci"] = ci[f"era::{era}::sir_dr"][0] > 0
        gates[f"{era}_sir_ultra_positive_ci"] = ci[f"era::{era}::sir_ur"][0] > 0
        early = era_row(early_summary["eras"], era)
        late = era_row(late_summary["eras"], era)
        gates[f"{era}_temporal_sir_double"] = early["sir_vs_double_log"] > 0 and late["sir_vs_double_log"] > 0
        gates[f"{era}_temporal_sir_ultra"] = early["sir_vs_ultra_log"] > 0 and late["sir_vs_ultra_log"] > 0
        gates[f"{era}_loo_sir_double"] = all(
            row["metrics"][f"era::{era}::sir_dr"] > 0 for row in loo
        )
        gates[f"{era}_loo_sir_ultra"] = all(
            row["metrics"][f"era::{era}::sir_ur"] > 0 for row in loo
        )

    passed = all(gates.values())

    set_ci_rows = []
    for row in summary["sets"]:
        set_name = row["set_name"]
        set_ci_rows.append(
            {
                **row,
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
            }
        )
    era_ci_rows = []
    for row in summary["eras"]:
        era = row["era_name"]
        era_ci_rows.append(
            {
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
            }
        )

    heterogeneity = {}
    for contrast_name, key in (
        ("ultra_vs_double", "ultra_vs_double_log"),
        ("sir_vs_double", "sir_vs_double_log"),
        ("sir_vs_ultra", "sir_vs_ultra_log"),
    ):
        vals = np.array([float(row[key]) for row in summary["sets"]], dtype=float)
        heterogeneity[contrast_name] = {
            "set_log_min": float(np.min(vals)),
            "set_log_max": float(np.max(vals)),
            "set_log_range": float(np.max(vals) - np.min(vals)),
            "set_log_sd": float(np.std(vals, ddof=1)),
            "multiplier_min": math.exp(float(np.min(vals))),
            "multiplier_max": math.exp(float(np.max(vals))),
        }

    controls_payload = {
        "model_run_id": MODEL_RUN_ID,
        "model_version": MODEL_VERSION,
        "as_of_date": MODEL_AS_OF_DATE,
        "cards": [{"card_id": cid, **controls[cid]} for cid in sorted(controls)],
    }

    return {
        "study_id": "set_relative_treatment_hierarchy_v1_followup",
        "decision_token": (
            "SET_RELATIVE_TREATMENT_HIERARCHY_SUPPORTED_FOR_EXPANSION"
            if passed
            else "SET_RELATIVE_TREATMENT_HIERARCHY_NOT_YET_SUPPORTED"
        ),
        "status": "research_only",
        "reason": "global shared Treatment levels failed confirmatory effect-size replication; Set-specific levels are estimated before era aggregation",
        "formula": {
            "model": "theta_set(high)-theta_set(low)+shared_scarcity*log(p_low/p_high)+artist_delta/100",
            "reference": "Double Rare=0 independently inside every Set",
            "bootstrap": "2000 stratified whole-triad resamples within Set",
            "temporal": "chronological median split within each edge",
        },
        "inputs": {
            "panel_fingerprint": panel["target"]["fingerprint"],
            "control_fingerprint": stable_hash(controls_payload),
            "ready_triads": 20,
            "edges": 60,
            "sets": 5,
            "eras": 2,
            "collector_model_run_id": MODEL_RUN_ID,
        },
        "fit": {
            "rank": rank,
            "condition_number": condition,
            "scarcity_beta": float(beta[-2]),
            "scarcity_beta_ci95": [ci["beta::scarcity"][0], ci["beta::scarcity"][2]],
            "artist_beta_per_100": float(beta[-1]),
            "artist_beta_ci95": [ci["beta::artist"][0], ci["beta::artist"][2]],
            "bootstrap_valid_draws": valid,
        },
        "sets": set_ci_rows,
        "eras": era_ci_rows,
        "temporal": {"early": early_summary, "late": late_summary},
        "leave_one_triad_out": loo,
        "heterogeneity": heterogeneity,
        "gates": gates,
        "production_writes": 0,
    }


def render(result: dict[str, Any]) -> str:
    lines = [
        "# Set-Relative Treatment Hierarchy V1 — Follow-up Result",
        "",
        f"Decision token: `{result['decision_token']}`",
        "",
        "## Shared nuisance coefficients",
        "",
        f"- Scarcity beta: **{result['fit']['scarcity_beta']:.3f}** "
        f"(95% {result['fit']['scarcity_beta_ci95'][0]:.3f}–{result['fit']['scarcity_beta_ci95'][1]:.3f})",
        f"- Artist beta / 100 points: **{result['fit']['artist_beta_per_100']:.3f}**",
        f"- Design rank: **{result['fit']['rank']}**; condition number: **{result['fit']['condition_number']:.2f}**",
        "",
        "## Set-specific Treatment levels",
        "",
        "| Era | Set | Ultra/Double | SIR/Double | SIR/Ultra |",
        "|---|---|---:|---:|---:|",
    ]
    for row in result["sets"]:
        lines.append(
            f"| {row['era_name']} | {row['set_name']} | "
            f"{row['ultra_vs_double_multiplier']:.2f}x | "
            f"{row['sir_vs_double_multiplier']:.2f}x | "
            f"{row['sir_vs_ultra_multiplier']:.2f}x |"
        )
    lines += ["", "## Era summaries", ""]
    for row in result["eras"]:
        lines.append(
            f"- **{row['era_name']}** — Ultra/Double {row['ultra_vs_double_multiplier']:.2f}x; "
            f"SIR/Double {row['sir_vs_double_multiplier']:.2f}x; "
            f"SIR/Ultra {row['sir_vs_ultra_multiplier']:.2f}x"
        )
    lines += ["", "## Frozen gates", ""]
    for key, value in result["gates"].items():
        lines.append(f"- {key}: **{'PASS' if value else 'FAIL'}**")
    lines += [
        "",
        "## Interpretation",
        "",
        "This study tests Set-relative Treatment levels after the universal global ladder failed quantitative replication. A positive decision supports continuing the hierarchy as Set → Era → cross-era rather than assigning one universal rarity coefficient.",
        "",
        "Production writes: **ZERO**.",
        "",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)

    panel = json.loads(args.panel.read_text(encoding="utf-8"))
    triads = _ready_triads(panel)
    card_ids = sorted(
        {
            str(card["canonical_card_id"])
            for triad in triads
            for card in triad["cards"]
        }
    )

    load_dotenv(ROOT / "backend/.env", override=False)
    from backend.db.clients.supabase_client import supabase

    controls = load_controls(supabase, card_ids)
    result = estimate(panel, controls)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(render(result), encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k != "leave_one_triad_out"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
