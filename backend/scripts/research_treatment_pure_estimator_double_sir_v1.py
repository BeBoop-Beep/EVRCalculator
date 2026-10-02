"""Research-only PURE_TREATMENT estimator for SIR vs Double Rare.

Consumes a previously captured exact-NM gate artifact, reads frozen Collector V7
controls by explicit model_run_id, and estimates a scarcity-controlled treatment
premium. No production writes.
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
SIR = "Special Illustration Rare"
DOUBLE = "Double Rare"


def stable_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _chunks(values: list[str], size: int = 100):
    for start in range(0, len(values), size):
        yield values[start:start + size]


def fit_ols(rows: list[dict[str, Any]], *, pure: bool) -> tuple[np.ndarray, int, float]:
    y = np.array([float(row["mean_log_ratio"]) for row in rows], dtype=float)
    if pure:
        X = np.array(
            [
                [
                    1.0,
                    float(row["scarcity_log_ratio"]),
                    float(row["artist_delta"]) / 100.0,
                ]
                for row in rows
            ],
            dtype=float,
        )
    else:
        X = np.array(
            [[1.0, float(row["artist_delta"]) / 100.0] for row in rows],
            dtype=float,
        )
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    return beta, int(np.linalg.matrix_rank(X)), float(np.linalg.cond(X))


def load_controls(db: Any, card_ids: list[str]) -> dict[str, dict[str, Any]]:
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
    out: dict[str, dict[str, Any]] = {}
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


def build_pairs(gate: dict[str, Any], controls: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    cards = list(gate["target"]["cards"])
    panels = dict(gate["panels"])
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for card in cards:
        grouped[(str(card["set_name"]), str(card["subject_key"]))].append(card)

    pairs: list[dict[str, Any]] = []
    for (set_name, subject_key), group in sorted(grouped.items()):
        if len(group) != 2 or {str(card["rarity"]) for card in group} != {SIR, DOUBLE}:
            raise RuntimeError(f"unexpected treatment group {set_name} {subject_key}")
        sir = next(card for card in group if card["rarity"] == SIR)
        double = next(card for card in group if card["rarity"] == DOUBLE)

        sir_history = {
            str(row["date"]): float(row["price"])
            for row in panels[str(sir["canonical_card_id"])]["history"]
        }
        double_history = {
            str(row["date"]): float(row["price"])
            for row in panels[str(double["canonical_card_id"])]["history"]
        }
        shared = sorted(set(sir_history) & set(double_history))
        if len(shared) < 30:
            raise RuntimeError(f"pair fell below frozen readiness gate {set_name} {subject_key}")
        ratios = [
            math.log(sir_history[day] / double_history[day])
            for day in shared
            if sir_history[day] > 0 and double_history[day] > 0
        ]
        if len(ratios) != len(shared):
            raise RuntimeError(f"non-positive historical price {set_name} {subject_key}")

        sir_control = controls[str(sir["canonical_card_id"])]
        double_control = controls[str(double["canonical_card_id"])]
        subject_delta = sir_control["subject"] - double_control["subject"]
        playability_delta = sir_control["playability"] - double_control["playability"]
        if abs(subject_delta) > 1e-9:
            raise RuntimeError(f"subject control does not cancel {set_name} {subject_key}")
        if abs(playability_delta) > 1e-9:
            raise RuntimeError(f"playability control does not cancel {set_name} {subject_key}")

        cut = len(shared) // 2
        pairs.append(
            {
                "era_name": str(sir["era_name"]),
                "set_name": set_name,
                "subject_key": subject_key,
                "sir_card_id": str(sir["canonical_card_id"]),
                "double_card_id": str(double["canonical_card_id"]),
                "shared_dates": len(shared),
                "first_date": shared[0],
                "last_date": shared[-1],
                "mean_log_ratio": float(np.mean(ratios)),
                "median_log_ratio": float(np.median(ratios)),
                "early_mean_log_ratio": float(np.mean(ratios[:cut])),
                "late_mean_log_ratio": float(np.mean(ratios[cut:])),
                "sir_probability": float(sir["modeled_probability"]),
                "double_probability": float(double["modeled_probability"]),
                "scarcity_log_ratio": math.log(
                    float(double["modeled_probability"]) / float(sir["modeled_probability"])
                ),
                "artist_delta": sir_control["artist"] - double_control["artist"],
                "playability_delta": playability_delta,
                "subject_delta": subject_delta,
                "raw_price_multiplier": math.exp(float(np.mean(ratios))),
            }
        )

    if len(pairs) != 8:
        raise RuntimeError(f"expected 8 matched identities, got {len(pairs)}")
    return pairs


def estimate(gate: dict[str, Any], controls: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if gate.get("status") != "COMPLETE":
        raise RuntimeError("gate artifact is not complete")
    if gate.get("cross_era_progression") is not True:
        raise RuntimeError("frozen cross-era gate did not pass")
    if int(gate.get("production_writes") or 0) != 0:
        raise RuntimeError("gate artifact reports production writes")

    pairs = build_pairs(gate, controls)
    pure, rank, condition_number = fit_ols(pairs, pure=True)
    package, _, _ = fit_ols(pairs, pure=False)

    early = [{**row, "mean_log_ratio": row["early_mean_log_ratio"]} for row in pairs]
    late = [{**row, "mean_log_ratio": row["late_mean_log_ratio"]} for row in pairs]
    early_beta, _, _ = fit_ols(early, pure=True)
    late_beta, _, _ = fit_ols(late, pure=True)

    rng = np.random.default_rng(SEED)
    bootstrap = []
    for _ in range(BOOTSTRAP_DRAWS):
        indices = rng.integers(0, len(pairs), len(pairs))
        sample = [pairs[int(index)] for index in indices]
        pure_sample, _, _ = fit_ols(sample, pure=True)
        package_sample, _, _ = fit_ols(sample, pure=False)
        bootstrap.append([*map(float, pure_sample), *map(float, package_sample)])
    bootstrap_array = np.array(bootstrap)
    ci = np.percentile(bootstrap_array, [2.5, 50, 97.5], axis=0)

    for row in pairs:
        row["pure_log_effect"] = (
            row["mean_log_ratio"]
            - float(pure[1]) * row["scarcity_log_ratio"]
            - float(pure[2]) * (row["artist_delta"] / 100.0)
        )
        row["pure_multiplier"] = math.exp(row["pure_log_effect"])

    set_rows = []
    for era_name, set_name in sorted(
        {(row["era_name"], row["set_name"]) for row in pairs}
    ):
        values = [
            row["pure_log_effect"]
            for row in pairs
            if row["era_name"] == era_name and row["set_name"] == set_name
        ]
        mean_value = float(np.mean(values))
        set_rows.append(
            {
                "era_name": era_name,
                "set_name": set_name,
                "identity_count": len(values),
                "mean_pure_log_effect": mean_value,
                "pure_multiplier": math.exp(mean_value),
            }
        )

    era_rows = []
    for era_name in sorted({row["era_name"] for row in pairs}):
        values = [
            row["pure_log_effect"] for row in pairs if row["era_name"] == era_name
        ]
        mean_value = float(np.mean(values))
        era_rows.append(
            {
                "era_name": era_name,
                "identity_count": len(values),
                "mean_pure_log_effect": mean_value,
                "pure_multiplier": math.exp(mean_value),
            }
        )

    leave_one_out = []
    for index, row in enumerate(pairs):
        sample = pairs[:index] + pairs[index + 1 :]
        beta, _, _ = fit_ols(sample, pure=True)
        leave_one_out.append(
            {
                "dropped_set": row["set_name"],
                "dropped_subject": row["subject_key"],
                "pure_intercept_log": float(beta[0]),
                "pure_multiplier": math.exp(float(beta[0])),
            }
        )

    controls_payload = {
        "model_run_id": MODEL_RUN_ID,
        "model_version": MODEL_VERSION,
        "as_of_date": MODEL_AS_OF_DATE,
        "cards": [{"card_id": cid, **controls[cid]} for cid in sorted(controls)],
    }

    return {
        "study_id": "pure_treatment_sir_double_v1",
        "decision_token": "PURE_TREATMENT_SIR_DOUBLE_PILOT_ESTIMATED",
        "formula": {
            "pairOutcome": "mean exact-date log(SIR_NM_price / DoubleRare_NM_price)",
            "packageModel": "outcome ~ intercept + artist_delta/100",
            "pureModel": "outcome ~ intercept + log(DR_pull_probability/SIR_pull_probability) + artist_delta/100",
            "subjectControl": "exact matched identity; verified delta=0",
            "playabilityControl": "frozen V7 score; verified delta=0 for all 8 pairs",
            "bootstrap": "2000 whole matched-identity pair resamples",
            "temporalSplit": "chronological median within each pair",
        },
        "inputs": {
            "gate_artifact_digest": stable_hash(gate),
            "control_fingerprint": stable_hash(controls_payload),
            "collector_model_run_id": MODEL_RUN_ID,
            "collector_model_version": MODEL_VERSION,
            "collector_as_of_date": MODEL_AS_OF_DATE,
            "pairs": len(pairs),
            "sets": len(set_rows),
            "eras": len(era_rows),
        },
        "package": {
            "intercept_log": float(package[0]),
            "multiplier": math.exp(float(package[0])),
            "artist_beta_per_100": float(package[1]),
            "bootstrap_intercept_log_ci95": [float(ci[0, 3]), float(ci[2, 3])],
            "bootstrap_multiplier_ci95": [
                math.exp(float(ci[0, 3])),
                math.exp(float(ci[2, 3])),
            ],
        },
        "pure": {
            "intercept_log": float(pure[0]),
            "multiplier": math.exp(float(pure[0])),
            "scarcity_beta": float(pure[1]),
            "artist_beta_per_100": float(pure[2]),
            "design_rank": rank,
            "design_condition_number": condition_number,
            "bootstrap_intercept_log_ci95": [float(ci[0, 0]), float(ci[2, 0])],
            "bootstrap_multiplier_ci95": [
                math.exp(float(ci[0, 0])),
                math.exp(float(ci[2, 0])),
            ],
            "bootstrap_scarcity_beta_ci95": [float(ci[0, 1]), float(ci[2, 1])],
            "bootstrap_artist_beta_ci95": [float(ci[0, 2]), float(ci[2, 2])],
        },
        "scarcity_association": {
            "package_minus_pure_log": float(package[0] - pure[0]),
            "share_of_package_log_premium": float((package[0] - pure[0]) / package[0]),
        },
        "temporal": {
            "early_pure_intercept_log": float(early_beta[0]),
            "early_multiplier": math.exp(float(early_beta[0])),
            "late_pure_intercept_log": float(late_beta[0]),
            "late_multiplier": math.exp(float(late_beta[0])),
            "same_positive_sign": bool(early_beta[0] > 0 and late_beta[0] > 0),
        },
        "pairs": pairs,
        "sets": set_rows,
        "eras": era_rows,
        "leave_one_pair_out": leave_one_out,
        "robustness": {
            "all_pair_adjusted_effects_positive": all(
                row["pure_log_effect"] > 0 for row in pairs
            ),
            "leave_one_pair_out_multiplier_min": min(
                row["pure_multiplier"] for row in leave_one_out
            ),
            "leave_one_pair_out_multiplier_max": max(
                row["pure_multiplier"] for row in leave_one_out
            ),
        },
        "limitations": [
            "Minimal preregistered gate-clearing pilot: 8 matched identities / 4 Sets / 2 eras.",
            "Scarcity and artist nuisance coefficients are estimated from only 8 independent matched pairs.",
            "Artist bootstrap interval may include zero; treatment intercept is more stable than nuisance coefficient estimates.",
            "This is research evidence only and does not define a production Treatment score.",
        ],
        "production_writes": 0,
    }


def render_report(result: dict[str, Any]) -> str:
    pure = result["pure"]
    package = result["package"]
    temporal = result["temporal"]
    scarcity = result["scarcity_association"]
    robust = result["robustness"]
    lines = [
        "# PURE_TREATMENT SIR vs Double Rare V1 — Pilot Result",
        "",
        f"Decision token: `{result['decision_token']}`",
        "",
        "## Main result",
        "",
        f"- Treatment Package premium after Artist control, before scarcity control: **{package['multiplier']:.2f}x**",
        f"- Package bootstrap 95% interval: **{package['bootstrap_multiplier_ci95'][0]:.2f}x–{package['bootstrap_multiplier_ci95'][1]:.2f}x**",
        f"- Scarcity-controlled PURE_TREATMENT premium: **{pure['multiplier']:.2f}x**",
        f"- Whole-pair bootstrap 95% interval: **{pure['bootstrap_multiplier_ci95'][0]:.2f}x–{pure['bootstrap_multiplier_ci95'][1]:.2f}x**",
        f"- Scarcity coefficient: **{pure['scarcity_beta']:.3f}**",
        f"- Scarcity-associated share of the Artist-controlled package log-premium: **{100*scarcity['share_of_package_log_premium']:.1f}%**",
        "",
        "## Temporal stability",
        "",
        f"- Early half: **{temporal['early_multiplier']:.2f}x**",
        f"- Late half: **{temporal['late_multiplier']:.2f}x**",
        f"- Same positive sign: **{str(temporal['same_positive_sign']).lower()}**",
        "",
        "## Set-level adjusted effects",
        "",
        "| Era | Set | Identities | Pure SIR multiplier |",
        "|---|---|---:|---:|",
    ]
    for row in result["sets"]:
        lines.append(
            f"| {row['era_name']} | {row['set_name']} | {row['identity_count']} | {row['pure_multiplier']:.2f}x |"
        )
    lines.extend(["", "## Era-level adjusted effects", ""])
    for row in result["eras"]:
        lines.append(
            f"- **{row['era_name']}**: {row['pure_multiplier']:.2f}x across {row['identity_count']} identities"
        )
    lines.extend(
        [
            "",
            "## Influence robustness",
            "",
            f"- Leave-one-identity-out global multiplier range: **{robust['leave_one_pair_out_multiplier_min']:.2f}x–{robust['leave_one_pair_out_multiplier_max']:.2f}x**",
            f"- All eight adjusted matched-pair effects positive: **{str(robust['all_pair_adjusted_effects_positive']).lower()}**",
            f"- Design rank: **{pure['design_rank']}**; condition number: **{pure['design_condition_number']:.2f}**",
            "",
            "## Interpretation",
            "",
            "This pilot supports a large SIR-over-Double-Rare treatment/presentation signal beyond modeled pull scarcity alone and validates the Set → Era → Cross-Era research architecture for this treatment family. It does not justify a universal production SIR score; additional treatment families must be estimated before a cross-family Treatment Appeal authority is constructed.",
            "",
            "Production writes: **ZERO**.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate-artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)

    load_dotenv(ROOT / "backend/.env", override=False)
    from backend.db.clients.supabase_client import supabase

    gate = json.loads(args.gate_artifact.read_text(encoding="utf-8"))
    card_ids = [str(card["canonical_card_id"]) for card in gate["target"]["cards"]]
    controls = load_controls(supabase, card_ids)
    result = estimate(gate, controls)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(render_report(result), encoding="utf-8")

    public = {key: value for key, value in result.items() if key not in {"pairs", "leave_one_pair_out"}}
    print(json.dumps(public, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
