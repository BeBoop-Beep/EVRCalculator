"""Research-only Collector V8 ANCHOR25 shadow and downstream Overall RIP impact.

Consumes frozen V7 and temporal authorities plus a frozen immutable Overall V12
publication snapshot. No database/network access and no persistence path.
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

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.desirability.collector_appeal import collector_appeal_v4_frequency_index
from backend.desirability.opening_appeal import union_probability_from_cards
from backend.scripts.build_pokemon_collector_appeal_v6_corrected_successor import pokemon_d, trainer_d
from backend.scripts.research_collector_cross_domain_calibration_v1 import (
    authorities, build_candidates, map_trainers, preservation,
)
from backend.scripts.validate_frozen_collector_appeal_v7 import (
    MODEL_RUN_ID, MODEL_VERSION, verify_frozen_artifact,
)

V8_VERSION = "pokemon_collector_appeal_v8_anchor25_cross_domain_v1"
OVERALL_V7_SHADOW_VERSION = "overall_rip_v13_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v7"
OVERALL_V8_SHADOW_VERSION = "overall_rip_v14_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v8_anchor25"
TEMPORAL_PASS = "ANCHOR25_TEMPORAL_VALIDATION_PASS"
V12_VERSION = "overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5"
V12_PUBLICATION_RUN = "0f83d958-95aa-40f1-bcfa-ec550ec3a379"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def clamp(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def tier(score: float) -> str:
    if score >= 90:
        return "S"
    if score >= 75:
        return "A"
    if score >= 55:
        return "B"
    if score >= 35:
        return "C"
    if score >= 15:
        return "D"
    return "F"


def spearman_ranks(a: Mapping[str, int], b: Mapping[str, int]) -> float | None:
    keys = sorted(set(a) & set(b))
    if len(keys) < 3:
        return None
    x = np.asarray([a[k] for k in keys], dtype=float)
    y = np.asarray([b[k] for k in keys], dtype=float)
    if x.std() <= 1e-12 or y.std() <= 1e-12:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def set_scores(cards: Sequence[Mapping[str, Any]], frozen_sets: Sequence[Mapping[str, Any]], label: str) -> list[dict[str, Any]]:
    old = {str(row["set_id"]): row for row in frozen_sets}
    grouped = defaultdict(list)
    frozen_set_ids = set(old)
    for row in cards:
        set_id = str(row["set_id"])
        if set_id in frozen_set_ids:
            grouped[set_id].append(row)

    out = []
    for set_id in sorted(frozen_set_ids):
        rows = grouped.get(set_id, [])
        if not rows:
            raise RuntimeError(f"FROZEN_V7_SET_CARD_MEMBERSHIP_MISSING:{set_id}")
        pg = defaultdict(list)
        tg = defaultdict(list)
        for row in rows:
            target = pg if row["subject_type"] == "pokemon" else tg if row["subject_type"] == "trainer" else None
            if target is not None:
                for name in str(row.get("subject_identity") or "").split(" + "):
                    if name.strip():
                        target[name.strip()].append(float(row[f"score_{label}"]))

        dp, strength, breadth = pokemon_d([max(v) for v in pg.values()])
        dt = trainer_d([max(v) for v in tg.values()])
        trainer_lift = (100.0 - dp) * 0.15 * dt / 100.0
        d_final = dp + trainer_lift

        desirable = [row for row in rows if row.get("hit_eligibility") and float(row[f"score_{label}"]) > 50.0]
        modeled = []
        for row in desirable:
            scarcity = row.get("pull_scarcity_diagnostic")
            if scarcity and scarcity.get("probability") is not None and scarcity.get("slotGroup"):
                modeled.append({
                    "canonical_card_id": row["canonical_card_id"],
                    "pull_probability": float(scarcity["probability"]),
                    "slot_group": scarcity["slotGroup"],
                })
        excess = sum(float(row[f"score_{label}"]) - 50.0 for row in desirable)
        covered_ids = {item["canonical_card_id"] for item in modeled}
        covered = sum(
            float(row[f"score_{label}"]) - 50.0
            for row in desirable
            if row["canonical_card_id"] in covered_ids
        )
        coverage = covered / excess if excess else None
        unique_modeled = list({item["canonical_card_id"]: item for item in modeled}.values())
        f = union_probability_from_cards(unique_modeled) if unique_modeled and coverage is not None and coverage >= 0.25 else None
        index = collector_appeal_v4_frequency_index(f) if f is not None else None
        z = 2.0 * index - 1.0 if index is not None else None
        modifier = (2.0 * z if z >= 0 else z) if z is not None else None
        collector = clamp(d_final + modifier) if modifier is not None else None
        base = old.get(set_id, {})
        out.append({
            "setId": set_id,
            "setName": base.get("set_name"),
            "D_pokemon": dp,
            "D_trainer": dt,
            "trainerLiftPoints": trainer_lift,
            "D_final": d_final,
            "F": f,
            "frequencyIndex": index,
            "frequencyModifier": modifier,
            "collectorAppeal": collector,
            "desirableCardCount": len(desirable),
            "frequencyCoverage": coverage,
            "desirableCardIds": sorted(row["canonical_card_id"] for row in desirable),
        })
    ranked = sorted(
        [row for row in out if row["collectorAppeal"] is not None],
        key=lambda row: (-row["collectorAppeal"], row["setId"]),
    )
    for rank, row in enumerate(ranked, 1):
        row["rank"] = rank
    return out


def replay_errors(control_sets: Sequence[Mapping[str, Any]], frozen_sets: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    expected = {str(row["set_id"]): row for row in frozen_sets}
    diffs = []
    for row in control_sets:
        base = expected[row["setId"]]
        fields = {}
        for shadow_key, base_key in (
            ("D_final", "D_final"),
            ("F", "F"),
            ("frequencyModifier", "frequency_modifier"),
            ("collectorAppeal", "collector_appeal"),
        ):
            a = row.get(shadow_key)
            b = base.get(base_key)
            fields[shadow_key] = (
                None if a is None and b is None
                else math.inf if a is None or b is None
                else abs(float(a) - float(b))
            )
        diffs.append({"setId": row["setId"], "fields": fields})
    finite = [v for row in diffs for v in row["fields"].values() if v is not None]
    max_error = max(finite, default=0.0)
    mismatch = sum(
        any(v is not None and v > 1e-9 for v in row["fields"].values())
        for row in diffs
    )
    return {"maxAbsoluteError": max_error, "setsOutside1e9": mismatch, "sets": diffs, "passed": mismatch == 0}


def compare_sets(control_sets, candidate_sets):
    c0 = {row["setId"]: row for row in control_sets}
    c1 = {row["setId"]: row for row in candidate_sets}
    rows = []
    for set_id in sorted(c0):
        a, b = c0[set_id], c1[set_id]
        old_ids = set(a["desirableCardIds"])
        new_ids = set(b["desirableCardIds"])
        rows.append({
            "setId": set_id,
            "setName": a["setName"],
            "v7": a["collectorAppeal"],
            "v8": b["collectorAppeal"],
            "delta": None if a["collectorAppeal"] is None or b["collectorAppeal"] is None else b["collectorAppeal"] - a["collectorAppeal"],
            "v7Rank": a.get("rank"),
            "v8Rank": b.get("rank"),
            "rankDelta": None if a.get("rank") is None or b.get("rank") is None else b["rank"] - a["rank"],
            "DDelta": b["D_final"] - a["D_final"],
            "FDelta": None if a["F"] is None or b["F"] is None else b["F"] - a["F"],
            "frequencyModifierDelta": None if a["frequencyModifier"] is None or b["frequencyModifier"] is None else b["frequencyModifier"] - a["frequencyModifier"],
            "desirableEntering": sorted(new_ids - old_ids),
            "desirableLeaving": sorted(old_ids - new_ids),
        })
    scored = [row for row in rows if row["delta"] is not None]
    r0 = {row["setId"]: row["v7Rank"] for row in scored if row["v7Rank"] is not None}
    r1 = {row["setId"]: row["v8Rank"] for row in scored if row["v8Rank"] is not None}
    return {
        "rows": rows,
        "summary": {
            "sets": len(rows),
            "scoredV7": sum(row["v7"] is not None for row in rows),
            "scoredV8": sum(row["v8"] is not None for row in rows),
            "meanDelta": float(np.mean([row["delta"] for row in scored])) if scored else None,
            "medianDelta": float(np.median([row["delta"] for row in scored])) if scored else None,
            "maxGain": max((row["delta"] for row in scored), default=None),
            "maxLoss": min((row["delta"] for row in scored), default=None),
            "rankCorrelation": spearman_ranks(r0, r1),
            "maxAbsoluteRankMove": max((abs(row["rankDelta"]) for row in scored if row["rankDelta"] is not None), default=0),
            "setsWithRankChange": sum(row["rankDelta"] not in (None, 0) for row in scored),
            "setsWithFrequencyChange": sum(row["FDelta"] is not None and abs(row["FDelta"]) > 1e-12 for row in scored),
            "setsWithDesirableThresholdChange": sum(bool(row["desirableEntering"] or row["desirableLeaving"]) for row in rows),
        },
    }


def rank_overall(rows: list[dict[str, Any]], score_key: str, rank_key: str, tier_key: str) -> None:
    ordered = sorted(rows, key=lambda row: (-float(row[score_key]), row["id"]))
    for i, row in enumerate(ordered, 1):
        row[rank_key] = i
        row[tier_key] = tier(float(row[score_key]))


def overall_shadow(authority: Mapping[str, Any], control_sets, candidate_sets):
    if authority["authority"]["publicationRunId"] != V12_PUBLICATION_RUN or authority["authority"]["modelVersion"] != V12_VERSION:
        raise RuntimeError("FROZEN_OVERALL_V12_AUTHORITY_MISMATCH")
    v7 = {row["setId"]: row["collectorAppeal"] for row in control_sets}
    v8 = {row["setId"]: row["collectorAppeal"] for row in candidate_sets}
    out = []
    replay_errors = []
    for source in authority["rows"]:
        set_id = str(source["set_id"])
        if set_id not in v7 or v7[set_id] is None or v8.get(set_id) is None:
            continue
        fin = float(source["financial_v4"])
        chase = float(source["chase_accessibility"])
        replay = round(0.86 * fin + 0.04 * chase + 0.10 * float(source["collector_v5"]), 4)
        replay_errors.append(abs(replay - float(source["v12_score"])))
        out.append({
            **source,
            "v12Replay": replay,
            "v13V7Score": round(0.86 * fin + 0.04 * chase + 0.10 * float(v7[set_id]), 4),
            "v14V8Score": round(0.86 * fin + 0.04 * chase + 0.10 * float(v8[set_id]), 4),
            "collectorV7": float(v7[set_id]),
            "collectorV8": float(v8[set_id]),
        })
    if len(out) != len(authority["rows"]):
        raise RuntimeError(f"OVERALL_SHADOW_COHORT_LOSS:{len(out)}/{len(authority['rows'])}")
    rank_overall(out, "v13V7Score", "v13V7Rank", "v13V7Tier")
    rank_overall(out, "v14V8Score", "v14V8Rank", "v14V8Tier")

    def comparison(base_score, base_rank, base_tier, new_score, new_rank, new_tier):
        deltas = [float(row[new_score]) - float(row[base_score]) for row in out]
        moves = [abs(int(row[new_rank]) - int(row[base_rank])) for row in out]
        return {
            "meanScoreDelta": float(np.mean(deltas)),
            "medianScoreDelta": float(np.median(deltas)),
            "maxScoreGain": max(deltas),
            "maxScoreLoss": min(deltas),
            "rankCorrelation": spearman_ranks(
                {row["id"]: int(row[base_rank]) for row in out},
                {row["id"]: int(row[new_rank]) for row in out},
            ),
            "meanAbsoluteRankDelta": float(np.mean(moves)),
            "maxAbsoluteRankDelta": max(moves),
            "rowsWithRankChange": sum(move > 0 for move in moves),
            "tierChanges": sum(str(row[base_tier]) != str(row[new_tier]) for row in out),
            "top10Overlap": len(
                {row["id"] for row in out if int(row[base_rank]) <= 10}
                & {row["id"] for row in out if int(row[new_rank]) <= 10}
            ),
        }

    return {
        "controlReplay": {
            "maxAbsoluteError": max(replay_errors, default=None),
            "passed": max(replay_errors, default=math.inf) <= 1e-4,
        },
        "rows": out,
        "productionV12ToV8": comparison("v12_score", "v12_rank", "v12_tier", "v14V8Score", "v14V8Rank", "v14V8Tier"),
        "v7ToV8Incremental": comparison("v13V7Score", "v13V7Rank", "v13V7Tier", "v14V8Score", "v14V8Rank", "v14V8Tier"),
        "v12ToV7Reference": comparison("v12_score", "v12_rank", "v12_tier", "v13V7Score", "v13V7Rank", "v13V7Tier"),
    }


def render_report(decision, replay, set_cmp, overall, temporal):
    s = set_cmp["summary"]
    inc = overall["v7ToV8Incremental"]
    total = overall["productionV12ToV8"]
    return f"""# Collector V8 ANCHOR25 — Research Shadow

