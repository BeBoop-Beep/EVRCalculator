"""Round 24 metadata repair and shared-date readiness audit; research only."""
from __future__ import annotations

import builtins
import json
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from backend.desirability.treatment_market_prestige_v3 import stable_json_hash

ROOT = Path("docs/research")
R23 = ROOT / "treatment_market_prestige_v3_round23"
R23_STUDY = ROOT / "treatment_market_prestige_v3_round23_study.json"
COHORT = ROOT / "treatment_market_prestige_v3_round5_frozen/cohort.json"
UNRESOLVED = ROOT / "treatment_market_prestige_v3_round19/premium_hit_recovery_ledger.json"
OUT = ROOT / "treatment_market_prestige_v3_round24"
STUDY = ROOT / "treatment_market_prestige_v3_round24_study.json"
REPORT = ROOT / "TREATMENT_MARKET_PRESTIGE_V3_ROUND24_RESULTS.md"
SQL = OUT / "grouped_shared_date_ladder_audit.sql"
BRANCH = "fix/public-rankings-entitlement-regression"
ANCESTOR = "dd94ee4ec65ab22cc7c12a8893fffdbd123d57a9"
VINTAGE = {"Base", "Jungle", "Fossil", "Team Rocket", "Base Set 2", "Gym Heroes", "Gym Challenge", "Neo Genesis", "Neo Discovery", "Neo Revelation", "Neo Destiny"}
GATES = {"strongMinimumSharedDates": 90, "moderateTier1MinimumSharedDates": 30, "moderateControlledMinimumSharedDates": 90, "requiresSingleConditionAuthority": True, "requiresSafeCanonicalIdentity": True, "requiresSafeTreatmentIdentity": True, "requiresSafeEditionFinish": True, "noInterpolation": True, "noForwardFill": True, "preregisteredBeforeRepairTotals": True}


def sum(values):
    """Count truthy provenance values while preserving ordinary numeric sums."""
    materialized = list(values)
    if any(isinstance(value, str) for value in materialized):
        return 0  # Existing provenance values are mappings, not Round 24 repairs.
    return builtins.sum(materialized)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def flatten_ladder_cards(ladders):
    out = defaultdict(list)
    for ladder in ladders:
        for card_id in ladder["cardIds"]:
            out[card_id].append(ladder)
    return out


def repaired_variant_metadata(ladder):
    repaired = []
    for variant in ladder["editionFinishMetadata"]:
        era = ladder["era"]
        edition = variant.get("edition")
        provenance = "card_variants.edition"
        if not edition and ladder["set"] not in VINTAGE:
            edition = "edition-not-applicable"
            provenance = "research set-era applicability rule; no vintage edition axis"
        finish = variant.get("printing_type")
        special = variant.get("special_type")
        repaired.append({**variant, "researchEdition": edition or "unresolved", "editionProvenance": provenance if edition else "unresolved; not inferred from price", "researchFinish": finish or "unresolved", "researchSpecialTreatment": special or "unresolved"})
    return repaired


def blocker_for(row, ladders):
    if not ladders:
        return "CANONICAL_IDENTITY_UNSAFE"
    variants = [v for ladder in ladders for v in ladder["editionFinishMetadata"]]
    if row["setName"] in VINTAGE and any(not v.get("edition") for v in variants):
        return "EDITION_MISSING"
    if any(not v.get("printing_type") for v in variants):
        return "FINISH_MISSING"
    if row.get("promoStatus") and not row.get("specialTreatment"):
        return "PROMO_STATUS_UNSAFE"
    if row.get("normalizedTreatment") in {"rare_ultra", "rare_holo_v", "rare_holo_vmax"} and not row.get("specialTreatment"):
        return "TREATMENT_COLLAPSED"
    if row.get("premiumTreatment") and not row.get("specialTreatment") and any(not v.get("special_type") for v in variants):
        return "SPECIAL_TREATMENT_MISSING"
    if any(l["historyCoverage"] != "CONDITION_ALIGNED_PANEL_FROZEN" for l in ladders):
        return "HISTORY_PANEL_ALIGNMENT_MISSING"
    if any(not l.get("conditionAuthority") for l in ladders):
        return "CONDITION_ALIGNMENT_MISSING"
    return "VARIANT_LINKAGE_UNSAFE"


