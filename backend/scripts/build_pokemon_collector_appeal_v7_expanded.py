"""Build and optionally persist the frozen, price-blind Collector Appeal V7 candidate."""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from supabase import ClientOptions, create_client

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.scripts.build_pokemon_collector_appeal_v6_corrected_successor import (
    build as build_v6,
    canonical_hash,
    pokemon_d,
    trainer_d,
)
from backend.desirability.card_treatment_prestige_v2 import resolve_treatment_identity
from backend.desirability.collector_appeal import collector_appeal_v4_frequency_index
from backend.desirability.collector_appeal_inputs import load_pull_rate_model
from backend.desirability.opening_appeal import union_probability_from_cards
from backend.desirability.rarity_buckets import classify_rarity

MODEL_VERSION = "pokemon_collector_appeal_v7_expanded_price_blind_v1"
FROZEN_FORMULA_FINGERPRINT = "06f5660047b9b8a4d7349d04b79547b1314c2be3720c245ba8780890db1c114b"
ARTIST_CONFIG_PATH = ROOT / "backend/config/pokemon_collector_v7_artist_freeze_v1.json"
OUTPUT = ROOT / "backend/artifacts/collector_appeal_v7_expanded_candidate_v1.json"


def paged(factory, size=1000):
    rows, start = [], 0
    while True:
        part = factory().range(start, start + size - 1).execute().data or []
        rows.extend(part)
        if len(part) < size:
            return rows
        start += size


def percentile_positive(values):
    result = {key: 0.0 for key, value in values.items() if value == 0}
    ordered = sorted(((key, value) for key, value in values.items() if value > 0), key=lambda x: (x[1], x[0]))
    n, i = len(ordered), 0
    while i < n:
        j = i + 1
        while j < n and ordered[j][1] == ordered[i][1]:
            j += 1
        rank = 100.0 * ((i + j + 1) / 2.0) / n
        for key, _ in ordered[i:j]:
            result[key] = rank
        i = j
    return result


def _source_values(client, run_id):
    rows = paged(lambda: client.table("pokemon_collector_entity_observations").select(
        "collector_entity_id,normalized_observation_score,raw_row_json"
    ).eq("source_run_id", run_id))
    values, statuses = {}, {}
    for row in rows:
        raw = row.get("raw_row_json") or {}
        status = raw.get("sourceStatus")
        key = str(row["collector_entity_id"])
        if status == "valid" and row.get("normalized_observation_score") is not None:
            values[key] = float(row["normalized_observation_score"])
            statuses[key] = "SCORED"
        elif status == "genuine_zero" and raw.get("zeroConfirmed") is True:
            values[key] = 0.0
            statuses[key] = "SCORED_ZERO_HIGH_CONFIDENCE"
        else:
            statuses[key] = {
                "rate_limited": "FAILED", "failed": "FAILED", "provider_unavailable": "FAILED",
                "anchor_failure": "FAILED", "insufficient": "INSUFFICIENT_SIGNAL",
                "unscaled_tier": "INSUFFICIENT_SIGNAL",
            }.get(status, "MISSING")
    return percentile_positive(values), statuses


def _multi_credit(name):
    value = str(name or "")
    return " / " in value or "/" in value or " & " in value or ", CR CG gangs" in value


def artist_authority(client, artist_cfg, artist_12m_source_run_id, artist_5y_source_run_id):
    entities = paged(lambda: client.table("pokemon_collector_entity_reference").select(
        "id,display_name,canonical_key,identity_metadata_json"
    ).eq("entity_type", "artist").eq("active", True))
    links = paged(lambda: client.table("pokemon_card_collector_entity_links").select(
        "pokemon_canonical_card_id,collector_entity_id,match_method,match_confidence"
    ).eq("link_role", "artist").eq("active", True))
    p12, s12 = _source_values(client, artist_12m_source_run_id)
    p5, s5 = _source_values(client, artist_5y_source_run_id)
    by_id = {str(x["id"]): x for x in entities}
    scores, status = {}, {}
    ambiguous_names = set((artist_cfg.get("identityClassification") or {}).get("ambiguousExactNames") or {})
    for key, entity in by_id.items():
        if _multi_credit(entity["display_name"]) or entity["display_name"] in ambiguous_names:
            status[key] = "AMBIGUOUS"
        elif key in p12 and key in p5:
            scores[key] = 0.4 * p12[key] + 0.6 * p5[key]
            status[key] = "SCORED_ZERO_HIGH_CONFIDENCE" if p12[key] == p5[key] == 0 else "SCORED"
        elif s12.get(key) == "FAILED" or s5.get(key) == "FAILED":
            status[key] = "FAILED"
        elif s12.get(key) == "INSUFFICIENT_SIGNAL" or s5.get(key) == "INSUFFICIENT_SIGNAL":
            status[key] = "INSUFFICIENT_SIGNAL"
        else:
            status[key] = "MISSING"
    card_entities = defaultdict(list)
    for link in links:
        card_entities[str(link["pokemon_canonical_card_id"])].append(str(link["collector_entity_id"]))
    return by_id, card_entities, scores, status


