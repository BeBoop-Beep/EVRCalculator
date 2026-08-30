"""Round 11 older-era history and Trainer/Energy estimand feasibility research."""
from __future__ import annotations
import json,math
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from typing import Any
import numpy as np

from backend.desirability.treatment_market_prestige_v3 import stable_json_hash
from backend.scripts.build_treatment_market_prestige_v3_round4 import ontology
from backend.scripts.build_treatment_market_prestige_v3_round5 import clean_rows,hierarchical
from backend.scripts.build_treatment_market_prestige_v3_round6 import CONTRACT,temporal_audit,treatment_readiness,universe_status

ROOT=Path("docs/research");OUT=ROOT/"treatment_market_prestige_v3_round11_pilot";STUDY=ROOT/"treatment_market_prestige_v3_round11_study.json";REPORT=ROOT/"TREATMENT_MARKET_PRESTIGE_V3_ROUND11_RESULTS.md"
COHORT=ROOT/"treatment_market_prestige_v3_round5_frozen/cohort.json";SETMAP=ROOT/"treatment_market_prestige_v3_frozen_cohort/set_era_mapping.json";HISTORY=ROOT/"treatment_market_prestige_v3_round11_history_audit.json";OBS=ROOT/"treatment_market_prestige_v3_round11_history_observations.json";R10=ROOT/"treatment_market_prestige_v3_round10_study.json"

def load(p:Path)->Any:return json.loads(p.read_text(encoding="utf-8"))
def audit(rows:list[dict[str,Any]],era:str)->dict[str,Any]:
 g=[r for r in rows if r["era_name"]==era]
 def counts(k):return dict(sorted(Counter(str(r.get(k) if r.get(k) is not None else "__NULL__") for r in g).items()))
 return {"pricedCards":len(g),"sets":len({r["set_id"] for r in g}),"species":len({r["species_id"] for r in g if r.get("species_id")}),"taxonomyMapped":sum(r.get("rarity_designation") is not None for r in g),"taxonomyUnmapped":sum(r.get("rarity_designation") is None for r in g),"canonicalMappingGaps":sum(not r.get("species_id") for r in g),"currentPriceCoverage":sum(r.get("market_price") is not None for r in g)/len(g),"normalizedTreatments":counts("rarity_designation"),"rawRarities":counts("rarity_designation_raw"),"printingFinishes":counts("printing_finish"),"specialTreatments":counts("special_treatment"),"editionStatuses":counts("edition_status"),"mechanics":dict(sorted(Counter(x for r in g for x in r.get("mechanic_or_card_form",[])).items()))}

def structures(rows,setmap):
 out={}
 for era in ("EX","Black and White"):
  tl=ontology(rows,setmap,era);dist=[]
  for i in range(1,len(tl)):
   a,b=set(tl[i-1]["features"]),set(tl[i]["features"]);dist.append({"afterIndex":i,"left":tl[i-1]["set_name"],"right":tl[i]["set_name"],"distance":1-len(a&b)/max(len(a|b),1)})
  cuts=[]
  for x in sorted(dist,key=lambda z:(-z["distance"],z["afterIndex"])):
   if x["distance"]<.5:continue
   proposed=sorted(cuts+[x["afterIndex"]]);bounds=[0,*proposed,len(tl)]
   if all(bounds[i+1]-bounds[i]>=3 for i in range(len(bounds)-1)):cuts=proposed
  bounds=[0,*cuts,len(tl)];regs=[]
  for i,(lo,hi) in enumerate(zip(bounds,bounds[1:]),1):regs.append({"universeId":era if len(bounds)==2 else f"black_and_white_r{i}","setIds":[x["set_id"] for x in tl[lo:hi]],"sets":[x["set_name"] for x in tl[lo:hi]]})
  out[era]={"decision":"ERA_RELATIVE" if len(regs)==1 else "TREATMENT_REGIME_RELATIVE","adjacentDistances":dist,"universes":regs}
 return out

