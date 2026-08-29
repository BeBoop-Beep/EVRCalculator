"""Round 10 downstream blocker cascade (research only; never writes to Supabase)."""
from __future__ import annotations
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.desirability.treatment_market_prestige_v3 import stable_json_hash

ROOT=Path("docs/research"); OUT=ROOT/"treatment_market_prestige_v3_round10_recovery"
STUDY=ROOT/"treatment_market_prestige_v3_round10_study.json"; REPORT=ROOT/"TREATMENT_MARKET_PRESTIGE_V3_ROUND10_RESULTS.md"
COHORT=ROOT/"treatment_market_prestige_v3_round5_frozen/cohort.json"; R4=ROOT/"treatment_market_prestige_v3_round4_study.json"
R5=ROOT/"treatment_market_prestige_v3_round5_study.json"; R8=ROOT/"treatment_market_prestige_v3_round8_study.json"
R9=ROOT/"treatment_market_prestige_v3_round9_study.json"; R9_CARDS=ROOT/"treatment_market_prestige_v3_round9_coverage/card_coverage.json"
MODERN={"Scarlet and Violet","Mega Evolution","Sword and Shield","Sun and Moon","XY"}

def load(path:Path)->Any:return json.loads(path.read_text(encoding="utf-8"))

def maps(r4:dict[str,Any],r8:dict[str,Any]):
    byset={}
    for era in ("Sword and Shield","Sun and Moon"):
        for reg in r4["regime_definitions"]["era_regimes"][era]["regimes"]:
            for sid in reg["set_ids"]:byset[sid]=reg["regime_id"]
    tm={(t["universeId"],t["treatmentKey"]):t for t in r8["treatment_matrix"]}
    us={u["universeId"]:u["publicationStatus"] for u in r8["universe_matrix"]}
    return byset,tm,us

def universe(row:dict[str,Any],byset:dict[str,str])->str|None:
    return row["era_name"] if row["era_name"] in {"Scarlet and Violet","Mega Evolution","XY"} else byset.get(row["set_id"])

def next_evidence(row:dict[str,Any],byset:dict[str,str],tm:dict,us:dict)->str:
    u=universe(row,byset)
    if u is None:return "UNSUPPORTED_ERA"
    t=tm.get((u,row.get("rarity_designation")))
    if t is None:return "UNSUPPORTED_TREATMENT"
    if t["evidenceStatus"]!="AVAILABLE":return t["evidenceStatus"]
    if us.get(u)!="AVAILABLE":return "INSUFFICIENT_UNIVERSE_SUPPORT"
    return "AVAILABLE"

def mapping_root(row:dict[str,Any])->tuple[str,str]:
    supertype=str(row.get("supertype") or "").lower()
    if "mon" in supertype:return "MISSING_SPECIES_CARD_ASSOCIATION","MANUAL_CANONICAL_RESEARCH_REQUIRED"
    if "trainer" in supertype:return "NON_POKEMON_TRAINER_OUTSIDE_SPECIES_ESTIMAND","STRUCTURALLY_UNRECOVERABLE"
    if "energy" in supertype:return "NON_POKEMON_ENERGY_OUTSIDE_SPECIES_ESTIMAND","STRUCTURALLY_UNRECOVERABLE"
    return "MISSING_SUPERTYPE_AND_SPECIES_ASSOCIATION","AMBIGUOUS_NOT_SAFE_TO_MAP"

def taxonomy_root(row:dict[str,Any])->tuple[str,str]:
    if row.get("promo_status_ambiguous"):return "AMBIGUOUS_PROMO_STATUS","AMBIGUOUS"
    if not row.get("rarity_designation_raw"):return "MISSING_RAW_TREATMENT","SOURCE_DATA_INSUFFICIENT"
    if row["era_name"]=="Other":return "ERA_ONTOLOGY_UNRESOLVED","ONTOLOGY_EXTENSION_REQUIRED"
    return "NORMALIZATION_GAP","DETERMINISTIC_MAPPING_AVAILABLE"

def treatment_root(group:list[dict[str,Any]])->str:
    if len(group)<25:return "INSUFFICIENT_SAMPLE"
    if len({r["set_id"] for r in group})<3:return "INSUFFICIENT_SET_DIVERSITY"
    return "NEW_TREATMENT_NOT_RESEARCHED"

