"""Set-first scarcity-controlled Treatment estimator for Hyper Rare / Ultra Rare / SIR.

Consumes the exhaustive full-family artifact. Research only; zero production writes.
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
HR = "Hyper Rare"
UR = "Ultra Rare"
SIR = "Special Illustration Rare"
SEED = 20261002
BOOTSTRAP_DRAWS = 2000
MAX_BOOTSTRAP_ATTEMPTS = 30000


def stable_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def chunks(values: list[str], size: int = 100):
    for start in range(0, len(values), size):
        yield values[start:start + size]


def load_controls(db: Any, card_ids: list[str]) -> dict[str, dict[str, float]]:
    rows: list[dict[str, Any]] = []
    for chunk in chunks(card_ids):
        rows.extend(
            db.table("pokemon_card_collector_appeal_scores")
            .select(
                "pokemon_canonical_card_id,subject_baseline_score,"
                "artist_recognition_score,playability_score,"
                "price_input_excluded,treatment_input_excluded"
            )
            .eq("model_run_id", MODEL_RUN_ID)
            .in_("pokemon_canonical_card_id", chunk)
            .execute().data
            or []
        )
    if len(rows) != len(card_ids):
        raise RuntimeError(f"control coverage mismatch expected={len(card_ids)} got={len(rows)}")
    out: dict[str, dict[str, float]] = {}
    for row in rows:
        cid = str(row["pokemon_canonical_card_id"])
        if row.get("price_input_excluded") is not True or row.get("treatment_input_excluded") is not True:
            raise RuntimeError(f"frozen control contract violated {cid}")
        out[cid] = {
            "subject": float(row["subject_baseline_score"]),
            "artist": 0.0 if row.get("artist_recognition_score") is None else float(row["artist_recognition_score"]),
            "playability": 0.0 if row.get("playability_score") is None else float(row["playability_score"]),
        }
    return out


def build_rows(artifact: dict[str, Any], controls: dict[str, dict[str, float]]):
    if artifact.get("status") != "COMPLETE" or artifact.get("progression_pass") is not True:
        raise RuntimeError("full Hyper family artifact did not pass frozen progression gate")
    if int(artifact.get("production_writes") or 0) != 0:
        raise RuntimeError("artifact reports production writes")

    cards = list(artifact["target"]["cards"])
    panels = dict(artifact["panels"])
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for card in cards:
        groups[(str(card["set_name"]), str(card["subject_key"]))].append(card)

    rows: list[dict[str, Any]] = []
    subjects: list[dict[str, Any]] = []
    for (set_name, subject_key), group in sorted(groups.items()):
        by = {str(card["rarity"]): card for card in group}
        if set(by) != {HR, UR, SIR}:
            raise RuntimeError(f"incomplete Hyper triangle {set_name} {subject_key}: {sorted(by)}")

        histories: dict[str, dict[str, float]] = {}
        common: set[str] | None = None
        for treatment in (HR, UR, SIR):
            cid = str(by[treatment]["canonical_card_id"])
            histories[treatment] = {
                str(item["date"]): float(item["price"])
                for item in panels[cid]["history"]
            }
            dates = set(histories[treatment])
            common = dates if common is None else common & dates

        shared = sorted(common or set())
        if len(shared) < 30:
            raise RuntimeError(f"triangle below frozen moderate gate {set_name} {subject_key} {len(shared)}")
        status = "PANEL_READY_STRONG" if len(shared) >= 90 else "PANEL_READY_MODERATE"

        ur = by[UR]
        urc = controls[str(ur["canonical_card_id"])]
        cut = len(shared) // 2
        for treatment, contrast in ((HR, "hyper"), (SIR, "sir")):
            card = by[treatment]
            control = controls[str(card["canonical_card_id"])]
            if abs(control["subject"] - urc["subject"]) > 1e-9:
                raise RuntimeError(f"subject control mismatch {set_name} {subject_key} {treatment}")
            ratios = [
                math.log(histories[treatment][day] / histories[UR][day])
                for day in shared
            ]
            rows.append(
                {
                    "era_name": str(card["era_name"]),
                    "set_name": set_name,
                    "subject_key": subject_key,
                    "contrast": contrast,
                    "shared_dates": len(shared),
                    "panel_status": status,
                    "mean_log_ratio": float(np.mean(ratios)),
                    "early_mean_log_ratio": float(np.mean(ratios[:cut])),
                    "late_mean_log_ratio": float(np.mean(ratios[cut:])),
                    "scarcity_log_ratio": math.log(
                        float(ur["modeled_probability"]) / float(card["modeled_probability"])
                    ),
                    "artist_delta": control["artist"] - urc["artist"],
                    "playability_delta": control["playability"] - urc["playability"],
                }
            )
        subjects.append(
            {
                "era_name": str(ur["era_name"]),
                "set_name": set_name,
                "subject_key": subject_key,
                "shared_dates": len(shared),
                "panel_status": status,
            }
        )

    if len(subjects) != 11 or len(rows) != 22:
        raise RuntimeError(f"unexpected exhaustive Hyper size subjects={len(subjects)} rows={len(rows)}")
    return rows, subjects


def fit(rows: list[dict[str, Any]], key: str = "mean_log_ratio"):
    y = np.array([float(row[key]) for row in rows], dtype=float)
    X = np.array(
        [
            [
                1.0 if row["contrast"] == "hyper" else 0.0,
                1.0 if row["contrast"] == "sir" else 0.0,
                float(row["scarcity_log_ratio"]),
                float(row["artist_delta"]) / 100.0,
                float(row["playability_delta"]) / 100.0,
            ]
            for row in rows
        ],
        dtype=float,
    )
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    return beta, int(np.linalg.matrix_rank(X)), float(np.linalg.cond(X))


def transform(beta: np.ndarray) -> dict[str, float]:
    hyper = float(beta[0])
    sir = float(beta[1])
    return {
        "hyper_vs_ultra_log": hyper,
        "hyper_vs_ultra_multiplier": math.exp(hyper),
        "sir_vs_ultra_log": sir,
        "sir_vs_ultra_multiplier": math.exp(sir),
        "sir_vs_hyper_log": sir - hyper,
        "sir_vs_hyper_multiplier": math.exp(sir - hyper),
        "scarcity_beta": float(beta[2]),
        "artist_beta_per_100": float(beta[3]),
        "playability_beta_per_100": float(beta[4]),
    }


def adjusted_rows(rows: list[dict[str, Any]], beta: np.ndarray):
    out = []
    for row in rows:
        value = (
            float(row["mean_log_ratio"])
            - float(beta[2]) * float(row["scarcity_log_ratio"])
            - float(beta[3]) * float(row["artist_delta"]) / 100.0
            - float(beta[4]) * float(row["playability_delta"]) / 100.0
        )
        out.append({**row, "adjusted_log_effect": value})
    return out


def set_first_hierarchy(rows: list[dict[str, Any]], beta: np.ndarray):
    adjusted = adjusted_rows(rows, beta)
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in adjusted:
        grouped[(row["set_name"], row["contrast"])].append(row["adjusted_log_effect"])

    sets = []
    for set_name in sorted({row["set_name"] for row in adjusted}):
        hyper = float(np.mean(grouped[(set_name, "hyper")]))
        sir = float(np.mean(grouped[(set_name, "sir")]))
        sets.append(
            {
                "set_name": set_name,
                "hyper_vs_ultra_log": hyper,
                "hyper_vs_ultra_multiplier": math.exp(hyper),
                "sir_vs_ultra_log": sir,
                "sir_vs_ultra_multiplier": math.exp(sir),
                "sir_vs_hyper_log": sir - hyper,
                "sir_vs_hyper_multiplier": math.exp(sir - hyper),
            }
        )

    hyper = float(np.mean([row["hyper_vs_ultra_log"] for row in sets]))
    sir = float(np.mean([row["sir_vs_ultra_log"] for row in sets]))
    return {
        "sets": sets,
        "global": {
            "set_count": len(sets),
            "hyper_vs_ultra_log": hyper,
            "hyper_vs_ultra_multiplier": math.exp(hyper),
            "sir_vs_ultra_log": sir,
            "sir_vs_ultra_multiplier": math.exp(sir),
            "sir_vs_hyper_log": sir - hyper,
            "sir_vs_hyper_multiplier": math.exp(sir - hyper),
        },
    }


def estimate(artifact: dict[str, Any], controls: dict[str, dict[str, float]]):
    rows, subjects = build_rows(artifact, controls)
    beta, rank, condition = fit(rows)
    if rank < 5:
        raise RuntimeError(f"Hyper full-family design rank deficient rank={rank}")

    early, erank, _ = fit(rows, "early_mean_log_ratio")
    late, lrank, _ = fit(rows, "late_mean_log_ratio")
    if erank < 5 or lrank < 5:
        raise RuntimeError("Hyper temporal design rank deficient")

    hierarchy = set_first_hierarchy(rows, beta)

    by_subject: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    by_set_subjects: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for row in rows:
        key = (row["set_name"], row["subject_key"])
        by_subject[key].append(row)
    for key in sorted(by_subject):
        by_set_subjects[key[0]].append(key)

    rng = np.random.default_rng(SEED)
    boot_effects = []
    valid = 0
    attempts = 0
    set_names = sorted(by_set_subjects)
    while valid < BOOTSTRAP_DRAWS and attempts < MAX_BOOTSTRAP_ATTEMPTS:
        attempts += 1
        sample = []
        sampled_sets = [set_names[int(i)] for i in rng.integers(0, len(set_names), len(set_names))]
        for set_index, set_name in enumerate(sampled_sets):
            subject_keys = by_set_subjects[set_name]
            sampled_subjects = [
                subject_keys[int(i)] for i in rng.integers(0, len(subject_keys), len(subject_keys))
            ]
            boot_set = f"bootset{set_index}"
            for subject_key in sampled_subjects:
                for row in by_subject[subject_key]:
                    sample.append({**row, "_boot_set": boot_set})
        b, rk, _ = fit(sample)
        if rk < 5 or not np.all(np.isfinite(b)):
            continue
        adjusted = adjusted_rows(sample, b)
        grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
        for row in adjusted:
            grouped[(row["_boot_set"], row["contrast"])].append(row["adjusted_log_effect"])
        hvals = []
        svals = []
        for boot_set in sorted({key[0] for key in grouped}):
            if (boot_set, "hyper") not in grouped or (boot_set, "sir") not in grouped:
                continue
            hvals.append(float(np.mean(grouped[(boot_set, "hyper")])))
            svals.append(float(np.mean(grouped[(boot_set, "sir")])))
        if len(hvals) != len(set_names):
            continue
        h = float(np.mean(hvals))
        s = float(np.mean(svals))
        boot_effects.append([h, s, s - h])
        valid += 1

    if valid < 1000:
        raise RuntimeError(f"insufficient valid Hyper bootstrap draws {valid} attempts={attempts}")
    B = np.array(boot_effects)
    ci = np.percentile(B, [2.5, 50, 97.5], axis=0)
    hierarchy["global"]["bootstrap_hyper_ci95"] = [
        math.exp(float(ci[0, 0])),
        math.exp(float(ci[2, 0])),
    ]
    hierarchy["global"]["bootstrap_sir_ci95"] = [
        math.exp(float(ci[0, 1])),
        math.exp(float(ci[2, 1])),
    ]
    hierarchy["global"]["bootstrap_sir_vs_hyper_ci95"] = [
        math.exp(float(ci[0, 2])),
        math.exp(float(ci[2, 2])),
    ]
    hierarchy["global"]["bootstrap_valid_draws"] = valid

    loo = []
    for key in sorted(by_subject):
        sample = [
            row
            for row in rows
            if (row["set_name"], row["subject_key"]) != key
        ]
        b, rk, cond = fit(sample)
        if rk < 5:
            continue
        h = set_first_hierarchy(sample, b)["global"]
        loo.append(
            {
                "dropped_set": key[0],
                "dropped_subject": key[1],
                "rank": rk,
                "condition_number": cond,
                **h,
            }
        )

    result = {
        "study_id": "treatment_hyper_full_family_set_first_v2",
        "decision_token": "TREATMENT_HYPER_SET_FIRST_HIERARCHY_ESTIMATED",
        "inputs": {
            "artifact_digest": stable_hash(artifact),
            "collector_model_run_id": MODEL_RUN_ID,
            "collector_model_version": MODEL_VERSION,
            "collector_as_of_date": MODEL_AS_OF_DATE,
            "subjects": len(subjects),
            "contrasts": len(rows),
            "sets": len(hierarchy["sets"]),
            "era": "Scarlet and Violet",
        },
        "pooled": {
            **transform(beta),
            "rank": rank,
            "condition_number": condition,
        },
        "hierarchy": hierarchy,
        "temporal": {
            "early": transform(early),
            "late": transform(late),
            "all_contrast_signs_stable": bool(
                np.sign(early[0]) == np.sign(late[0])
                and np.sign(early[1]) == np.sign(late[1])
                and np.sign(early[1] - early[0]) == np.sign(late[1] - late[0])
            ),
        },
        "subjects": subjects,
        "contrasts_detail": rows,
        "leave_one_subject_out": loo,
        "robustness": {
            "loo_hyper_range": [
                min(row["hyper_vs_ultra_multiplier"] for row in loo),
                max(row["hyper_vs_ultra_multiplier"] for row in loo),
            ],
            "loo_sir_range": [
                min(row["sir_vs_ultra_multiplier"] for row in loo),
                max(row["sir_vs_ultra_multiplier"] for row in loo),
            ],
            "loo_sir_vs_hyper_range": [
                min(row["sir_vs_hyper_multiplier"] for row in loo),
                max(row["sir_vs_hyper_multiplier"] for row in loo),
            ],
        },
        "production_writes": 0,
    }
    return result


def render(result: dict[str, Any]) -> str:
    h = result["hierarchy"]["global"]
    p = result["pooled"]
    t = result["temporal"]
    r = result["robustness"]
    lines = [
        "# Set-first Hyper Rare / Ultra Rare / SIR Treatment V2",
        "",
        f"Decision token: `{result['decision_token']}`",
        "",
        "## Set-first S&V hierarchy",
        "",
        "- Ultra Rare anchor: **1.00x**",
        f"- Hyper Rare vs Ultra Rare: **{h['hyper_vs_ultra_multiplier']:.2f}x** "
        f"(nested bootstrap {h['bootstrap_hyper_ci95'][0]:.2f}x–{h['bootstrap_hyper_ci95'][1]:.2f}x)",
        f"- SIR vs Ultra Rare: **{h['sir_vs_ultra_multiplier']:.2f}x** "
        f"(nested bootstrap {h['bootstrap_sir_ci95'][0]:.2f}x–{h['bootstrap_sir_ci95'][1]:.2f}x)",
        f"- SIR vs Hyper Rare: **{h['sir_vs_hyper_multiplier']:.2f}x** "
        f"(nested bootstrap {h['bootstrap_sir_vs_hyper_ci95'][0]:.2f}x–{h['bootstrap_sir_vs_hyper_ci95'][1]:.2f}x)",
        "",
        "## Pooled nuisance model",
        "",
        f"- Hyper/Ultra: **{p['hyper_vs_ultra_multiplier']:.2f}x**",
        f"- SIR/Ultra: **{p['sir_vs_ultra_multiplier']:.2f}x**",
        f"- SIR/Hyper: **{p['sir_vs_hyper_multiplier']:.2f}x**",
        f"- Scarcity beta: **{p['scarcity_beta']:.3f}**",
        f"- Artist beta /100: **{p['artist_beta_per_100']:.3f}**",
        f"- Playability beta /100: **{p['playability_beta_per_100']:.3f}**",
        f"- Rank / condition: **{p['rank']} / {p['condition_number']:.2f}**",
        "",
        "## Set results",
        "",
    ]
    for row in result["hierarchy"]["sets"]:
        lines.append(
            f"- **{row['set_name']}**: Hyper/Ultra {row['hyper_vs_ultra_multiplier']:.2f}x; "
            f"SIR/Ultra {row['sir_vs_ultra_multiplier']:.2f}x; "
            f"SIR/Hyper {row['sir_vs_hyper_multiplier']:.2f}x"
        )
    lines += [
        "",
        "## Temporal / influence",
        "",
        f"- Early Hyper/Ultra {t['early']['hyper_vs_ultra_multiplier']:.2f}x; "
        f"late {t['late']['hyper_vs_ultra_multiplier']:.2f}x",
        f"- Early SIR/Ultra {t['early']['sir_vs_ultra_multiplier']:.2f}x; "
        f"late {t['late']['sir_vs_ultra_multiplier']:.2f}x",
        f"- All contrast signs stable: **{str(t['all_contrast_signs_stable']).lower()}**",
        f"- LOO Hyper/Ultra range: **{r['loo_hyper_range'][0]:.2f}x–{r['loo_hyper_range'][1]:.2f}x**",
        f"- LOO SIR/Ultra range: **{r['loo_sir_range'][0]:.2f}x–{r['loo_sir_range'][1]:.2f}x**",
        f"- LOO SIR/Hyper range: **{r['loo_sir_vs_hyper_range'][0]:.2f}x–{r['loo_sir_vs_hyper_range'][1]:.2f}x**",
        "",
        "Research only. Production writes: **ZERO**.",
        "",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)

    load_dotenv(ROOT / "backend/.env", override=False)
    from backend.db.clients.supabase_client import supabase

    artifact = json.loads(args.artifact.read_text(encoding="utf-8"))
    card_ids = [str(card["canonical_card_id"]) for card in artifact["target"]["cards"]]
    controls = load_controls(supabase, card_ids)
    result = estimate(artifact, controls)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(render(result), encoding="utf-8")
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in {"contrasts_detail", "leave_one_subject_out"}},
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