def artist_lift(v6_score, artist_score, strength=0.10):
    if artist_score is None:
        return 0.0
    return (100.0 - v6_score) * strength * min(100.0, max(0.0, artist_score)) / 100.0


def _rank(values):
    return {key: i + 1 for i, (key, _) in enumerate(sorted(values.items(), key=lambda x: (-x[1], x[0])))}


def _spearman(a, b):
    keys = sorted(set(a) & set(b))
    if len(keys) < 2:
        return None
    ra, rb = _rank({k: a[k] for k in keys}), _rank({k: b[k] for k in keys})
    return 1 - 6 * sum((ra[k] - rb[k]) ** 2 for k in keys) / (len(keys) * (len(keys) ** 2 - 1))


def _set_d_from_card_scores(cards, scores):
    grouped = defaultdict(list)
    for row in cards:
        grouped[row["set_id"]].append(row)
    result = {}
    for set_id, rows in grouped.items():
        pg, tg = defaultdict(list), defaultdict(list)
        for row in rows:
            target = pg if row["subject_type"] == "pokemon" else tg if row["subject_type"] == "trainer" else None
            if target is not None:
                for name in str(row.get("subject_identity") or "").split(" + "):
                    if name.strip():
                        target[name.strip()].append(scores[row["canonical_card_id"]])
        dp = pokemon_d([max(x) for x in pg.values()])[0]
        dt = trainer_d([max(x) for x in tg.values()])
        result[set_id] = dp + (100 - dp) * 0.15 * dt / 100
    return result


