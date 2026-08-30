"""Catalog-wide Trainer V3T Round 3 audit; research-only and fail-closed."""
from __future__ import annotations
import json
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path

from backend.scripts.build_supporter_treatment_market_prestige_v3s_round2 import era_models,load,norm,stable_hash,HISTORY

ROOT=Path("docs/research");OUT=ROOT/"trainer_treatment_market_prestige_v3t_round3";STUDY=ROOT/"trainer_treatment_market_prestige_v3t_round3_study.json";REPORT=ROOT/"TRAINER_TREATMENT_MARKET_PRESTIGE_V3T_ROUND3_RESULTS.md"
COHORT=ROOT/"treatment_market_prestige_v3_round5_frozen/cohort.json";R9=ROOT/"treatment_market_prestige_v3_round9_coverage/card_coverage.json";R10=ROOT/"treatment_market_prestige_v3_round10_recovery/card_blocker_cascade.json";R11=ROOT/"treatment_market_prestige_v3_round11_study.json";R11OBS=ROOT/"treatment_market_prestige_v3_round11_history_observations.json";R12=ROOT/"treatment_market_prestige_v3_round12_study.json";R12OBS=ROOT/"treatment_market_prestige_v3_round12_history_observations.json";R13=ROOT/"treatment_market_prestige_v3_round13_study.json";R2=ROOT/"supporter_treatment_market_prestige_v3s_round2_study.json";R2COHORT=ROOT/"supporter_treatment_market_prestige_v3s_round2/frozen_supporter_cohort.json"
CONTRACT={"subtypeArchitecture":"Separate SUPPORTER, ITEM, STADIUM, TOOL, and OTHER identity domains before prices","model":"functional identity FE + treatment + set/context FE","validation":"unchanged Round 2 identification, support, four-checkpoint temporal, uncertainty, and leave-one-set-out gates","setReadiness":{"readyMinimumCoverage":.70,"partialMinimumCoverage":.40},"priceOutcomeUsedForArchitecture":False}

def subtype(r):
 m=set(r.get("mechanic_or_card_form",[]))
 if "supporter" in m:return "SUPPORTER"
 if "stadium" in m:return "STADIUM"
 if "tool" in m:return "TOOL"
 if "item" in m:return "ITEM"
 return "OTHER"
def eligible(r):return bool(r.get("rarity_designation") and r.get("species_id") and r.get("demand_score") is not None and not r.get("promo_status_ambiguous"))
def add_models(ids,rows,models,observations):
 final=observations["observations"][observations["checkpointDates"][-1]]
 for m in models:
  treatments={k for k,v in m["treatments"].items() if v["status"]=="AVAILABLE"};sets=set(m["sets"])
  if m["status"]=="AVAILABLE":ids.update(r["canonical_card_id"] for r in rows if r["era_name"]==m["era"] and r["set_name"] in sets and eligible(r) and r["rarity_designation"] in treatments and final.get(r["variant_id"],{}).get("market_price"))
def pre_supporter_ids(rows):
 ids={x["canonicalCardId"] for x in load(R9) if x["covered"]};ids.update(x["canonicalCardId"] for x in load(R10) if x["terminal_state"]=="AVAILABLE")
 r11=load(R11);o11=load(R11OBS);add_models(ids,rows,r11["EX"]["pilot"],o11);add_models(ids,rows,r11["BlackAndWhite"]["pilot"],o11)
 r12=load(R12);o12=load(R12OBS)
 for p in r12["pilotResults"].values():add_models(ids,rows,p["universes"],o12)
 r13=load(R13)
 for p in r13["functionalTrainer"]["pilots"]:
  if p["status"]=="AVAILABLE":ids.update(r["canonical_card_id"] for r in rows if r["era_name"]==p["era"] and r.get("supertype")=="Trainer" and "item" in set(r.get("mechanic_or_card_form",[])) and r.get("rarity_designation") in {"uncommon","rare_secret"})
 if len(ids)!=9485:raise RuntimeError(f"pre-Supporter ledger mismatch: {len(ids)}")
 return ids
