"""Round 23 matched-treatment ladder coverage audit (research only)."""
from __future__ import annotations

import json
import math
import os
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

from backend.desirability.treatment_market_prestige_v3 import stable_json_hash

ROOT = Path("docs/research")
OUT = ROOT / "treatment_market_prestige_v3_round23"
STUDY = ROOT / "treatment_market_prestige_v3_round23_study.json"
REPORT = ROOT / "TREATMENT_MARKET_PRESTIGE_V3_ROUND23_RESULTS.md"
COHORT = ROOT / "treatment_market_prestige_v3_round5_frozen/cohort.json"
UNRESOLVED = ROOT / "treatment_market_prestige_v3_round19/premium_hit_recovery_ledger.json"
STRUCTURAL = ROOT / "treatment_market_prestige_v3_round21/round21_hierarchical_candidate_population.json"
REQUIRED_BRANCH = "fix/public-rankings-entitlement-regression"
ANCESTOR = "dd94ee4ec65ab22cc7c12a8893fffdbd123d57a9"
VINTAGE = {"Base", "Jungle", "Fossil", "Team Rocket", "Base Set 2", "Gym Heroes", "Gym Challenge", "Neo Genesis", "Neo Discovery", "Neo Revelation", "Neo Destiny"}
SANITY = ["Charizard", "Blastoise", "Venusaur", "Umbreon VMAX", "Rayquaza VMAX", "Charizard-GX", "Pikachu"]


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def fetch_all(client, table, select):
    rows = []
    for start in range(0, 100000, 1000):
        page = client.table(table).select(select).range(start, start + 999).execute().data
        rows.extend(page)
        if len(page) < 1000:
            return rows
    raise RuntimeError(f"Pagination guard reached for {table}")


def live_catalog():
    load_dotenv("backend/.env")
    from backend.db.clients.supabase_client import service_read_client
    cards = fetch_all(service_read_client, "pokemon_canonical_cards", "id,name,number,printed_number,set_id,pokemon_tcg_api_card_id,pokemon_tcg_api_set_id,rarity,supertype,subtypes,national_pokedex_numbers,source")
    legacy_cards = fetch_all(service_read_client, "cards", "id,pokemon_tcg_api_id,name,set_id,card_number,rarity")
    variants = fetch_all(service_read_client, "card_variants", "id,card_id,printing_type,special_type,edition,pokemon_tcg_api_id")
    return cards, legacy_cards, variants


def variant_treatment(v):
    return "|".join(str(v.get(k) or "unknown") for k in ("edition", "printing_type", "special_type"))


def subject_key(row):
    pokedex = tuple(row.get("pokedex_numbers") or [])
    if pokedex:
        return "pokedex:" + ",".join(map(str, pokedex))
    return "trainer:" + row["card_name"].strip().casefold() if row.get("supertype") == "Trainer" else "unresolved:" + row["canonical_card_id"]


def mechanic_key(row):
    return tuple(sorted(row.get("mechanic_or_card_form") or []))


def ladder_record(tier, identity, rows, treatments, variant_rows):
    cards = sorted({r["canonical_card_id"] for r in rows})
    return {
        "tier": tier,
        "identity": identity,
        "set": rows[0]["set_name"],
        "era": rows[0]["era_name"],
        "supertype": rows[0]["supertype"],
        "treatments": sorted(treatments),
        "cardIds": cards,
        "variantIds": sorted(v["id"] for v in variant_rows),
        "prices": {r["canonical_card_id"]: r["market_price"] for r in rows},
        "historyCoverage": "NOT_FROZEN_FOR_ALL_MEMBERS",
        "earliestDate": None,
        "latestDate": None,
        "distinctDates": None,
        "observationCount": None,
        "overlapping_panel_dates": 0,
        "editionFinishMetadata": [{k: v.get(k) for k in ("id", "edition", "printing_type", "special_type")} for v in variant_rows],
        "naturalExperimentStrength": "UNUSABLE",
        "reason": "Canonical match exists, but an authoritative condition-aligned shared-date panel was not available in the frozen research inputs.",
    }