def older_models(rows,obs,struct):
 results={}
 for era in ("EX","Black and White"):
  for reg in struct[era]["universes"]:
   setids=set(reg["setIds"]);series=[];current=[]
   for date in obs["checkpointDates"]:
    priced=[]
    for r in rows:
     p=obs["observations"][date].get(r["variant_id"])
     if r["era_name"]==era and r["set_id"] in setids and p:
      priced.append({**r,"market_price":p["market_price"],"log_price":math.log(p["market_price"])})
    current=clean_rows(priced,era,setids)
    series.append({"date":date,"rows":current})
   last=series[-1]["rows"]
   provisional=hierarchical(last,0.,1.,99,20260911);effects=provisional.get("effects",{})
   center=float(np.median([x["population_effect"] for x in effects.values()])) if effects else 0.;scale=float(np.subtract(*np.quantile([r["log_price"] for r in last],[.75,.25]))) if last else 1.;scale=scale or 1.
   modeled=[]
   for i,x in enumerate(series):modeled.append({"date":x["date"],"n":len(x["rows"]),"model":hierarchical(x["rows"],center,scale,399,20260911+i)})
   temporal=temporal_audit(modeled);ready=treatment_readiness(last,modeled[-1]["model"],temporal);status=universe_status(ready,"regime" if struct[era]["decision"]=="TREATMENT_REGIME_RELATIVE" else "era")
   results[reg["universeId"]]={"era":era,"sets":reg["sets"],"baseline":{"frozenCenter":center,"frozenScale":scale},"series":modeled,"temporalAudit":temporal,"treatments":ready,"status":status,"scoreableCards":sum(1 for r in last if ready.get(r["rarity_designation"],{}).get("status")=="AVAILABLE") if status=="AVAILABLE" else 0}
 return results

def domain_audit(rows,domain,history):
 g=[r for r in rows if r.get("supertype")==domain];names=Counter(r["card_name"] for r in g);multi={n for n in names if len({r.get("rarity_designation") for r in g if r["card_name"]==n})>=2};within={(r["set_id"],r["card_name"]) for r in g if len({x.get("rarity_designation") for x in g if x["set_id"]==r["set_id"] and x["card_name"]==r["card_name"]})>=2}
 byera={e:{"cards":sum(r["era_name"]==e for r in g),"identities":len({r["card_name"] for r in g if r["era_name"]==e}),"treatments":dict(Counter(r.get("rarity_designation") or "__UNMAPPED__" for r in g if r["era_name"]==e))} for e in sorted({r["era_name"] for r in g})}
 return {"cards":len(g),"exactCardNameIdentities":len(names),"usableIdentityCards":len(g),"repeatedIdentityCards":sum(n for n in names.values() if n>=2),"multiTreatmentIdentities":len(multi),"withinSetCrossTreatmentIdentities":len(within),"ambiguity":"Exact card_name is authoritative but not a reviewed character/entity identity; aliases and role variants remain unresolved.","byEra":byera,"treatmentOntology":dict(Counter(r.get("rarity_designation") or "__UNMAPPED__" for r in g)),"history":history["summary"][domain]}