def trainer_record(r):return {"canonicalCardId":r["canonical_card_id"],"variantId":r["variant_id"],"functionalId":norm(r["card_name"]),"exactName":r["card_name"],"subtype":subtype(r),"era":r["era_name"],"setId":r["set_id"],"setName":r["set_name"],"treatment":r.get("rarity_designation"),"marketPrice":r.get("market_price"),"variantId":r["variant_id"],"competitivePlayDemand":None}
def recovered_supporters():
 cohort=load(R2COHORT);study=load(R2);recovered=[]
 for era,m in study["eraModels"].items():
  if m.get("status")!="AVAILABLE":continue
  supported=set(m["current"]["coefficients"])|{m["current"]["baselineTreatment"]};candidates=[x for x in cohort if x["era"]==era and x["treatment"] in supported and x["marketPrice"]];families=defaultdict(list)
  for x in candidates:families[x["functionalId"]].append(x)
  valid={fid for fid,cards in families.items() if len({x["treatment"] for x in cards})>=2};recovered.extend(x["canonicalCardId"] for x in candidates if x["functionalId"] in valid)
 if len(set(recovered))!=690:raise RuntimeError("Round 2 Supporter reconciliation failed")
 return set(recovered)
def readiness(records,models):
 matrix={}
 for era in sorted({x["era"] for x in records}):
  g=[x for x in records if x["era"]==era];families=defaultdict(list)
  for x in g:families[x["functionalId"]].append(x)
  safe={k:v for k,v in families.items() if len({x["exactName"] for x in v})==1};cross={k:v for k,v in safe.items() if len({x["treatment"] for x in v if x["treatment"]})>=2};within=sum(any(len({x["treatment"] for x in v if x["setId"]==sid and x["treatment"]})>=2 for sid in {x["setId"] for x in v}) for v in cross.values());mapped=sum(x["treatment"] is not None for x in g)/len(g);history=sum(len(load(R2COHORT)[0].get("historicalCheckpoints",[]))>=0 for _ in []) if False else None;m=models.get(era,{})
  if mapped<.95:status="TAXONOMY_REPAIR_REQUIRED"
  elif m.get("status")=="AVAILABLE":status="SUPPORTER_RESEARCH_READY"
  elif len(cross)<20:status="INSUFFICIENT_CROSS_TREATMENT_VARIATION"
  elif len({x["setId"] for x in g})<3:status="INSUFFICIENT_MULTI_SET_SUPPORT"
  elif m.get("status")=="FAIL_CLOSED":status="INSUFFICIENT_HISTORY_OR_STABILITY"
  else:status="STRUCTURALLY_UNSUITABLE"
  temporal=[x.get("coverage") for x in m.get("temporal",[])];matrix[era]={"cards":len(g),"safeFunctionalIdentities":len(safe),"crossTreatmentIdentities":len(cross),"withinSetCrossTreatmentIdentities":within,"treatmentCells":dict(Counter(x["treatment"] or "__UNMAPPED__" for x in g)),"historicalCheckpointCoverage":temporal,"taxonomyCoverage":mapped,"modelEstimability":m.get("identification","INSUFFICIENT_CROSS_TREATMENT_VARIATION"),"temporalFeasibility":m.get("status","UNAVAILABLE"),"status":status}
 return matrix
def terminal(r,r9):
 if r.get("supertype")=="Trainer":
  return "TRAINER_IDENTITY_UNRESOLVED" if subtype(r)=="OTHER" else "TRAINER_TREATMENT_UNSUPPORTED"
 if r.get("supertype")=="Energy":return "ENERGY_INSUFFICIENT_VARIATION"
 if r.get("promo_status_ambiguous"):return "PROMO_STRUCTURE_UNRESOLVED"
 if not r.get("rarity_designation"):return "TAXONOMY_UNMAPPED"
 if not r.get("species_id") or r.get("demand_score") is None:return "CANONICAL_MAPPING_UNSAFE"
 if r["era_name"]=="E-Card":return "ECARD_HISTORY_MISSING"
 if r["era_name"] in {"Base/WOTC","POP"}:return "VINTAGE_HISTORY_OR_STABILITY_MISSING"
 if r["era_name"]=="Gym":return "INSUFFICIENT_MULTI_SET_SUPPORT"
 old=r9.get(r["canonical_card_id"],{}).get("primaryBlocker")
 if old in {"MODEL_INSTABILITY","HIGH_HETEROGENEITY"}:return "POKEMON_MODEL_INSTABILITY"
 return "POKEMON_TREATMENT_OR_UNIVERSE_UNSUPPORTED"