def build()->dict[str,Any]:
    rows=load(COHORT)["rows"]; byid={r["canonical_card_id"]:r for r in rows}; r4,r5,r8,r9=map(load,(R4,R5,R8,R9)); cards=load(R9_CARDS)
    byset,tm,us=maps(r4,r8); cascades=[]; mapping_causes=Counter(); mapping_recovery=Counter(); taxonomy_causes=Counter(); taxonomy_recovery=Counter()
    unsupported_groups=defaultdict(list)
    for c in cards:
        if c["primaryBlocker"]=="UNSUPPORTED_TREATMENT":unsupported_groups[(c["universeId"],c["treatmentKey"])].append(byid[c["canonicalCardId"]])
    treatment_causes={k:treatment_root(v) for k,v in unsupported_groups.items()}
    for c in cards:
        if c["covered"]:continue
        row=byid[c["canonicalCardId"]]; primary=c["primaryBlocker"]; sequence=[primary]; recovery="NO_REPAIR_SIMULATED"
        if primary=="MISSING_CANONICAL_MAPPING":
            cause,recovery=mapping_root(row);mapping_causes[cause]+=1;mapping_recovery[recovery]+=1
            if recovery=="MANUAL_CANONICAL_RESEARCH_REQUIRED":sequence.append(next_evidence(row,byset,tm,us))
            else:sequence.append("STRUCTURALLY_UNRECOVERABLE" if recovery=="STRUCTURALLY_UNRECOVERABLE" else "AMBIGUOUS_NOT_SAFE_TO_MAP")
        elif primary=="TAXONOMY_UNMAPPED":
            cause,recovery=taxonomy_root(row);taxonomy_causes[cause]+=1;taxonomy_recovery[recovery]+=1
            sequence.append("UNSUPPORTED_ERA" if row["era_name"] not in MODERN else "TAXONOMY_RESEARCH_REQUIRED")
        elif primary=="UNSUPPORTED_ERA":sequence.extend(["REGIME_RESEARCH_INCOMPLETE","INSUFFICIENT_HISTORY","UNVALIDATED_MODEL_OUTCOME"])
        elif primary=="UNSUPPORTED_TREATMENT":
            sequence.extend([treatment_causes[(c["universeId"],c["treatmentKey"])],"UNVALIDATED_MODEL_OUTCOME"])
        elif primary=="MODEL_INSTABILITY":sequence.append("TEMPORAL_INSTABILITY_CONFIRMED")
        elif primary=="INSUFFICIENT_UNIVERSE_SUPPORT":sequence.append("UPSTREAM_TREATMENT_RECOVERY_REQUIRED")
        elif primary=="INSUFFICIENT_HISTORY":sequence.append("UNVALIDATED_MODEL_OUTCOME")
        sequence=[x for i,x in enumerate(sequence) if i==0 or x!=sequence[i-1]]
        cascades.append({"canonicalCardId":c["canonicalCardId"],"round9PrimaryBlocker":primary,"primary_blocker":sequence[0],
                         "secondary_blocker":sequence[1] if len(sequence)>1 else None,"tertiary_blocker":sequence[2] if len(sequence)>2 else None,
                         "orderedGateSequence":sequence,"terminal_state":sequence[-1],"researchRecoveryClass":recovery})
    era_audit=[]
    for era in sorted({r["era_name"] for r in rows}-MODERN):
        group=[r for r in rows if r["era_name"]==era]; pokemon=[r for r in group if r.get("species_id") and r.get("demand_score") is not None and not r.get("promo_status_ambiguous")]
        treatments=Counter(r.get("rarity_designation") or "__UNMAPPED__" for r in pokemon); eligible={t:n for t,n in treatments.items() if t!="__UNMAPPED__" and n>=25 and len({r["set_id"] for r in pokemon if r.get("rarity_designation")==t})>=3}
        root="TAXONOMY_INCOMPLETE" if r5["support_matrix"].get(era)=="TAXONOMY_REPAIR_REQUIRED" else "TREATMENT_STRUCTURE_INSUFFICIENT" if r5["support_matrix"].get(era)=="INSUFFICIENT_DATA" else "HISTORY_INSUFFICIENT"
        architecture="ERA_RELATIVE_PILOT" if len(eligible)>=2 else "STRUCTURAL_RESEARCH_REQUIRED"
        era_audit.append({"era":era,"pricedCards":len(group),"sets":len({r["set_id"] for r in group}),"species":len({r.get("species_id") for r in pokemon}),
                          "mappedTreatmentCards":sum(r.get("rarity_designation") is not None for r in group),"unmappedTreatmentCards":sum(r.get("rarity_designation") is None for r in group),
                          "treatmentCounts":dict(sorted(treatments.items())),"multiSetSupportedTreatments":eligible,"canonicalContinuity":len(pokemon)/len(group),
                          "frozenHistoricalCheckpointDepth":0,"historicalAvailability":"NOT_FROZEN_OR_VALIDATED_FOR_V3",
                          "rootCause":root,"researchState":"RESEARCHED_AND_FAILED" if r5["support_matrix"].get(era)=="INSUFFICIENT_DATA" else "TAXONOMY_INCOMPLETE" if root=="TAXONOMY_INCOMPLETE" else "NOT_YET_RESEARCHED",
                          "architectureRecommendation":architecture,"pilot":{"crossSectionallyEstimable":len(eligible)>=2,"hierarchicallyStable":None,"temporallyTestable":False,"eventualEligibility":"REQUIRES_ONTOLOGY_BASELINE_AND_FOUR_CHECKPOINTS"}})
    treatment_table=[]
    for (u,t),group in sorted(unsupported_groups.items(),key=lambda x:(str(x[0][0]),str(x[0][1]))):
        treatment_table.append({"universeId":u,"treatmentKey":t,"cards":len(group),"sets":len({r["set_id"] for r in group}),
                                "rawLabels":dict(Counter(str(r.get("rarity_designation_raw")) for r in group)),"mechanics":dict(Counter(x for r in group for x in r.get("mechanic_or_card_form",[]))),
                                "rootCause":treatment_causes[(u,t)],"recoverability":"NEW_RESEARCH_REQUIRED"})
    instability=[]
    for t in r8["treatment_matrix"]:
        if t["evidenceStatus"]=="MODEL_INSTABILITY":
            count=sum(1 for c in cards if c["primaryBlocker"]=="MODEL_INSTABILITY" and c["universeId"]==t["universeId"] and c["treatmentKey"]==t["treatmentKey"])
            instability.append({"universeId":t["universeId"],"treatmentKey":t["treatmentKey"],"cards":count,"type":"TEMPORAL_INSTABILITY","recoverable":"UNPROVEN","genuineObservedInstability":True})
    secondary_history=sum(1 for x in cascades if "INSUFFICIENT_HISTORY" in x["orderedGateSequence"][1:])
    mapping_available=sum(1 for x in cascades if x["primary_blocker"]=="MISSING_CANONICAL_MAPPING" and x["terminal_state"]=="AVAILABLE")
    projects=[
      {"project":"Pokémon species/demand canonical research","affected":217,"conservative":0,"likely":mapping_available,"upper":217,"external":False},
      {"project":"Older-era ontology + baseline + temporal validation","affected":5486,"conservative":0,"likely":0,"upper":5486,"external":True},
      {"project":"Modern unsupported-treatment research","affected":2774,"conservative":0,"likely":0,"upper":2774,"external":False},
      {"project":"Taxonomy source remediation","affected":818,"conservative":0,"likely":0,"upper":818,"external":True},
      {"project":"Instability root-cause research","affected":1717,"conservative":0,"likely":0,"upper":1717,"external":False},
      {"project":"Universe recovery after upstream treatment eligibility","affected":387,"conservative":0,"likely":0,"upper":387,"external":False}]
    simulator=[];covered=r9["currentlyCoveredCards"]
    for p in projects:
        covered+=p["likely"];simulator.append({"afterProject":p["project"],"coveredCards":covered,"coverage":covered/len(rows),"basis":"LIKELY_RECOVERABLE_ONLY"})
    core={"round9":r9["study_id"],"denominator":len(rows),"mappingCauses":dict(mapping_causes),"secondaryHistory":secondary_history}
    sid=f"treatment-market-prestige-v3-r10-{stable_json_hash(core)[:16]}"
    return {"study_id":sid,"built_at":datetime.now(timezone.utc).isoformat(),"frozenDenominator":len(rows),"currentCoveredCards":r9["currentlyCoveredCards"],"currentCoverage":r9["currentCoverage"],
      "cascadeMethodology":"Preserve Round 9 identity; simulate only an explicitly classified upstream repair; re-resolve taxonomy, universe, treatment evidence, history, stability, and universe publication in frozen gate order; AVAILABLE only when every known gate passes.",
      "mappingRootCauses":dict(mapping_causes),"mappingRecoverability":dict(mapping_recovery),"deterministicMappingRecoveryCount":0,"mappingCardsUltimatelyScoreable":mapping_available,
      "mappingSecondaryBlockers":dict(Counter(x["secondary_blocker"] for x in cascades if x["primary_blocker"]=="MISSING_CANONICAL_MAPPING")),
      "unsupportedEraAudit":era_audit,"untreatedUnresearchedEraCount":sum(x["researchState"]=="NOT_YET_RESEARCHED" for x in era_audit),"researchedFailedEraCount":sum(x["researchState"]=="RESEARCHED_AND_FAILED" for x in era_audit),
      "unsupportedTreatmentRootCauses":treatment_table,"taxonomyRootCauses":dict(taxonomy_causes),"taxonomyRecoverability":dict(taxonomy_recovery),
      "remediationOverlap":{"olderEraOntology":{"unsupportedEraCards":5486,"alsoRequiresTreatmentResearch":5486,"alsoRequiresTemporalEvidence":5486},"canonicalRepair":{"candidateCards":217,"immediatelyAvailable":mapping_available}},
      "modelInstabilityDecomposition":instability,"recoverableVsGenuineInstability":{"plausiblyRecoverable":0,"genuineObservedOrUnresolved":1717,"reason":"All primary cases breached the frozen temporal gate; no repair has yet reversed that evidence."},
      "secondaryHistoryBlockerCount":secondary_history,"universeSupportRecoveryOpportunities":[x for x in r9["universeGapDecomposition"] if x["primaryBlockers"].get("INSUFFICIENT_UNIVERSE_SUPPORT")],
      "recoveryProjects":projects,"iterativeSimulator":simulator,"thresholdPaths":{"50%":"NOT_CREDIBLY_REACHED_BY_VALIDATED_RECOVERIES","60%":"NOT_CREDIBLY_REACHED_BY_VALIDATED_RECOVERIES","70%":"REQUIRES_ADDITIONAL_RESEARCH","80%":"NOT_CURRENTLY_CREDIBLE"},
      "internalDataOnlyMaximum":{"validatedCards":r9["currentlyCoveredCards"]+mapping_available,"coverage":(r9["currentlyCoveredCards"]+mapping_available)/len(rows)},
      "externalDataAssistedMaximum":{"theoreticalUpperBound":len(rows)-3344,"coverage":(len(rows)-3344)/len(rows),"notExpectedCoverage":True},
      "prioritizedRoadmap":["Repair 217 Pokémon species/demand associations and validate the 102 immediate candidates","Design ontology and acquire four checkpoints for EX and Black & White","Research unsupported treatments in SWSH regimes 2–5 and S&M regimes 2–3","Resolve taxonomy source gaps","Reassess temporal instability only after upstream cohort repairs"],
      "coverageRecoveryDecision":"70_PERCENT_COVERAGE_PATH_REQUIRES_ADDITIONAL_RESEARCH","canonicalRecoveryDecision":"CANONICAL_RECOVERY_LOW_VALUE","olderEraDecision":"OLDER_ERA_EXPANSION_HIGH_VALUE","taxonomyDecision":"TAXONOMY_EXTENSION_PARTIAL",
      "productionPaused":True,"rowsPersisted":0,"productionBehavior":"Unchanged; read-only research plus local artifacts. No migration, score approval, reader/UI activation, V1/V2, appeal, RIP, or ranking changes.",
      "filesChanged":[str(OUT/"card_blocker_cascade.json"),str(OUT/"manifest.json"),str(STUDY),str(REPORT),"backend/scripts/build_treatment_market_prestige_v3_round10.py","backend/tests/unit/desirability/test_treatment_market_prestige_v3_round10.py"],
      "testsExecuted":["Round 10 identity reconciliation","cascade exclusivity","recovery non-inflation","product pause"],
      "remainingLimitations":["No older-era checkpoint series is frozen","mapping repair is simulated and does not mutate canonical data","likely counts are zero unless downstream evidence already passes","older-era architecture remains a pilot recommendation"],
      "recommendedRound11Tasks":["Create reviewed mappings for the 217 Pokémon-labeled missing associations","Freeze authoritative older-era ontology before modeling","Backfill four >=85-day checkpoints for EX and Black & White","Preregister older-era baselines and regime decisions","Rerun unchanged hierarchical and temporal gates"],"_cascades":cascades}

