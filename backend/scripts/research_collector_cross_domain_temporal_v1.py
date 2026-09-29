"""Offline independent temporal validation for frozen ANCHOR25 Collector calibration.

Research-only. All predictor/cohort rows and all six price states are immutable
repo artifacts. This script performs no database or network access.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.research.collector_appeal_market_validation.stats import prediction_metrics
from backend.scripts.research_collector_cross_domain_calibration_v1 import (
    TARGETS,
    cv_metrics,
    pair_diagnostics,
    raw_within_set,
)
from backend.scripts.validate_frozen_collector_appeal_v7 import (
    CARD_FINGERPRINT,
    MODEL_FINGERPRINT,
    MODEL_RUN_ID,
    MODEL_VERSION,
    SET_FINGERPRINT,
    verify_frozen_artifact,
)

CANDIDATE = "ANCHOR25"
BASELINE_DATE = "2026-09-11"
TEMPORAL_DATES = ("2026-09-14", "2026-09-17", "2026-09-20", "2026-09-23", "2026-09-26")
EXPECTED_COUNTS = {
    "candidateCards": 4355,
    "modeledRows": 4331,
    "modeledSets": 22,
    "dropped": {"no_modeled_pull_probability": 24},
}
GUARDRAILS = {
    "weightedWithinSetRho": -0.005,
    "controlledOosR2": -0.002,
    "heldOutSpearman": -0.010,
    "pairConcordance": 0.0,
}
BASE_SEED = 20260929
PARENT_SHA = "012e38b1e9a85491ba2ba72b746f8baead6112ea"
FROZEN_DIR = ROOT / "docs/research/collector_appeal/cross_domain_temporal_v1"
COHORT_PARTS = ("frozen_temporal_cohort_part1.json", "frozen_temporal_cohort_part2.json")
PRICE_FILES = {
    BASELINE_DATE: "prices_20260911.json",
    "2026-09-14": "prices_20260914.json",
    "2026-09-17": "prices_20260917.json",
    "2026-09-20": "prices_20260920.json",
    "2026-09-23": "prices_20260923.json",
    "2026-09-26": "prices_20260926.json",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def canonical_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def fold_seed(market_date: str) -> int:
    return BASE_SEED + int(market_date.replace("-", ""))


def fold_pass(data_valid: bool, deltas: Mapping[str, float | None]) -> bool:
    return data_valid and all(
        deltas.get(metric) is not None and float(deltas[metric]) >= floor
        for metric, floor in GUARDRAILS.items()
    )


def decide(structural_valid: bool, folds: Sequence[Mapping[str, Any]]) -> str:
    if not structural_valid:
        return "ANCHOR25_TEMPORAL_VALIDATION_INVALID"
    valid = sum(bool(row.get("dataValid")) for row in folds)
    passed = sum(bool(row.get("passed")) for row in folds)
    if valid < 4:
        return "ANCHOR25_TEMPORAL_AUTHORITY_INSUFFICIENT"
    return "ANCHOR25_TEMPORAL_VALIDATION_PASS" if passed >= 4 else "ANCHOR25_TEMPORAL_VALIDATION_FAIL"


def interval(values: Sequence[float]) -> dict[str, Any]:
    arr = np.asarray([float(x) for x in values if math.isfinite(float(x))], dtype=float)
    if arr.size == 0:
        return {"n": 0, "mean": None, "median": None, "ci95": [None, None]}
    return {
        "n": int(arr.size),
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "ci95": [
            float(np.quantile(arr, 0.025, method="linear")),
            float(np.quantile(arr, 0.975, method="linear")),
        ],
    }


def load_frozen_cohort(root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payloads = [read_json(root / name) for name in COHORT_PARTS]
    metas = [payload["meta"] for payload in payloads]
    if any(meta != metas[0] for meta in metas[1:]):
        raise RuntimeError("TEMPORAL_FROZEN_COHORT_META_MISMATCH")
    rows = [row for payload in payloads for row in payload["rows"]]
    if len(rows) != EXPECTED_COUNTS["modeledRows"] or len({row["id"] for row in rows}) != len(rows):
        raise RuntimeError("TEMPORAL_FROZEN_COHORT_ROW_CONTRACT_FAILED")
    return rows, metas[0]


def load_price_state(root: Path, market_date: str) -> tuple[dict[str, float], dict[str, Any]]:
    rows = read_json(root / PRICE_FILES[market_date])
    by_id = {str(row["id"]): float(row["p"]) for row in rows}
    if len(rows) != EXPECTED_COUNTS["modeledRows"] or len(by_id) != len(rows):
        raise RuntimeError(f"TEMPORAL_PRICE_STATE_COVERAGE_FAILED:{market_date}")
    if any(not math.isfinite(price) or price <= 0 for price in by_id.values()):
        raise RuntimeError(f"TEMPORAL_PRICE_STATE_INVALID_PRICE:{market_date}")
    lineage = {
        "marketDate": market_date,
        "rows": len(rows),
        "observedDateCounts": dict(sorted(Counter(str(row.get("obs") or "") for row in rows).items())),
        "priceStateFingerprint": canonical_hash(sorted((str(row["id"]), float(row["p"])) for row in rows)),
    }
    return by_id, lineage


def expand_rows(compact_rows: Sequence[Mapping[str, Any]], prices: Mapping[str, float]) -> tuple[list[dict[str, Any]], list[str]]:
    rows, missing = [], []
    for source in compact_rows:
        card_id = str(source["id"])
        price = prices.get(card_id)
        if price is None:
            missing.append(card_id)
            continue
        rows.append({
            "card_id": card_id,
            "canonical_card_id": card_id,
            "set_id": str(source["set"]),
            "set_name": source["sn"],
            "era": source["era"],
            "market_price": float(price),
            "log_price": math.log(float(price)),
            "pull_scarcity": float(source["ps"]),
            "rarity_key": source["rk"],
            "slot_group": source["sg"],
            "is_secret": float(source["sec"]),
            "is_promo": float(source["promo"]),
            "is_mechanic_card": float(source["mech"]),
            "is_stage2": float(source["st2"]),
            "is_trainer": float(source["tr"]),
            "log_release_age": float(source["age"]),
            "subject_type": str(source["dom"]),
            "subject_cluster_key": None,
            "score_CONTROL": float(source["c"]),
            "score_ANCHOR25": float(source["a"]),
        })
    return rows, sorted(missing)


def baseline_lock(compact_rows, prices, expected_sets):
    rows, missing = expand_rows(compact_rows, prices)
    replay = raw_within_set(rows, "score_CONTROL")
    expected = {str(row["setId"]): (int(row["n"]), float(row["spearmanLogPrice"])) for row in expected_sets}
    observed = {str(row["setId"]): (int(row["n"]), float(row["spearmanLogPrice"])) for row in replay["sets"]}
    checks = []
    for set_id in sorted(expected):
        actual = observed.get(set_id)
        checks.append({
            "setId": set_id,
            "nMatch": actual is not None and actual[0] == expected[set_id][0],
            "rhoError": None if actual is None else abs(actual[1] - expected[set_id][1]),
        })
    summary = replay["summary"]
    global_errors = {
        "medianRho": abs(float(summary["medianRho"]) - TARGETS["medianRho"]),
        "weightedMeanRho": abs(float(summary["weightedMeanRho"]) - TARGETS["weightedMeanRho"]),
        "positivePct": abs(float(summary["positivePct"]) - TARGETS["positivePct"]),
    }
    passed = (
        not missing
        and len(rows) == EXPECTED_COUNTS["modeledRows"]
        and len(replay["sets"]) == EXPECTED_COUNTS["modeledSets"]
        and all(row["nMatch"] and row["rhoError"] is not None and row["rhoError"] <= 1e-12 for row in checks)
        and max(global_errors.values()) <= 1e-12
    )
    return {
        "passed": passed,
        "pricedRows": len(rows),
        "missingCount": len(missing),
        "maxPerSetRhoError": max((row["rhoError"] for row in checks if row["rhoError"] is not None), default=None),
        "globalErrors": global_errors,
        "setChecks": checks,
        "controlSummary": summary,
    }


def metric_delta(candidate: Mapping[str, Any], control: Mapping[str, Any], key: str) -> float | None:
    a, b = candidate.get(key), control.get(key)
    return None if a is None or b is None else float(a) - float(b)


def bootstrap_fold(rows, pairs, cvs, *, draws: int, seed: int) -> dict[str, Any]:
    by_set = defaultdict(list)
    for row in rows:
        by_set[str(row["set_id"])].append(row)
    set_ids = sorted(by_set)
    pred = {}
    for label in ("CONTROL", CANDIDATE):
        grouped = defaultdict(list)
        for row in cvs[label].get("_predictions", []):
            grouped[str(row["set_id"])].append(row)
        pred[label] = grouped

    samples = defaultdict(list)
    rng = np.random.default_rng(seed)
    for _ in range(draws):
        picked = [set_ids[int(i)] for i in rng.choice(len(set_ids), len(set_ids), replace=True)]
        sampled = [row for sid in picked for row in by_set[sid]]
        summaries = {
            label: raw_within_set(sampled, f"score_{label}")["summary"]
            for label in ("CONTROL", CANDIDATE)
        }
        samples["weightedWithinSetRho"].append(
            float(summaries[CANDIDATE]["weightedMeanRho"]) - float(summaries["CONTROL"]["weightedMeanRho"])
        )
        samples["medianWithinSetRho"].append(
            float(summaries[CANDIDATE]["medianRho"]) - float(summaries["CONTROL"]["medianRho"])
        )

        def pair_concordance(label: str) -> float:
            values = [v for sid in picked for v in pairs[label]["_bySet"].get(sid, [])]
            return float(np.mean(values)) if values else math.nan

        samples["pairConcordance"].append(pair_concordance(CANDIDATE) - pair_concordance("CONTROL"))

        def prediction_sample(label: str) -> dict[str, Any]:
            values = [p for sid in picked for p in pred[label].get(sid, [])]
            if not values:
                return {"r2": math.nan, "spearman": math.nan, "mae": math.nan, "rmse": math.nan}
            return prediction_metrics([p["actual"] for p in values], [p["predicted"] for p in values])

        control = prediction_sample("CONTROL")
        candidate = prediction_sample(CANDIDATE)
        for target, source in (
            ("controlledOosR2", "r2"),
            ("heldOutSpearman", "spearman"),
            ("oosMae", "mae"),
            ("oosRmse", "rmse"),
        ):
            samples[target].append(float(candidate[source]) - float(control[source]))

    return {
        "seed": seed,
        "draws": draws,
        "method": "deterministic whole-Set resampling; aligned held-out predictions resampled by Set",
        "deltas": {key: interval(values) for key, values in samples.items()},
    }


def evaluate_fold(compact_rows, prices, market_date, bootstrap_draws):
    rows, missing = expand_rows(compact_rows, prices)
    represented = len({row["set_id"] for row in rows})
    data_valid = not missing and len(rows) == EXPECTED_COUNTS["modeledRows"] and represented == EXPECTED_COUNTS["modeledSets"]
    base = {
        "marketDate": market_date,
        "dataValid": data_valid,
        "coverage": {
            "expectedRows": EXPECTED_COUNTS["modeledRows"],
            "pricedRows": len(rows),
            "missingRows": len(missing),
            "representedSets": represented,
            "missingCardIds": missing,
        },
    }
    if not data_valid:
        return {**base, "passed": False, "metrics": None, "deltas": None}, {
            "marketDate": market_date, "seed": fold_seed(market_date), "draws": 0, "status": "NOT_RUN_INVALID_COVERAGE"
        }

    within = {label: raw_within_set(rows, f"score_{label}") for label in ("CONTROL", CANDIDATE)}
    pairs = {label: pair_diagnostics(rows, f"score_{label}") for label in ("CONTROL", CANDIDATE)}
    cv_private = {label: cv_metrics(rows, f"score_{label}", private=True) for label in ("CONTROL", CANDIDATE)}
    cv_public = {label: {k: v for k, v in payload.items() if k != "_predictions"} for label, payload in cv_private.items()}
    deltas = {
        "weightedWithinSetRho": float(within[CANDIDATE]["summary"]["weightedMeanRho"]) - float(within["CONTROL"]["summary"]["weightedMeanRho"]),
        "medianWithinSetRho": float(within[CANDIDATE]["summary"]["medianRho"]) - float(within["CONTROL"]["summary"]["medianRho"]),
        "pairConcordance": float(pairs[CANDIDATE]["directionalConcordance"]) - float(pairs["CONTROL"]["directionalConcordance"]),
        "controlledOosR2": metric_delta(cv_public[CANDIDATE], cv_public["CONTROL"], "r2"),
        "heldOutSpearman": metric_delta(cv_public[CANDIDATE], cv_public["CONTROL"], "spearman"),
        "oosMae": metric_delta(cv_public[CANDIDATE], cv_public["CONTROL"], "mae"),
        "oosRmse": metric_delta(cv_public[CANDIDATE], cv_public["CONTROL"], "rmse"),
    }
    metrics = {
        "withinSet": within,
        "pairs": {label: {k: v for k, v in payload.items() if k != "_bySet"} for label, payload in pairs.items()},
        "oos": cv_public,
    }
    boot = bootstrap_fold(rows, pairs, cv_private, draws=bootstrap_draws, seed=fold_seed(market_date))
    boot["marketDate"] = market_date
    return {**base, "passed": fold_pass(data_valid, deltas), "metrics": metrics, "deltas": deltas}, boot


def report_text(decision, structural, folds, draws):
    lines = [
        "# Collector Cross-Domain Calibration V1 — Independent Temporal Validation",
        "",
        "Decision: " + decision["decision"],
        "",
        "## Frozen authority",
        "",
        "- Parent Phase 1 SHA: " + PARENT_SHA,
        "- Frozen Collector control: " + MODEL_VERSION + " / " + MODEL_RUN_ID,
        "- Candidate: ANCHOR25 only",
        "- Cohort/predictors: immutable frozen V7 4,331-row artifact",
        "- Price states: immutable repo artifacts generated with pre-drift Phase 1 SQL semantics",
        "- Production mutations: NONE",
        "",
        "## Structural lock",
        "",
        f"- Frozen V7 artifact valid: {structural['artifactVerified']}",
        f"- Frozen cohort contract: {structural['cohortContract']}",
        f"- Sep-11 exact baseline replay: {structural['baselineReplay']['passed']}",
        f"- Pokemon unchanged: {structural['pokemonUnchanged']}",
        f"- Trainer Spearman >= 0.995: {structural['trainerSpearmanGte995']}",
        "",
        "## Fixed temporal folds",
        "",
        "| Date | Coverage | Pass | delta weighted rho | delta OOS R2 | delta held-out rho | delta pair concordance |",
        "|---|---:|:---:|---:|---:|---:|---:|",
    ]
    for row in folds:
        delta = row.get("deltas") or {}
        def fmt(key):
            return "n/a" if delta.get(key) is None else f"{float(delta[key]):+.6f}"
        lines.append(
            f"| {row['marketDate']} | {row['coverage']['pricedRows']}/{EXPECTED_COUNTS['modeledRows']} | "
            f"{'YES' if row.get('passed') else 'NO'} | {fmt('weightedWithinSetRho')} | "
            f"{fmt('controlledOosR2')} | {fmt('heldOutSpearman')} | {fmt('pairConcordance')} |"
        )
    lines += [
        "",
        "## Gate",
        "",
        f"- Data-valid folds: {decision['dataValidFolds']}/5",
        f"- Passing folds: {decision['passingFolds']}/5",
        "- Required: at least 4 of 5 complete fold passes.",
        f"- Bootstrap: {draws} deterministic whole-Set draws per data-valid fold.",
        "",
        "A PASS supports only a research-only Collector V8 shadow. It does not change current Collector V7 or publish Overall RIP.",
        "",
        decision["decision"],
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frozen-dir", type=Path, default=FROZEN_DIR)
    parser.add_argument("--artifact", type=Path, default=ROOT / "backend/artifacts/collector_appeal_v7_expanded_candidate_v1.json")
    parser.add_argument("--output-dir", type=Path, default=FROZEN_DIR)
    parser.add_argument("--bootstrap-draws", type=int, default=1000)
    args = parser.parse_args()

    frozen_v7 = read_json(args.artifact)
    artifact = verify_frozen_artifact(frozen_v7)
    compact_rows, cohort_meta = load_frozen_cohort(args.frozen_dir)
    cohort_contract = (
        cohort_meta.get("version") == "collector_temporal_frozen_cohort_v1"
        and cohort_meta.get("run") == MODEL_RUN_ID
        and int(cohort_meta.get("rows") or 0) == EXPECTED_COUNTS["modeledRows"]
        and len(compact_rows) == EXPECTED_COUNTS["modeledRows"]
        and len({row["set"] for row in compact_rows}) == EXPECTED_COUNTS["modeledSets"]
    )
    pokemon_unchanged = max(abs(float(row["a"]) - float(row["c"])) for row in compact_rows if row["dom"] == "pokemon") <= 1e-12
    trainer_spearman = float(cohort_meta["phase1TrainerSpearman"])

    price_states, price_lineage = {}, {}
    for market_date in (BASELINE_DATE,) + TEMPORAL_DATES:
        price_states[market_date], price_lineage[market_date] = load_price_state(args.frozen_dir, market_date)

    expected_sets = read_json(ROOT / "docs/research/collector_appeal_v7_price_validation/within_set_results.json")["card_appeal_v7"]["sets"]
    baseline = baseline_lock(compact_rows, price_states[BASELINE_DATE], expected_sets)
    structural = {
        "artifactVerified": bool(artifact.get("verified")),
        "modelVersion": MODEL_VERSION,
        "modelRunId": MODEL_RUN_ID,
        "modelFingerprint": MODEL_FINGERPRINT,
        "cardFingerprint": CARD_FINGERPRINT,
        "setFingerprint": SET_FINGERPRINT,
        "cohortContract": cohort_contract,
        "cohortMeta": cohort_meta,
        "cohortCardFingerprint": canonical_hash(sorted(str(row["id"]) for row in compact_rows)),
        "pokemonUnchanged": pokemon_unchanged,
        "trainerSpearman": trainer_spearman,
        "trainerSpearmanGte995": trainer_spearman >= 0.995,
        "baselineReplay": baseline,
        "priceLineage": price_lineage,
        "authorityAmendment": "AUTHORITY_AMENDMENT_3.md",
        "databaseReadsDuringEvaluation": 0,
        "productionMutations": "NONE",
    }
    structural_valid = all((
        structural["artifactVerified"],
        structural["cohortContract"],
        structural["pokemonUnchanged"],
        structural["trainerSpearmanGte995"],
        structural["baselineReplay"]["passed"],
    ))

    folds, boots = [], []
    if structural_valid:
        for market_date in TEMPORAL_DATES:
            fold, boot = evaluate_fold(compact_rows, price_states[market_date], market_date, args.bootstrap_draws)
            fold["priceLineage"] = price_lineage[market_date]
            folds.append(fold)
            boots.append(boot)
    else:
        for market_date in TEMPORAL_DATES:
            folds.append({
                "marketDate": market_date, "dataValid": False, "passed": False,
                "coverage": {"expectedRows": EXPECTED_COUNTS["modeledRows"], "pricedRows": 0, "missingRows": EXPECTED_COUNTS["modeledRows"], "representedSets": 0, "missingCardIds": []},
                "metrics": None, "deltas": None, "status": "NOT_RUN_STRUCTURAL_INVALID",
                "priceLineage": price_lineage.get(market_date),
            })

    decision_name = decide(structural_valid, folds)
    decision = {
        "decision": decision_name,
        "candidate": CANDIDATE,
        "alpha": 0.25,
        "temporalDates": list(TEMPORAL_DATES),
        "dataValidFolds": sum(bool(row.get("dataValid")) for row in folds),
        "passingFolds": sum(bool(row.get("passed")) for row in folds),
        "requiredPassingFolds": 4,
        "guardrails": GUARDRAILS,
        "structuralValid": structural_valid,
        "productionMutations": "NONE",
        "nextStep": "COLLECTOR_V8_SHADOW_ONLY" if decision_name == "ANCHOR25_TEMPORAL_VALIDATION_PASS" else "STOP_ANCHOR25_PROMOTION_WORK",
    }

    out = args.output_dir
    write_json(out / "temporal_results.json", {
        "contract": "collector_cross_domain_temporal_v1_offline_frozen",
        "parentPhase1Sha": PARENT_SHA,
        "structural": structural,
        "folds": folds,
    })
    write_json(out / "bootstrap_intervals.json", {
        "baseSeed": BASE_SEED,
        "drawsPerValidFold": args.bootstrap_draws,
        "folds": boots,
    })
    write_json(out / "decision.json", decision)
    (out / "FINAL_REPORT.md").write_text(report_text(decision, structural, folds, args.bootstrap_draws), encoding="utf-8")
    print(json.dumps({
        "decision": decision_name,
        "structuralValid": structural_valid,
        "dataValidFolds": decision["dataValidFolds"],
        "passingFolds": decision["passingFolds"],
        "outputDir": str(out),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
