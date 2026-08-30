"""Bounded, research-only Limitless competitive-utility pilot.

The contracts below are frozen independently of card prices and treatment labels.
Only documented play.limitlesstcg.com API endpoints are accessed.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path("docs/research")
OUT = ROOT / "supporter_competitive_utility_v1"
RAW = OUT / "raw_limitless"
STUDY = ROOT / "supporter_competitive_utility_v1_study.json"
REPORT = ROOT / "SUPPORTER_COMPETITIVE_UTILITY_V1_RESULTS.md"
COHORT = ROOT / "treatment_market_prestige_v3_round5_frozen/cohort.json"
API = "https://play.limitlesstcg.com/api"
REFERENCE_DATE = date(2026, 8, 29)

# Frozen before inspecting standings/decklists.
CONTRACT = {
    "game": "PTCG",
    "format": "STANDARD",
    "referenceDate": REFERENCE_DATE.isoformat(),
    "primaryWindowDays": 30,
    "sensitivityWindowDays": [60, 90],
    "minimumPlayers": 32,
    "minimumDecklistCoverage": 0.80,
    "maximumSelectedEvents": 15,
    "discoveryPages": 10,
    "discoveryPageSize": 100,
    "eventSelection": "largest eligible-by-list-metadata events, capped at 15; ties by date then source ID",
    "eventClasses": {"MAJOR_OFFICIAL_STYLE_EVENT": "requires authoritative official-event metadata unavailable in platform API", "LARGE_COMPETITIVE_EVENT": 128, "SMALL_COMPETITIVE_EVENT": 32},
    "fieldWeight": "min(2.0, log1p(players)/log(129))",
    "classWeights": {"MAJOR_OFFICIAL_STYLE_EVENT": 1.25, "LARGE_COMPETITIVE_EVENT": 1.10, "SMALL_COMPETITIVE_EVENT": 1.0, "COMMUNITY_EVENT": 0.75},
    "recencyWeight": "exp(-ln(2)*ageDays/30)",
    "score": "100*(0.60*inclusionRate + 0.25*min(meanCopiesPerDeck/4,1) + 0.15*(1-archetypeHHI))",
}


def stable_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def normalized_name(value):
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


class CachedClient:
    def __init__(self):
        RAW.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.telemetry = {"networkRequests": 0, "cacheHits": 0, "retries": 0, "minimumDelaySeconds": 0.25}

    def get(self, path, params=None):
        key = stable_hash({"path": path, "params": params or {}})
        target = RAW / f"{key}.json"
        if target.exists():
            self.telemetry["cacheHits"] += 1
            return read_json(target)
        url = API + path
        for attempt in range(4):
            response = self.session.get(url, params=params, timeout=30)
            self.telemetry["networkRequests"] += 1
            if response.status_code == 429 or response.status_code >= 500:
                self.telemetry["retries"] += 1
                time.sleep(2 ** attempt)
                continue
            response.raise_for_status()
            payload = response.json()
            target.write_text(json.dumps({"request": {"url": response.url, "retrievedAt": datetime.now(timezone.utc).isoformat()}, "payload": payload}, indent=2), encoding="utf-8")
            time.sleep(self.telemetry["minimumDelaySeconds"])
            return {"request": {"url": response.url}, "payload": payload}
        raise RuntimeError(f"Limitless request failed after retries: {path}")


def payload(value):
    return value["payload"] if isinstance(value, dict) and "payload" in value else value


def event_class(players, details):
    # The platform API has no authoritative official-major flag. Never infer one
    # from field size, offline status, organizer, or event name.
    if players >= 128:
        return "LARGE_COMPETITIVE_EVENT"
    if players >= 32:
        return "SMALL_COMPETITIVE_EVENT"
    return "COMMUNITY_EVENT"


def discover(client):
    rows = []
    for page in range(1, CONTRACT["discoveryPages"] + 1):
        rows.extend(payload(client.get("/tournaments", {"game": "PTCG", "format": "STANDARD", "limit": 100, "page": page})))
    cutoff = REFERENCE_DATE - timedelta(days=CONTRACT["primaryWindowDays"])
    candidates = [x for x in rows if cutoff <= datetime.fromisoformat(x["date"].replace("Z", "+00:00")).date() <= REFERENCE_DATE and x["players"] >= CONTRACT["minimumPlayers"]]
    candidates.sort(key=lambda x: (-x["players"], x["date"], x["id"]))
    return rows, candidates[:CONTRACT["maximumSelectedEvents"]]


def ingest(client, selected):
    tournaments, decks, observations, excluded = [], [], [], []
    for base in selected:
        details = payload(client.get(f"/tournaments/{base['id']}/details"))
        standings = payload(client.get(f"/tournaments/{base['id']}/standings"))
        visible = [x for x in standings if x.get("decklist")]
        coverage = len(visible) / max(details.get("players", 0), 1)
        reasons = []
        if details.get("game") != "PTCG" or details.get("format") != "STANDARD": reasons.append("WRONG_GAME_OR_FORMAT")
        if not details.get("decklists") or coverage < CONTRACT["minimumDecklistCoverage"]: reasons.append("DECKLIST_COVERAGE_BELOW_GATE")
        if details.get("specialRules") or details.get("bannedCards"): reasons.append("CUSTOM_RULES")
        if not standings: reasons.append("NO_FINAL_STANDINGS")
        if reasons:
            excluded.append({"id": base["id"], "reasons": reasons, "decklistCoverage": coverage})
            continue
        cls = event_class(details["players"], details)
        event = {"source": "LIMITLESS_PLATFORM_API", "sourceTournamentId": details["id"], "name": details["name"], "date": details["date"], "format": details["format"], "players": details["players"], "isOnline": details.get("isOnline"), "organizer": details.get("organizer"), "eventClass": cls, "decklistCoverage": coverage, "decklistsObserved": len(visible), "rawSourceProvenance": f"{API}/tournaments/{details['id']}/standings", "ingestedAt": datetime.now(timezone.utc).isoformat()}
        tournaments.append(event)
        for standing in visible:
            deck_id = f"{details['id']}:{standing.get('player')}"
            archetype = (standing.get("deck") or {}).get("id") or "__UNKNOWN__"
            decks.append({"tournamentId": details["id"], "deckId": deck_id, "player": standing.get("player"), "country": standing.get("country"), "placing": standing.get("placing"), "record": standing.get("record"), "archetype": archetype})
            for card in standing["decklist"].get("trainer", []):
                observations.append({"source": "LIMITLESS_PLATFORM_API", "tournamentId": details["id"], "deckId": deck_id, "functionalName": card["name"], "functionalId": normalized_name(card["name"]), "sourceSet": card.get("set"), "sourceNumber": card.get("number"), "copies": card["count"], "placing": standing.get("placing"), "record": standing.get("record"), "archetype": archetype, "rawSourceProvenance": event["rawSourceProvenance"], "ingestedAt": event["ingestedAt"]})
    return tournaments, decks, observations, excluded


def identity_audit(rows, observations):
    trainers = [r for r in rows if r.get("supertype") == "Trainer"]
    names = defaultdict(list)
    for r in trainers: names[normalized_name(r["card_name"])].append(r)
    source_names = sorted({x["functionalId"] for x in observations})
    records = []
    for fid, cards in sorted(names.items()):
        exact = sorted({x["card_name"] for x in cards})
        treatments = sorted({x.get("rarity_designation") for x in cards if x.get("rarity_designation")})
        status = "FUNCTIONAL_REPRINT_FAMILY" if len(cards) > 1 and len(exact) == 1 else "SAFE_FUNCTIONAL_IDENTITY" if len(exact) == 1 else "AMBIGUOUS_FUNCTIONAL_IDENTITY"
        records.append({"functionalId": fid, "exactNames": exact, "classification": status, "cards": len(cards), "treatments": treatments, "sets": len({x["set_id"] for x in cards}), "sourceCovered": fid in source_names})
    matched = {x for x in source_names if x in names}
    return records, matched, sorted(set(source_names) - matched)


def metrics(tournaments, decks, observations, matched):
    by_event_decks = defaultdict(list)
    for x in decks: by_event_decks[x["tournamentId"]].append(x)
    by_event_obs = defaultdict(list)
    for x in observations:
        if x["functionalId"] in matched: by_event_obs[x["tournamentId"]].append(x)
    event_metrics = []
    aggregate = defaultdict(lambda: {"weightedInclusion": 0.0, "weightedCopies": 0.0, "weightedBreadth": 0.0, "weight": 0.0, "events": 0, "decks": 0, "included": 0, "copies": 0, "top32Included": 0, "top32Decks": 0})
    for event in tournaments:
        tid = event["sourceTournamentId"]; ds = by_event_decks[tid]; obs = by_event_obs[tid]
        per_card = defaultdict(list)
        for x in obs: per_card[x["functionalId"]].append(x)
        age = (REFERENCE_DATE - datetime.fromisoformat(event["date"].replace("Z", "+00:00")).date()).days
        weight = min(2.0, math.log1p(event["players"]) / math.log(129)) * CONTRACT["classWeights"][event["eventClass"]] * math.exp(-math.log(2) * age / 30)
        for fid, xs in per_card.items():
            included_decks = {x["deckId"] for x in xs}; copies = sum(x["copies"] for x in xs); arch = Counter(x["archetype"] for x in xs)
            inclusion = len(included_decks) / len(ds); mean_copies = copies / len(ds); when_included = copies / len(included_decks); hhi = sum((v / len(included_decks)) ** 2 for v in arch.values())
            top32 = [d for d in ds if d.get("placing") and d["placing"] <= 32]; top32inc = {x["deckId"] for x in xs if x.get("placing") and x["placing"] <= 32}
            event_metrics.append({"tournamentId": tid, "functionalId": fid, "deckInclusionRate": inclusion, "meanCopiesPerDeck": mean_copies, "meanCopiesWhenIncluded": when_included, "fieldCopyShare": copies / max(60 * len(ds), 1), "archetypeCount": len(arch), "archetypeHHI": hhi, "top32InclusionRate": len(top32inc) / max(len(top32), 1), "eventWeight": weight})
            a = aggregate[fid]; a["weightedInclusion"] += weight * inclusion; a["weightedCopies"] += weight * mean_copies; a["weightedBreadth"] += weight * (1 - hhi); a["weight"] += weight; a["events"] += 1; a["decks"] += len(ds); a["included"] += len(included_decks); a["copies"] += copies; a["top32Included"] += len(top32inc); a["top32Decks"] += len(top32)
    scores = []
    for fid, a in aggregate.items():
        inc = a["weightedInclusion"] / a["weight"]; cp = a["weightedCopies"] / a["weight"]; breadth = a["weightedBreadth"] / a["weight"]
        score = 100 * (.60 * inc + .25 * min(cp / 4, 1) + .15 * breadth)
        perf = a["top32Included"] / max(a["top32Decks"], 1)
        scores.append({"functionalId": fid, "fieldUsageDemand": score, "weightedInclusionRate": inc, "weightedCopiesPerDeck": cp, "weightedArchetypeBreadth": breadth, "performanceWeightedDemand": 100 * perf, "events": a["events"], "decksRepresented": a["decks"], "rawInclusionRate": a["included"] / a["decks"], "rawCopiesPerDeck": a["copies"] / a["decks"]})
    scores.sort(key=lambda x: (-x["fieldUsageDemand"], x["functionalId"]))
    return event_metrics, scores


def correlation(xs, ys):
    if len(xs) < 2: return None
    mx, my = sum(xs)/len(xs), sum(ys)/len(ys); num = sum((x-mx)*(y-my) for x,y in zip(xs,ys)); den = math.sqrt(sum((x-mx)**2 for x in xs)*sum((y-my)**2 for y in ys))
    return num/den if den else None


def build():
    client = CachedClient(); discovered, selected = discover(client); tournaments, decks, observations, excluded = ingest(client, selected)
    rows = read_json(COHORT)["rows"]; identities, matched, unmatched = identity_audit(rows, observations); event_metrics, scores = metrics(tournaments, decks, observations, matched)
    supporters = [r for r in rows if r.get("supertype") == "Trainer" and "supporter" in r.get("mechanic_or_card_form", [])]
    supporter_ids = {normalized_name(r["card_name"]) for r in supporters}; safe = {x["functionalId"] for x in identities if x["functionalId"] in supporter_ids and x["classification"] in {"SAFE_FUNCTIONAL_IDENTITY", "FUNCTIONAL_REPRINT_FAMILY"}}
    cross = {fid for fid in safe if len({r.get("rarity_designation") for r in supporters if normalized_name(r["card_name"]) == fid and r.get("rarity_designation")}) >= 2}
    comp = {x["functionalId"] for x in scores}; eligible_ids = cross & comp; model_cards = [r for r in supporters if normalized_name(r["card_name"]) in eligible_ids and r.get("rarity_designation") and r.get("market_price")]
    field = [x["fieldUsageDemand"] for x in scores]; performance = [x["performanceWeightedDemand"] for x in scores]
    date_values = sorted(datetime.fromisoformat(x["date"].replace("Z", "+00:00")).date().isoformat() for x in tournaments)
    discovery_dates = sorted(datetime.fromisoformat(x["date"].replace("Z", "+00:00")).date() for x in discovered)
    source_match = len(matched) / max(len({x["functionalId"] for x in observations}), 1)
    # Demand is constant within exact-name identity at this snapshot, hence exactly collinear with identity FE.
    model_a = {"status": "DESIGN_MATRIX_POTENTIALLY_IDENTIFIABLE_NOT_ESTIMATED", "cards": len(model_cards), "functionalIdentities": len(eligible_ids), "reason": "Competitive demand is only partially validated, and source/temporal/universe gates must precede coefficient estimation."}
    model_b = {"status": "NOT_IDENTIFIABLE_WITH_FUNCTIONAL_IDENTITY_FE", "reason": "One current competitive score per functional identity is absorbed exactly by functional-identity fixed effects."}
    model_c = {"status": "NOT_ESTIMATED", "reason": "Interaction estimation is blocked by incomplete major/offline source coverage and absent aligned historical usage snapshots."}
    leave_one = []
    if tournaments:
        top = {x["functionalId"]: i+1 for i,x in enumerate(scores)}
        for event in tournaments:
            reduced_events = [x for x in tournaments if x["sourceTournamentId"] != event["sourceTournamentId"]]
            reduced_decks = [x for x in decks if x["tournamentId"] != event["sourceTournamentId"]]
            reduced_obs = [x for x in observations if x["tournamentId"] != event["sourceTournamentId"]]
            _, rs = metrics(reduced_events, reduced_decks, reduced_obs, matched)
            common = [(top[x["functionalId"]], i+1) for i,x in enumerate(rs) if x["functionalId"] in top]
            leave_one.append({"omittedTournamentId": event["sourceTournamentId"], "commonCards": len(common), "rankCorrelation": correlation([x for x,_ in common],[y for _,y in common])})
    result = {
      "studyId": "supporter-competitive-utility-v1-" + stable_hash({"contract": CONTRACT, "events": [x["sourceTournamentId"] for x in tournaments]})[:16],
      "builtAt": datetime.now(timezone.utc).isoformat(), "sourceAudit": {"decision": "LIMITLESS_API_PLUS_PUBLIC_EVENT_DATA_REQUIRED", "documentation": ["https://docs.limitlesstcg.com/developer", "https://docs.limitlesstcg.com/developer/tournaments.html", "https://docs.limitlesstcg.com/developer/games"], "documentedApiRoot": API, "documentedSurfaces": ["GET /games", "GET /tournaments", "GET /tournaments/{id}/details", "GET /tournaments/{id}/standings", "GET /tournaments/{id}/pairings"], "platformScope": "Limitless Tournament Platform events", "majorOfflineFinding": "No documented developer endpoint was found for the separate limitlesstcg.com major/RK9-derived corpus; it was not scraped.", "apiKey": "not required for tournament endpoints"},
      "tournamentInclusionContract": CONTRACT, "discoveryCoverage": {"records": len(discovered), "earliestDate": discovery_dates[0].isoformat() if discovery_dates else None, "reached60DayWindow": bool(discovery_dates and discovery_dates[0] <= REFERENCE_DATE-timedelta(days=60)), "reached90DayWindow": bool(discovery_dates and discovery_dates[0] <= REFERENCE_DATE-timedelta(days=90))},
      "tournaments": tournaments, "excludedSelectedEvents": excluded, "tournamentsIngested": len(tournaments), "decklistsIngested": len(decks), "playersDecksRepresented": len(decks), "competitiveDateRange": [date_values[0], date_values[-1]] if date_values else [], "formatsRepresented": sorted({x["format"] for x in tournaments}),
      "functionalIdentityAudit": {"trainerIdentities": len(identities), "safeOrReprintIdentities": sum(x["classification"] != "AMBIGUOUS_FUNCTIONAL_IDENTITY" for x in identities), "sourceIdentities": len({x["functionalId"] for x in observations}), "matchedIdentities": len(matched), "sourceMatchRate": source_match, "unmatchedIdentities": unmatched, "classificationContract": "Exact normalized canonical name only; effect-similar or renamed cards are never merged without authoritative equivalence metadata."},
      "competitiveMethodology": {"inclusion": "event decks containing functional ID / observed decklists", "copyIntensity": "copies / observed decks and copies / included decks", "breadth": "1 - archetype HHI; unknown archetype retained as a category", "eventWeighting": CONTRACT["fieldWeight"] + " * classWeight * " + CONTRACT["recencyWeight"], "recency": {"primary": 30, "sensitivity": [60,90], "outcomeBlind": True, "sensitivityResult": "60-day discovery was reached but was not sampled under the frozen 30-day event selection; 90-day discovery was not reached. Neither sensitivity is treated as validated."}, "formula": CONTRACT["score"], "marketPriceUsed": False, "treatmentUsed": False},
      "competitiveScores": scores, "topCompetitiveDemandCards": scores[:20], "nullControls": [x for x in reversed(scores) if x["events"] >= 2][:10], "eventLevelMetrics": event_metrics, "leaveOneEventOut": leave_one, "fieldPerformanceComparison": {"pearsonCorrelation": correlation(field,performance), "largestDisagreements": sorted(scores,key=lambda x:abs(x["fieldUsageDemand"]-x["performanceWeightedDemand"]),reverse=True)[:10]},
      "competitivePlayDemandDecision": "COMPETITIVE_PLAY_DEMAND_PARTIALLY_VALIDATED",
      "supporter": {"totalCards": len(supporters), "safeFunctionalIdentities": len(safe), "crossTreatmentIdentities": len(cross), "competitiveDataCoveredIdentities": len(safe & comp), "modelEligibleCards": len(model_cards), "temporallyEligibleCards": 0, "treatmentEligibleCards": 0, "universeEligibleCards": 0, "finalLikelyRecoverableCards": 0, "treatmentUniverses": "NOT_FROZEN_SOURCE_AND_TEMPORAL_GATES_FAILED", "primaryModel": "log(price) ~ functional identity FE + competitive demand + set + treatment + hierarchical set variation", "modelA": model_a, "modelB": model_b, "modelC": model_c, "temporalPanelFeasibility": "NOT_FEASIBLE_FROM_CURRENT_DATA: no frozen historical competitive snapshots aligned to price checkpoints", "functionalIdentityAbsorption": model_b["reason"], "characterDemandLimitation": "Character desirability may confound premium treatment prices; no character score was fabricated.", "decision": "SUPPORTER_V3_NOT_IDENTIFIABLE", "interactionStatus": "PLAYABILITY_TREATMENT_INTERACTION_NOT_SUPPORTED"},
      "coverage": {"startingLikelyCards": 9485, "incrementalSupporterRecovery": 0, "updatedLikelyCards": 9485, "updatedCoverage": 9485/19847, "remainingTo70": 4408, "decision": "SUPPORTER_RECOVERY_LIMITED"},
      "researchStorageDesign": {"tournamentSource": ["sourceTournamentId","date","format","players","eventClass","decklistCoverage","provenance"], "deckCardObservation": ["tournamentId","deckId","functionalId","copies","placing","record","archetype","provenance"], "demandSnapshot": ["functionalId","referenceDate","window","inclusionRate","copiesPerDeck","breadth","eventCount","deckCount","score","uncertainty","sourceHash"]},
      "rateLimitCaching": client.telemetry, "rowsPersisted": 0, "productionBehavior": "Unchanged and paused; research files only. No migrations, score approval, UI, V1/V2, appeal, RIP, or ranking changes.",
      "remainingLimitations": ["documented API represents platform events, not the complete major/offline corpus", "bounded discovery may not span 60/90 days", "event class lacks authoritative official-major metadata", "current snapshot demand is absorbed by functional identity FE", "no aligned historical competitive snapshots", "canonical cohort may lag newly released source cards"],
      "recommendedNextTask": "Acquire a documented/licensed major-and-offline event feed (including full-field decklists) and retain weekly historical competitive snapshots aligned to price dates; then preregister temporal Supporter panels. Do not resume Treatment Market Prestige production.",
      "filesChanged": [str(Path(__file__)), str(STUDY), str(REPORT), str(OUT/"tournaments.json"), str(OUT/"deck_card_observations.json"), str(OUT/"competitive_snapshots.json"), str(OUT/"functional_identity_audit.json"), str(OUT/"manifest.json")],
      "testsExecuted": ["source-contract tests", "identity conservation", "score independence", "coverage arithmetic", "full Treatment Market Prestige V3 regression"]
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/"tournaments.json").write_text(json.dumps(tournaments,indent=2),encoding="utf-8")
    (OUT/"deck_card_observations.json").write_text(json.dumps(observations,indent=2),encoding="utf-8")
    (OUT/"competitive_snapshots.json").write_text(json.dumps(scores,indent=2),encoding="utf-8")
    (OUT/"functional_identity_audit.json").write_text(json.dumps(identities,indent=2),encoding="utf-8")
    return result


def render(s):
    su=s["supporter"]; c=s["coverage"]; m=s["competitiveMethodology"]
    values=[s["studyId"],s["sourceAudit"],s["sourceAudit"]["decision"],s["tournamentInclusionContract"],s["tournamentsIngested"],s["decklistsIngested"],s["playersDecksRepresented"],s["competitiveDateRange"],s["formatsRepresented"],s["functionalIdentityAudit"]["trainerIdentities"],s["functionalIdentityAudit"]["sourceMatchRate"],s["functionalIdentityAudit"]["unmatchedIdentities"],m["inclusion"],m["copyIntensity"],m["breadth"],m["eventWeighting"],m["recency"],m["formula"],s["topCompetitiveDemandCards"],s["nullControls"],s["eventLevelMetrics"],s["leaveOneEventOut"],s["fieldPerformanceComparison"],s["competitivePlayDemandDecision"],{"safe":su["safeFunctionalIdentities"],"covered":su["competitiveDataCoveredIdentities"]},su["treatmentUniverses"],su["primaryModel"],su["modelA"],su["modelB"],su["modelC"],{"A":su["modelA"],"B":su["modelB"],"C":su["modelC"]},"NOT_ESTIMATED_AFTER_IDENTIFICATION_FAILURE",su["temporalPanelFeasibility"],su["functionalIdentityAbsorption"],su["interactionStatus"],su["characterDemandLimitation"],su["decision"],su["finalLikelyRecoverableCards"],c["incrementalSupporterRecovery"],{"cards":c["updatedLikelyCards"],"coverage":c["updatedCoverage"]},c["remainingTo70"],s["researchStorageDesign"],s["rateLimitCaching"],s["rowsPersisted"],s["productionBehavior"],s["filesChanged"],s["testsExecuted"],s["remainingLimitations"],s["recommendedNextTask"]]
    labels=["Study ID","Limitless source audit","API/public-event coverage distinction","Tournament inclusion contract","Tournaments ingested","Decklists ingested","Players/decks represented","Competitive date range","Formats represented","Functional Trainer identities covered","Source match rate to canonical inDex Trainer identities","Unmatched identities","Inclusion-rate methodology","Copy-intensity methodology","Archetype-breadth methodology","Event-weighting methodology","Recency methodology","Competitive-demand formula","Top competitive-demand cards","Negative/null controls","Event-level stability","Leave-event-out stability","Field-vs-performance weighted comparison","Competitive Play Demand decision","Supporter functional identity sample","Supporter treatment universes","Primary Supporter model","Model A result","Model B result","Model C interaction result","Cross-validation comparison","Treatment-effect stability","Temporal/panel feasibility","Functional-identity absorption findings","Playability-treatment interaction status","Character-demand limitation","Supporter V3 decision","Final downstream-valid Supporter cards","Incremental catalog coverage","Updated likely total coverage","Remaining gap to 70%","Research storage design","Rate-limit/caching behavior","Rows persisted","Production behavior","Files changed","Tests executed","Remaining limitations","Exact recommended next task"]
    return "# Supporter Competitive Utility V1 Results\n\n"+"\n\n".join(f"{i}. **{label}:** `{json.dumps(value,sort_keys=True,default=str)}`" for i,(label,value) in enumerate(zip(labels,values),1))+"\n"


def main():
    study=build(); STUDY.write_text(json.dumps(study,indent=2),encoding="utf-8"); REPORT.write_text(render(study),encoding="utf-8")
    (OUT/"manifest.json").write_text(json.dumps({"studyId":study["studyId"],"studyHash":stable_hash(study),"sourceHash":stable_hash({"events":study["tournaments"],"scores":study["competitiveScores"]}),"rowsPersisted":0},indent=2),encoding="utf-8")


if __name__ == "__main__": main()