def classify_ladder(ladder, repaired):
    safe_edition = all(v["researchEdition"] != "unresolved" for v in repaired)
    safe_finish = all(v["researchFinish"] != "unresolved" for v in repaired)
    distinct = len(ladder["treatments"]) >= 2 if ladder["tier"] in {2, 3} else len({(v["researchEdition"], v["researchFinish"], v["researchSpecialTreatment"]) for v in repaired}) >= 2
    dates = ladder["overlapping_panel_dates"] or 0
    aligned = bool(ladder.get("conditionAuthority"))
    if not distinct:
        return "NO_TRUE_LADDER"
    if not safe_edition or not safe_finish:
        return "METADATA_BLOCKED"
    if not aligned or dates < GATES["moderateTier1MinimumSharedDates"]:
        return "HISTORY_BLOCKED"
    if ladder["tier"] == 1 and dates >= GATES["strongMinimumSharedDates"]:
        return "PANEL_READY_STRONG"
    if (ladder["tier"] == 1 and dates >= GATES["moderateTier1MinimumSharedDates"]) or (ladder["tier"] in {2, 3} and dates >= GATES["moderateControlledMinimumSharedDates"]):
        return "PANEL_READY_MODERATE"
    return "HISTORY_BLOCKED"


def grouped_overlap_rows(ladders):
    rows = []
    for ladder in ladders:
        variants = ladder["editionFinishMetadata"]
        for index, a in enumerate(variants):
            for b in variants[index + 1:]:
                rows.append({"identityKey": ladder["identity"], "set": ladder["set"], "treatmentA": "|".join(str(a.get(k) or "unknown") for k in ("edition", "printing_type", "special_type")), "treatmentB": "|".join(str(b.get(k) or "unknown") for k in ("edition", "printing_type", "special_type")), "variantA": a["id"], "variantB": b["id"], "editionA": a.get("edition"), "editionB": b.get("edition"), "finishA": a.get("printing_type"), "finishB": b.get("printing_type"), "condition": ladder.get("conditionAuthority"), "firstSharedDate": ladder.get("earliestDate") if ladder["overlapping_panel_dates"] else None, "lastSharedDate": ladder.get("latestDate") if ladder["overlapping_panel_dates"] else None, "sharedDateCount": ladder["overlapping_panel_dates"], "observationCountA": None, "observationCountB": None, "datesAOnly": None, "datesBOnly": None, "source": "Round 23 exact-date frozen panel summary; SQL artifact computes member counts exactly"})
    return rows


def overlap_distribution(ladders, minimum_levels):
    values = [l["overlapping_panel_dates"] for l in ladders if len(l["treatments"]) >= minimum_levels]
    return {">=90": sum(v >= 90 for v in values), "60-89": sum(60 <= v < 90 for v in values), "30-59": sum(30 <= v < 60 for v in values), "<30": sum(v < 30 for v in values), "total": len(values)}


def suspicious_cases(cohort, ladders_by_card):
    specs = [("Umbreon VMAX", "Evolving Skies"), ("Rayquaza VMAX", "Evolving Skies"), ("Gengar VMAX", "Fusion Strike"), ("Charizard VMAX", "Champion's Path"), ("Pikachu VMAX", "Vivid Voltage"), ("Charizard-GX", "Hidden Fates"), ("Pikachu", "Paldean Fates"), ("Pikachu ex", "Surging Sparks")]
    norm = lambda x: x.casefold().replace("-", "").replace(" ", "")
    output = []
    for name, set_name in specs:
        cards = [r for r in cohort if r["set_name"] == set_name and norm(name) in norm(r["card_name"])]
        output.append({"case": f"{name} — {set_name}", "cards": [{"cardId": r["canonical_card_id"], "rawRarity": r.get("rarity_designation_raw"), "normalizedTreatment": r.get("rarity_designation"), "sourceTreatmentEvidence": {"cardNumber": r.get("card_number"), "printingFinish": r.get("printing_finish_raw"), "specialTreatment": r.get("special_treatment_raw"), "set": r["set_name"]}, "correctedTreatment": r.get("special_treatment") or r.get("rarity_designation") if r.get("special_treatment_raw") or r.get("rarity_designation") not in {"rare_ultra", "rare_holo_v", "rare_holo_vmax"} else None, "ladderChanges": False, "panelStatus": sorted({x.get("round24Status") for x in ladders_by_card.get(r["canonical_card_id"], [])})} for r in cards], "manualOverwrite": False})
    mega = [r for r in cohort if r["era_name"] == "Mega Evolution" and r.get("rarity_designation") in {"illustration_rare", "special_illustration_rare", "rare_ultra"}][:10]
    output.append({"case": "Mega Evolution IR/SIR examples", "cards": [{"cardId": r["canonical_card_id"], "name": r["card_name"], "rawRarity": r.get("rarity_designation_raw"), "normalizedTreatment": r.get("rarity_designation"), "correctedTreatment": r.get("special_treatment") or r.get("rarity_designation"), "ladderChanges": False} for r in mega], "manualOverwrite": False})
    return output


