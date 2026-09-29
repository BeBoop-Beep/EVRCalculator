"""Research-only Collector V8 ANCHOR25 shadow.

Recomputes frozen V7 Set Collector Appeal exactly, substitutes only the validated
ANCHOR25 Trainer calibration, recomputes generalized frequency, and evaluates a
V13-style Overall shadow against current ready V12 component rows.

No database writes, no publication, no pointer changes.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
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

from backend.desirability.collector_appeal import collector_appeal_v4_frequency_index
from backend.desirability.opening_appeal import union_probability_from_cards
from backend.research.collector_appeal_market_validation.stats import spearman
from backend.scripts.build_pokemon_collector_appeal_v6_corrected_successor import pokemon_d, trainer_d
from backend.scripts.research_collector_cross_domain_calibration_v1 import (
    authorities,
    build_candidates,
    map_trainers,
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
ALPHA = 0.25
TEMPORAL_DECISION_PATH = ROOT / "docs/research/collector_appeal/cross_domain_temporal_v1/decision.json"
V7_ARTIFACT = ROOT / "backend/artifacts/collector_appeal_v7_expanded_candidate_v1.json"
OUT_DIR = ROOT / "docs/research/collector_appeal/collector_v8_anchor25_shadow_v1"
OVERALL_WEIGHTS = {"financial": 0.86, "chase": 0.04, "collector": 0.10}
V8_VERSION = "pokemon_collector_appeal_v8_anchor25_cross_domain_shadow_v1"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def ranked(items: Sequence[Mapping[str, Any]], score_key: str, id_key: str) -> dict[str, int]:
    ordered = sorted(items, key=lambda x: (-float(x[score_key]), str(x[id_key])))
    return {str(row[id_key]): index for index, row in enumerate(ordered, 1)}


def set_score_rows(
    *,
    frozen_cards: Sequence[Mapping[str, Any]],
    candidate_rows: Sequence[Mapping[str, Any]],
    frozen_sets: Sequence[Mapping[str, Any]],
    label: str,
) -> list[dict[str, Any]]:
    card_source = {str(row["canonical_card_id"]): row for row in frozen_cards}
    frozen_set = {str(row["set_id"]): row for row in frozen_sets}
    by_set: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in candidate_rows:
        by_set[str(row["set_id"])].append(row)

    out = []
    for set_id, rows in sorted(by_set.items()):
        pokemon_groups: dict[str, list[float]] = defaultdict(list)
        trainer_groups: dict[str, list[float]] = defaultdict(list)
        score_key = f"score_{label}"

        def card_score(row: Mapping[str, Any]) -> float:
            if label == "CONTROL":
                return float(card_source[str(row["canonical_card_id"])]["card_collector_appeal_v7"])
            return float(row[score_key])

        for row in rows:
            target = pokemon_groups if row["subject_type"] == "pokemon" else trainer_groups if row["subject_type"] == "trainer" else None
            if target is None:
                continue
            for identity in str(row.get("subject_identity") or "").split(" + "):
                identity = identity.strip()
                if identity:
                    target[identity].append(card_score(row))

        dp, strength, breadth = pokemon_d([max(values) for values in pokemon_groups.values()])
        dt = trainer_d([max(values) for values in trainer_groups.values()])
        trainer_lift = (100.0 - dp) * 0.15 * dt / 100.0
        d_final = dp + trainer_lift

        desirable = [
            row for row in rows
            if row.get("hit_eligibility") and card_score(row) > 50.0
        ]
        modeled = []
        covered_ids = set()
        for row in desirable:
            source = card_source[str(row["canonical_card_id"])]
            scarcity = source.get("pull_scarcity_diagnostic")
            if scarcity and scarcity.get("probability") is not None and scarcity.get("slotGroup"):
                modeled.append({
                    "canonical_card_id": str(row["canonical_card_id"]),
                    "pull_probability": float(scarcity["probability"]),
                    "slot_group": str(scarcity["slotGroup"]),
                })
                covered_ids.add(str(row["canonical_card_id"]))

        excess = sum(card_score(row) - 50.0 for row in desirable)
        covered = sum(
            card_score(row) - 50.0
            for row in desirable
            if str(row["canonical_card_id"]) in covered_ids
        )
        coverage = covered / excess if excess > 0 else None
        unique_modeled = list({row["canonical_card_id"]: row for row in modeled}.values())
        frequency = (
            union_probability_from_cards(unique_modeled)
            if unique_modeled and coverage is not None and coverage >= 0.25
            else None
        )
        index = collector_appeal_v4_frequency_index(frequency) if frequency is not None else None
        z = 2.0 * index - 1.0 if index is not None else None
        modifier = (2.0 * z if z >= 0 else z) if z is not None else None
        appeal = min(100.0, max(0.0, d_final + modifier)) if modifier is not None else None

        base = frozen_set.get(set_id) or {}
        out.append({
            "set_id": set_id,
            "set_name": base.get("set_name"),
            "D_pokemon": float(dp),
            "S": float(strength),
            "B": float(breadth),
            "D_trainer": float(dt),
            "trainer_lift_points": float(trainer_lift),
            "D_final": float(d_final),
            "F": None if frequency is None else float(frequency),
            "frequency_index": None if index is None else float(index),
            "frequency_modifier": None if modifier is None else float(modifier),
            "collector_appeal": None if appeal is None else float(appeal),
            "desirable_card_count": len(desirable),
            "frequency_excess_coverage": coverage,
        })
    eligible = [row for row in out if row["collector_appeal"] is not None]
    ranks = ranked(eligible, "collector_appeal", "set_id")
    for row in out:
        row["rank"] = ranks.get(row["set_id"])
    return out


def v7_replay_check(recomputed: Sequence[Mapping[str, Any]], frozen_sets: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    expected = {str(row["set_id"]): row for row in frozen_sets}
    details = []
    for row in recomputed:
        base = expected.get(str(row["set_id"])) or {}
        fields = {}
        for actual_key, expected_key in (
            ("D_final", "D_final"),
            ("F", "F"),
            ("frequency_modifier", "frequency_modifier"),
            ("collector_appeal", "collector_appeal"),
        ):
            a = row.get(actual_key)
            b = base.get(expected_key)
            error = None if a is None or b is None else abs(float(a) - float(b))
            fields[actual_key] = {
                "actual": a,
                "expected": b,
                "absoluteError": error,
                "nullMatch": (a is None) == (b is None),
            }
        details.append({"setId": row["set_id"], "setName": row.get("set_name"), "fields": fields})

    errors = [
        payload["absoluteError"]
        for detail in details
        for payload in detail["fields"].values()
        if payload["absoluteError"] is not None
    ]
    null_ok = all(payload["nullMatch"] for detail in details for payload in detail["fields"].values())
    max_error = max(errors, default=0.0)
    return {
        "passed": len(details) == len(frozen_sets) and null_ok and max_error <= 1e-12,
        "setCount": len(details),
        "maxAbsoluteError": max_error,
        "details": details,
    }


def compare_sets(v7: Sequence[Mapping[str, Any]], v8: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    a = {str(row["set_id"]): row for row in v7 if row.get("collector_appeal") is not None}
    b = {str(row["set_id"]): row for row in v8 if row.get("collector_appeal") is not None}
    common = sorted(set(a) & set(b))
    rows = []
    for set_id in common:
        rows.append({
            "setId": set_id,
            "setName": b[set_id].get("set_name"),
            "v7": float(a[set_id]["collector_appeal"]),
            "v8": float(b[set_id]["collector_appeal"]),
            "delta": float(b[set_id]["collector_appeal"]) - float(a[set_id]["collector_appeal"]),
            "v7Rank": a[set_id].get("rank"),
            "v8Rank": b[set_id].get("rank"),
            "rankMove": None if a[set_id].get("rank") is None or b[set_id].get("rank") is None else int(b[set_id]["rank"]) - int(a[set_id]["rank"]),
            "v7F": a[set_id].get("F"),
            "v8F": b[set_id].get("F"),
            "frequencyDelta": None if a[set_id].get("F") is None or b[set_id].get("F") is None else float(b[set_id]["F"]) - float(a[set_id]["F"]),
            "desirableCountV7": a[set_id]["desirable_card_count"],
            "desirableCountV8": b[set_id]["desirable_card_count"],
        })
    deltas = [row["delta"] for row in rows]
    rank_moves = [abs(row["rankMove"]) for row in rows if row["rankMove"] is not None]
    return {
        "setCount": len(rows),
        "scoreSpearman": spearman([row["v7"] for row in rows], [row["v8"] for row in rows]),
        "rankSpearman": spearman([row["v7Rank"] for row in rows], [row["v8Rank"] for row in rows]),
        "meanDelta": float(np.mean(deltas)) if deltas else None,
        "medianDelta": float(np.median(deltas)) if deltas else None,
        "maxGain": max(deltas) if deltas else None,
        "maxLoss": min(deltas) if deltas else None,
        "setsChanged": sum(abs(x) > 1e-12 for x in deltas),
        "maxAbsoluteRankMove": max(rank_moves, default=0),
        "rows": rows,
    }


def paged(factory, page_size: int = 1000) -> list[dict[str, Any]]:
    rows, start = [], 0
    while True:
        part = factory().range(start, start + page_size - 1).execute().data or []
        rows.extend(part)
        if len(part) < page_size:
            return rows
        start += page_size


def load_current_v12_rows(client: Any) -> tuple[str, list[dict[str, Any]]]:
    latest = (
        client.table("simulation_sealed_product_results")
        .select("price_as_of")
        .eq("overall_rip_v12_status", "ready")
        .order("price_as_of", desc=True)
        .limit(1)
        .execute().data or []
    )
    if not latest:
        raise RuntimeError("NO_READY_V12_ROWS")
    market_date = str(latest[0]["price_as_of"])
    rows = paged(lambda: (
        client.table("simulation_sealed_product_results")
        .select("id,set_id,sealed_product_id,product_name,product_family,financial_rip_v4_score,overall_rip_v12_score,overall_rip_v12_payload,overall_rip_v12_status,price_as_of")
        .eq("price_as_of", market_date)
        .eq("overall_rip_v12_status", "ready")
        .order("id")
    ))
    return market_date, rows


def overall_shadow(v12_rows: Sequence[Mapping[str, Any]], v7_sets, v8_sets) -> dict[str, Any]:
    v7 = {str(row["set_id"]): row for row in v7_sets if row.get("collector_appeal") is not None}
    v8 = {str(row["set_id"]): row for row in v8_sets if row.get("collector_appeal") is not None}
    output = []
    replay_errors = []
    for row in v12_rows:
        set_id = str(row["set_id"])
        if set_id not in v7 or set_id not in v8:
            continue
        payload = row.get("overall_rip_v12_payload") or {}
        components = payload.get("components") or {}
        chase = ((components.get("chaseAccessibility") or {}).get("score"))
        collector_v5 = ((components.get("collectorAppeal") or {}).get("score"))
        financial = row.get("financial_rip_v4_score")
        if financial is None or chase is None or collector_v5 is None:
            continue
        financial = float(financial)
        chase = float(chase)
        collector_v5 = float(collector_v5)
        v12_replay = (
            OVERALL_WEIGHTS["financial"] * financial
            + OVERALL_WEIGHTS["chase"] * chase
            + OVERALL_WEIGHTS["collector"] * collector_v5
        )
        stored_v12 = float(row["overall_rip_v12_score"])
        replay_errors.append(abs(round(v12_replay, 4) - stored_v12))

        overall_v7 = (
            OVERALL_WEIGHTS["financial"] * financial
            + OVERALL_WEIGHTS["chase"] * chase
            + OVERALL_WEIGHTS["collector"] * float(v7[set_id]["collector_appeal"])
        )
        overall_v8 = (
            OVERALL_WEIGHTS["financial"] * financial
            + OVERALL_WEIGHTS["chase"] * chase
            + OVERALL_WEIGHTS["collector"] * float(v8[set_id]["collector_appeal"])
        )
        output.append({
            "resultId": str(row["id"]),
            "sealedProductId": str(row["sealed_product_id"]),
            "setId": set_id,
            "productName": row.get("product_name"),
            "productFamily": row.get("product_family"),
            "financialV4": financial,
            "chaseV1": chase,
            "collectorV7": float(v7[set_id]["collector_appeal"]),
            "collectorV8": float(v8[set_id]["collector_appeal"]),
            "overallV7Shadow": round(overall_v7, 4),
            "overallV8Shadow": round(overall_v8, 4),
            "overallDelta": round(overall_v8, 4) - round(overall_v7, 4),
        })

    v7_ranks = ranked(output, "overallV7Shadow", "resultId")
    v8_ranks = ranked(output, "overallV8Shadow", "resultId")
    for row in output:
        row["v7Rank"] = v7_ranks[row["resultId"]]
        row["v8Rank"] = v8_ranks[row["resultId"]]
        row["rankMove"] = row["v8Rank"] - row["v7Rank"]

    deltas = [row["overallDelta"] for row in output]
    moves = [abs(row["rankMove"]) for row in output]
    top_v7 = {row["resultId"] for row in output if row["v7Rank"] <= 10}
    top_v8 = {row["resultId"] for row in output if row["v8Rank"] <= 10}
    by_id = {row["resultId"]: row for row in output}

    return {
        "v12Replay": {
            "rows": len(replay_errors),
            "maxRoundedAbsoluteError": max(replay_errors, default=None),
            "passed": bool(replay_errors) and max(replay_errors) <= 1e-12,
        },
        "cohortRows": len(output),
        "setCount": len({row["setId"] for row in output}),
        "scoreSpearman": spearman([row["overallV7Shadow"] for row in output], [row["overallV8Shadow"] for row in output]),
        "rankSpearman": spearman([row["v7Rank"] for row in output], [row["v8Rank"] for row in output]),
        "meanDelta": float(np.mean(deltas)) if deltas else None,
        "medianDelta": float(np.median(deltas)) if deltas else None,
        "maxGain": max(deltas) if deltas else None,
        "maxLoss": min(deltas) if deltas else None,
        "rowsWithRankChange": sum(move > 0 for move in moves),
        "meanAbsoluteRankMove": float(np.mean(moves)) if moves else None,
        "maxAbsoluteRankMove": max(moves, default=0),
        "top10Overlap": len(top_v7 & top_v8),
        "top10Entered": [by_id[x] for x in sorted(top_v8 - top_v7)],
        "top10Exited": [by_id[x] for x in sorted(top_v7 - top_v8)],
        "rows": output,
    }


def render_report(result: Mapping[str, Any]) -> str:
    sets = result["setComparison"]
    overall = result["overallComparison"]
    largest_sets = sorted(sets["rows"], key=lambda x: abs(x["delta"]), reverse=True)[:5]
    lines = [
        "# Collector V8 ANCHOR25 Shadow V1",
        "",
        "Decision: " + result["decision"],
        "",
        "## Inputs",
        "",
        "- Frozen V7 model run: " + MODEL_RUN_ID,
        "- Candidate: ANCHOR25 only",
        "- Temporal prerequisite: ANCHOR25_TEMPORAL_VALIDATION_PASS",
        "- Production mutations: NONE",
        "",
        "## V7 replay",
        "",
        f"- Exact Set replay: {result['v7Replay']['passed']}",
        f"- Max absolute replay error: {result['v7Replay']['maxAbsoluteError']}",
        "",
        "## V8 Set impact",
        "",
        f"- Sets: {sets['setCount']}",
        f"- Score Spearman V7 vs V8: {sets['scoreSpearman']}",
        f"- Rank Spearman V7 vs V8: {sets['rankSpearman']}",
        f"- Mean / median score delta: {sets['meanDelta']} / {sets['medianDelta']}",
        f"- Maximum Set rank move: {sets['maxAbsoluteRankMove']}",
        "",
        "| Set | V7 | V8 | Delta | V7 rank | V8 rank |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in largest_sets:
        lines.append(
            f"| {row['setName']} | {row['v7']:.4f} | {row['v8']:.4f} | {row['delta']:+.4f} | {row['v7Rank']} | {row['v8Rank']} |"
        )
    lines += [
        "",
        "## Hypothetical Overall impact",
        "",
        f"- Market date: {result['marketDate']}",
        f"- V12 component replay passed: {overall['v12Replay']['passed']}",
        f"- Products: {overall['cohortRows']} across {overall['setCount']} Sets",
        f"- Score Spearman V7-shadow vs V8-shadow: {overall['scoreSpearman']}",
        f"- Rank Spearman: {overall['rankSpearman']}",
        f"- Mean / median Overall delta: {overall['meanDelta']} / {overall['medianDelta']}",
        f"- Maximum absolute product-rank move: {overall['maxAbsoluteRankMove']}",
        f"- Top-10 overlap: {overall['top10Overlap']}/10",
        "",
        "This is a research-only substitution of V8 for V7 inside the same 86/4/10 Overall structure. "
        "It does not publish a new Collector version or Overall version.",
        "",
        result["decision"],
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", type=Path, default=V7_ARTIFACT)
    ap.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = ap.parse_args()

    temporal = read_json(TEMPORAL_DECISION_PATH)
    if temporal.get("decision") != "ANCHOR25_TEMPORAL_VALIDATION_PASS" or temporal.get("passingFolds") != 5:
        raise RuntimeError("V8_SHADOW_TEMPORAL_PREREQUISITE_NOT_MET")

    frozen = read_json(args.artifact)
    artifact_check = verify_frozen_artifact(frozen)
    pokemon, trainers = authorities(frozen["cards"])
    anchors = map_trainers(trainers, pokemon)
    candidate_rows, equivalence = build_candidates(frozen["cards"], anchors)

    v7_sets = set_score_rows(
        frozen_cards=frozen["cards"],
        candidate_rows=candidate_rows,
        frozen_sets=frozen["sets"],
        label="CONTROL",
    )
    v8_sets = set_score_rows(
        frozen_cards=frozen["cards"],
        candidate_rows=candidate_rows,
        frozen_sets=frozen["sets"],
        label=CANDIDATE,
    )
    v7_replay = v7_replay_check(v7_sets, frozen["sets"])
    if not v7_replay["passed"]:
        raise RuntimeError("V8_SHADOW_V7_SET_REPLAY_FAILED")

    set_comparison = compare_sets(v7_sets, v8_sets)

    load_dotenv(ROOT / "backend/.env", override=False)
    from backend.db.clients.supabase_client import service_read_client
    market_date, v12_rows = load_current_v12_rows(service_read_client)
    overall = overall_shadow(v12_rows, v7_sets, v8_sets)
    if not overall["v12Replay"]["passed"]:
        raise RuntimeError("V8_SHADOW_V12_COMPONENT_REPLAY_FAILED")

    decision = "COLLECTOR_V8_ANCHOR25_SHADOW_READY_FOR_PROMOTION_REVIEW"
    result = {
        "studyVersion": "collector_v8_anchor25_shadow_v1",
        "decision": decision,
        "candidateVersion": V8_VERSION,
        "productionMutations": "NONE",
        "frozenV7Authority": {
            "modelVersion": MODEL_VERSION,
            "modelRunId": MODEL_RUN_ID,
            "modelFingerprint": MODEL_FINGERPRINT,
            "cardFingerprint": CARD_FINGERPRINT,
            "setFingerprint": SET_FINGERPRINT,
            "artifactVerified": artifact_check.get("verified"),
            "candidateLiftEquivalence": equivalence,
        },
        "temporalPrerequisite": temporal,
        "marketDate": market_date,
        "v7Replay": v7_replay,
        "setComparison": set_comparison,
        "overallComparison": overall,
    }

    out = args.output_dir
    write_json(out / "shadow_results.json", result)
    write_json(out / "set_rows_v8.json", {"version": V8_VERSION, "sets": v8_sets})
    (out / "FINAL_REPORT.md").write_text(render_report(result), encoding="utf-8")
    print(json.dumps({
        "decision": decision,
        "setCount": set_comparison["setCount"],
        "setRankSpearman": set_comparison["rankSpearman"],
        "marketDate": market_date,
        "overallRows": overall["cohortRows"],
        "overallRankSpearman": overall["rankSpearman"],
        "top10Overlap": overall["top10Overlap"],
        "productionMutations": "NONE",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
