"""C3B price-independent bounded Playability-lift research and card shadow export."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.desirability.rarity_buckets import HIT_BUCKETS, classify_rarity
LIMITLESS_RUN = "9947aaf7-8647-484f-8c9c-2cec59792cdb"
TRAINER_12M = "b3997343-1363-45aa-b1b0-9a6de1ce3793"
TRAINER_5Y = "648e5375-47cb-4972-b01d-faceb6348d1d"
SUBJECT_FINGERPRINT = "0773b4d23fd4f50ceaab2598c5f33de12ba2a60f3f04d902e4c7720e5ac8d4af"
VERSION = "collector_c3b_bounded_playability_lift_research_v2"
LAMBDAS = (0.10, 0.15, 0.20, 0.25, 0.30, 0.40)
WINNER = 0.20


def pranks(values):
    out = {key: 0.0 for key, value in values.items() if value == 0}
    ordered = sorted(((key, value) for key, value in values.items() if value != 0), key=lambda item: (item[1], item[0]))
    n, index = max(len(ordered), 1), 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][1] == ordered[index][1]: end += 1
        rank = 100 * ((index + end + 1) / 2) / n
        for key, _ in ordered[index:end]: out[key] = rank
        index = end
    return out


def spearman(a, b):
    keys = set(a) & set(b)
    if len(keys) < 2: return None
    ra, rb = pranks({key: a[key] for key in keys}), pranks({key: b[key] for key in keys})
    ma, mb = statistics.mean(ra.values()), statistics.mean(rb.values())
    numerator = sum((ra[key] - ma) * (rb[key] - mb) for key in keys)
    denominator = math.sqrt(sum((ra[key] - ma) ** 2 for key in keys) * sum((rb[key] - mb) ** 2 for key in keys))
    return numerator / denominator if denominator else None


def summary(scores):
    values = sorted(scores.values()); n = len(values)
    at = lambda p: values[min(n - 1, int((n - 1) * p))] if n else None
    return {"count": n, "min": at(0), "p10": at(.1), "p25": at(.25), "median": at(.5),
            "p75": at(.75), "p90": at(.9), "p95": at(.95), "max": at(1),
            "mean": statistics.mean(values) if values else None}


def paged(factory, size=1000):
    rows, start = [], 0
    while True:
        page = factory().range(start, start + size - 1).execute().data or []
        rows.extend(page)
        if len(page) < size:
            return rows
        start += size


def bounded_score(subject, playability, lift_strength):
    subject = min(100.0, max(0.0, float(subject)))
    if playability is None:
        return subject
    playability = min(100.0, max(0.0, float(playability)))
    return subject + (100.0 - subject) * lift_strength * playability / 100.0


def confidence_factor(events, decks):
    return (1.0 - math.exp(-max(0, decks) / 20.0)) * (0.5 + 0.5 * min(max(0, events) / 3.0, 1.0))


def playability_status(events, decks, has_evidence=True):
    if not has_evidence:
        return "unknown"
    return "scoreable" if events >= 3 or decks >= 20 else "insufficient"


def percentile_summary(values):
    return summary({str(i): value for i, value in enumerate(values)}) if values else summary({})


def lift_buckets(lifts):
    counts = Counter()
    for value in lifts:
        if value < 1: counts["lt1"] += 1
        elif value < 3: counts["1to3"] += 1
        elif value < 5: counts["3to5"] += 1
        elif value <= 10: counts["5to10"] += 1
        else: counts["gt10"] += 1
    n = len(lifts) or 1
    return {key: {"count": counts[key], "share": counts[key] / n} for key in ("lt1", "1to3", "3to5", "5to10", "gt10")}


def rank_diagnostics(base, final):
    rb, rf = pranks(base), pranks(final)
    movement = {key: abs(rf[key] - rb[key]) for key in base}
    return {
        "spearmanVsSubject": spearman(base, final),
        "absolutePercentileMovement": summary(movement),
        "movedAtLeast5PercentilePoints": sum(value >= 5 for value in movement.values()),
        "movedAtLeast10PercentilePoints": sum(value >= 10 for value in movement.values()),
    }


def build_playability(client, source_run_id=LIMITLESS_RUN):
    observations = paged(lambda: client.table("pokemon_playability_event_observations").select("*").eq("source_run_id", source_run_id))
    grouped = defaultdict(list)
    for row in observations:
        if row.get("functional_reference_id"):
            grouped[str(row["functional_reference_id"])].append(row)
    event_fields, event_dates = {}, {}
    for row in observations:
        event_fields[str(row["event_external_id"])] = int(row["field_deck_count"])
        event_dates[str(row["event_external_id"])] = date.fromisoformat(row["event_date"])
    denominator = sum(event_fields.values())
    features = {}
    for key, rows in grouped.items():
        appearances = sum(int(row["deck_appearance_count"]) for row in rows)
        copies = sum(int(row["copy_count"]) for row in rows)
        top = sum(int(row["top_cut_deck_count"]) for row in rows)
        events = len({str(row["event_external_id"]) for row in rows})
        features[key] = {
            "inclusion": appearances / denominator,
            "copiesPerUsingDeck": copies / max(appearances, 1),
            "eventBreadth": events / len(event_fields),
            "topCut": top / max(32 * len(event_fields), 1),
            "weightedCopies": copies / denominator,
            "decks": appearances,
            "events": events,
        }
    fields = ("inclusion", "copiesPerUsingDeck", "eventBreadth", "topCut", "weightedCopies")
    ranks = {field: pranks({key: row[field] for key, row in features.items()}) for field in fields}
    result = {}
    for key, row in features.items():
        raw = (.45 * ranks["inclusion"][key] + .15 * ranks["copiesPerUsingDeck"][key]
               + .15 * ranks["eventBreadth"][key] + .15 * ranks["topCut"][key]
               + .10 * ranks["weightedCopies"][key])
        confidence = confidence_factor(row["events"], row["decks"])
        status = playability_status(row["events"], row["decks"])
        result[key] = {**row, "rawScore": raw, "confidence": confidence,
                       "candidateC": raw * confidence, "status": status}
    return result


def trainer_scores(client, trainer_12m_source_run_id=TRAINER_12M,
                   trainer_5y_source_run_id=TRAINER_5Y):
    def run(run_id):
        rows = client.table("pokemon_collector_entity_observations").select(
            "collector_entity_id,normalized_observation_score").eq("source_run_id", run_id).execute().data or []
        return {str(row["collector_entity_id"]): float(row["normalized_observation_score"] or 0) for row in rows}
    p12, p5 = pranks(run(trainer_12m_source_run_id)), pranks(run(trainer_5y_source_run_id))
    return {key: .4 * p12[key] + .6 * p5[key] for key in set(p12) & set(p5)}


def main(output_path):
    load_dotenv(ROOT / "backend/.env", override=False)
    from backend.db.clients.supabase_client import supabase

    exception_payload = json.loads((ROOT / "backend/config/pokemon_collector_neutral_subject_exceptions_v1.json").read_text(encoding="utf-8"))
    exceptions = exception_payload["exceptions"]
    cohort_contract = json.loads((ROOT / "backend/config/pokemon_collector_c3b_eligible_cohort_v1.json").read_text(encoding="utf-8"))
    cards = paged(lambda: supabase.table("pokemon_canonical_cards").select(
        "id,set_id,pokemon_tcg_api_card_id,name,supertype,subtypes,rarity,catalog_role,opening_eligible,canonical_review_status")
        .eq("catalog_role", "main").eq("opening_eligible", True).eq("canonical_review_status", "approved"))
    cards = [row for row in cards if str(row.get("supertype") or "").casefold() in {"pokémon", "pokemon", "trainer"}]
    card_ids = {str(row["id"]) for row in cards}
    functional_links = paged(lambda: supabase.table("pokemon_card_functional_links").select(
        "pokemon_canonical_card_id,functional_reference_id,match_confidence").eq("active", True))
    functional_by_card = {str(row["pokemon_canonical_card_id"]): row for row in functional_links if str(row["pokemon_canonical_card_id"]) in card_ids}
    functional_refs = paged(lambda: supabase.table("pokemon_card_functional_reference").select(
        "id,functional_key,display_name,supertype,functional_identity_json").eq("active", True))
    refs = {str(row["id"]): row for row in functional_refs}
    play = build_playability(supabase)

    pokemon_scores = paged(lambda: supabase.table("pokemon_desirability_composite_scores").select(
        "pokemon_reference_id,pokemon_name,desirability_score").eq("scoring_version", "pokemon_desirability_composite_v1").eq("fan_popularity_snapshot_id", 2))
    pokemon_raw = {str(row["pokemon_reference_id"]): float(row["desirability_score"]) for row in pokemon_scores}
    pokemon_pct = pranks(pokemon_raw)
    pokemon_names = {str(row["pokemon_reference_id"]): row["pokemon_name"] for row in pokemon_scores}
    desirability_links = paged(lambda: supabase.table("pokemon_card_desirability_links").select(
        "pokemon_canonical_card_id,pokemon_reference_id,contribution_weight,is_hit_eligible"))
    pokemon_by_card = defaultdict(list)
    for row in desirability_links:
        if str(row["pokemon_canonical_card_id"]) in card_ids:
            pokemon_by_card[str(row["pokemon_canonical_card_id"])].append(row)

    trainers = trainer_scores(supabase)
    entity_refs = paged(lambda: supabase.table("pokemon_collector_entity_reference").select("id,display_name,entity_type").eq("active", True))
    entity_names = {str(row["id"]): row["display_name"] for row in entity_refs}
    collector_links = paged(lambda: supabase.table("pokemon_card_collector_entity_links").select(
        "pokemon_canonical_card_id,collector_entity_id,contribution_weight,link_role").eq("active", True).eq("link_role", "subject"))
    trainer_by_card = defaultdict(list)
    for row in collector_links:
        cid, eid = str(row["pokemon_canonical_card_id"]), str(row["collector_entity_id"])
        if cid in card_ids and eid in trainers:
            trainer_by_card[cid].append(row)

    rows = []
    for card in cards:
        cid, supertype = str(card["id"]), str(card.get("supertype") or "")
        subjects = pokemon_by_card.get(cid, []) if supertype.casefold() in {"pokémon", "pokemon"} else trainer_by_card.get(cid, [])
        if subjects and supertype.casefold() in {"pokémon", "pokemon"}:
            weights = [float(x.get("contribution_weight") or 0) for x in subjects]; den = sum(weights) or 1
            raw = sum(pokemon_raw.get(str(x["pokemon_reference_id"]), 0) * w for x, w in zip(subjects, weights)) / den
            baseline = sum(pokemon_pct.get(str(x["pokemon_reference_id"]), 0) * w for x, w in zip(subjects, weights)) / den
            subject_type = "pokemon"; identity = " + ".join(pokemon_names.get(str(x["pokemon_reference_id"]), "unknown") for x in subjects)
        elif subjects:
            weights = [float(x.get("contribution_weight") or 0) for x in subjects]; den = sum(weights) or 1
            raw = baseline = sum(trainers[str(x["collector_entity_id"])] * w for x, w in zip(subjects, weights)) / den
            subject_type = "trainer"; identity = " + ".join(entity_names.get(str(x["collector_entity_id"]), "unknown") for x in subjects)
        elif str(card.get("pokemon_tcg_api_card_id")) in exceptions:
            exception = exceptions[str(card["pokemon_tcg_api_card_id"])]
            raw = baseline = float(exception["subjectAppeal"]); subject_type = "neutral_functional"; identity = exception["classification"]
        elif supertype.casefold() == "trainer":
            raw = baseline = 50.0; subject_type = "neutral_functional"; identity = None
        else:
            raw = baseline = None; subject_type = "subject_unavailable"; identity = None
        flink = functional_by_card.get(cid); fid = str(flink["functional_reference_id"]) if flink else None
        evidence = play.get(fid) if fid else None
        status = evidence["status"] if evidence else "unknown"
        applied_play = evidence["candidateC"] if evidence and status == "scoreable" else None
        hit = (any(bool(x.get("is_hit_eligible")) for x in pokemon_by_card.get(cid, []))
               if pokemon_by_card.get(cid) else classify_rarity(card.get("rarity")).bucket in HIT_BUCKETS)
        final = bounded_score(baseline, applied_play, WINNER) if baseline is not None else None
        rows.append({"canonical_card_id": cid, "card_name": card["name"], "supertype": supertype,
            "set_id": str(card["set_id"]), "pokemon_tcg_api_card_id": card.get("pokemon_tcg_api_card_id"), "rarity": card.get("rarity"),
            "subject_type": subject_type, "subject_identity": identity, "subject_appeal_raw": raw,
            "subject_appeal_percentile": baseline, "neutral_baseline_flag": subject_type == "neutral_functional",
            "playability_functional_identity": refs.get(fid, {}).get("functional_key") if fid else None,
            "playability_functional_name": refs.get(fid, {}).get("display_name") if fid else None,
            "playability_raw_score": evidence["rawScore"] if evidence else None,
            "confidence": evidence["confidence"] if evidence else None, "playability_status": status,
            "applied_lift": final - baseline if final is not None else None, "final_card_collector_appeal": final,
            "hit_eligibility": hit, "source_runs": {"playability": LIMITLESS_RUN, "trainer12m": TRAINER_12M, "trainer5y": TRAINER_5Y},
            "scoring_version": VERSION, "formula_fingerprint": None})

    config = {"version": VERSION, "architecture": "B+(100-B)*lambda*(P/100)", "lambdaGrid": list(LAMBDAS),
        "winnerLambda": WINNER, "playabilityCandidateC": {"weights": {"inclusion": .45, "copiesPerUsingDeck": .15,
        "eventBreadth": .15, "top32": .15, "weightedCopies": .10},
        "confidence": "(1-exp(-usingDecks/20))*(0.5+0.5*min(events/3,1))",
        "scoreable": "events>=3 OR usingDecks>=20"}, "subjectFingerprint": SUBJECT_FINGERPRINT,
        "neutral": 50, "missing": "unknown/insufficient => no lift", "artist": False, "treatment": False,
        "marketPrice": False, "sources": [LIMITLESS_RUN, TRAINER_12M, TRAINER_5Y],
        "eligibleCohortVersion": cohort_contract["version"], "neutralExceptionVersion": exception_payload["version"]}
    fingerprint = hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    for row in rows: row["formula_fingerprint"] = fingerprint
    scoreable_rows = [row for row in rows if row["subject_appeal_percentile"] is not None]
    base = {row["canonical_card_id"]: row["subject_appeal_percentile"] for row in scoreable_rows}
    grid = {}
    for strength in LAMBDAS:
        final, lifts = {}, []
        for row in scoreable_rows:
            p = row["playability_raw_score"] * row["confidence"] if row["playability_status"] == "scoreable" else None
            score = bounded_score(row["subject_appeal_percentile"], p, strength)
            final[row["canonical_card_id"]] = score; lifts.append(score - row["subject_appeal_percentile"])
        active_lifts = [value for value in lifts if value > 0]
        grid[str(strength)] = {"liftAllCards": percentile_summary(lifts), "liftReceivingCards": percentile_summary(active_lifts), "liftBuckets": lift_buckets(lifts),
            "final": summary(final), "rank": rank_diagnostics(base, final), "saturation95Count": sum(x >= 95 for x in final.values()),
            "saturation99Count": sum(x >= 99 for x in final.values())}
    by_class = {}
    for subject_type in ("pokemon", "trainer", "neutral_functional"):
        group = [row for row in rows if row["subject_type"] == subject_type]
        by_class[subject_type] = {"cards": len(group), "nonzeroLift": sum(row["applied_lift"] > 0 for row in group),
            "lift": percentile_summary([row["applied_lift"] for row in group]),
            "playabilityStatus": dict(Counter(row["playability_status"] for row in group))}
    focus_names = {"Rare Candy", "Ultra Ball", "Buddy-Buddy Poffin", "Switch", "Crushing Hammer", "Poké Pad",
                   "Professor's Research", "Boss's Orders", "Iono", "Lillie's Determination", "Dreepy", "Drakloak"}
    focus = [row for row in rows if row["card_name"] in focus_names]
    family = defaultdict(list)
    for row in rows:
        if row["playability_functional_identity"]: family[row["playability_functional_identity"]].append(row)
    family_checks = {}
    for name in ("Professor's Research", "Switch", "Potion", "Energy Search", "Rare Candy"):
        matches = [g for g in family.values() if g and g[0]["playability_functional_name"] == name]
        family_checks[name] = [{"printingCount": len(g), "functionalIdentity": g[0]["playability_functional_identity"],
                                "distinctPlayabilityValues": len({(x["playability_raw_score"], x["confidence"], x["playability_status"]) for x in g})} for g in matches]
    threshold = []
    for fid, evidence in play.items():
        threshold.append({"functionalName": refs.get(fid, {}).get("display_name"), **evidence})
    def take(candidates, key, reverse=True):
        ordered = sorted((row for row in threshold if candidates(row)), key=key, reverse=reverse)
        return ordered[0] if ordered else None
    confidence_cases = {
        "exactly3Events": take(lambda x: x["events"] == 3, lambda x: x["rawScore"]),
        "highDeckCountFewEvents": take(lambda x: x["events"] <= 2 and x["decks"] >= 20, lambda x: x["decks"]),
        "manyEventsLowUsage": take(lambda x: x["events"] >= 3 and x["decks"] < 20, lambda x: x["events"]),
        "oneOrTwoEvents": take(lambda x: x["events"] <= 2, lambda x: x["rawScore"]),
        "highRawLowConfidence": take(lambda x: x["confidence"] < .5, lambda x: x["rawScore"]),
        "highRawHighConfidence": take(lambda x: x["confidence"] >= .9, lambda x: x["rawScore"]),
    }
    report = {"decision": "PLAYABILITY_LIFT_READY", "configuration": config, "formulaFingerprint": fingerprint,
        "lambdaGrid": grid, "stratified": by_class, "focusCases": focus,
        "functionalFamilyPropagation": family_checks,
        "confidenceShrinkage": {"formula": config["playabilityCandidateC"]["confidence"], "cases": confidence_cases},
        "shadowDiagnostics": {"rowCount": len(rows), "unknown": sum(x["playability_status"] == "unknown" for x in rows),
            "insufficient": sum(x["playability_status"] == "insufficient" for x in rows),
            "subjectUnavailable": sum(x["subject_appeal_percentile"] is None for x in rows),
            "nonzeroLift": sum((x["applied_lift"] or 0) > 0 for x in rows),
            "largestLifts": sorted(rows, key=lambda x: x["applied_lift"] or 0, reverse=True)[:30],
            "atLeast95": sum((x["final_card_collector_appeal"] or -1) >= 95 for x in rows),
            "atLeast99": sum((x["final_card_collector_appeal"] or -1) >= 99 for x in rows)},
        "shadowRows": rows}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "shadowRows"}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "backend/artifacts/collector_c3b_card_appeal_shadow_v2.json")
    args = parser.parse_args()
    raise SystemExit(main(args.output))