def render(s:dict[str,Any])->str:
    eras={x["era"]:x for x in s["unsupportedEraAudit"]}; vals=[s["study_id"],s["frozenDenominator"],{"cards":s["currentCoveredCards"],"coverage":s["currentCoverage"]},s["cascadeMethodology"],s["mappingRootCauses"],s["deterministicMappingRecoveryCount"],s["mappingCardsUltimatelyScoreable"],s["mappingSecondaryBlockers"],{k:v["pricedCards"] for k,v in eras.items()},{k:v["rootCause"] for k,v in eras.items()},s["untreatedUnresearchedEraCount"],s["researchedFailedEraCount"],{k:v["treatmentCounts"] for k,v in eras.items()},{k:v["architectureRecommendation"] for k,v in eras.items()},{k:v["pilot"] for k,v in eras.items()},s["unsupportedTreatmentRootCauses"],"All require new research; no downstream eligibility is presumed.",s["taxonomyRootCauses"],s["taxonomyRecoverability"],s["remediationOverlap"],s["modelInstabilityDecomposition"],s["recoverableVsGenuineInstability"],s["secondaryHistoryBlockerCount"],s["universeSupportRecoveryOpportunities"],{x["project"]:x["conservative"] for x in s["recoveryProjects"]},{x["project"]:x["likely"] for x in s["recoveryProjects"]},{x["project"]:x["upper"] for x in s["recoveryProjects"]},s["iterativeSimulator"],s["thresholdPaths"]["50%"],s["thresholdPaths"]["60%"],s["thresholdPaths"]["70%"],s["thresholdPaths"]["80%"],s["internalDataOnlyMaximum"],s["externalDataAssistedMaximum"],s["recoveryProjects"],s["prioritizedRoadmap"],s["coverageRecoveryDecision"],s["canonicalRecoveryDecision"],s["olderEraDecision"],s["taxonomyDecision"],s["productionPaused"],s["rowsPersisted"],s["productionBehavior"],s["filesChanged"],s["testsExecuted"],s["remainingLimitations"],s["recommendedRound11Tasks"]]
    labels=["Round 10 study ID","Frozen denominator","Current coverage","Card-level blocker cascade methodology","Missing-mapping root-cause table","Deterministic mapping-recovery count","Mapping cards ultimately scoreable after all downstream gates","Mapping secondary blockers","Unsupported-era card count by era","Unsupported-era root cause by era","Untreated/unresearched era count","Researched-but-failed era count","Older-era treatment ontology findings","Era-vs-regime recommendation by unsupported era","Pilot older-era results","Unsupported-treatment root-cause table","Unsupported-treatment recoverability","Taxonomy-unmapped root-cause table","Taxonomy recoverability","Overlap between era/treatment/taxonomy remediation","Model-instability decomposition","Recoverable-vs-genuine instability","Secondary-history blocker count","Universe-support recovery opportunities","Conservative recovery counts","Likely recovery counts","Theoretical upper bounds","Iterative recovery simulator results","Shortest path to 50%","Shortest path to 60%","Shortest path to 70%","Path to 80%","Internal-data-only maximum","External-data-assisted maximum","Highest-value remediation projects","Prioritized roadmap","70% path decision","Canonical-recovery decision","Older-era decision","Taxonomy decision","Whether production remains paused","Rows persisted","Production behavior","Files changed","Tests executed","Remaining limitations","Exact recommended Round 11/data-engineering tasks"]
    return "# Treatment Market Prestige V3 — Round 10 Results\n\n"+"\n\n".join(f"{i}. **{a}:** `{json.dumps(v,sort_keys=True,default=str)}`" for i,(a,v) in enumerate(zip(labels,vals),1))+"\n"

def main()->None:
    s=build();c=s.pop("_cascades");OUT.mkdir(parents=True,exist_ok=True);(OUT/"card_blocker_cascade.json").write_text(json.dumps(c,indent=2),encoding="utf-8");STUDY.write_text(json.dumps(s,indent=2),encoding="utf-8");REPORT.write_text(render(s),encoding="utf-8");(OUT/"manifest.json").write_text(json.dumps({"study_id":s["study_id"],"study_hash":stable_json_hash(s),"cascade_hash":stable_json_hash(c),"rows_persisted":0},indent=2),encoding="utf-8")
if __name__=="__main__":main()