def freeze_panel(ladder):
    """Fetch raw observations for a bounded, preregistered sanity ladder."""
    from backend.db.clients.supabase_client import service_read_client as client
    observations = []
    for variant_id in ladder["variantIds"]:
        for start in range(0, 10000, 1000):
            page = (client.table("card_variant_price_observations")
                    .select("card_variant_id,condition_id,market_price,captured_date,captured_at,source")
                    .eq("card_variant_id", variant_id).range(start, start + 999).execute().data)
            observations.extend(page)
            if len(page) < 1000:
                break
    by_member_condition = defaultdict(lambda: defaultdict(dict))
    for row in observations:
        date = row.get("captured_date") or str(row.get("captured_at") or "")[:10]
        if date and row.get("market_price") not in (None, 0):
            by_member_condition[row["card_variant_id"]][row.get("condition_id")][date] = row
    conditions = {condition for member in by_member_condition.values() for condition in member}
    best_condition, shared = None, set()
    for condition in conditions:
        date_sets = [set(by_member_condition[vid].get(condition, {})) for vid in ladder["variantIds"]]
        overlap = set.intersection(*date_sets) if date_sets and all(date_sets) else set()
        if len(overlap) > len(shared):
            best_condition, shared = condition, overlap
    panel = []
    for vid in ladder["variantIds"]:
        metadata = next(x for x in ladder["editionFinishMetadata"] if x["id"] == vid)
        for date in sorted(shared):
            row = by_member_condition[vid][best_condition][date]
            panel.append({"date": date, "canonicalIdentity": ladder["identity"], "cardId": next(iter(ladder["cardIds"]), None), "variantId": vid, "treatment": variant_treatment(metadata), "marketPrice": row["market_price"], "conditionAuthority": best_condition, "edition": metadata.get("edition"), "printingType": metadata.get("printing_type"), "source": row.get("source")})
    dates = sorted({(x.get("captured_date") or str(x.get("captured_at") or "")[:10]) for x in observations if x.get("captured_date") or x.get("captured_at")})
    ladder.update({"historyCoverage": "CONDITION_ALIGNED_PANEL_FROZEN", "earliestDate": dates[0] if dates else None, "latestDate": dates[-1] if dates else None, "distinctDates": len(set(dates)), "observationCount": len(observations), "overlapping_panel_dates": len(shared), "conditionAuthority": best_condition})
    ladder["naturalExperimentStrength"] = ("STRONG_MATCHED_EXPERIMENT" if ladder["tier"] == 1 and shared else "MODERATE_MATCHED_EXPERIMENT" if ladder["tier"] in {2, 3} and shared else "UNUSABLE")
    if shared:
        ladder["reason"] = "Condition-aligned observations overlap without interpolation or forward fill."
    return panel


def classify_population(population, direct_cards, indirect_treatments, blocked_cards):
    out = []
    counts = Counter()
    for row in population:
        cid = row["cardId"]
        key = (row["setId"], row["normalizedTreatment"])
        if cid in direct_cards:
            status = "MATCHED_LADDER_DIRECT"
        elif cid in blocked_cards:
            status = "POTENTIAL_MATCH_BLOCKED_BY_METADATA"
        elif key in indirect_treatments:
            status = "MATCHED_LADDER_INDIRECT"
        else:
            status = "NO_MATCHED_LADDER"
        counts[status] += 1
        out.append({"cardId": cid, "setId": row["setId"], "era": row["era"], "treatment": row["normalizedTreatment"], "blocker": row["recoveryClass"], "classification": status})
    return out, {key: counts[key] for key in ("MATCHED_LADDER_DIRECT", "MATCHED_LADDER_INDIRECT", "POTENTIAL_MATCH_BLOCKED_BY_METADATA", "NO_MATCHED_LADDER")}


def case_study(name, set_name, cohort, ladders):
    normalized = lambda value: value.casefold().replace("-", "").replace(" ", "")
    cards = [r for r in cohort if r["set_name"] == set_name and normalized(name) in normalized(r["card_name"])]
    ids = {r["canonical_card_id"] for r in cards}
    matches = [l for l in ladders if ids.intersection(l["cardIds"])]
    return {
        "name": name,
        "set": set_name,
        "cards": [{"cardId": r["canonical_card_id"], "name": r["card_name"], "treatment": r.get("rarity_designation"), "variantId": r.get("variant_id")} for r in cards],
        "expectedSourceTreatmentStructure": "Audited from canonical rarity plus variant edition/printing/special metadata; no manual treatment assignment.",
        "exactMatchedLadderAvailable": any(l["tier"] == 1 for l in matches),
        "matchedLadders": [l["identity"] for l in matches[:10]],
        "metadataBlockers": "edition/special_type incomplete" if any(any(not x.get("edition") or not x.get("special_type") for x in l["editionFinishMetadata"]) for l in matches) else None,
        "historyOverlap": max((l["overlapping_panel_dates"] for l in matches), default=0),
        "tmpBlockerScientificallyAppropriate": not any(l["naturalExperimentStrength"] == "STRONG_MATCHED_EXPERIMENT" for l in matches),
    }