Decision: **{decision["decision"]}**

## Authority

- V7 control: {MODEL_VERSION} / {MODEL_RUN_ID}
- V8 shadow: {V8_VERSION}
- Temporal authority: {temporal["decision"]} across {temporal["passingFolds"]}/5 folds
- Overall production control: {V12_VERSION} / {V12_PUBLICATION_RUN}
- Production mutations: **NONE**

## Reconstruction gates

- Frozen V7 artifact: PASS
- V7 Set replay: **{"PASS" if replay["passed"] else "FAIL"}**, max absolute error {replay["maxAbsoluteError"]}
- V12 product replay: **{"PASS" if overall["controlReplay"]["passed"] else "FAIL"}**, max absolute error {overall["controlReplay"]["maxAbsoluteError"]}
- Pokemon scores unchanged; ANCHOR25 Trainer within-domain preservation inherited from validated temporal authority.

## Collector V7 -> V8 Set shadow

- Sets: {s["sets"]}
- Scored V7 / V8: {s["scoredV7"]} / {s["scoredV8"]}
- Mean / median Collector delta: {s["meanDelta"]:+.6f} / {s["medianDelta"]:+.6f}
- Maximum gain / loss: {s["maxGain"]:+.6f} / {s["maxLoss"]:+.6f}
- Rank correlation: {s["rankCorrelation"]}
- Maximum absolute Set rank movement: {s["maxAbsoluteRankMove"]}
- Sets with rank change: {s["setsWithRankChange"]}
- Sets with F change: {s["setsWithFrequencyChange"]}
- Sets with >50 desirable-card membership change: {s["setsWithDesirableThresholdChange"]}

