"""Independent temporal validation for frozen ANCHOR25 Collector calibration.

Research-only: historical reads plus local artifact writes. No DB persistence path.
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
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.research.collector_appeal_market_validation.stats import prediction_metrics
from backend.scripts.research_collector_cross_domain_calibration_v1 import (
    TARGETS,
    authorities,
    build_candidates,
    controlled_cohort,
    cv_metrics,
    joined_market,
    map_trainers,
    pair_diagnostics,
    preservation,
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
FORMULA_FINGERPRINT = "06f5660047b9b8a4d7349d04b79547b1314c2be3720c245ba8780890db1c114b"
PARENT_SHA = "012e38b1e9a85491ba2ba72b746f8baead6112ea"

PHASE1_PRICE_AUTHORITY = "get_pokemon_set_value_canonical_prices_as_of_v2_shadow_legacy_identity"
EXECUTABLE_PRICE_RPC = "get_pokemon_set_value_canonical_prices_as_of_v2_shadow"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def canonical_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def fold_seed(market_date: str) -> int:
    return BASE_SEED + int(market_date.replace("-", ""))


def historical_prices_legacy_rpc(client: Any, set_ids: Sequence[str], market_date: str):
    rows = []
    for set_id in sorted(set_ids):
        rows.extend(
            client.rpc(
                EXECUTABLE_PRICE_RPC,
                {"target_set_id": set_id, "target_date": market_date},
            ).execute().data or []
        )
    by_card = {}
    normalized = []
    for row in rows:
        card_id = str(row.get("canonical_card_id") or "")
        price = row.get("market_price")
        if not card_id or price is None:
            continue
        if card_id in by_card:
            raise RuntimeError(f"duplicate canonical historical price: {card_id}")
        by_card[card_id] = float(price)
        normalized.append({
            "root_set_id": row.get("set_id"),
            "member_set_id": row.get("set_id"),
            "canonical_card_id": card_id,
            "card_variant_id": row.get("card_variant_id"),
            "market_price": float(price),
            "observed_date": row.get("captured_at"),
            "printing_type": row.get("printing_type"),
            "special_type": None,
            "source": row.get("source") or EXECUTABLE_PRICE_RPC,
        })
    return by_card, normalized


def attach_prices(membership_rows: Sequence[Mapping[str, Any]], prices: Mapping[str, float]):
    rows, missing = [], []
    for row in membership_rows:
        card_id = str(row["card_id"])
        price = prices.get(card_id)
        if price is None or not math.isfinite(float(price)) or float(price) <= 0:
            missing.append(card_id)
        else:
            rows.append({**row, "market_price": float(price), "log_price": math.log(float(price))})
    return rows, sorted(missing)


def lineage_summary(rows: Sequence[Mapping[str, Any]], market_date: str) -> dict[str, Any]:
    pairs = sorted(
        (str(r.get("canonical_card_id") or ""), float(r["market_price"]))
        for r in rows
        if r.get("canonical_card_id") and r.get("market_price") is not None
    )
    return {
        "marketDate": market_date,
        "returnedRows": len(rows),
        "observedDateCounts": dict(sorted(Counter(str(r.get("observed_date") or "") for r in rows).items())),
        "sourceCounts": dict(sorted(Counter(str(r.get("source") or "") for r in rows).items())),
        "priceStateFingerprint": canonical_hash(pairs),
    }


def metric_delta(candidate: Mapping[str, Any], control: Mapping[str, Any], key: str):
    a, b = candidate.get(key), control.get(key)
    return None if a is None or b is None else float(a) - float(b)


def fold_pass(data_valid: bool, deltas: Mapping[str, float | None]) -> bool:
    return data_valid and all(
        deltas.get(metric) is not None and float(deltas[metric]) >= floor
        for metric, floor in GUARDRAILS.items()
    )


def decide(structural_valid: bool, folds: Sequence[Mapping[str, Any]]) -> str:
    if not structural_valid:
        return "ANCHOR25_TEMPORAL_VALIDATION_INVALID"
    valid = sum(bool(x.get("dataValid")) for x in folds)
    passed = sum(bool(x.get("passed")) for x in folds)
    if valid < 4:
        return "ANCHOR25_TEMPORAL_AUTHORITY_INSUFFICIENT"
    return "ANCHOR25_TEMPORAL_VALIDATION_PASS" if passed >= 4 else "ANCHOR25_TEMPORAL_VALIDATION_FAIL"


def interval(values: Sequence[float]) -> dict[str, Any]:
    arr = np.asarray([float(x) for x in values if math.isfinite(float(x))], dtype=float)
    if not len(arr):
        return {"n": 0, "mean": None, "median": None, "ci95": [None, None]}
    return {
        "n": int(len(arr)),
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "ci95": [
            float(np.quantile(arr, 0.025, method="linear")),
            float(np.quantile(arr, 0.975, method="linear")),
        ],
    }


def bootstrap_fold(rows, pairs, cvs, *, draws: int, seed: int) -> dict[str, Any]:
    by_set = defaultdict(list)
    for row in rows:
        by_set[str(row["set_id"])].append(row)
    ids = sorted(by_set)
    pred = {}
    for label in ("CONTROL", CANDIDATE):
        grouped = defaultdict(list)
        for row in cvs[label].get("_predictions", []):
            grouped[str(row["set_id"])].append(row)
        pred[label] = grouped

    out = defaultdict(list)
    rng = np.random.default_rng(seed)
    for _ in range(draws):
        picked = [ids[int(i)] for i in rng.choice(len(ids), len(ids), replace=True)]
        sampled = [row for sid in picked for row in by_set[sid]]
        summaries = {label: raw_within_set(sampled, f"score_{label}")["summary"] for label in ("CONTROL", CANDIDATE)}
        out["weightedWithinSetRho"].append(
            float(summaries[CANDIDATE]["weightedMeanRho"]) - float(summaries["CONTROL"]["weightedMeanRho"])
        )
        out["medianWithinSetRho"].append(
            float(summaries[CANDIDATE]["medianRho"]) - float(summaries["CONTROL"]["medianRho"])
        )

        def pc(label):
            vals = [v for sid in picked for v in pairs[label]["_bySet"].get(sid, [])]
            return float(np.mean(vals)) if vals else math.nan

        out["pairConcordance"].append(pc(CANDIDATE) - pc("CONTROL"))

        def pm(label):
            vals = [p for sid in picked for p in pred[label].get(sid, [])]
            if not vals:
                return {"r2": math.nan, "spearman": math.nan, "mae": math.nan, "rmse": math.nan}
            return prediction_metrics([p["actual"] for p in vals], [p["predicted"] for p in vals])

        control, candidate = pm("CONTROL"), pm(CANDIDATE)
        for key, source in (("controlledOosR2", "r2"), ("heldOutSpearman", "spearman"), ("oosMae", "mae"), ("oosRmse", "rmse")):
            out[key].append(float(candidate[source]) - float(control[source]))

    return {
        "seed": seed,
        "draws": draws,
        "method": "whole-Set resampling with aligned held-out predictions",
        "deltas": {key: interval(values) for key, values in out.items()},
    }


def baseline_lock(client, set_ids, membership_rows, candidate_rows, expected_sets):
    prices, lineage = historical_prices_legacy_rpc(client, set_ids, BASELINE_DATE)
    priced, missing = attach_prices(membership_rows, prices)
    joined = joined_market(priced, candidate_rows)
    replay = raw_within_set(joined, "score_CONTROL")
    expected = {str(x["setId"]): (int(x["n"]), float(x["spearmanLogPrice"])) for x in expected_sets}
    observed = {str(x["setId"]): (int(x["n"]), float(x["spearmanLogPrice"])) for x in replay["sets"]}
    set_checks = []
    for sid in sorted(expected):
        actual = observed.get(sid)
        set_checks.append({
            "setId": sid,
            "nMatch": actual is not None and actual[0] == expected[sid][0],
            "rhoError": None if actual is None else abs(actual[1] - expected[sid][1]),
        })
    summary = replay["summary"]
    global_errors = {
        "medianRho": abs(float(summary["medianRho"]) - TARGETS["medianRho"]),
        "weightedMeanRho": abs(float(summary["weightedMeanRho"]) - TARGETS["weightedMeanRho"]),
        "positivePct": abs(float(summary["positivePct"]) - TARGETS["positivePct"]),
    }
    passed = (
        not missing
        and len(joined) == EXPECTED_COUNTS["modeledRows"]
        and len(set_checks) == EXPECTED_COUNTS["modeledSets"]
        and all(x["nMatch"] and x["rhoError"] is not None and x["rhoError"] <= 1e-12 for x in set_checks)
        and max(global_errors.values()) <= 1e-12
    )
    return {
        "passed": passed,
        "pricedRows": len(joined),
        "missingCount": len(missing),
        "maxPerSetRhoError": max((x["rhoError"] for x in set_checks if x["rhoError"] is not None), default=None),
        "globalErrors": global_errors,
        "setChecks": set_checks,
        "priceLineage": lineage_summary(lineage, BASELINE_DATE),
    }


def evaluate_fold(client, market_date, set_ids, membership_rows, candidate_rows, bootstrap_draws):
    prices, lineage = historical_prices_legacy_rpc(client, set_ids, market_date)
    priced, missing = attach_prices(membership_rows, prices)
    joined = joined_market(priced, candidate_rows)
    represented = len({str(x["set_id"]) for x in joined})
    data_valid = not missing and len(joined) == EXPECTED_COUNTS["modeledRows"] and represented == EXPECTED_COUNTS["modeledSets"]
    base = {
        "marketDate": market_date,
        "dataValid": data_valid,
        "coverage": {
            "expectedRows": EXPECTED_COUNTS["modeledRows"],
            "pricedRows": len(joined),
            "missingRows": len(missing),
            "representedSets": represented,
            "missingCardIds": missing,
        },
        "priceLineage": lineage_summary(lineage, market_date),
    }
    if not data_valid:
        return {**base, "passed": False, "metrics": None, "deltas": None}, {
            "marketDate": market_date, "seed": fold_seed(market_date), "draws": 0, "status": "NOT_RUN_INVALID_COVERAGE"
        }

    within = {label: raw_within_set(joined, f"score_{label}") for label in ("CONTROL", CANDIDATE)}
    pairs = {label: pair_diagnostics(joined, f"score_{label}") for label in ("CONTROL", CANDIDATE)}
    cv_private = {label: cv_metrics(joined, f"score_{label}", private=True) for label in ("CONTROL", CANDIDATE)}
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
    public_pairs = {label: {k: v for k, v in payload.items() if k != "_bySet"} for label, payload in pairs.items()}
    metrics = {"withinSet": within, "pairs": public_pairs, "oos": cv_public}
    boot = bootstrap_fold(joined, pairs, cv_private, draws=bootstrap_draws, seed=fold_seed(market_date))
    boot["marketDate"] = market_date
    return {**base, "passed": fold_pass(data_valid, deltas), "metrics": metrics, "deltas": deltas}, boot


def report_text(decision, structural, folds, draws):
    lines = [
        "# Collector Cross-Domain Calibration V1 — Independent Temporal Validation",
        "",
        "Decision: " + decision["decision"],
        "",
        "## Authority",
        "",
        "- Parent Phase 1 SHA: " + PARENT_SHA,
        "- Frozen Collector control: " + MODEL_VERSION + " / " + MODEL_RUN_ID,
        "- Candidate: ANCHOR25 only",
        "- Historical price authority: get_pokemon_set_value_canonical_prices_as_of_v2_shadow (legacy identity chain; exact Sep-11 replay required)",
        "- Production mutations: NONE",
        "",
        "## Structural lock",
        "",
        f"- Frozen artifact valid: {structural['artifactVerified']}",
        f"- Sep-11 exact baseline replay: {structural['baselineReplay']['passed']}",
        f"- Cohort contract: {structural['cohortContract']}",
        f"- Pokemon unchanged: {structural['pokemonUnchanged']}",
        f"- Trainer Spearman >= 0.995: {structural['trainerSpearmanGte995']}",
        "",
        "## Fixed temporal folds",
        "",
        "| Date | Coverage | Pass | delta weighted rho | delta OOS R2 | delta held-out rho | delta pair concordance |",
        "|---|---:|:---:|---:|---:|---:|---:|",
    ]
    for row in folds:
        d = row.get("deltas") or {}
        def fmt(k):
            return "n/a" if d.get(k) is None else f"{float(d[k]):+.6f}"
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", type=Path, default=ROOT / "backend/artifacts/collector_appeal_v7_expanded_candidate_v1.json")
    ap.add_argument("--output-dir", type=Path, default=ROOT / "docs/research/collector_appeal/cross_domain_temporal_v1")
    ap.add_argument("--bootstrap-draws", type=int, default=1000)
    args = ap.parse_args()

    frozen = read_json(args.artifact)
    artifact = verify_frozen_artifact(frozen)
    if frozen["manifest"].get("formulaFingerprint") != FORMULA_FINGERPRINT:
        raise RuntimeError("TEMPORAL_V1_FORMULA_AUTHORITY_MISMATCH")

    pokemon, trainers = authorities(frozen["cards"])
    anchors = map_trainers(trainers, pokemon)
    candidate_rows, equivalence = build_candidates(frozen["cards"], anchors)
    preserve = preservation(candidate_rows)

    expected_sets = read_json(ROOT / "docs/research/collector_appeal_v7_price_validation/within_set_results.json")["card_appeal_v7"]["sets"]
    set_ids = [str(x["setId"]) for x in expected_sets]

    load_dotenv(ROOT / "backend/.env", override=False)
    from backend.db.clients.supabase_client import service_read_client

    membership, excluded = controlled_cohort(
        service_read_client,
        set_ids,
        price_source="frozen Phase 1 structural membership",
        membership_only=True,
    )
    counts = membership["manifest"]["counts"]
    cohort_contract = counts == EXPECTED_COUNTS and len(excluded) == EXPECTED_COUNTS["dropped"]["no_modeled_pull_probability"]
    baseline = baseline_lock(service_read_client, set_ids, membership["rows"], candidate_rows, expected_sets)
    structural = {
        "artifactVerified": bool(artifact.get("verified")),
        "modelVersion": MODEL_VERSION,
        "modelRunId": MODEL_RUN_ID,
        "modelFingerprint": MODEL_FINGERPRINT,
        "cardFingerprint": CARD_FINGERPRINT,
        "setFingerprint": SET_FINGERPRINT,
        "liftEquivalence": equivalence,
        "cohortContract": cohort_contract,
        "cohortCounts": counts,
        "cohortCardFingerprint": canonical_hash(sorted(str(x["card_id"]) for x in membership["rows"])),
        "pokemonUnchanged": preserve["pokemon"][CANDIDATE]["maxScoreDelta"] == 0,
        "trainerSpearman": preserve["trainer"][CANDIDATE]["spearman"],
        "trainerSpearmanGte995": preserve["trainer"][CANDIDATE]["spearman"] >= 0.995,
        "baselineReplay": baseline,
        "historicalPriceAuthority": PHASE1_PRICE_AUTHORITY,
        "historicalPriceExecutable": EXECUTABLE_PRICE_RPC,
    }
    structural_valid = all([
        structural["artifactVerified"],
        structural["cohortContract"],
        structural["pokemonUnchanged"],
        structural["trainerSpearmanGte995"],
        structural["baselineReplay"]["passed"],
        bool(equivalence.get("passed")),
    ])

    folds, boots = [], []
    if structural_valid:
        for market_date in TEMPORAL_DATES:
            fold, boot = evaluate_fold(
                service_read_client, market_date, set_ids, membership["rows"], candidate_rows, args.bootstrap_draws
            )
            folds.append(fold)
            boots.append(boot)
    else:
        for market_date in TEMPORAL_DATES:
            folds.append({
                "marketDate": market_date,
                "dataValid": False,
                "passed": False,
                "coverage": {"expectedRows": EXPECTED_COUNTS["modeledRows"], "pricedRows": 0, "missingRows": EXPECTED_COUNTS["modeledRows"], "representedSets": 0, "missingCardIds": []},
                "priceLineage": None,
                "metrics": None,
                "deltas": None,
                "status": "NOT_RUN_STRUCTURAL_INVALID",
            })

    decision_name = decide(structural_valid, folds)
    decision = {
        "decision": decision_name,
        "candidate": CANDIDATE,
        "alpha": 0.25,
        "temporalDates": list(TEMPORAL_DATES),
        "dataValidFolds": sum(bool(x.get("dataValid")) for x in folds),
        "passingFolds": sum(bool(x.get("passed")) for x in folds),
        "requiredPassingFolds": 4,
        "guardrails": GUARDRAILS,
        "structuralValid": structural_valid,
        "productionMutations": "NONE",
        "nextStep": "COLLECTOR_V8_SHADOW_ONLY" if decision_name == "ANCHOR25_TEMPORAL_VALIDATION_PASS" else "STOP_ANCHOR25_PROMOTION_WORK",
    }

    out = args.output_dir
    write_json(out / "temporal_results.json", {"parentPhase1Sha": PARENT_SHA, "structural": structural, "folds": folds})
    write_json(out / "bootstrap_intervals.json", {"baseSeed": BASE_SEED, "drawsPerValidFold": args.bootstrap_draws, "folds": boots})
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