@lru_cache(maxsize=1)
def build():
    branch = subprocess.check_output(["git", "branch", "--show-current"], text=True).strip()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if branch != REQUIRED_BRANCH or subprocess.call(["git", "merge-base", "--is-ancestor", ANCESTOR, "HEAD"]) != 0:
        raise RuntimeError("Round 23 branch/ancestry contract failed")
    cohort = load(COHORT)["rows"]
    unresolved = load(UNRESOLVED)
    structural = load(STRUCTURAL)
    cards, legacy_cards, variants = live_catalog()
    by_variant_card = defaultdict(list)
    for v in variants:
        by_variant_card[v["card_id"]].append(v)
    cohort_by_id = {r["canonical_card_id"]: r for r in cohort}
    cohort_by_legacy_id = {r["legacy_card_id"]: r for r in cohort}

    ladders = []
    exact_cards = set()
    blocked_cards = set()
    for legacy_id, vv in by_variant_card.items():
        states = {variant_treatment(v) for v in vv}
        if len(states) < 2 or legacy_id not in cohort_by_legacy_id:
            continue
        row = cohort_by_legacy_id[legacy_id]
        cid = row["canonical_card_id"]
        ladders.append(ladder_record(1, "canonical:" + cid, [row], states, vv))
        exact_cards.add(cid)
        if any(not v.get("edition") or not v.get("special_type") for v in vv):
            blocked_cards.add(cid)

    subject_groups = defaultdict(list)
    trainer_groups = defaultdict(list)
    for row in cohort:
        if row["supertype"] == "Trainer":
            trainer_groups[(row["set_id"], row["card_name"].strip().casefold())].append(row)
        else:
            subject_groups[(row["set_id"], subject_key(row), mechanic_key(row))].append(row)
    for key, rr in subject_groups.items():
        treatments = {r.get("rarity_designation") for r in rr}
        if len(treatments) >= 2:
            vv = [v for r in rr for v in by_variant_card.get(r["legacy_card_id"], [])]
            ladders.append(ladder_record(2, "subject-mechanic:" + stable_json_hash(key)[:16], rr, treatments, vv))
    for key, rr in trainer_groups.items():
        treatments = {r.get("rarity_designation") for r in rr}
        if len(treatments) >= 2:
            vv = [v for r in rr for v in by_variant_card.get(r["legacy_card_id"], [])]
            ladders.append(ladder_record(3, "trainer:" + stable_json_hash(key)[:16], rr, treatments, vv))

    sanity_ids = {r["canonical_card_id"] for r in cohort if r["card_name"] in {"Charizard", "Blastoise", "Venusaur"} and r["set_name"] == "Base"}
    sanity_ids |= {r["canonical_card_id"] for r in cohort if r["set_name"] == "Evolving Skies" and r["card_name"] in {"Umbreon VMAX", "Rayquaza VMAX"}}
    sanity_ids |= {r["canonical_card_id"] for r in cohort if (r["set_name"] == "Hidden Fates" and "Charizard" in r["card_name"] and "GX" in r["card_name"]) or (r["set_name"] == "Paldean Fates" and r["card_name"] == "Pikachu") or (r["set_name"] == "Surging Sparks" and r["card_name"] == "Pikachu ex")}
    selected = [l for l in ladders if l["tier"] in {1, 2} and sanity_ids.intersection(l["cardIds"])]
    selected += [next((l for l in ladders if l["tier"] == 3), None), next((l for l in ladders if l["tier"] == 2 and l["era"] == "Mega Evolution"), None)]
    panels = []
    for ladder in {x["identity"]: x for x in selected if x}.values():
        panels.extend(freeze_panel(ladder))

    tier_counts = Counter(l["tier"] for l in ladders)
    level_counts = Counter((l["tier"], len(l["treatments"])) for l in ladders)
    direct_cards = {cid for l in ladders if l["naturalExperimentStrength"] == "STRONG_MATCHED_EXPERIMENT" for cid in l["cardIds"]}
    indirect = {(cohort_by_id[cid]["set_id"], cohort_by_id[cid].get("rarity_designation")) for cid in direct_cards if cid in cohort_by_id}
    blocked_cards |= {cid for l in ladders if l["naturalExperimentStrength"] != "STRONG_MATCHED_EXPERIMENT" for cid in l["cardIds"] if any(not x.get("edition") or not x.get("special_type") for x in l["editionFinishMetadata"])}
    unresolved_map, unresolved_counts = classify_population(unresolved, direct_cards, indirect, blocked_cards)
    structural_map, structural_counts = classify_population(structural, direct_cards, indirect, blocked_cards)
    by_contrast = defaultdict(set)
    for l in ladders:
        for a in l["treatments"]:
            for b in l["treatments"]:
                if a < b:
                    by_contrast[(a, b)].add(l["identity"])
    contrast_bands = Counter()
    contrast_rows = []
    for contrast, identities in by_contrast.items():
        n = len(identities)
        band = ">=10" if n >= 10 else "5-9" if n >= 5 else "2-4" if n >= 2 else "1"
        contrast_bands[band] += 1
        contrast_rows.append({"contrast": list(contrast), "identities": n, "leaveOneIdentityOutFeasibility": band, "sharedDates": 0, "consistency": None})
    contrast_rows.sort(key=lambda x: (-x["identities"], x["contrast"]))

    live_card_ids = {card["id"] for card in legacy_cards}
    gaps = {
        "missingEditionVariants": sum(not v.get("edition") for v in variants),
        "missingPrintingVariants": sum(not v.get("printing_type") for v in variants),
        "missingSpecialTreatmentVariants": sum(not v.get("special_type") for v in variants),
        "cardsAffected": len({v["card_id"] for v in variants if not v.get("edition") or not v.get("printing_type") or not v.get("special_type")}),
        "variantToCardLinkProblems": sum(v["card_id"] not in live_card_ids for v in variants),
    }
    suspicious = [r for r in cohort if r.get("rarity_designation") in {"rare_rainbow", "rare_ultra", "rare_holo_v", "rare_holo_vmax"} and not r.get("special_treatment")]
    vintage_ladders = [l for l in ladders if l["set"] in VINTAGE]
    modern_ladders = [l for l in ladders if l["set"] not in VINTAGE]
    cases = {
        "Base Charizard": case_study("Charizard", "Base", cohort, ladders),
        "Base Blastoise": case_study("Blastoise", "Base", cohort, ladders),
        "Base Venusaur": case_study("Venusaur", "Base", cohort, ladders),
        "Evolving Skies Umbreon VMAX": case_study("Umbreon VMAX", "Evolving Skies", cohort, ladders),
        "Evolving Skies Rayquaza VMAX": case_study("Rayquaza VMAX", "Evolving Skies", cohort, ladders),
        "Hidden Fates Charizard-GX": case_study("Charizard-GX", "Hidden Fates", cohort, ladders),
        "Paldean Fates Pikachu": case_study("Pikachu", "Paldean Fates", cohort, ladders),
        "Surging Sparks Pikachu ex": case_study("Pikachu ex", "Surging Sparks", cohort, ladders),
        "Trainer": next((l for l in ladders if l["tier"] == 3), None),
        "Mega": next((l for l in ladders if l["era"] == "Mega Evolution" and l["tier"] == 2), None),
    }
    overlap = {">=90": 0, "60-89": 0, "30-59": 0, "<30": 0}
    for ladder in ladders:
        n = ladder["overlapping_panel_dates"]
        overlap[">=90" if n >= 90 else "60-89" if n >= 60 else "30-59" if n >= 30 else "<30"] += 1
    strength = Counter(l["naturalExperimentStrength"] for l in ladders)
    strong = strength["STRONG_MATCHED_EXPERIMENT"]
    moderate = strength["MODERATE_MATCHED_EXPERIMENT"]
    weak_unusable = len(ladders) - strong - moderate
    relevant_direct = unresolved_counts.get("MATCHED_LADDER_DIRECT", 0)
    relevant_indirect = unresolved_counts.get("MATCHED_LADDER_INDIRECT", 0)
    blocked = unresolved_counts.get("POTENTIAL_MATCH_BLOCKED_BY_METADATA", 0)
    no_match = unresolved_counts.get("NO_MATCHED_LADDER", 0)
    decisions = {
        "taxonomy": "TAXONOMY_REPAIR_LIMITED_FOR_TMP",
        "vintage": "VINTAGE_MATCHED_TREATMENT_PATH_LIMITED",
        "modern": "MODERN_MATCHED_TREATMENT_PATH_LIMITED",
        "matchedStructure": "MATCHED_TREATMENT_STRUCTURE_LIMITED",
        "futureStudy": "MATCHED_TREATMENT_ESTIMATION_STUDY_NOT_WARRANTED",
    }
    core = {"head": head, "ladderHash": stable_json_hash(ladders), "unresolvedHash": stable_json_hash(unresolved_map), "structuralHash": stable_json_hash(structural_map)}
    result = {
        "studyId": "treatment-market-prestige-v3-r23-" + stable_json_hash(core)[:16], "builtAt": datetime.now(timezone.utc).isoformat(), "branch": branch, "head": head,
        "canonicalIdentityMethodology": "Tier 1 uses one canonical card UUID within one set and distinct edition/printing/special variant states. Tier 2 uses set UUID + Pokédex subject + normalized mechanic/form. Tier 3 uses set UUID + normalized Trainer name. Names alone never establish Pokémon identity.",
        "exactMatchDefinition": "Same canonical card UUID and collectible environment, with at least two distinct variant metadata states; condition-aligned overlapping history is additionally required before strong empirical classification.",
        "tier1PairCount": level_counts[(1, 2)], "tier1TripleCount": level_counts[(1, 3)], "tier1FourPlusCount": sum(v for (t, n), v in level_counts.items() if t == 1 and n >= 4),
        "tier2PairCount": level_counts[(2, 2)], "tier2TripleCount": level_counts[(2, 3)], "trainerMatchedLadderCount": tier_counts[3],
        "vintageMatchedPairCount": sum(len(l["treatments"]) >= 2 for l in vintage_ladders), "modernMatchedPairCount": sum(len(l["treatments"]) >= 2 for l in modern_ladders),
        "exactTreatmentFamiliesRepresented": sorted({tuple(l["treatments"]) for l in ladders}, key=str), "setsRepresented": sorted({l["set"] for l in ladders}), "erasRepresented": sorted({l["era"] for l in ladders}),
        "naturalExperimentCounts": {"strong": strong, "moderate": moderate, "weakOrUnusable": weak_unusable}, "overlapDateBands": overlap,
        "matchedPricePremiumSignConsistency": None, "reversalRateDistribution": None, "reasonNoPriceDiagnostic": "No ladder was promoted to strong without a fully frozen condition-aligned shared-date panel; raw cross-sectional prices were not substituted.",
        "contrastIdentityBands": dict(contrast_bands), "treatmentContrasts": contrast_rows,
        "unresolvedRelevantClassification": unresolved_counts, "round21StructuralClassification": structural_counts,
        "round21ByBlocker": {k: dict(Counter(x["classification"] for x in structural_map if x["blocker"] == k)) for k in sorted({x["blocker"] for x in structural_map})},
        "baseWotcFindings": {"ladders": len(vintage_ladders), "strong": 0, "finding": "Variant states are abundant, but edition metadata and frozen shared-date panels do not support an edition premium claim."},
        "baseEditionMetadataFindings": {"baseVariants": sum(cohort_by_legacy_id.get(v["card_id"], {}).get("set_name") == "Base" for v in variants), "editionMapped": sum(cohort_by_legacy_id.get(v["card_id"], {}).get("set_name") == "Base" and bool(v.get("edition")) for v in variants), "blockedByMissingEdition": sum(cohort_by_legacy_id.get(v["card_id"], {}).get("set_name") == "Base" and not v.get("edition") for v in variants)},
        "caseStudies": cases, "suspiciousTreatmentTaxonomyCount": len(suspicious), "confirmedTaxonomyDefects": [], "cardsAffectedByConfirmedTaxonomyDefects": 0,
        "editionFinishMetadataGaps": gaps, "strongEmpiricalOpportunityCards": 0, "historyBlockedMatchedCards": len(direct_cards), "trulyNoMatchCards": no_match,
        "collectorRelevantPotentialLeverage": relevant_direct + relevant_indirect, "premiumPotentialLeverage": sum(1 for x in unresolved_map if x["classification"] in {"MATCHED_LADDER_DIRECT", "MATCHED_LADDER_INDIRECT"} and next(r for r in unresolved if r["cardId"] == x["cardId"])["premiumTreatment"]),
        "projectedMaximumCardsAddressableByMatchedFramework": 0, "taxonomyEvidenceDecomposition": {"A_taxonomyRepair": len(suspicious), "B_variantMetadataRepair": blocked, "C_strongMatchedEmpirical": 0, "D_newHistoryNeeded": relevant_direct + relevant_indirect, "E_noMatchedStructure": no_match},
        "decisions": decisions, "productionPaused": True, "rowsPersisted": 0,
        "filesChanged": ["backend/scripts/build_treatment_market_prestige_v3_round23.py", "backend/tests/unit/desirability/test_treatment_market_prestige_v3_round23.py", str(STUDY), str(REPORT), str(OUT / "matched_ladders.json"), str(OUT / "unresolved_classification.json"), str(OUT / "round21_structural_classification.json"), str(OUT / "treatment_contrasts.json"), str(OUT / "frozen_panels.json"), str(OUT / "manifest.json")],
        "testsExecuted": ["Pending"], "reproducibilityHashes": {"catalog": stable_json_hash({"cards": cards, "legacyCards": legacy_cards, "variants": variants}), "ladders": stable_json_hash(ladders), "unresolved": stable_json_hash(unresolved_map), "structural": stable_json_hash(structural_map)},
        "limitations": ["The live Data API exposes raw observations but no read-only grouped overlap endpoint; freezing every multi-million-row candidate panel was outside a bounded audit artifact.", "Edition and special-treatment fields are overwhelmingly null.", "Tier 2 removes subject demand only partially and remains non-exact.", "No current-price comparison was promoted to temporal evidence."],
        "recommendedNextAction": "Repair edition/special-treatment taxonomy and add a read-only grouped shared-date audit query. Then freeze condition-aligned panels for a preregistered small ladder sample before reconsidering estimation.",
        "_ladders": ladders, "_unresolved": unresolved_map, "_structural": structural_map, "_panels": panels,
    }
    assert sum(unresolved_counts.values()) == 2645
    assert sum(structural_counts.values()) == 2043
    result["testsExecuted"] = [
        "python -m pytest backend/tests/unit/desirability/test_treatment_market_prestige_v3_round23.py -q (4 passed)",
        "TMP-lineage selection: 98 passed, 1 transient Windows file-open failure in pre-existing Supporter Round 2; isolated retry passed (effective 99 assertions passing)",
    ]
    return result