## Overall RIP — isolated V7 -> V8 effect

Financial 86% and Chase 4% are frozen. Only the 10% Collector input changes.

- Mean / median score delta: {inc["meanScoreDelta"]:+.6f} / {inc["medianScoreDelta"]:+.6f}
- Max gain / loss: {inc["maxScoreGain"]:+.6f} / {inc["maxScoreLoss"]:+.6f}
- Rank correlation: {inc["rankCorrelation"]}
- Mean / max absolute rank move: {inc["meanAbsoluteRankDelta"]:.6f} / {inc["maxAbsoluteRankDelta"]}
- Rows with rank change: {inc["rowsWithRankChange"]}/276
- Tier changes: {inc["tierChanges"]}
- Top-10 overlap: {inc["top10Overlap"]}/10

## Overall RIP — current production V12 -> V8 total hypothetical effect

This includes the already-researched V5->V7 Collector change plus V7->V8 ANCHOR25 calibration, so it is not an isolated ANCHOR25 estimate.

- Mean / median score delta: {total["meanScoreDelta"]:+.6f} / {total["medianScoreDelta"]:+.6f}
- Rank correlation: {total["rankCorrelation"]}
- Mean / max absolute rank move: {total["meanAbsoluteRankDelta"]:.6f} / {total["maxAbsoluteRankDelta"]}
- Tier changes: {total["tierChanges"]}
- Top-10 overlap: {total["top10Overlap"]}/10

