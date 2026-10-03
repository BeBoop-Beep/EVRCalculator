"""Confirmatory analyzer for Treatment Direct Preference V1.

Consumes a frozen price-independent pair manifest and human pairwise responses.
Research only. No database writes and no price inputs.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np

STUDY_VERSION = "treatment_direct_preference_v1"
SEED = 20261003
BOOTSTRAP_DRAWS = 2000
MIN_EVALUABLE = 40
MIN_NON_TIE = 20
MIN_TRIAD_COVERAGE = 0.90
MIN_ERA_TRIAD_COVERAGE = 0.80

SIR = "Special Illustration Rare"
ULTRA = "Ultra Rare"
DOUBLE = "Double Rare"
PRIMARY_EDGES = ((SIR, DOUBLE), (SIR, ULTRA), (ULTRA, DOUBLE))


def _edge_key(a: str, b: str) -> str:
    return f"{a}__{b}"


def load_responses(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if text.startswith("["):
        rows = json.loads(text)
        if not isinstance(rows, list):
            raise RuntimeError("response JSON must be a list")
        return [dict(row) for row in rows]
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _manifest_pairs(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    subset = manifest.get("study_subset") or {}
    pairs = list(subset.get("pairs") or [])
    if subset.get("triad_count") != 45 or subset.get("pair_count") != 135:
        raise RuntimeError("frozen study subset size drift")
    if len(pairs) != 135:
        raise RuntimeError("frozen pair list size drift")
    if not subset.get("subject_concentration_gate_le_10pct"):
        raise RuntimeError("frozen subject concentration gate failed")
    return [dict(row) for row in pairs]


def validate_and_dedupe(
    manifest: dict[str, Any],
    responses: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    pairs = _manifest_pairs(manifest)
    by_id = {str(row["underlying_pair_id"]): row for row in pairs}
    if len(by_id) != len(pairs):
        raise RuntimeError("duplicate underlying pair id in manifest")

    validated: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    for index, row in enumerate(responses):
        try:
            if str(row.get("study_version") or "") != STUDY_VERSION:
                raise ValueError("STUDY_VERSION_MISMATCH")
            session = str(row.get("anonymous_session_id") or "").strip()
            pair_id = str(row.get("underlying_pair_id") or "").strip()
            if not session:
                raise ValueError("SESSION_ID_MISSING")
            pair = by_id.get(pair_id)
            if not pair:
                raise ValueError("PAIR_ID_UNKNOWN")
            left = str(row.get("left_card_id") or "")
            right = str(row.get("right_card_id") or "")
            a = str(pair["card_a_id"])
            b = str(pair["card_b_id"])
            if left == a and right == b:
                orientation = "A_LEFT"
            elif left == b and right == a:
                orientation = "B_LEFT"
            else:
                raise ValueError("CARD_ORIENTATION_INVALID")
            receipt = str(row.get("randomized_orientation_receipt") or "")
            if receipt != orientation:
                raise ValueError("ORIENTATION_RECEIPT_MISMATCH")
            response = str(row.get("response") or "").upper()
            if response not in {"LEFT", "RIGHT", "TIE"}:
                raise ValueError("RESPONSE_INVALID")
            submitted = str(row.get("submitted_at") or "")
            if not submitted:
                raise ValueError("SUBMITTED_AT_MISSING")

            if response == "TIE":
                winner = None
            elif response == "LEFT":
                winner = "A" if orientation == "A_LEFT" else "B"
            else:
                winner = "B" if orientation == "A_LEFT" else "A"

            validated.append({
                "session": session,
                "pair_id": pair_id,
                "submitted_at": submitted,
                "orientation": orientation,
                "response": response,
                "winner": winner,
                "pair": pair,
            })
        except Exception as exc:
            invalid.append({"index": index, "error": str(exc)})

    # Frozen duplicate rule: earliest submitted response per session + pair wins.
    validated.sort(key=lambda r: (r["session"], r["pair_id"], r["submitted_at"]))
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    duplicate_count = 0
    for row in validated:
        key = (row["session"], row["pair_id"])
        if key in seen:
            duplicate_count += 1
            continue
        seen.add(key)
        deduped.append(row)

    return deduped, {
        "input_rows": len(responses),
        "valid_rows_before_dedupe": len(validated),
        "invalid_rows": len(invalid),
        "invalid_examples": invalid[:20],
        "duplicate_rows_removed": duplicate_count,
        "evaluable_rows": len(deduped),
    }


def pair_statistics(
    manifest: dict[str, Any],
    responses: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    pairs = _manifest_pairs(manifest)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in responses:
        grouped[row["pair_id"]].append(row)

    stats: list[dict[str, Any]] = []
    for pair in pairs:
        pid = str(pair["underlying_pair_id"])
        rows = grouped.get(pid, [])
        wins_a = sum(row["winner"] == "A" for row in rows)
        wins_b = sum(row["winner"] == "B" for row in rows)
        ties = sum(row["winner"] is None for row in rows)
        n = len(rows)
        non_tie = wins_a + wins_b
        primary_ready = n >= MIN_EVALUABLE and non_tie >= MIN_NON_TIE
        log_odds_a = (
            math.log((wins_a + 0.5) / (wins_b + 0.5))
            if primary_ready else None
        )
        stats.append({
            "pair_id": pid,
            "set_id": pair["set_id"],
            "set_name": pair["set_name"],
            "era_name": pair["era_name"],
            "subject_key": pair["subject_key"],
            "treatment_a": pair["treatment_a"],
            "treatment_b": pair["treatment_b"],
            "evaluable": n,
            "non_tie": non_tie,
            "ties": ties,
            "wins_a": wins_a,
            "wins_b": wins_b,
            "primary_ready": primary_ready,
            "log_odds_a_over_b": log_odds_a,
            "non_tie_share_a": (wins_a / non_tie if non_tie else None),
        })
    return stats


def collection_coverage(
    manifest: dict[str, Any],
    pair_stats: list[dict[str, Any]],
) -> dict[str, Any]:
    pairs = _manifest_pairs(manifest)
    triad_pairs: dict[tuple[str, str], list[str]] = defaultdict(list)
    triad_era: dict[tuple[str, str], str] = {}
    for pair in pairs:
        key = (str(pair["set_id"]), str(pair["subject_key"]))
        triad_pairs[key].append(str(pair["underlying_pair_id"]))
        triad_era[key] = str(pair["era_name"])
    ready_pair_ids = {row["pair_id"] for row in pair_stats if row["primary_ready"]}
    triad_ready = {
        key: len(ids) == 3 and all(pid in ready_pair_ids for pid in ids)
        for key, ids in triad_pairs.items()
    }
    total = len(triad_ready)
    ready = sum(triad_ready.values())
    by_era_total = Counter(triad_era.values())
    by_era_ready = Counter(
        triad_era[key] for key, value in triad_ready.items() if value
    )
    era_pass = {
        era: (
            by_era_ready[era] / by_era_total[era] >= MIN_ERA_TRIAD_COVERAGE
            if by_era_total[era] else False
        )
        for era in sorted(by_era_total)
    }
    return {
        "total_triads": total,
        "ready_triads": ready,
        "ready_share": ready / total if total else 0.0,
        "by_era_total": dict(by_era_total),
        "by_era_ready": dict(by_era_ready),
        "by_era_pass": era_pass,
        "pass": (
            total == 45
            and ready / total >= MIN_TRIAD_COVERAGE
            and all(era_pass.values())
        ),
    }


def orientation_diagnostic(responses: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [row for row in responses if row["winner"] is not None]
    if not rows:
        return {
            "non_tie_responses": 0,
            "left_choice_share": None,
            "left_deviation": None,
            "orientation_beta": None,
            "orientation_beta_ci95": None,
            "pass": False,
        }

    left_chosen = np.array([
        1.0 if row["response"] == "LEFT" else 0.0 for row in rows
    ])
    left_share = float(np.mean(left_chosen))

    # Model P(A wins) using edge intercepts plus A-on-left orientation indicator.
    edge_names = sorted({
        _edge_key(row["pair"]["treatment_a"], row["pair"]["treatment_b"])
        for row in rows
    })
    X = []
    y = []
    for row in rows:
        edge = _edge_key(row["pair"]["treatment_a"], row["pair"]["treatment_b"])
        vector = [1.0 if edge == name else 0.0 for name in edge_names]
        vector.append(1.0 if row["orientation"] == "A_LEFT" else 0.0)
        X.append(vector)
        y.append(1.0 if row["winner"] == "A" else 0.0)
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    beta = np.zeros(X.shape[1], dtype=float)
    cov = None
    for _ in range(100):
        eta = np.clip(X @ beta, -30, 30)
        p = 1.0 / (1.0 + np.exp(-eta))
        w = np.clip(p * (1.0 - p), 1e-8, None)
        h = X.T @ (w[:, None] * X)
        g = X.T @ (y - p)
        step = np.linalg.pinv(h) @ g
        beta_new = beta + step
        if float(np.max(np.abs(step))) < 1e-9:
            beta = beta_new
            cov = np.linalg.pinv(h)
            break
        beta = beta_new
        cov = np.linalg.pinv(h)
    orientation_beta = float(beta[-1])
    se = math.sqrt(max(0.0, float(cov[-1, -1]))) if cov is not None else float("inf")
    ci = [orientation_beta - 1.96 * se, orientation_beta + 1.96 * se]
    return {
        "non_tie_responses": len(rows),
        "left_choice_share": left_share,
        "left_deviation": abs(left_share - 0.5),
        "orientation_beta": orientation_beta,
        "orientation_beta_ci95": ci,
        "pass": abs(left_share - 0.5) <= 0.075 and ci[0] <= 0 <= ci[1],
    }


def edge_result(
    pair_stats: list[dict[str, Any]],
    treatment_a: str,
    treatment_b: str,
) -> dict[str, Any]:
    rows = [
        row for row in pair_stats
        if row["primary_ready"]
        and row["treatment_a"] == treatment_a
        and row["treatment_b"] == treatment_b
    ]
    values = np.asarray([row["log_odds_a_over_b"] for row in rows], dtype=float)
    if not len(values):
        return {
            "treatment_a": treatment_a,
            "treatment_b": treatment_b,
            "ready_pairs": 0,
        }
    point = float(np.mean(values))
    rng = np.random.default_rng(SEED)
    draws = np.empty(BOOTSTRAP_DRAWS, dtype=float)
    for i in range(BOOTSTRAP_DRAWS):
        sample = rng.choice(values, size=len(values), replace=True)
        draws[i] = float(np.mean(sample))
    ci = np.percentile(draws, [2.5, 50, 97.5])
    positive_pairs = sum(
        (row["non_tie_share_a"] or 0.0) > 0.5 for row in rows
    ) / len(rows)
    loo = []
    if len(values) > 1:
        for i in range(len(values)):
            loo.append(float(np.mean(np.delete(values, i))))
    else:
        loo = [point]
    return {
        "treatment_a": treatment_a,
        "treatment_b": treatment_b,
        "ready_pairs": len(rows),
        "mean_pair_log_odds": point,
        "preference_odds": math.exp(point),
        "bootstrap_ci95_log_odds": [float(ci[0]), float(ci[2])],
        "bootstrap_ci95_odds": [math.exp(float(ci[0])), math.exp(float(ci[2]))],
        "pair_positive_share": positive_pairs,
        "loo_min_log_odds": min(loo),
        "loo_max_log_odds": max(loo),
        "gates_without_orientation": {
            "point_positive": point > 0,
            "bootstrap_lower_positive": float(ci[0]) > 0,
            "pair_positive_share_ge_70pct": positive_pairs >= 0.70,
            "loo_sign_positive": min(loo) > 0,
        },
    }


def analyze(manifest: dict[str, Any], raw_responses: list[dict[str, Any]]) -> dict[str, Any]:
    responses, validation = validate_and_dedupe(manifest, raw_responses)
    stats = pair_statistics(manifest, responses)
    coverage = collection_coverage(manifest, stats)
    orientation = orientation_diagnostic(responses)

    if not coverage["pass"]:
        return {
            "study_id": STUDY_VERSION,
            "decision_token": "TREATMENT_DIRECT_PREFERENCE_V1_INSUFFICIENT_COLLECTION_COVERAGE",
            "validation": validation,
            "coverage": coverage,
            "orientation": orientation,
            "production_writes": 0,
        }

    edges = {
        _edge_key(a, b): edge_result(stats, a, b)
        for a, b in PRIMARY_EDGES
    }
    for result in edges.values():
        gates = result.get("gates_without_orientation") or {}
        result["gates"] = {**gates, "orientation_bias_pass": orientation["pass"]}
        result["supported"] = bool(gates) and all(result["gates"].values())

    sir_dr = edges[_edge_key(SIR, DOUBLE)]["supported"]
    sir_ur = edges[_edge_key(SIR, ULTRA)]["supported"]
    decision = (
        "TREATMENT_DIRECT_PREFERENCE_V1_SUPPORTED"
        if sir_dr and sir_ur and orientation["pass"]
        else "TREATMENT_DIRECT_PREFERENCE_V1_NOT_SUPPORTED"
    )
    return {
        "study_id": STUDY_VERSION,
        "decision_token": decision,
        "validation": validation,
        "coverage": coverage,
        "orientation": orientation,
        "edges": edges,
        "pair_stats": stats,
        "production_writes": 0,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--responses", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    result = analyze(manifest, load_responses(args.responses))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    printable = {k:v for k,v in result.items() if k != "pair_stats"}
    print(json.dumps(printable, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