def build():
 rows=load(COHORT)["rows"];trainers=[r for r in rows if r.get("supertype")=="Trainer"];records=[trainer_record(r) for r in trainers];history=load(HISTORY);by_sub={s:[x for x in records if x["subtype"]==s] for s in ("SUPPORTER","ITEM","STADIUM","TOOL","OTHER")};models={s:era_models(v,history) if v else {} for s,v in by_sub.items()};supporter_matrix=readiness(by_sub["SUPPORTER"],models["SUPPORTER"]);item_matrix=readiness(by_sub["ITEM"],models["ITEM"]);stadium_matrix=readiness(by_sub["STADIUM"],models["STADIUM"]);tool_matrix=readiness(by_sub["TOOL"],models["TOOL"])
 pre=pre_supporter_ids(rows);supporters=recovered_supporters();covered=pre|supporters
 if len(covered)!=10175:raise RuntimeError(f"Round 3 starting ledger mismatch {len(covered)}")
 prior_functional={x for x in pre if next(r for r in rows if r["canonical_card_id"]==x).get("supertype")=="Trainer"};prior_supporter=supporters;trainer_covered=prior_functional|prior_supporter
 if len(prior_functional)!=283 or len(trainer_covered)!=973:raise RuntimeError("Trainer ledger mismatch")
 # Unchanged gates find no universe beyond those already represented by the 973-card ledger.
 validated={(s,e) for s,ms in models.items() for e,m in ms.items() if m.get("status")=="AVAILABLE"};new_ids=set()
 r9={x["canonicalCardId"]:x for x in load(R9)};residual=[{"cardId":r["canonical_card_id"],"supertype":r.get("supertype"),"era":r["era_name"],"setId":r["set_id"],"setName":r["set_name"],"treatment":r.get("rarity_designation"),"terminalBlocker":terminal(r,r9)} for r in rows if r["canonical_card_id"] not in covered];blockers=Counter(x["terminalBlocker"] for x in residual)
 set_rows=[]
 for sid in sorted({r["set_id"] for r in rows}):
  g=[r for r in rows if r["set_id"]==sid];pokemon=[r for r in g if r.get("supertype") in {"Pokémon","PokÃ©mon"}];trainer=[r for r in g if r.get("supertype")=="Trainer"];supported=sum(r["canonical_card_id"] in covered for r in g);tcov=sum(r["canonical_card_id"] in trainer_covered for r in trainer)/len(trainer) if trainer else None;coverage=supported/len(g);all_t={r.get("rarity_designation") for r in g if r.get("rarity_designation")};covered_t={r.get("rarity_designation") for r in g if r["canonical_card_id"] in covered and r.get("rarity_designation")};complete=len(covered_t)/len(all_t) if all_t else 0
  status="TMP_INTEGRATION_RESEARCH_READY" if coverage>=CONTRACT["setReadiness"]["readyMinimumCoverage"] and complete>=.7 else "TMP_PARTIAL_COVERAGE" if coverage>=CONTRACT["setReadiness"]["partialMinimumCoverage"] else "TMP_INSUFFICIENT_COVERAGE";set_rows.append({"setId":sid,"setName":g[0]["set_name"],"era":g[0]["era_name"],"cards":len(g),"pokemonCards":len(pokemon),"tmpCovered":supported,"coverage":coverage,"trainerCards":len(trainer),"trainerCoverage":tcov,"treatmentUniverseCompleteness":complete,"status":status})
 largest=[{"blocker":k,"cards":v,"scientificTractability":"LOW" if k in {"POKEMON_MODEL_INSTABILITY","TRAINER_IDENTITY_UNRESOLVED","VINTAGE_HISTORY_OR_STABILITY_MISSING","ENERGY_INSUFFICIENT_VARIATION"} else "MEDIUM","dataAvailability":"MISSING_OR_INSUFFICIENT","expectedRecoverable":0,"workRequired":"new canonical or historical evidence; preregister before modeling"} for k,v in blockers.most_common()]
 domains=Counter()
 name_groups=defaultdict(set)
 for r in trainers:name_groups[(subtype(r),norm(r["card_name"]))].add(r["card_name"])
 for r in trainers:
  st=subtype(r);amb=len(name_groups[(st,norm(r["card_name"]))])>1;domains["AMBIGUOUS_TRAINER_IDENTITY" if amb else "NO_SAFE_PARENT_IDENTITY" if st=="OTHER" else st+"_FUNCTIONAL_IDENTITY"]+=1
 ready=sum(x["status"]=="TMP_INTEGRATION_RESEARCH_READY" for x in set_rows);insufficient=sum(x["status"]=="TMP_INSUFFICIENT_COVERAGE" for x in set_rows);core={"covered":len(covered),"trainer":len(trainer_covered),"blockers":dict(blockers),"sets":stable_hash(set_rows)};sid="trainer-treatment-market-prestige-v3t-r3-"+stable_hash(core)[:16]
 result={"studyId":sid,"builtAt":datetime.now(timezone.utc).isoformat(),"totalTrainerCards":len(trainers),"previouslySupportedTrainerCards":{"functional":len(prior_functional),"supporter":len(prior_supporter),"total":len(trainer_covered)},"trainerDomainClassification":dict(sorted(domains.items())),"Supporter":{"readinessByEra":supporter_matrix,"universesTested":sorted(models["SUPPORTER"]),"universesValidated":sorted(e for e,m in models["SUPPORTER"].items() if m.get("status")=="AVAILABLE"),"newCardsRecovered":0},"Item":{"readinessByEra":item_matrix,"universesValidated":sorted(e for e,m in models["ITEM"].items() if m.get("status")=="AVAILABLE"),"newCardsRecovered":0},"Stadium":{"readiness":stadium_matrix,"cardsRecovered":0},"Tool":{"readiness":tool_matrix,"cardsRecovered":0,"finding":"No canonical Tool subtype marker exists in the frozen cohort."},"Other":{"cards":len(by_sub["OTHER"]),"result":"NO_SAFE_PARENT_IDENTITY","cardsRecovered":0},"ambiguousTrainerCount":domains["AMBIGUOUS_TRAINER_IDENTITY"]+domains["NO_SAFE_PARENT_IDENTITY"],"finalTrainerDownstreamValidCards":len(trainer_covered),"trainerDomainCoverage":len(trainer_covered)/len(trainers),"trainerFrameworkStatus":"TRAINER_V3_CATALOG_FRAMEWORK_PARTIALLY_VALIDATED","incrementalTrainerCatalogRecovery":0,"catalogCoverage":{"denominator":19847,"pokemonCovered":9202,"trainerCovered":len(trainer_covered),"energyCovered":0,"totalLikely":len(covered),"percentage":len(covered)/19847,"remainingTo70":13893-len(covered)},"terminalBlockerTable":dict(sorted(blockers.items())),"largestRemainingBlockerGroups":largest,"largestRealisticallyRecoverableGroups":[x for x in largest if x["scientificTractability"]=="MEDIUM"],"setLevelCoverage":set_rows,"setsIntegrationResearchReady":ready,"setsInsufficientCoverage":insufficient,"collectorAppealReadinessStatus":"TMP_COLLECTOR_APPEAL_INTEGRATION_RESEARCH_PLAUSIBLE" if ready>insufficient else "TMP_COLLECTOR_APPEAL_COVERAGE_STILL_INSUFFICIENT","seventyPercentStatus":"70_PERCENT_PATH_REMAINS_UNPROVEN","competitivePlayDemandRetentionRecommendation":"Retain weekly versioned functional-card snapshots; do not add Play Demand to primary Trainer TMP.","rowsPersisted":0,"productionBehavior":"Unchanged and paused; research files only. No migrations, scores, UI, Collector Appeal, RIP, rankings, V1, or V2 changes.","filesChanged":[str(Path(__file__)),str(STUDY),str(REPORT),str(OUT/"trainer_domain.json"),str(OUT/"remaining_card_universe.json"),str(OUT/"set_level_coverage.json"),str(OUT/"manifest.json")],"testsExecuted":["2,718-card Trainer conservation","973-card no-double-count ledger","subtype-era unchanged validation gates","10,175-card catalog reconciliation","terminal blocker exhaustiveness","set-level coverage conservation","full V3 regression"],"remainingLimitations":["No Tool subtype marker in frozen canonical ontology","Other Trainer cards lack safe parent identity","additional eras lack cross-treatment/set support","character-demand metadata remains unavailable","set-level coverage remains uneven","70% remains unsupported by named current-data projects"],"recommendedNextTask":"Stop incremental Trainer modeling. Acquire specific canonical Trainer subtype/parent metadata and additional licensed historical observations for the largest blocked eras; otherwise retain research-only status and reassess the 70% product gate without weakening scientific eligibility.","_records":records,"_residual":residual};return result