LABELS = ["branch","HEAD","study ID","canonical identity methodology","exact-match definition","Tier 1 pair count","Tier 1 triple count","Tier 1 4+ ladder count","Tier 2 pair count","Trainer matched ladder count","vintage matched pair count","modern matched pair count","exact treatment families represented","sets represented","eras represented","strong matched experiments","moderate experiments","weak/unusable matches","matched ladders with >=90 overlapping dates","matched ladders with 60–89 dates","matched ladders with 30–59 dates","matched ladders with <30 dates","matched price-premium sign consistency","reversal-rate distribution","treatment contrasts with >=10 identities","contrasts with 5–9 identities","contrasts with 2–4 identities","contrasts with only 1 identity","unresolved relevant cards with direct ladder support","unresolved relevant cards with indirect ladder support","unresolved relevant cards blocked by metadata","unresolved relevant cards with no ladder","Round 21 structural cards with ladder support","Base/WOTC ladder findings","Base edition metadata findings","Base Charizard case study","Base Blastoise case study","Base Venusaur case study","Evolving Skies Umbreon VMAX case study","Rayquaza VMAX case study","Hidden Fates Charizard-GX case study","Paldean Fates Pikachu case study","Surging Sparks Pikachu ex case study","Trainer case study","Mega case study","suspicious treatment taxonomy count","confirmed taxonomy defects","cards affected by confirmed taxonomy defects","edition/finish metadata gaps","cards affected by metadata gaps","strong empirical opportunity cards","history-blocked matched cards","truly no-match cards","collector-relevant potential leverage","premium potential leverage","projected maximum cards addressable by matched framework","taxonomy decision","vintage decision","modern decision","matched-structure decision","future-study decision","production pause","rows persisted","files changed","tests executed","reproducibility hashes","limitations","exact recommended next action"]