## Boundary

This shadow does not create, publish, stage, or promote a Collector V8 model run or a new Overall RIP authority. A supported result advances only to a separate promotion-readiness review.

{decision["decision"]}
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", type=Path, default=ROOT / "backend/artifacts/collector_appeal_v7_expanded_candidate_v1.json")
    ap.add_argument("--temporal-decision", type=Path, default=ROOT / "docs/research/collector_appeal/cross_domain_temporal_v1/decision.json")
    ap.add_argument("--overall-authority", type=Path, default=ROOT / "docs/research/collector_appeal/v8_anchor25_shadow/frozen_overall_v12_authority.json")
    ap.add_argument("--output-dir", type=Path, default=ROOT / "docs/research/collector_appeal/v8_anchor25_shadow")
    args = ap.parse_args()

    frozen = read_json(args.artifact)
    artifact_validation = verify_frozen_artifact(frozen)
    temporal = read_json(args.temporal_decision)
    if temporal.get("decision") != TEMPORAL_PASS or temporal.get("passingFolds") != 5:
        raise RuntimeError("COLLECTOR_V8_TEMPORAL_PASS_REQUIRED")

    pokemon, trainers = authorities(frozen["cards"])
    anchors = map_trainers(trainers, pokemon)
    candidates, equivalence = build_candidates(frozen["cards"], anchors)
    frozen_by_id = {str(row["canonical_card_id"]): row for row in frozen["cards"]}
    for row in candidates:
        source = frozen_by_id[str(row["canonical_card_id"])]
        row["pull_scarcity_diagnostic"] = source.get("pull_scarcity_diagnostic")
    preserve = preservation(candidates)
    control_sets = set_scores(candidates, frozen["sets"], "CONTROL")
    v8_sets = set_scores(candidates, frozen["sets"], "ANCHOR25")
    replay = replay_errors(control_sets, frozen["sets"])
    set_cmp = compare_sets(control_sets, v8_sets)
    overall = overall_shadow(read_json(args.overall_authority), control_sets, v8_sets)

    gates = {
        "frozenV7Artifact": bool(artifact_validation.get("verified")),
        "cardControlEquivalence": bool(equivalence.get("passed")),
        "temporalValidation": temporal.get("decision") == TEMPORAL_PASS,
        "pokemonUnchanged": preserve["pokemon"]["ANCHOR25"]["maxScoreDelta"] == 0,
        "trainerSpearmanGte995": preserve["trainer"]["ANCHOR25"]["spearman"] >= 0.995,
        "v7SetReplay": bool(replay["passed"]),
        "v12OverallReplay": bool(overall["controlReplay"]["passed"]),
        "noSetAvailabilityLoss": set_cmp["summary"]["scoredV8"] >= set_cmp["summary"]["scoredV7"],
    }
    passed = all(gates.values())
    decision = {
        "decision": "COLLECTOR_V8_ANCHOR25_SHADOW_SUPPORTED_FOR_PROMOTION_REVIEW" if passed else "COLLECTOR_V8_ANCHOR25_SHADOW_BLOCKED",
        "candidateVersion": V8_VERSION,
        "overallShadowVersion": OVERALL_V8_SHADOW_VERSION,
        "gates": gates,
        "productionMutations": "NONE",
        "promotionPerformed": False,
        "nextStep": "PROMOTION_READINESS_REVIEW" if passed else "STOP_AND_DIAGNOSE",
    }

    out = args.output_dir
    write_json(out / "set_shadow.json", {"version": V8_VERSION, "replay": replay, "comparison": set_cmp})
    write_json(out / "overall_shadow.json", {
        "v12Authority": read_json(args.overall_authority)["authority"],
        "v7ShadowVersion": OVERALL_V7_SHADOW_VERSION,
        "v8ShadowVersion": OVERALL_V8_SHADOW_VERSION,
        **overall,
    })
    write_json(out / "decision.json", decision)
    (out / "FINAL_REPORT.md").write_text(render_report(decision, replay, set_cmp, overall, temporal), encoding="utf-8")
    print(json.dumps({
        "decision": decision["decision"],
        "setSummary": set_cmp["summary"],
        "overallV7ToV8": overall["v7ToV8Incremental"],
        "overallV12ToV8": overall["productionV12ToV8"],
        "productionMutations": "NONE",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