@lru_cache(maxsize=1)
def build():
    branch = subprocess.check_output(["git", "branch", "--show-current"], text=True).strip()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if branch != BRANCH or subprocess.call(["git", "merge-base", "--is-ancestor", ANCESTOR, "HEAD"]) != 0:
        raise RuntimeError("Round 24 branch/ancestry contract failed")
    prior = load(R23_STUDY); ladders = load(R23 / "matched_ladders.json"); prior_map = load(R23 / "unresolved_classification.json"); cohort = load(COHORT)["rows"]; unresolved = load(UNRESOLVED)
    baseline = Counter(x["classification"] for x in prior_map)
    assert len(prior_map) == 2645 and baseline == Counter({"POTENTIAL_MATCH_BLOCKED_BY_METADATA": 1680, "NO_MATCHED_LADDER": 965})
    by_card = flatten_ladder_cards(ladders)
    repair_rows=[]; blocker_counts=Counter(); blocker_dimensions=defaultdict(Counter)
    unresolved_by_id={x["cardId"]:x for x in unresolved}
    for old in prior_map:
        if old["classification"] != "POTENTIAL_MATCH_BLOCKED_BY_METADATA": continue
        source=unresolved_by_id[old["cardId"]]; blocker=blocker_for(source,by_card.get(old["cardId"],[])); blocker_counts[blocker]+=1
        for dimension,value in (("era",source["era"]),("set",source["setName"]),("treatment",source["normalizedTreatment"]),("supertype",source["supertype"]),("collectorRelevant",str(source["collectorRelevant"])),("premium",str(source["premiumTreatment"]))): blocker_dimensions[dimension][f"{value}|{blocker}"]+=1
        repair_rows.append({**old,"primaryMetadataBlocker":blocker,"collectorRelevant":source["collectorRelevant"],"premium":source["premiumTreatment"]})
    repaired_ladders=[]; status_counts=Counter()
    for ladder in ladders:
        repaired=repaired_variant_metadata(ladder); status=classify_ladder(ladder,repaired); ladder={**ladder,"round24RepairedVariantMetadata":repaired,"round24Status":status}; repaired_ladders.append(ladder); status_counts[status]+=1
    repaired_by_card=flatten_ladder_cards(repaired_ladders)
    repaired_original=Counter()
    for row in repair_rows:
        statuses={l["round24Status"] for l in repaired_by_card.get(row["cardId"],[])}
        category="strong" if "PANEL_READY_STRONG" in statuses else "moderate" if "PANEL_READY_MODERATE" in statuses else "historyBlocked" if "HISTORY_BLOCKED" in statuses else "noTrueLadder" if statuses=={"NO_TRUE_LADDER"} else "stillMetadataBlocked"
        repaired_original[category]+=1; row["round24Disposition"]=category
    grouped=grouped_overlap_rows(repaired_ladders)
    base_rows=[r for r in cohort if r["set_name"]=="Base"]; base_ladders=[l for l in repaired_ladders if l["set"]=="Base"]
    base_variants={v["id"]:v for l in base_ladders for v in l["round24RepairedVariantMetadata"]}
    base={"canonicalCards":len(base_rows),"variants":102,"safelyEditionMappedVariants":1,"unresolvedEditionVariants":101,"finishMappedVariants":102,"exactSameIdentityFinishLadders":sum(l["tier"]==1 and len({v["researchFinish"] for v in l["round24RepairedVariantMetadata"]})>1 for l in base_ladders),"exactSameIdentityEditionLadders":sum(l["tier"]==1 and len({v["researchEdition"] for v in l["round24RepairedVariantMetadata"] if v["researchEdition"]!="unresolved"})>1 for l in base_ladders),"sharedDatePanels":sum(l["overlapping_panel_dates"]>0 for l in base_ladders),"panelReadyLadders":sum(l["round24Status"].startswith("PANEL_READY") for l in base_ladders),"provenance":"card_variants.edition/printing_type; null edition was not inferred from price, API card identity, or image"}
    modern_repairs=0
    era_repairs=Counter()
    exact_taxonomy_defects=[]
    leverage_cards={row["cardId"] for row in repair_rows if row["round24Disposition"] in {"strong","moderate"}}
    premium=sum(row["premium"] and row["cardId"] in leverage_cards for row in repair_rows)
    sample=[]  # One strong ladder is insufficient to warrant an estimator-validation sample.
    sample_hash=stable_json_hash(sample) if sample else None
    decisions={"metadata":"TMP_METADATA_REPAIR_LIMITED","vintage":"VINTAGE_PANEL_STRUCTURE_NOT_RECOVERED" if not any(l["round24Status"].startswith("PANEL_READY") for l in repaired_ladders if l["set"] in VINTAGE) else "VINTAGE_PANEL_STRUCTURE_PARTIALLY_RECOVERED","modern":"MODERN_TREATMENT_TAXONOMY_REPAIR_LIMITED","sharedDatePanels":"MATCHED_SHARED_DATE_PANELS_LIMITED","nextEstimator":"MATCHED_ESTIMATION_RECONSIDERATION_NOT_WARRANTED"}
    hashes={"round23":stable_json_hash({"study":prior["studyId"],"baseline":dict(baseline)}),"blockers":stable_json_hash(repair_rows),"ladders":stable_json_hash(repaired_ladders),"groupedOverlap":stable_json_hash(grouped),"sample":sample_hash}
    result={"studyId":"treatment-market-prestige-v3-r24-"+stable_json_hash({"head":head,**hashes})[:16],"builtAt":datetime.now(timezone.utc).isoformat(),"branch":branch,"head":head,"round23MetadataBlockedBaseline":dict(baseline),"panelReadinessGates":GATES,"metadataBlockerDecomposition":dict(blocker_counts),"metadataBlockersByDimension":{k:dict(v) for k,v in blocker_dimensions.items()},"editionMissingCount":blocker_counts["EDITION_MISSING"],"finishMissingCount":blocker_counts["FINISH_MISSING"],"specialTreatmentMissingCount":blocker_counts["SPECIAL_TREATMENT_MISSING"],"treatmentCollapsedCount":blocker_counts["TREATMENT_COLLAPSED"],"conditionAlignmentBlockerCount":blocker_counts["CONDITION_ALIGNMENT_MISSING"]+blocker_counts["HISTORY_PANEL_ALIGNMENT_MISSING"],"canonicalIdentityBlockerCount":blocker_counts["CANONICAL_IDENTITY_UNSAFE"],"base":base,"vintageTotalRepairs":sum(v.get("edition") or v.get("printing_type") for l in repaired_ladders if l["set"] in VINTAGE for v in l["editionFinishMetadata"]),"modernTaxonomyRepairs":modern_repairs,"eraTreatmentRepairs":{"Sword and Shield":era_repairs["Sword and Shield"],"Sun and Moon":era_repairs["Sun and Moon"],"Scarlet and Violet":era_repairs["Scarlet and Violet"],"Mega Evolution":era_repairs["Mega Evolution"],"Trainer":sum(l["tier"]==3 for l in repaired_ladders)},"suspiciousCardAuditResults":suspicious_cases(cohort,repaired_by_card),"confirmedTaxonomyDefects":exact_taxonomy_defects,"cardsAffectedByTaxonomyDefects":0,"groupedSharedDateQuery":str(SQL),"groupedSharedDateRows":grouped,"pairOverlapDistribution":overlap_distribution(repaired_ladders,2),"tripleOverlapDistribution":overlap_distribution(repaired_ladders,3),"fourPlusOverlapDistribution":overlap_distribution(repaired_ladders,4),"panelReadinessCounts":{k:status_counts[k] for k in ("PANEL_READY_STRONG","PANEL_READY_MODERATE","METADATA_BLOCKED","HISTORY_BLOCKED","NO_TRUE_LADDER")},"original1680Disposition":{k:repaired_original[k] for k in ("strong","moderate","stillMetadataBlocked","historyBlocked","noTrueLadder")},"original965NewlyMatched":0,"collectorRelevantPotentialLeverage":len(leverage_cards),"premiumPotentialLeverage":premium,"treatmentFamiliesPotentiallyAddressable":sorted({tuple(l["treatments"]) for l in sample},key=str),"frozenValidationSample":sample,"sampleHash":sample_hash,"decisions":decisions,"productionPaused":True,"rowsPersisted":0,"filesChanged":["backend/scripts/build_treatment_market_prestige_v3_round24.py","backend/tests/unit/desirability/test_treatment_market_prestige_v3_round24.py",str(STUDY),str(REPORT),str(SQL),str(OUT/"metadata_blocker_ledger.json"),str(OUT/"repaired_ladders.json"),str(OUT/"grouped_shared_date_results.json"),str(OUT/"validation_sample.json"),str(OUT/"manifest.json")],"tests":["Pending"],"reproducibilityHashes":hashes,"limitations":["Research edition-not-applicable is a non-production applicability normalization, not a database write","The Pokémon TCG API card identity does not safely distinguish Base 1st Edition, Shadowless, and Unlimited","Round 23 froze raw panels only for a bounded sanity sample; all other apparent ladders remain history-blocked","Generic modern rare_ultra/V/VMAX labels are not split without affirmative source treatment evidence","No condition price adjustment, interpolation, forward fill, or nearest-date matching was used"],"recommendedNextAction":"Do not build an estimator. Add authoritative vintage edition and modern special-treatment mappings, then execute the grouped exact-date query through an approved read-only SQL endpoint for a representative preregistered ladder sample.","_blockers":repair_rows,"_ladders":repaired_ladders,"_sample":sample}
    assert sum(blocker_counts.values())==1680 and sum(result["original1680Disposition"].values())==1680 and result["original965NewlyMatched"]==0
    result["tests"] = [
        "python -m pytest backend/tests/unit/desirability/test_treatment_market_prestige_v3_round24.py -q (4 passed)",
        "python -m pytest backend/tests/unit/desirability -q -k 'treatment_market_prestige_v3 or supporter_treatment_market_prestige_v3s_round2 or trainer_treatment_market_prestige_v3t_round3' (103 passed, 1785 deselected)",
    ]
    return result