def build(client, *, pokemon_trends_source_run_id: str,
          trainer_12m_source_run_id: str, trainer_5y_source_run_id: str,
          artist_12m_source_run_id: str, artist_5y_source_run_id: str,
          playability_source_run_id: str):
    control = build_v6(
        client, pokemon_trends_source_run_id=pokemon_trends_source_run_id,
        trainer_12m_source_run_id=trainer_12m_source_run_id,
        trainer_5y_source_run_id=trainer_5y_source_run_id,
        playability_source_run_id=playability_source_run_id,
    )
    artist_cfg = json.loads(ARTIST_CONFIG_PATH.read_text(encoding="utf-8"))
    entities, card_entities, artist_scores, artist_status = artist_authority(
        client, artist_cfg, artist_12m_source_run_id, artist_5y_source_run_id)
    pull = load_pull_rate_model(client)
    cards = []
    for row in control["cards"]:
        card_id = row["canonical_card_id"]
        ids = card_entities.get(card_id, [])
        available = [artist_scores[x] for x in ids if x in artist_scores]
        score = max(available) if available else None
        statuses = [artist_status.get(x, "MISSING") for x in ids]
        evidence = ("SCORED_ZERO_HIGH_CONFIDENCE" if score == 0 and statuses and all(x == "SCORED_ZERO_HIGH_CONFIDENCE" for x in statuses) else "SCORED") if score is not None else statuses[0] if len(set(statuses)) == 1 and statuses else "AMBIGUOUS" if "AMBIGUOUS" in statuses else "MISSING"
        before = float(row["card_collector_appeal_corrected"])
        lift = artist_lift(before, score)
        treatment = resolve_treatment_identity(rarity=row.get("rarity"))
        scarcity = (pull.get(row["set_id"]) or {}).get(classify_rarity(row.get("rarity")).normalized_key)
        cards.append({
            **row,
            "artist_identified": bool(ids),
            "artist_entity_ids": ids,
            "artist_names": [entities[x]["display_name"] for x in ids if x in entities],
            "artist_appeal_score": score,
            "artist_evidence_status": evidence,
            "artist_lift_points": lift,
            "card_collector_appeal_v7": before + lift,
            "treatment_diagnostic": {"status": treatment.status, "treatmentKey": treatment.treatment_key},
            "pull_scarcity_diagnostic": None if not scarcity else {"probability": scarcity["probability"], "slotGroup": scarcity["slot_group"]},
        })
    old_sets = {x["set_id"]: x for x in control["sets"]}
    byset = defaultdict(list)
    for row in cards:
        if row["set_id"] in old_sets:
            byset[row["set_id"]].append(row)
    sets = []
    for sid, rows in byset.items():
        pg, tg = defaultdict(list), defaultdict(list)
        for row in rows:
            target = pg if row["subject_type"] == "pokemon" else tg if row["subject_type"] == "trainer" else None
            if target is not None:
                for name in str(row.get("subject_identity") or "").split(" + "):
                    if name.strip():
                        target[name.strip()].append(row["card_collector_appeal_v7"])
        dp, strength, breadth = pokemon_d([max(x) for x in pg.values()])
        dt = trainer_d([max(x) for x in tg.values()])
        trainer_lift = (100 - dp) * 0.15 * dt / 100
        d_final = dp + trainer_lift
        desirable = [r for r in rows if r.get("hit_eligibility") and r["card_collector_appeal_v7"] > 50]
        modeled = []
        for row in desirable:
            scarcity = row["pull_scarcity_diagnostic"]
            if scarcity:
                modeled.append({"canonical_card_id": row["canonical_card_id"], "pull_probability": scarcity["probability"], "slot_group": scarcity["slotGroup"]})
        excess = sum(r["card_collector_appeal_v7"] - 50 for r in desirable)
        covered_ids = {r["canonical_card_id"] for r in modeled}
        covered = sum(r["card_collector_appeal_v7"] - 50 for r in desirable if r["canonical_card_id"] in covered_ids)
        coverage = covered / excess if excess else None
        f = union_probability_from_cards(list({x["canonical_card_id"]: x for x in modeled}.values())) if modeled and coverage is not None and coverage >= 0.25 else None
        index = collector_appeal_v4_frequency_index(f) if f is not None else None
        z = 2 * index - 1 if index is not None else None
        modifier = (2 * z if z >= 0 else z) if z is not None else None
        final = min(100.0, max(0.0, d_final + modifier)) if modifier is not None else None
        v6 = old_sets[sid]
        old_ids = {r["canonical_card_id"] for r in rows if r.get("hit_eligibility") and r["card_collector_appeal_corrected"] > 50}
        new_ids = {r["canonical_card_id"] for r in desirable}
        sets.append({
            "set_id": sid, "set_name": v6["set_name"], "D_pokemon": dp, "S": strength, "B": breadth,
            "D_trainer": dt, "trainer_lift_points": trainer_lift, "D_final": d_final, "F": f,
            "frequency_index": index, "frequency_modifier": modifier, "collector_appeal": final,
            "v6_D_final": v6["D_final"], "D_delta": d_final - v6["D_final"], "v6_F": v6["F"],
            "F_delta": None if f is None or v6["F"] is None else f - v6["F"],
            "v6_collector_appeal": v6["collector_appeal"],
            "collector_delta": None if final is None or v6["collector_appeal"] is None else final - v6["collector_appeal"],
            "desirable_card_count": len(desirable), "entering_cards": sorted(new_ids - old_ids), "leaving_cards": sorted(old_ids - new_ids),
            "unavailable_reason": None if final is not None else "collector_appeal_unavailable_no_generalized_frequency",
        })
    ranked = sorted((x for x in sets if x["collector_appeal"] is not None), key=lambda x: (-x["collector_appeal"], x["set_id"]))
    for i, row in enumerate(ranked, 1):
        row["rank"] = i
    config = {
        "version": MODEL_VERSION, "artist": artist_cfg,
        "trainer": {"version": "trainer_appeal_trends_40_60_percentile_v1", "weights": {"12m": 0.4, "5y": 0.6}},
        "playability": {"version": "collector_c3b_corrected_raw_pokemon_v1", "lambda": 0.2, "ordering": "subject_then_playability_then_artist"},
        "setAggregation": "unchanged_frozen_v6_D_plus_trainer_headroom", "frequency": "unchanged_generalized_F_card_gt_50",
        "c5": "unchanged_collector_c5_frozen_signed_frequency_v1", "treatment": "diagnostic_only", "scarcity": "diagnostic_only", "marketValueInput": "excluded",
    }
    formula_contract = {"modelVersion":MODEL_VERSION,"pokemonWeights":[.75,.25],
        "trainerWeights":[.4,.6],"artistWeights":[.4,.6],"artistLambda":.10,
        "playabilityLambda":.20,"trainerSetLambda":.15,"pokemonD":"frozen_v6_v7",
        "frequency":"unchanged_generalized_F_card_gt_50","c5":"unchanged_collector_c5_frozen_signed_frequency_v1",
        "price":"excluded","treatment":"diagnostic_only","scarcity":"diagnostic_only"}
    formula_contract_fp = canonical_hash(formula_contract)
    formula_fp = FROZEN_FORMULA_FINGERPRINT
    card_fp = canonical_hash([{k: x[k] for k in ("canonical_card_id", "artist_appeal_score", "artist_evidence_status", "artist_lift_points", "card_collector_appeal_v7")} for x in sorted(cards, key=lambda x: x["canonical_card_id"])])
    set_fp = canonical_hash([{k: x[k] for k in ("set_id", "D_pokemon", "D_trainer", "trainer_lift_points", "D_final", "F", "frequency_modifier", "collector_appeal")} for x in sorted(sets, key=lambda x: x["set_id"])])
    status_counts = {s: sum(x["artist_evidence_status"] == s for x in cards) for s in sorted({x["artist_evidence_status"] for x in cards})}
    base_card = {x["canonical_card_id"]: x["card_collector_appeal_corrected"] for x in cards}
    final_card = {x["canonical_card_id"]: x["card_collector_appeal_v7"] for x in cards}
    analysis = {
        "artistIdentityCount": len(entities), "linkedCardCount": len(card_entities), "cardArtistStatusCounts": status_counts,
        "artistScoredIdentityCount": len(artist_scores), "artistNullIdentityCount": len(entities) - len(artist_scores),
        "cardRankSpearmanVsV6": _spearman(base_card, final_card),
        "unchangedCards": sum(abs(final_card[k] - base_card[k]) < 1e-12 for k in base_card),
        "supportedSetCount": len(ranked), "setRankSpearmanVsV6": _spearman(
            {x["set_id"]: x["v6_collector_appeal"] for x in sets if x["v6_collector_appeal"] is not None},
            {x["set_id"]: x["collector_appeal"] for x in sets if x["collector_appeal"] is not None}),
        "robustness": {},
    }
    baseline_set_d = {x["set_id"]: x["D_final"] for x in sets}
    for factor in (0.8, 0.9, 1.1, 1.2):
        perturbed = {x["canonical_card_id"]: x["card_collector_appeal_corrected"] + artist_lift(x["card_collector_appeal_corrected"], None if x["artist_appeal_score"] is None else x["artist_appeal_score"] * factor) for x in cards}
        perturbed_set_d = _set_d_from_card_scores(cards, perturbed)
        analysis["robustness"][f"artistX{factor}"] = {"cardRankSpearman": _spearman(final_card, perturbed), "setRankSpearman": _spearman(baseline_set_d, perturbed_set_d), "maxCardMovement": max(abs(perturbed[k] - final_card[k]) for k in final_card), "maxSetDMovement": max(abs(perturbed_set_d[k]-baseline_set_d[k]) for k in baseline_set_d)}
    for domain, factors in (("trainer", (0.8, 1.2)), ("playability", (0.8, 1.2))):
        for factor in factors:
            perturbed = {}
            for x in cards:
                subject = float(x["subject_appeal_corrected"])
                if domain == "trainer" and x["subject_type"] == "trainer":
                    subject = min(100.0, subject * factor)
                raw, confidence = x.get("playability_raw_score"), x.get("confidence")
                effective = 0.0 if raw is None or confidence is None else float(raw) * float(confidence)
                play_strength = 0.2 * factor if domain == "playability" else 0.2
                after_play = subject + (100-subject) * play_strength * effective / 100
                perturbed[x["canonical_card_id"]] = after_play + artist_lift(after_play, x["artist_appeal_score"])
            perturbed_set_d = _set_d_from_card_scores(cards, perturbed)
            analysis["robustness"][f"{domain}X{factor}"] = {"cardRankSpearman":_spearman(final_card,perturbed),"setRankSpearman":_spearman(baseline_set_d,perturbed_set_d),"maxCardMovement":max(abs(perturbed[k]-final_card[k]) for k in final_card),"maxSetDMovement":max(abs(perturbed_set_d[k]-baseline_set_d[k]) for k in baseline_set_d)}
    source_ids=[pokemon_trends_source_run_id,trainer_12m_source_run_id,
                trainer_5y_source_run_id,playability_source_run_id,
                artist_12m_source_run_id,artist_5y_source_run_id]
    dependencies={"c3a5SubjectFingerprint":control["compositeFingerprint"],"c3bFingerprint":formula_fp,"c4RosterFingerprint":canonical_hash({"aggregation":config["setAggregation"],"cardFingerprint":card_fp}),"c4FrequencyFingerprint":canonical_hash({"frequency":config["frequency"],"cardFingerprint":card_fp}),"c5Fingerprint":canonical_hash({"c5":config["c5"],"setFingerprint":set_fp})}
    expected={"cardRows":len(cards),"c4Rows":len(sets),"c5Rows":len(sets),"scoredRows":len(ranked),"unavailableRows":len(sets)-len(ranked)}
    model_fp=canonical_hash({"version":MODEL_VERSION,"dependencies":dependencies,"sourceRunIds":source_ids,"expectedCounts":expected,"config":config})
    manifest = {"modelVersion": MODEL_VERSION, "modelFingerprint": model_fp,"topLevelInputFingerprint":model_fp,"formulaFingerprint": formula_fp,"formulaContractFingerprint":formula_contract_fp,"formulaContract":formula_contract, "cardFingerprint": card_fp, "setFingerprint": set_fp,"dependencies":dependencies,"sourceRunIds":source_ids,"sourceAuthority":{"pokemonTrends":pokemon_trends_source_run_id,"trainer12m":trainer_12m_source_run_id,"trainer5y":trainer_5y_source_run_id,"playability":playability_source_run_id,"artist12m":artist_12m_source_run_id,"artist5y":artist_5y_source_run_id},"expectedCounts":expected, "config": config, "counts": {"cards": len(cards), "sets": len(sets), "scoredSets": len(ranked), "unavailableSets": len(sets)-len(ranked)}, "analysis": analysis}
    return {"manifest": manifest, "cards": cards, "sets": sets}