def build()->dict[str,Any]:
 rows=load(COHORT)["rows"];hist=load(HISTORY);obs=load(OBS);r10=load(R10);struct=structures(rows,load(SETMAP));models=older_models(rows,obs,struct);ex=audit(rows,"EX");bw=audit(rows,"Black and White");trainer=domain_audit(rows,"Trainer",hist);energy=domain_audit(rows,"Energy",hist)
 exmods=[v for v in models.values() if v["era"]=="EX"];bwmods=[v for v in models.values() if v["era"]=="Black and White"]
 exrec=sum(x["scoreableCards"] for x in exmods);bwrec=sum(x["scoreableCards"] for x in bwmods);current=r10["internalDataOnlyMaximum"]["validatedCards"]
 trainer_upper=trainer["cards"];energy_upper=energy["cards"]
 ceilings={"pokemonOnly":{"conservative":current,"likely":current+exrec+bwrec,"upper":current+ex["pricedCards"]+bw["pricedCards"]},"pokemonPlusOlderHistory":{"conservative":current,"likely":current+exrec+bwrec,"upper":current+5486},"pokemonPlusTrainer":{"conservative":current,"likely":current,"upper":current+trainer_upper},"pokemonTrainerEnergy":{"conservative":current,"likely":current,"upper":current+trainer_upper+energy_upper},"combined":{"conservative":current,"likely":current+exrec+bwrec,"upper":min(19847,current+5486+trainer_upper+energy_upper)}}
 required=[r for r in rows if r["era_name"] in {"EX","Black and White"} and r.get("species_id") and r.get("demand_score") is not None and not r.get("promo_status_ambiguous")]
 history_classes=[]
 for r in required:
  available=[d for d in obs["checkpointDates"] if r["variant_id"] in obs["observations"][d]]
  history_classes.append({"canonicalCardId":r["canonical_card_id"],"variantId":r["variant_id"],"era":r["era_name"],"perDate":{d:("INTERNAL_HISTORY_AVAILABLE" if d in available else "INTERNAL_HISTORY_MISSING") for d in obs["checkpointDates"]},"overall":"INTERNAL_HISTORY_AVAILABLE" if len(available)==4 else "INTERNAL_HISTORY_MISSING" if not available else "INTERNAL_HISTORY_PARTIAL"})
 core={"historyHash":hist["observationIdentityHash"],"structures":struct,"modelStatuses":{k:v["status"] for k,v in models.items()},"trainerCards":trainer["cards"],"energyCards":energy["cards"]};sid=f"treatment-market-prestige-v3-r11-{stable_json_hash(core)[:16]}"
 external={"required":False,"contract":{"dates":"four immutable checkpoints spanning >=85 days","identity":"provider product -> canonical card -> canonical variant","condition":"Near Mint or demonstrably equivalent raw condition","price":"repeatable positive USD transaction-derived market price; listings are not substitutes","provenance":"source, retrieval time, market date, mapping version","coverage":">=95% per treatment/universe checkpoint"}}
 return {"study_id":sid,"built_at":datetime.now(timezone.utc).isoformat(),"historyAudit":hist,"EX":{"audit":ex,"ontology":ex["normalizedTreatments"],"architecture":struct["EX"],"internalHistory":{**hist["summary"]["EX"],"earliestReliableDate":"2026-05-31"},"externalHistoryRequirement":external,"pilot":exmods,"downstreamBlockers":dict(Counter(t["status"] for m in exmods for t in m["treatments"].values() if t["status"]!="AVAILABLE")),"potentialRecovery":exrec},"BlackAndWhite":{"audit":bw,"ontology":bw["normalizedTreatments"],"architecture":struct["Black and White"],"internalHistory":{**hist["summary"]["Black and White"],"earliestReliableDate":"2026-05-31"},"externalHistoryRequirement":external,"pilot":bwmods,"downstreamBlockers":dict(Counter(t["status"] for m in bwmods for t in m["treatments"].values() if t["status"]!="AVAILABLE")),"potentialRecovery":bwrec},"olderEraBackfillStatus":"OLDER_ERA_BACKFILL_PIPELINE_VALIDATED","Trainer":{"audit":trainer,"demandControls":{"independentMeasureFound":False,"repositoryEvidence":"Existing desirability contracts explicitly state Trainer desirability is not modeled.","priceLeakage":False,"identityFixedEffectsFeasibility":"Plausible from repeated exact names, but exact card_name is not yet a reviewed canonical Trainer entity."},"identification":"PLAUSIBLE_NOT_VALIDATED","pilot":{"run":False,"reason":"No clean independent demand control and exact card-name identity has unresolved alias/character ambiguity; coefficients would overstate identification."},"scoreFeasibility":"TRAINER_SUPERTYPE_RELATIVE_WITHIN_ERA_OR_REGIME after identity validation; no cross-supertype calibration","temporalFeasibility":hist["summary"]["Trainer"],"decision":"TRAINER_V3_ESTIMAND_PLAUSIBLE","potentialGain":{"conservative":0,"likely":0,"upper":trainer_upper}},"Energy":{"audit":energy,"identity":"Exact card_name plus basic/special semantics when present; no reviewed normalized energy-type entity exists.","modelFeasibility":"Insufficient within-era/regime cross-treatment identity depth for a validated pilot","pilot":{"run":False,"reason":"Only 37 identities span treatments catalog-wide and 17 do so within a set; fragmentation by era leaves the design underidentified."},"decision":"ENERGY_V3_ESTIMAND_REQUIRES_MORE_DATA","potentialGain":{"conservative":0,"likely":0,"upper":energy_upper}},"crossSupertypeComparability":"NOT_VALIDATED_AND_DEFAULT_NO","recommendedSemantics":"SUPERTYPE_RELATIVE_WITHIN_ERA_OR_REGIME","ceilings":ceilings,"seventyPercentPathStatus":"70_PERCENT_PATH_REMAINS_UNPROVEN","priorityRoadmap":["Independently reproduce and preregister EX/B&W baselines and validate pilot scores","Review canonical Trainer entity aliases and fixed-effect design","Scale older-era history pipeline to the next largest structurally supported eras","Acquire independent Trainer demand only if identity FE validation fails","Extend Energy identity data before modeling"],"productionPaused":True,"rowsPersisted":0,"productionBehavior":"Research-only; no migrations, publications, production rows, UI/Card Detail, V1/V2, appeal, RIP, or ranking changes.","filesChanged":["backend/scripts/audit_treatment_market_prestige_v3_round11_history.py","backend/scripts/build_treatment_market_prestige_v3_round11.py","backend/tests/unit/desirability/test_treatment_market_prestige_v3_round11.py",str(HISTORY),str(OBS),str(OUT/"card_history_classification.json"),str(STUDY),str(REPORT),str(OUT/"manifest.json")],"testsExecuted":["read-only history coverage","price-blind structure","older-era contract pilot","Trainer/Energy identification","coverage ceilings","full V3 regression"],"limitations":["New older-era baselines are research pilots, not approved production baselines","Trainer exact names are not canonical character entities","Energy is underidentified after era segmentation","Only EX and Black & White were modeled"],"exactNextTask":"Round 12: independently reproduce EX/B&W pilot baselines and treatment results, conduct reviewed Trainer entity-resolution/alias mapping, then preregister a Trainer identity-FE model before estimating coefficients.","_models":models,"_history_classes":history_classes}