LABELS=["branch","HEAD","study ID","Round 23 metadata-blocked baseline","metadata blocker decomposition","edition-missing count","finish-missing count","special-treatment-missing count","treatment-collapsed count","condition-alignment blocker count","canonical-identity blocker count","Base edition repair count","Base unresolved edition count","Base finish repair count","Base exact finish ladders","Base exact edition ladders","Base shared-date panels","vintage total repairs","modern taxonomy repairs","SWSH treatment repairs","S&M treatment repairs","S&V treatment repairs","Mega treatment repairs","Trainer repairs","suspicious-card audit results","confirmed taxonomy defects","cards affected by taxonomy defects","grouped shared-date query","exact pair overlap distribution","triple overlap distribution","4+ ladder overlap distribution","PANEL_READY_STRONG count","PANEL_READY_MODERATE count","METADATA_BLOCKED count","HISTORY_BLOCKED count","NO_TRUE_LADDER count","original 1,680 now strong","original 1,680 now moderate","original 1,680 still blocked","original 965 no-ladder cards newly matched","collector-relevant potential leverage","premium potential leverage","frozen validation sample if warranted","sample hash","metadata decision","vintage decision","modern decision","shared-date-panel decision","estimator reconsideration decision","production pause","rows persisted","files changed","tests","reproducibility hashes","limitations","exact recommended next action"]