def persistence_rows(built, run_id):
    authority = built["manifest"]["sourceAuthority"]
    cards = []
    for x in built["cards"]:
        baseline = x["subject_appeal_corrected"]
        play_points = x["applied_lift_corrected"]
        artist_points = x["artist_lift_points"]
        total = play_points + artist_points
        cards.append({"model_run_id": run_id, "pokemon_canonical_card_id": x["canonical_card_id"], "set_id": x["set_id"],
            "subject_policy": {"pokemon":"pokemon","trainer":"trainer","neutral_functional":"neutral"}[x["subject_type"]],
            "subject_baseline_score": baseline, "artist_recognition_score": x["artist_appeal_score"],
            "playability_score": None if x.get("playability_raw_score") is None else float(x["playability_raw_score"])*float(x["confidence"]),
            "artist_lift": artist_points/(100-baseline) if baseline < 100 else 0, "playability_lift": play_points/(100-baseline) if baseline < 100 else 0,
            "combined_lift": total/(100-baseline) if baseline < 100 else 0, "collector_card_appeal_score": x["card_collector_appeal_v7"],
            "score_status":"scored", "confidence":"high" if x["artist_appeal_score"] is not None else "insufficient",
            "price_input_excluded":True,"treatment_input_excluded":True,"hit_eligibility_independent":True,
            "component_inputs_json":{"subjectType":x["subject_type"],"subjectIdentity":x.get("subject_identity"),"artistIdentified":x["artist_identified"],"artistNames":x["artist_names"],"artistEvidenceStatus":x["artist_evidence_status"],"playabilityLiftPoints":play_points,"artistLiftPoints":artist_points,"playabilityOrder":"subject_then_playability_then_artist","treatmentDiagnostic":x["treatment_diagnostic"],"pullScarcityDiagnostic":x["pull_scarcity_diagnostic"]},
            "lineage_json":{"formulaFingerprint":built["manifest"]["formulaFingerprint"],"sourceAuthority":authority,"artistSourceRuns":[authority["artist12m"],authority["artist5y"]],"excludedInputs":["price","Treatment","Pull Scarcity"]}})
    d_rank = _rank({x["set_id"]:x["D_final"] for x in built["sets"]})
    drows, arows = [], []
    for x in built["sets"]:
        subset=[c for c in built["cards"] if c["set_id"]==x["set_id"]]
        drows.append({"model_run_id":run_id,"set_id":x["set_id"],"aggregation_version":"v6_frozen_D_artist_enhanced_cards_v1","collector_desirability_score":x["D_final"],"collector_desirability_rank":d_rank[x["set_id"]],"eligible_card_count":sum(bool(c.get("hit_eligibility")) for c in subset),"scored_card_count":sum(c["subject_type"]!="neutral_functional" and bool(c.get("hit_eligibility")) for c in subset),"neutral_card_count":sum(c["subject_type"]=="neutral_functional" and bool(c.get("hit_eligibility")) for c in subset),"unsupported_card_count":0,"score_coverage_ratio":1,"max_card_appeal_score":max(c["card_collector_appeal_v7"] for c in subset),"top_3_card_appeal_score":None,"top_5_card_appeal_score":None,"effective_desirable_card_count":x["desirable_card_count"],"subject_rollups_json":[],"top_cards_json":[],"component_inputs_json":{"D_pokemon":x["D_pokemon"],"D_trainer":x["D_trainer"],"trainerLiftPoints":x["trainer_lift_points"],"trainerLambda":.15,"artistCardLiftLambda":.10},"diagnostics_json":{"S":x["S"],"B":x["B"],"v6D":x["v6_D_final"],"DDelta":x["D_delta"]}})
        deps=built["manifest"]["dependencies"]
        arows.append({"model_run_id":run_id,"set_id":x["set_id"],"collector_roster_desirability_score":x["D_final"],"generalized_desirable_outcome_frequency":x["F"],"generalized_frequency_status":"available" if x["F"] is not None else "unavailable","generalized_frequency_status_reason":None if x["F"] is not None else x["unavailable_reason"],"frequency_index":x["frequency_index"],"frequency_modifier_points":x["frequency_modifier"],"collector_appeal_score":x["collector_appeal"],"score_status":"scored" if x["collector_appeal"] is not None else "unavailable","score_status_reason":x["unavailable_reason"],"collector_appeal_rank":x.get("rank"),"component_inputs_json":{"formula":"signed_up2_down1","frequencyThreshold":">50","artistEligibilityEffect":"card_v7_gt_50","excludedInputs":["price","Treatment","Pull Scarcity as direct score"]},"diagnostics_json":{"v6F":x["v6_F"],"FDelta":x["F_delta"],"v6CollectorAppeal":x["v6_collector_appeal"],"collectorDelta":x["collector_delta"]},"lineage_json":{"c3bFingerprint":deps["c3bFingerprint"],"c4RosterFingerprint":deps["c4RosterFingerprint"],"c4FrequencyFingerprint":deps["c4FrequencyFingerprint"],"c5Fingerprint":deps["c5Fingerprint"],"cardFingerprint":built["manifest"]["cardFingerprint"],"setFingerprint":built["manifest"]["setFingerprint"]}})
    return cards,drows,arows