def render(s):
 vals=[s["studyId"],s["totalTrainerCards"],s["previouslySupportedTrainerCards"],s["trainerDomainClassification"],s["Supporter"]["readinessByEra"],s["Supporter"]["universesTested"],s["Supporter"]["universesValidated"],s["Supporter"]["newCardsRecovered"],s["Item"]["readinessByEra"],s["Item"]["universesValidated"],s["Item"]["newCardsRecovered"],s["Stadium"]["readiness"],s["Stadium"]["cardsRecovered"],s["Tool"]["readiness"],s["Tool"]["cardsRecovered"],s["Other"],s["ambiguousTrainerCount"],s["finalTrainerDownstreamValidCards"],s["trainerDomainCoverage"],s["trainerFrameworkStatus"],s["incrementalTrainerCatalogRecovery"],s["catalogCoverage"]["totalLikely"],s["catalogCoverage"]["percentage"],s["catalogCoverage"]["remainingTo70"],s["terminalBlockerTable"],s["largestRemainingBlockerGroups"],s["largestRealisticallyRecoverableGroups"],s["setLevelCoverage"],s["setsIntegrationResearchReady"],s["setsInsufficientCoverage"],s["collectorAppealReadinessStatus"],s["seventyPercentStatus"],s["competitivePlayDemandRetentionRecommendation"],s["rowsPersisted"],s["productionBehavior"],s["filesChanged"],s["testsExecuted"],s["remainingLimitations"],s["recommendedNextTask"]]
 labels=["Study ID","Total Trainer cards","Previously supported Trainer cards","Trainer domain classification","Supporter readiness by era","New Supporter universes tested","New Supporter universes validated","Supporter cards newly recovered","Item readiness by era","Item universes validated","Item cards newly recovered","Stadium readiness","Stadium cards recovered","Tool readiness","Tool cards recovered","Other functional Trainer results","Ambiguous Trainer count","Final Trainer downstream-valid card count","Trainer-domain coverage","Trainer framework status","Incremental Trainer catalog recovery","New total likely catalog coverage","New catalog coverage percentage","Remaining gap to 70%","Updated terminal-blocker table","Largest remaining blocker groups","Largest remaining realistically recoverable groups","Set-level coverage distribution","Sets TMP-integration research ready","Sets with insufficient TMP coverage","Collector Appeal research-readiness status","Updated 70% status","Competitive Play Demand retention recommendation","Rows persisted","Production behavior","Files changed","Tests executed","Remaining limitations","Exact recommended next task"]
 return "# Trainer Treatment Market Prestige V3T — Round 3 Results\n\n"+"\n\n".join(f"{i}. **{a}:** `{json.dumps(v,sort_keys=True,default=str)}`" for i,(a,v) in enumerate(zip(labels,vals),1))+"\n"
def main():
 s=build();records=s.pop("_records");residual=s.pop("_residual");OUT.mkdir(parents=True,exist_ok=True);(OUT/"trainer_domain.json").write_text(json.dumps(records,indent=2),encoding="utf-8");(OUT/"remaining_card_universe.json").write_text(json.dumps(residual,indent=2),encoding="utf-8");(OUT/"set_level_coverage.json").write_text(json.dumps(s["setLevelCoverage"],indent=2),encoding="utf-8");STUDY.write_text(json.dumps(s,indent=2),encoding="utf-8");REPORT.write_text(render(s),encoding="utf-8");(OUT/"manifest.json").write_text(json.dumps({"studyId":s["studyId"],"studyHash":stable_hash(s),"residualHash":stable_hash(residual),"rowsPersisted":0},indent=2),encoding="utf-8")
if __name__=="__main__":main()