def render(s):
 ex=s["EX"];bw=s["BlackAndWhite"];tr=s["Trainer"];en=s["Energy"];c=s["ceilings"]
 vals=[s["study_id"],ex["audit"]["pricedCards"],ex["ontology"],ex["architecture"]["decision"],ex["internalHistory"],ex["externalHistoryRequirement"],ex["downstreamBlockers"],ex["potentialRecovery"],bw["audit"]["pricedCards"],bw["ontology"],bw["architecture"]["decision"],bw["internalHistory"],bw["externalHistoryRequirement"],bw["downstreamBlockers"],bw["potentialRecovery"],s["olderEraBackfillStatus"],tr["audit"]["cards"],tr["audit"],tr["demandControls"],tr["audit"]["treatmentOntology"],tr["identification"],tr["pilot"],tr["scoreFeasibility"],tr["temporalFeasibility"],tr["decision"],tr["potentialGain"],en["audit"]["cards"],en["identity"],en["audit"]["treatmentOntology"],en["modelFeasibility"],en["pilot"],en["decision"],en["potentialGain"],s["crossSupertypeComparability"],s["recommendedSemantics"],{"cards":c["pokemonOnly"]["conservative"],"coverage":c["pokemonOnly"]["conservative"]/19847},c["pokemonPlusOlderHistory"],c["pokemonPlusTrainer"],c["pokemonTrainerEnergy"],c["combined"]["conservative"],c["combined"]["likely"],c["combined"]["upper"],s["seventyPercentPathStatus"],s["priorityRoadmap"],s["productionPaused"],s["rowsPersisted"],s["filesChanged"],s["testsExecuted"],s["limitations"],s["exactNextTask"]]
 labels=["Round 11 study ID","EX priced-card count","EX treatment ontology","EX era/regime decision","EX internal history coverage","EX external history requirement","EX downstream blockers","EX potential card recovery","Black & White priced-card count","Black & White ontology","Black & White era/regime decision","Black & White history coverage","Black & White external history requirement","Black & White downstream blockers","Black & White potential card recovery","Older-era backfill-pipeline status","Trainer card count","Trainer identity coverage","Trainer demand-control findings","Trainer treatment ontology","Trainer identification feasibility","Trainer pilot results","Trainer score feasibility","Trainer temporal feasibility","Trainer decision status","Trainer potential coverage gain","Energy card count","Energy identity structure","Energy ontology","Energy model feasibility","Energy pilot result","Energy decision status","Energy potential coverage gain","Cross-supertype score comparability result","Recommended supertype comparison semantics","Current Pokémon-domain coverage","Older-era-expanded potential coverage","Pokémon + Trainer potential coverage","Pokémon + Trainer + Energy potential coverage","Conservative catalog ceiling","Likely catalog ceiling","Theoretical catalog ceiling","Updated 70% path status","Priority roadmap","Production pause status","Rows persisted","Files changed","Tests executed","Remaining limitations","Exact next task"]
 return "# Treatment Market Prestige V3 — Round 11 Results\n\n"+"\n\n".join(f"{i}. **{a}:** `{json.dumps(v,sort_keys=True,default=str)}`" for i,(a,v) in enumerate(zip(labels,vals),1))+"\n"
def main():
 s=build();s.pop("_models");classes=s.pop("_history_classes");OUT.mkdir(parents=True,exist_ok=True);(OUT/"card_history_classification.json").write_text(json.dumps(classes,indent=2),encoding="utf-8");STUDY.write_text(json.dumps(s,indent=2),encoding="utf-8");REPORT.write_text(render(s),encoding="utf-8");(OUT/"manifest.json").write_text(json.dumps({"study_id":s["study_id"],"study_hash":stable_json_hash(s),"history_hash":s["historyAudit"]["observationIdentityHash"],"history_classification_hash":stable_json_hash(classes),"rows_persisted":0},indent=2),encoding="utf-8")
if __name__=="__main__":main()