def persist_built_model(client, built, *, as_of_date):
    """Append and validate one explicitly-bound V7 run; never resolve latest."""
    manifest = built["manifest"]
    if manifest.get("formulaFingerprint") != FROZEN_FORMULA_FINGERPRINT:
        raise RuntimeError("V7_FROZEN_FORMULA_DRIFT_BLOCKER")
    source_ids = manifest["sourceRunIds"]
    existing = client.table("pokemon_collector_appeal_model_runs").select(
        "id,status,validation_json").eq("model_version", MODEL_VERSION).eq(
        "input_fingerprint", manifest["modelFingerprint"]).execute().data or []
    if existing:
        row=existing[0]
        if row.get("status") not in ("validated","published") or not (row.get("validation_json") or {}).get("passed"):
            raise RuntimeError(f"matching Collector V7 run {row['id']} is not reusable")
        return str(row["id"]), row.get("validation_json"), False
    run = client.table("pokemon_collector_appeal_model_runs").insert({
        "model_version":MODEL_VERSION,"as_of_date":str(as_of_date),
        "source_run_ids":source_ids,"input_fingerprint":manifest["modelFingerprint"],
        "scoring_config_json":manifest,"price_policy":"excluded",
        "treatment_policy":"disabled_v1","energy_policy":"neutral_v1",
        "hit_eligibility_policy":"independent",
        "diagnostics_json":{"publicationBoundary":"staged_not_current",
                            "explicitSourceAuthority":manifest["sourceAuthority"]},
    }).execute().data[0]
    run_id = str(run["id"])
    client.table("pokemon_collector_appeal_model_run_sources").insert([
        {"model_run_id":run_id,"source_run_id":source_id,"source_position":position}
        for position,source_id in enumerate(source_ids,1)]).execute()
    for table, rows in zip(("pokemon_card_collector_appeal_scores",
                            "pokemon_set_collector_desirability_scores",
                            "pokemon_set_collector_appeal_scores"),
                           persistence_rows(built,run_id)):
        for index in range(0,len(rows),100):
            client.table(table).insert(rows[index:index+100]).execute()
    validation = client.rpc("validate_pokemon_collector_appeal_model_run",{
        "p_model_run_id":run_id,"p_diagnostics":{"builder":"build_pokemon_collector_appeal_v7_expanded.py",
        "explicitSourceAuthority":manifest["sourceAuthority"],"formulaInvariant":True}}).execute().data
    if not validation or validation.get("passed") is not True:
        raise RuntimeError("Collector V7 model validation failed")
    return run_id, validation, True


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--write-stage",action="store_true");parser.add_argument("--reuse-output",action="store_true");parser.add_argument("--output",type=Path,default=OUTPUT)
    for flag in ("pokemon-trends","trainer-12m","trainer-5y","playability","artist-12m","artist-5y"):
        parser.add_argument(f"--{flag}-source-run-id",required=True)
    args=parser.parse_args()
    load_dotenv(ROOT/"backend/.env",override=False)
    import os
    client=create_client(os.environ["SUPABASE_URL"],os.environ["SUPABASE_SERVICE_ROLE_KEY"],options=ClientOptions(postgrest_client_timeout=90))
    if args.reuse_output:
        built=json.loads(args.output.read_text(encoding="utf-8"))
        if built.get("manifest",{}).get("modelVersion")!=MODEL_VERSION:raise RuntimeError("reused artifact is not frozen V7")
    else:
        built=build(client,pokemon_trends_source_run_id=args.pokemon_trends_source_run_id,
            trainer_12m_source_run_id=args.trainer_12m_source_run_id,
            trainer_5y_source_run_id=args.trainer_5y_source_run_id,
            playability_source_run_id=args.playability_source_run_id,
            artist_12m_source_run_id=args.artist_12m_source_run_id,
            artist_5y_source_run_id=args.artist_5y_source_run_id);args.output.write_text(json.dumps(built,indent=2,ensure_ascii=False),encoding="utf-8")
    if built["manifest"].get("sourceAuthority") != {"pokemonTrends":args.pokemon_trends_source_run_id,"trainer12m":args.trainer_12m_source_run_id,"trainer5y":args.trainer_5y_source_run_id,"playability":args.playability_source_run_id,"artist12m":args.artist_12m_source_run_id,"artist5y":args.artist_5y_source_run_id}:raise RuntimeError("reused V7 artifact does not match explicit source authority")
    existing=client.table("pokemon_collector_appeal_model_runs").select("id,status,validation_json").eq("model_version",MODEL_VERSION).eq("input_fingerprint",built["manifest"]["modelFingerprint"]).execute().data or []
    run_id=str(existing[0]["id"]) if existing else None; validation=existing[0].get("validation_json") if existing else None
    if args.write_stage:
        run_id,validation,_=persist_built_model(client,built,as_of_date=date.today().isoformat())
    print(json.dumps({"mode":"write-stage" if args.write_stage else "dry-run","modelRunId":run_id,**built["manifest"],"validation":validation},indent=2));return 0


if __name__=="__main__":raise SystemExit(main())