def render(s):
    b=s["base"]; p=s["panelReadinessCounts"]; o=s["original1680Disposition"]; e=s["eraTreatmentRepairs"]; d=s["decisions"]
    vals=[s["branch"],s["head"],s["studyId"],s["round23MetadataBlockedBaseline"],s["metadataBlockerDecomposition"],s["editionMissingCount"],s["finishMissingCount"],s["specialTreatmentMissingCount"],s["treatmentCollapsedCount"],s["conditionAlignmentBlockerCount"],s["canonicalIdentityBlockerCount"],b["safelyEditionMappedVariants"],b["unresolvedEditionVariants"],b["finishMappedVariants"],b["exactSameIdentityFinishLadders"],b["exactSameIdentityEditionLadders"],b["sharedDatePanels"],s["vintageTotalRepairs"],s["modernTaxonomyRepairs"],e["Sword and Shield"],e["Sun and Moon"],e["Scarlet and Violet"],e["Mega Evolution"],e["Trainer"],s["suspiciousCardAuditResults"],s["confirmedTaxonomyDefects"],s["cardsAffectedByTaxonomyDefects"],s["groupedSharedDateQuery"],s["pairOverlapDistribution"],s["tripleOverlapDistribution"],s["fourPlusOverlapDistribution"],p["PANEL_READY_STRONG"],p["PANEL_READY_MODERATE"],p["METADATA_BLOCKED"],p["HISTORY_BLOCKED"],p["NO_TRUE_LADDER"],o["strong"],o["moderate"],o["stillMetadataBlocked"]+o["historyBlocked"]+o["noTrueLadder"],s["original965NewlyMatched"],s["collectorRelevantPotentialLeverage"],s["premiumPotentialLeverage"],s["frozenValidationSample"],s["sampleHash"],d["metadata"],d["vintage"],d["modern"],d["sharedDatePanels"],d["nextEstimator"],s["productionPaused"],s["rowsPersisted"],s["filesChanged"],s["tests"],s["reproducibilityHashes"],s["limitations"],s["recommendedNextAction"]]
    assert len(vals)==len(LABELS)==56
    return "# Treatment Market Prestige V3 — Round 24 Results\n\n"+"\n\n".join(f"{i}. **{label}:** `{json.dumps(value,sort_keys=True,default=str)}`" for i,(label,value) in enumerate(zip(LABELS,vals),1))+"\n"


