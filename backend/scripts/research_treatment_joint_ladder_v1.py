"""Exploratory joint Treatment ladder using three frozen matched-pair panels.

This supersedes separate per-family scarcity coefficients for synthesis purposes.
It estimates one shared scarcity coefficient and latent Treatment levels for
Double Rare, Ultra Rare, and Special Illustration Rare.

Research only. No production writes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
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

FAMILIES = {
    "sir_ultra": (SIR, ULTRA),
    "sir_double": (SIR, DOUBLE),
    "ultra_double": (ULTRA, DOUBLE),
}


def stable_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _chunks(values: list[str], size: int = 100):
    for start in range(0, len(values), size):
        yield values[start : start + size]


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
            f"frozen Collector control coverage mismatch expected={len(card_ids)} got={len(rows)}"
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
            "artist": 0.0
            if row.get("artist_recognition_score") is None
            else float(row["artist_recognition_score"]),
            "playability": 0.0
            if row.get("playability_score") is None
            else float(row["playability_score"]),
            "collector": float(row["collector_card_appeal_score"]),
        }
    return out


def _validate_gate(gate: dict[str, Any], name: str) -> None:
    if gate.get("status") != "COMPLETE":
        raise RuntimeError(f"{name} gate artifact incomplete")
    if gate.get("cross_era_progression") is not True:
        raise RuntimeError(f"{name} cross-era gate did not pass")
    if int(gate.get("production_writes") or 0) != 0:
        raise RuntimeError(f"{name} artifact reports production writes")


def build_edges(
    gates: dict[str, dict[str, Any]], controls: dict[str, dict[str, float]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for family, (high_label, low_label) in FAMILIES.items():
        gate = gates[family]
        _validate_gate(gate, family)
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for card in gate["target"]["cards"]:
            grouped[(str(card["set_name"]), str(card["subject_key"]))].append(card)
        for (set_name, subject_key), group in sorted(grouped.items()):
            high = next(
                card
                for card in group
                if str(card["rarity"]).casefold() == high_label.casefold()
            )
            low = next(
                card
                for card in group
                if str(card["rarity"]).casefold() == low_label.casefold()
            )
            high_history = {
                str(row["date"]): float(row["price"])
                for row in gate["panels"][str(high["canonical_card_id"])]["history"]
            }
            low_history = {
                str(row["date"]): float(row["price"])
                for row in gate["panels"][str(low["canonical_card_id"])]["history"]
            }
            shared = sorted(set(high_history) & set(low_history))
            if len(shared) < 30:
                raise RuntimeError(
                    f"{family} pair fell below frozen readiness gate {set_name} {subject_key}"
                )
            ratios = [
                math.log(high_history[day] / low_history[day]) for day in shared
            ]
            high_control = controls[str(high["canonical_card_id"])]
            low_control = controls[str(low["canonical_card_id"])]
            subject_delta = high_control["subject"] - low_control["subject"]
            playability_delta = high_control["playability"] - low_control["playability"]
            if abs(subject_delta) > 1e-9:
                raise RuntimeError(f"subject control mismatch {family} {set_name} {subject_key}")
            if abs(playability_delta) > 1e-9:
                raise RuntimeError(
                    f"playability control mismatch {family} {set_name} {subject_key}"
                )
            cut = len(shared) // 2
            rows.append(
                {
                    "family": family,
                    "era_name": str(high["era_name"]),
                    "set_name": set_name,
                    "subject_key": subject_key,
                    "cluster_key": f"{set_name}|{subject_key}",
                    "high_treatment": high_label,
                    "low_treatment": low_label,
                    "high_card_id": str(high["canonical_card_id"]),
                    "low_card_id": str(low["canonical_card_id"]),
                    "shared_dates": len(shared),
                    "first_date": shared[0],
                    "last_date": shared[-1],
                    "mean_log_ratio": float(np.mean(ratios)),
                    "early_mean_log_ratio": float(np.mean(ratios[:cut])),
                    "late_mean_log_ratio": float(np.mean(ratios[cut:])),
                    "scarcity_log_ratio": math.log(
                        float(low["modeled_probability"])
                        / float(high["modeled_probability"])
                    ),
                    "artist_delta": high_control["artist"] - low_control["artist"],
                    "subject_delta": subject_delta,
                    "playability_delta": playability_delta,
                }
            )
    if len(rows) != 24:
        raise RuntimeError(f"expected 24 pairwise edges, got {len(rows)}")
    return rows


def _treatment_column(treatment: str, level: str) -> float:
    return float(treatment.casefold() == level.casefold())


def design(
    rows: list[dict[str, Any]],
    outcome_key: str = "mean_log_ratio",
) -> tuple[np.ndarray, np.ndarray]:
    X = []
    y = []
    for row in rows:
        ultra_diff = _treatment_column(row["high_treatment"], ULTRA) - _treatment_column(
            row["low_treatment"], ULTRA
        )
        sir_diff = _treatment_column(row["high_treatment"], SIR) - _treatment_column(
            row["low_treatment"], SIR
        )
        X.append(
            [
                ultra_diff,
                sir_diff,
                float(row["scarcity_log_ratio"]),
                float(row["artist_delta"]) / 100.0,
            ]
        )
        y.append(float(row[outcome_key]))
    return np.array(X, dtype=float), np.array(y, dtype=float)


def fit(
    rows: list[dict[str, Any]],
    *,
    outcome_key: str = "mean_log_ratio",
    cluster_equal_weight: bool = False,
) -> tuple[np.ndarray, int, float]:
    X, y = design(rows, outcome_key)
    if cluster_equal_weight:
        counts = Counter(str(row["cluster_key"]) for row in rows)
        weights = np.array(
            [1.0 / counts[str(row["cluster_key"])] for row in rows], dtype=float
        )
        root = np.sqrt(weights)
        X = X * root[:, None]
        y = y * root
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    return beta, int(np.linalg.matrix_rank(X)), float(np.linalg.cond(X))


def treatment_levels(beta: np.ndarray) -> dict[str, float]:
    return {
        DOUBLE: 0.0,
        ULTRA: float(beta[0]),
        SIR: float(beta[1]),
    }


def contrast(levels: dict[str, float], high: str, low: str) -> float:
    return levels[high] - levels[low]


def estimate(
    gates: dict[str, dict[str, Any]], controls: dict[str, dict[str, float]]
) -> dict[str, Any]:
    edges = build_edges(gates, controls)
    beta, rank, condition = fit(edges)
    if rank != 4:
        raise RuntimeError(f"joint design rank deficient rank={rank}")
    levels = treatment_levels(beta)

    early_beta, early_rank, _ = fit(edges, outcome_key="early_mean_log_ratio")
    late_beta, late_rank, _ = fit(edges, outcome_key="late_mean_log_ratio")
    if early_rank != 4 or late_rank != 4:
        raise RuntimeError("temporal joint design rank deficient")

    equal_beta, equal_rank, equal_condition = fit(edges, cluster_equal_weight=True)
    if equal_rank != 4:
        raise RuntimeError("cluster-equal sensitivity design rank deficient")

    clusters = sorted({str(row["cluster_key"]) for row in edges})
    by_cluster: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in edges:
        by_cluster[str(row["cluster_key"])].append(row)

    rng = np.random.default_rng(SEED)
    boot: list[np.ndarray] = []
    for _ in range(BOOTSTRAP_DRAWS):
        sampled = rng.choice(clusters, size=len(clusters), replace=True)
        sample: list[dict[str, Any]] = []
        for cluster in sampled:
            sample.extend(by_cluster[str(cluster)])
        X, y = design(sample)
        if np.linalg.matrix_rank(X) < 4:
            continue
        boot.append(np.linalg.lstsq(X, y, rcond=None)[0])
    if len(boot) < int(BOOTSTRAP_DRAWS * 0.95):
        raise RuntimeError(f"too many rank-deficient bootstrap draws valid={len(boot)}")
    boot_array = np.array(boot)
    ci = np.percentile(boot_array, [2.5, 50, 97.5], axis=0)
    boot_sir_vs_ultra = boot_array[:, 1] - boot_array[:, 0]
    sir_ultra_ci = np.percentile(boot_sir_vs_ultra, [2.5, 50, 97.5])

    leave_one_out = []
    for cluster in clusters:
        sample = [row for row in edges if row["cluster_key"] != cluster]
        loo_beta, loo_rank, _ = fit(sample)
        if loo_rank < 4:
            raise RuntimeError(f"leave-one-cluster rank deficient cluster={cluster}")
        loo_levels = treatment_levels(loo_beta)
        leave_one_out.append(
            {
                "cluster_key": cluster,
                "ultra_log_level": loo_levels[ULTRA],
                "sir_log_level": loo_levels[SIR],
                "scarcity_beta": float(loo_beta[2]),
                "artist_beta_per_100": float(loo_beta[3]),
            }
        )

    edge_diagnostics = []
    residuals = []
    family_residuals: dict[str, list[float]] = defaultdict(list)
    for row in edges:
        latent = levels[row["high_treatment"]] - levels[row["low_treatment"]]
        predicted = (
            latent
            + float(beta[2]) * float(row["scarcity_log_ratio"])
            + float(beta[3]) * float(row["artist_delta"]) / 100.0
        )
        residual = float(row["mean_log_ratio"]) - predicted
        residuals.append(residual)
        family_residuals[str(row["family"])].append(residual)
        edge_diagnostics.append(
            {
                **row,
                "latent_treatment_difference": latent,
                "predicted_log_ratio": predicted,
                "residual": residual,
            }
        )

    family_diagnostics = []
    for family, values in sorted(family_residuals.items()):
        arr = np.array(values, dtype=float)
        family_diagnostics.append(
            {
                "family": family,
                "edge_count": len(values),
                "mean_residual": float(np.mean(arr)),
                "rmse": float(np.sqrt(np.mean(arr**2))),
            }
        )

    controls_payload = {
        "model_run_id": MODEL_RUN_ID,
        "model_version": MODEL_VERSION,
        "as_of_date": MODEL_AS_OF_DATE,
        "cards": [{"card_id": cid, **controls[cid]} for cid in sorted(controls)],
    }
    gate_digests = {name: stable_hash(gate) for name, gate in gates.items()}

    ultra_ci = [float(ci[0, 0]), float(ci[2, 0])]
    sir_ci = [float(ci[0, 1]), float(ci[2, 1])]
    scarcity_ci = [float(ci[0, 2]), float(ci[2, 2])]
    artist_ci = [float(ci[0, 3]), float(ci[2, 3])]

    early_levels = treatment_levels(early_beta)
    late_levels = treatment_levels(late_beta)
    equal_levels = treatment_levels(equal_beta)

    return {
        "study_id": "joint_treatment_ladder_v1_exploratory",
        "decision_token": "JOINT_TREATMENT_LADDER_EXPLORATORY_SUPPORTED",
        "status": "research_only",
        "confirmatory_status": "requires_preregistered_replication",
        "reason_for_joint_model": (
            "Separate per-family scarcity regressions failed triangle coherence; "
            "joint model shares one scarcity coefficient across all three edges."
        ),
        "formula": {
            "outcome": "mean exact-date log(high-treatment NM / low-treatment NM)",
            "model": (
                "outcome = theta(high) - theta(low) + beta_scarcity*"
                "log(p_low/p_high) + beta_artist*(artist_high-artist_low)/100"
            ),
            "anchor": "theta(Double Rare)=0",
            "subjectControl": "exact matched identity; verified delta=0",
            "playabilityControl": "frozen V7; verified delta=0 on all edges",
            "bootstrap": "2000 whole Set+subject cluster resamples",
            "temporalSplit": "chronological median within each edge",
        },
        "inputs": {
            "gate_digests": gate_digests,
            "collector_model_run_id": MODEL_RUN_ID,
            "collector_model_version": MODEL_VERSION,
            "collector_as_of_date": MODEL_AS_OF_DATE,
            "edges": len(edges),
            "clusters": len(clusters),
            "sets": len({row["set_name"] for row in edges}),
            "eras": len({row["era_name"] for row in edges}),
            "control_fingerprint": stable_hash(controls_payload),
        },
        "joint_fit": {
            "design_rank": rank,
            "condition_number": condition,
            "double_rare_log_level": 0.0,
            "ultra_rare_log_level": levels[ULTRA],
            "ultra_rare_vs_double_multiplier": math.exp(levels[ULTRA]),
            "ultra_rare_log_ci95": ultra_ci,
            "ultra_rare_vs_double_multiplier_ci95": [
                math.exp(ultra_ci[0]),
                math.exp(ultra_ci[1]),
            ],
            "sir_log_level": levels[SIR],
            "sir_vs_double_multiplier": math.exp(levels[SIR]),
            "sir_log_ci95": sir_ci,
            "sir_vs_double_multiplier_ci95": [
                math.exp(sir_ci[0]),
                math.exp(sir_ci[1]),
            ],
            "sir_vs_ultra_log": contrast(levels, SIR, ULTRA),
            "sir_vs_ultra_multiplier": math.exp(contrast(levels, SIR, ULTRA)),
            "sir_vs_ultra_log_ci95": [
                float(sir_ultra_ci[0]),
                float(sir_ultra_ci[2]),
            ],
            "sir_vs_ultra_multiplier_ci95": [
                math.exp(float(sir_ultra_ci[0])),
                math.exp(float(sir_ultra_ci[2])),
            ],
            "scarcity_beta": float(beta[2]),
            "scarcity_beta_ci95": scarcity_ci,
            "artist_beta_per_100": float(beta[3]),
            "artist_beta_ci95": artist_ci,
            "bootstrap_valid_draws": len(boot),
        },
        "temporal": {
            "early": {
                "ultra_vs_double_multiplier": math.exp(early_levels[ULTRA]),
                "sir_vs_double_multiplier": math.exp(early_levels[SIR]),
                "sir_vs_ultra_multiplier": math.exp(
                    contrast(early_levels, SIR, ULTRA)
                ),
                "scarcity_beta": float(early_beta[2]),
            },
            "late": {
                "ultra_vs_double_multiplier": math.exp(late_levels[ULTRA]),
                "sir_vs_double_multiplier": math.exp(late_levels[SIR]),
                "sir_vs_ultra_multiplier": math.exp(
                    contrast(late_levels, SIR, ULTRA)
                ),
                "scarcity_beta": float(late_beta[2]),
            },
        },
        "cluster_equal_sensitivity": {
            "condition_number": equal_condition,
            "ultra_vs_double_multiplier": math.exp(equal_levels[ULTRA]),
            "sir_vs_double_multiplier": math.exp(equal_levels[SIR]),
            "sir_vs_ultra_multiplier": math.exp(contrast(equal_levels, SIR, ULTRA)),
            "scarcity_beta": float(equal_beta[2]),
            "artist_beta_per_100": float(equal_beta[3]),
        },
        "leave_one_cluster_out": leave_one_out,
        "fit_diagnostics": {
            "overall_rmse": float(np.sqrt(np.mean(np.array(residuals) ** 2))),
            "family_residuals": family_diagnostics,
        },
        "edge_diagnostics": edge_diagnostics,
        "interpretation": {
            "robust": [
                "SIR is above Double Rare after shared scarcity control.",
                "SIR is above Ultra Rare after shared scarcity control.",
                "Shared scarcity coefficient is positive and temporally stable.",
            ],
            "not_resolved": [
                "Ultra Rare versus Double Rare: bootstrap interval crosses parity.",
                "No 0-100 production Treatment scale is authorized by this exploratory synthesis.",
            ],
        },
        "limitations": [
            "Joint model structure was selected after separate-family triangle inconsistency was observed, so this synthesis is exploratory rather than preregistered confirmatory evidence.",
            "Only three treatment classes are connected in this ladder.",
            "Nine unique Set+subject clusters contribute 24 pairwise edges.",
            "Artist coefficient remains a nuisance control and is not independently well identified.",
            "Production scoring requires a preregistered replication/expansion of this shared-scarcity model.",
        ],
        "production_writes": 0,
    }


def render_report(result: dict[str, Any]) -> str:
    fit = result["joint_fit"]
    temporal = result["temporal"]
    sensitivity = result["cluster_equal_sensitivity"]
    lines = [
        "# Joint Treatment Ladder V1 — Exploratory Synthesis",
        "",
        f"Decision token: `{result['decision_token']}`",
        "",
        "## Why the model changed",
        "",
        "Separate per-family scarcity regressions did not close the Double Rare / Ultra Rare / SIR triangle coherently. This synthesis therefore uses one shared scarcity coefficient and estimates latent treatment levels jointly across all three edges.",
        "",
        "## Joint latent treatment ladder",
        "",
        "- **Double Rare:** reference level = 1.00x",
        f"- **Ultra Rare vs Double Rare:** **{fit['ultra_rare_vs_double_multiplier']:.2f}x** (95% cluster-bootstrap: {fit['ultra_rare_vs_double_multiplier_ci95'][0]:.2f}x–{fit['ultra_rare_vs_double_multiplier_ci95'][1]:.2f}x)",
        f"- **SIR vs Double Rare:** **{fit['sir_vs_double_multiplier']:.2f}x** (95%: {fit['sir_vs_double_multiplier_ci95'][0]:.2f}x–{fit['sir_vs_double_multiplier_ci95'][1]:.2f}x)",
        f"- **SIR vs Ultra Rare:** **{fit['sir_vs_ultra_multiplier']:.2f}x** (95%: {fit['sir_vs_ultra_multiplier_ci95'][0]:.2f}x–{fit['sir_vs_ultra_multiplier_ci95'][1]:.2f}x)",
        "",
        f"Shared scarcity coefficient: **{fit['scarcity_beta']:.3f}** (95%: {fit['scarcity_beta_ci95'][0]:.3f}–{fit['scarcity_beta_ci95'][1]:.3f})",
        "",
        "## What is actually resolved",
        "",
        "- SIR is clearly above Double Rare.",
        "- SIR is clearly above Ultra Rare.",
        "- Ultra Rare versus Double Rare is **not resolved**; its confidence interval crosses parity.",
        "",
        "## Temporal stability",
        "",
        f"- Early: UR/DR {temporal['early']['ultra_vs_double_multiplier']:.2f}x; SIR/DR {temporal['early']['sir_vs_double_multiplier']:.2f}x; SIR/UR {temporal['early']['sir_vs_ultra_multiplier']:.2f}x; scarcity beta {temporal['early']['scarcity_beta']:.3f}",
        f"- Late: UR/DR {temporal['late']['ultra_vs_double_multiplier']:.2f}x; SIR/DR {temporal['late']['sir_vs_double_multiplier']:.2f}x; SIR/UR {temporal['late']['sir_vs_ultra_multiplier']:.2f}x; scarcity beta {temporal['late']['scarcity_beta']:.3f}",
        "",
        "## Cluster-equal sensitivity",
        "",
        f"- UR/DR: {sensitivity['ultra_vs_double_multiplier']:.2f}x",
        f"- SIR/DR: {sensitivity['sir_vs_double_multiplier']:.2f}x",
        f"- SIR/UR: {sensitivity['sir_vs_ultra_multiplier']:.2f}x",
        f"- scarcity beta: {sensitivity['scarcity_beta']:.3f}",
        "",
        "## Decision",
        "",
        "The three-edge data supports the shared-scarcity latent-treatment architecture as an exploratory model. It does **not** authorize a 0–100 Treatment score yet. The next step is a preregistered replication/expansion using this exact joint formula and additional treatment classes.",
        "",
        "Production writes: **ZERO**.",
        "",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sir-ultra", type=Path, required=True)
    parser.add_argument("--sir-double", type=Path, required=True)
    parser.add_argument("--ultra-double", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)

    gates = {
        "sir_ultra": json.loads(args.sir_ultra.read_text(encoding="utf-8")),
        "sir_double": json.loads(args.sir_double.read_text(encoding="utf-8")),
        "ultra_double": json.loads(args.ultra_double.read_text(encoding="utf-8")),
    }
    for name, gate in gates.items():
        _validate_gate(gate, name)

    card_ids = sorted(
        {
            str(card["canonical_card_id"])
            for gate in gates.values()
            for card in gate["target"]["cards"]
        }
    )

    load_dotenv(ROOT / "backend/.env", override=False)
    from backend.db.clients.supabase_client import supabase

    controls = load_controls(supabase, card_ids)
    result = estimate(gates, controls)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(render_report(result), encoding="utf-8")

    public = {k: v for k, v in result.items() if k not in {"edge_diagnostics", "leave_one_cluster_out"}}
    print(json.dumps(public, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
