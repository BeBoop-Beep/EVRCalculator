"""Research-only Collector V8 ANCHOR25 shadow.

Temporal authority: commit 26dde672086cfc429e9b4ca2a48062badc91a8ea,
decision ANCHOR25_TEMPORAL_VALIDATION_PASS (5/5 fixed folds).
No persistence or publication paths exist in this module.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.db.clients.supabase_client import service_read_client
from backend.scripts.build_pokemon_collector_appeal_v7_expanded import _set_d_from_card_scores
from backend.scripts.validate_frozen_collector_appeal_v7 import (
    MODEL_RUN_ID, MODEL_VERSION, verify_frozen_artifact,
)

TEMPORAL_SHA = "26dde672086cfc429e9b4ca2a48062badc91a8ea"
TEMPORAL_DECISION = "ANCHOR25_TEMPORAL_VALIDATION_PASS"
V8_SHADOW_VERSION = "pokemon_collector_appeal_v8_anchor25_cross_domain_shadow_v1"
V13 = "overall_rip_v13_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v7"
V12 = "overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5"
ALPHA = 0.25
OUT = ROOT / "docs/research/collector_appeal/v8_anchor25_shadow"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def tie_percentiles(values: Mapping[str, float]) -> dict[str, float]:
    ordered = sorted(values.items(), key=lambda item: (item[1], item[0]))
    n = len(ordered)
    out = {}
    i = 0
    while i < n:
        j = i + 1
        while j < n and ordered[j][1] == ordered[i][1]:
            j += 1
        pct = ((i + 1 + j) / 2.0 - 0.5) / n
        for key, _ in ordered[i:j]:
            out[key] = pct
        i = j
    return out


def authorities(cards: Sequence[Mapping[str, Any]]) -> tuple[dict[str, float], dict[str, float]]:
    grouped = {"pokemon": defaultdict(list), "trainer": defaultdict(list)}
    for card in cards:
        domain = str(card.get("subject_type") or "")
        identity = str(card.get("subject_identity") or "")
        if domain in grouped and identity:
            grouped[domain][identity].append(float(card["subject_appeal_corrected"]))
    result = []
    for domain in ("pokemon", "trainer"):
        values = {}
        for identity, scores in grouped[domain].items():
            if max(scores) - min(scores) > 1e-9:
                raise RuntimeError(f"non-unique {domain} authority: {identity}")
            values[identity] = scores[0]
        result.append(values)
    return result[0], result[1]


def build_card_scores(cards: Sequence[Mapping[str, Any]]) -> tuple[dict[str, float], dict[str, float], dict[str, Any]]:
    pokemon, trainer = authorities(cards)
    pct = tie_percentiles(trainer)
    pvals = np.asarray(sorted(pokemon.values()), dtype=float)
    anchors = {
        identity: float(np.quantile(pvals, value, method="linear"))
        for identity, value in pct.items()
    }
    control, shadow = {}, {}
    crossings = []
    pokemon_delta = 0.0
    for card in cards:
        card_id = str(card["canonical_card_id"])
        base = float(card["subject_appeal_corrected"])
        v7 = float(card["card_collector_appeal_v7"])
        lift = 0.0 if base >= 100 else (v7 - base) / (100 - base)
        domain = str(card.get("subject_type") or "")
        identity = str(card.get("subject_identity") or "")
        subject = (1 - ALPHA) * base + ALPHA * anchors.get(identity, base) if domain == "trainer" else base
        v8 = subject + (100 - subject) * lift
        control[card_id] = v7
        shadow[card_id] = v8
        if domain == "pokemon":
            pokemon_delta = max(pokemon_delta, abs(v8 - v7))
        if (v7 > 50) != (v8 > 50):
            crossings.append({
                "cardId": card_id,
                "cardName": card.get("card_name"),
                "setId": card.get("set_id"),
                "rarity": card.get("rarity"),
                "hitEligible": bool(card.get("hit_eligibility")),
                "v7": v7,
                "v8": v8,
            })
    if any(row["hitEligible"] for row in crossings):
        raise RuntimeError("V8 changes hit-eligible >50 membership; F must be recomputed")
    return control, shadow, {
        "pokemonIdentities": len(pokemon),
        "trainerIdentities": len(trainer),
        "pokemonMaxDelta": pokemon_delta,
        "thresholdCrossings": crossings,
        "frequencyMembershipUnchanged": True,
    }


def set_shadow(frozen: Mapping[str, Any], control: Mapping[str, float], shadow: Mapping[str, float]):
    control_d = _set_d_from_card_scores(frozen["cards"], control)
    shadow_d = _set_d_from_card_scores(frozen["cards"], shadow)
    rows = []
    replay_errors = []
    for source in frozen["sets"]:
        set_id = str(source["set_id"])
        if set_id not in control_d or set_id not in shadow_d:
            continue
        expected_d = float(source["D_final"])
        replay_errors.append(abs(control_d[set_id] - expected_d))
        modifier = source.get("frequency_modifier")
        control_score = source.get("collector_appeal")
        candidate = None if modifier is None else min(100.0, max(0.0, shadow_d[set_id] + float(modifier)))
        rows.append({
            "setId": set_id,
            "setName": source.get("set_name"),
            "scoreStatus": "scored" if control_score is not None else "unavailable",
            "v7D": expected_d,
            "v8D": shadow_d[set_id],
            "frequencyModifier": modifier,
            "v7Collector": control_score,
            "v8CollectorShadow": candidate,
            "collectorDelta": None if control_score is None or candidate is None else candidate - float(control_score),
        })
    comparable = [row for row in rows if row["collectorDelta"] is not None]
    return rows, {
        "sets": len(rows),
        "comparableSets": len(comparable),
        "maxControlDReplayError": max(replay_errors) if replay_errors else None,
        "meanCollectorDelta": float(np.mean([row["collectorDelta"] for row in comparable])),
        "medianCollectorDelta": float(np.median([row["collectorDelta"] for row in comparable])),
        "minCollectorDelta": min(row["collectorDelta"] for row in comparable),
        "maxCollectorDelta": max(row["collectorDelta"] for row in comparable),
    }


def paged(query, size=1000):
    rows, start = [], 0
    while True:
        page = query.range(start, start + size - 1).execute().data or []
        rows.extend(page)
        if len(page) < size:
            return rows
        start += size


def tier(score: float) -> str:
    if score >= 90: return "S"
    if score >= 75: return "A"
    if score >= 55: return "B"
    if score >= 35: return "C"
    if score >= 15: return "D"
    return "F"


def overall_shadow(set_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    v7 = {row["setId"]: row["v7Collector"] for row in set_rows if row["v7Collector"] is not None}
    v8 = {row["setId"]: row["v8CollectorShadow"] for row in set_rows if row["v8CollectorShadow"] is not None}

    pointer = service_read_client.table("pokemon_overall_rip_current_publication").select(
        "publication_run_id,activated_at"
    ).eq("scope", "pokemon").execute().data or []
    if len(pointer) != 1:
        raise RuntimeError("active Overall pointer is not singular")
    active = service_read_client.table("pokemon_overall_rip_publication_runs").select(
        "id,model_version,status,market_date,expected_row_count"
    ).eq("id", pointer[0]["publication_run_id"]).execute().data or []
    if len(active) != 1 or active[0]["model_version"] != V12 or active[0]["status"] != "published":
        raise RuntimeError("active Overall authority is not published V12")

    runs = service_read_client.table("pokemon_overall_rip_publication_runs").select(
        "id,model_version,status,market_date,expected_row_count,collector_run_id,validated_at"
    ).eq("model_version", V13).eq("collector_run_id", MODEL_RUN_ID).execute().data or []
    if not runs:
        raise RuntimeError("V13 Collector V7 control run missing")
    run = sorted(runs, key=lambda row: str(row.get("validated_at") or ""))[-1]
    control_rows = paged(
        service_read_client.table("pokemon_overall_rip_publication_rows").select(
            "source_result_id,sealed_product_id,set_id,score,rank,tier"
        ).eq("publication_run_id", run["id"]).eq("eligibility_state", "ready").order("rank")
    )
    candidate = []
    for row in control_rows:
        set_id = str(row["set_id"])
        if set_id not in v7 or set_id not in v8:
            raise RuntimeError(f"missing V8 Set score for Overall row {row['source_result_id']}")
        score = round(float(row["score"]) + 0.10 * (float(v8[set_id]) - float(v7[set_id])), 4)
        candidate.append({**row, "v8Score": score})

    ranked = sorted(candidate, key=lambda row: (-row["v8Score"], str(row["sealed_product_id"])))
    for index, row in enumerate(ranked, 1):
        row["v8Rank"] = index
        row["v8Tier"] = tier(row["v8Score"])

    control_rank = {str(row["source_result_id"]): int(row["rank"]) for row in control_rows}
    deltas = [row["v8Score"] - float(row["score"]) for row in ranked]
    rank_delta = [control_rank[str(row["source_result_id"])] - row["v8Rank"] for row in ranked]
    top_control = {str(row["source_result_id"]) for row in control_rows if int(row["rank"]) <= 10}
    top_v8 = {str(row["source_result_id"]) for row in ranked if row["v8Rank"] <= 10}
    return {
        "activeV12": {**active[0], "activatedAt": pointer[0]["activated_at"]},
        "v13Control": run,
        "summary": {
            "rows": len(ranked),
            "meanScoreDelta": float(np.mean(deltas)),
            "medianScoreDelta": float(np.median(deltas)),
            "minScoreDelta": min(deltas),
            "maxScoreDelta": max(deltas),
            "rankAgreement": float(np.corrcoef(
                [control_rank[str(row["source_result_id"])] for row in ranked],
                [row["v8Rank"] for row in ranked],
            )[0, 1]),
            "rowsWithRankChange": sum(value != 0 for value in rank_delta),
            "meanAbsoluteRankDelta": float(np.mean(np.abs(rank_delta))),
            "maxAbsoluteRankDelta": max(abs(value) for value in rank_delta),
            "rowsMovingFiveOrMore": sum(abs(value) >= 5 for value in rank_delta),
            "tierChanges": sum(str(row["tier"]) != row["v8Tier"] for row in ranked),
            "top10Overlap": len(top_control & top_v8),
        },
        "rows": ranked,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, default=ROOT / "backend/artifacts/collector_appeal_v7_expanded_candidate_v1.json")
    parser.add_argument("--output-dir", type=Path, default=OUT)
    args = parser.parse_args()

    frozen = read_json(args.artifact)
    verify_frozen_artifact(frozen)
    control, shadow, card_summary = build_card_scores(frozen["cards"])
    sets, set_summary = set_shadow(frozen, control, shadow)
    if card_summary["pokemonMaxDelta"] > 1e-12:
        raise RuntimeError("Pokemon score changed")
    if set_summary["maxControlDReplayError"] > 1e-9:
        raise RuntimeError("V7 Set D replay failed")
    overall = overall_shadow(sets)

    out = args.output_dir
    write_json(out / "set_shadow.json", {"cardSummary": card_summary, "summary": set_summary, "sets": sets})
    write_json(out / "overall_shadow.json", overall)
    write_json(out / "decision.json", {
        "status": "COLLECTOR_V8_ANCHOR25_SHADOW_READY_FOR_REVIEW",
        "version": V8_SHADOW_VERSION,
        "temporalAuthoritySha": TEMPORAL_SHA,
        "temporalDecision": TEMPORAL_DECISION,
        "productionMutations": "NONE",
        "promotionAuthorized": False,
    })
    print(json.dumps({
        "status": "COLLECTOR_V8_ANCHOR25_SHADOW_READY_FOR_REVIEW",
        "cardSummary": card_summary,
        "setSummary": set_summary,
        "overallSummary": overall["summary"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