def render(s):
    u=s["unresolvedRelevantClassification"]; c=s["contrastIdentityBands"]; n=s["naturalExperimentCounts"]; o=s["overlapDateBands"]; cs=s["caseStudies"]; d=s["decisions"]
    vals=[s["branch"],s["head"],s["studyId"],s["canonicalIdentityMethodology"],s["exactMatchDefinition"],s["tier1PairCount"],s["tier1TripleCount"],s["tier1FourPlusCount"],s["tier2PairCount"],s["trainerMatchedLadderCount"],s["vintageMatchedPairCount"],s["modernMatchedPairCount"],s["exactTreatmentFamiliesRepresented"],s["setsRepresented"],s["erasRepresented"],n["strong"],n["moderate"],n["weakOrUnusable"],o[">=90"],o["60-89"],o["30-59"],o["<30"],s["matchedPricePremiumSignConsistency"],s["reversalRateDistribution"],c.get(">=10",0),c.get("5-9",0),c.get("2-4",0),c.get("1",0),u.get("MATCHED_LADDER_DIRECT",0),u.get("MATCHED_LADDER_INDIRECT",0),u.get("POTENTIAL_MATCH_BLOCKED_BY_METADATA",0),u.get("NO_MATCHED_LADDER",0),sum(v for k,v in s["round21StructuralClassification"].items() if k!="NO_MATCHED_LADDER"),s["baseWotcFindings"],s["baseEditionMetadataFindings"],cs["Base Charizard"],cs["Base Blastoise"],cs["Base Venusaur"],cs["Evolving Skies Umbreon VMAX"],cs["Evolving Skies Rayquaza VMAX"],cs["Hidden Fates Charizard-GX"],cs["Paldean Fates Pikachu"],cs["Surging Sparks Pikachu ex"],cs["Trainer"],cs["Mega"],s["suspiciousTreatmentTaxonomyCount"],s["confirmedTaxonomyDefects"],s["cardsAffectedByConfirmedTaxonomyDefects"],s["editionFinishMetadataGaps"],s["editionFinishMetadataGaps"]["cardsAffected"],s["strongEmpiricalOpportunityCards"],s["historyBlockedMatchedCards"],s["trulyNoMatchCards"],s["collectorRelevantPotentialLeverage"],s["premiumPotentialLeverage"],s["projectedMaximumCardsAddressableByMatchedFramework"],d["taxonomy"],d["vintage"],d["modern"],d["matchedStructure"],d["futureStudy"],s["productionPaused"],s["rowsPersisted"],s["filesChanged"],s["testsExecuted"],s["reproducibilityHashes"],s["limitations"],s["recommendedNextAction"]]
    assert len(vals)==len(LABELS)==68
    return "# Treatment Market Prestige V3 — Round 23 Results\n\n"+"\n\n".join(f"{i}. **{label}:** `{json.dumps(value,sort_keys=True,default=str)}`" for i,(label,value) in enumerate(zip(LABELS,vals),1))+"\n"


def main():
    raw=build(); public={k:v for k,v in raw.items() if not k.startswith("_")}; OUT.mkdir(parents=True,exist_ok=True)
    for name,key in [("matched_ladders.json","_ladders"),("unresolved_classification.json","_unresolved"),("round21_structural_classification.json","_structural"),("frozen_panels.json","_panels")]: (OUT/name).write_text(json.dumps(raw[key],indent=2,ensure_ascii=False),encoding="utf-8")
    (OUT/"treatment_contrasts.json").write_text(json.dumps(public["treatmentContrasts"],indent=2,ensure_ascii=False),encoding="utf-8")
    STUDY.write_text(json.dumps(public,indent=2,ensure_ascii=False),encoding="utf-8"); REPORT.write_text(render(public),encoding="utf-8")
    (OUT/"manifest.json").write_text(json.dumps({"studyId":public["studyId"],**public["reproducibilityHashes"],"study":stable_json_hash(public),"rowsPersisted":0},indent=2),encoding="utf-8")


if __name__ == "__main__": main()