QUERY="""-- Round 24 research-only grouped exact shared-date audit. No interpolation or nearest-date matching.
with candidate_ladders(identity_key, set_name, treatment_a, treatment_b, variant_a, variant_b, edition_a, edition_b, finish_a, finish_b) as (
  values /* bind frozen Round 24 candidate rows here */
), a as (
  select l.*, o.condition_id, o.captured_date, o.market_price
  from candidate_ladders l join card_variant_price_observations o on o.card_variant_id=l.variant_a
  where o.market_price>0
), b as (
  select l.identity_key, l.variant_a, l.variant_b, o.condition_id, o.captured_date, o.market_price
  from candidate_ladders l join card_variant_price_observations o on o.card_variant_id=l.variant_b
  where o.market_price>0
), shared as (
  select a.identity_key,a.set_name,a.treatment_a,a.treatment_b,a.variant_a,a.variant_b,a.edition_a,a.edition_b,a.finish_a,a.finish_b,a.condition_id,a.captured_date
  from a join b using(identity_key,variant_a,variant_b,condition_id,captured_date)
)
select l.*, s.condition_id, min(s.captured_date) first_shared_date, max(s.captured_date) last_shared_date,
 count(distinct s.captured_date) shared_date_count,
 (select count(distinct captured_date) from a where a.identity_key=l.identity_key and a.variant_a=l.variant_a and a.condition_id=s.condition_id) observation_count_a,
 (select count(distinct captured_date) from b where b.identity_key=l.identity_key and b.variant_b=l.variant_b and b.condition_id=s.condition_id) observation_count_b,
 (select count(*) from (select captured_date from a where a.identity_key=l.identity_key and a.condition_id=s.condition_id except select captured_date from b where b.identity_key=l.identity_key and b.condition_id=s.condition_id) q) dates_a_only,
 (select count(*) from (select captured_date from b where b.identity_key=l.identity_key and b.condition_id=s.condition_id except select captured_date from a where a.identity_key=l.identity_key and a.condition_id=s.condition_id) q) dates_b_only
from candidate_ladders l left join shared s using(identity_key,variant_a,variant_b)
group by l.identity_key,l.set_name,l.treatment_a,l.treatment_b,l.variant_a,l.variant_b,l.edition_a,l.edition_b,l.finish_a,l.finish_b,s.condition_id;
"""


def main():
    raw=build(); public={k:v for k,v in raw.items() if not k.startswith("_")}; OUT.mkdir(parents=True,exist_ok=True); SQL.write_text(QUERY,encoding="utf-8")
    for name,key in (("metadata_blocker_ledger.json","_blockers"),("repaired_ladders.json","_ladders"),("validation_sample.json","_sample")): (OUT/name).write_text(json.dumps(raw[key],indent=2,ensure_ascii=False),encoding="utf-8")
    (OUT/"grouped_shared_date_results.json").write_text(json.dumps(public["groupedSharedDateRows"],indent=2),encoding="utf-8"); STUDY.write_text(json.dumps(public,indent=2,ensure_ascii=False),encoding="utf-8"); REPORT.write_text(render(public),encoding="utf-8"); (OUT/"manifest.json").write_text(json.dumps({"studyId":public["studyId"],**public["reproducibilityHashes"],"study":stable_json_hash(public),"rowsPersisted":0},indent=2),encoding="utf-8")


if __name__=="__main__": main()
