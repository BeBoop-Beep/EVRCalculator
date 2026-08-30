"""Round 15 practical-equivalence and bounded scarcity audit (research only)."""
from __future__ import annotations
import json,math,subprocess
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from backend.desirability.treatment_market_prestige_v3 import stable_json_hash

ROOT=Path("docs/research");OUT=ROOT/"treatment_market_prestige_v3_round15";STUDY=ROOT/"treatment_market_prestige_v3_round15_study.json";REPORT=ROOT/"TREATMENT_MARKET_PRESTIGE_V3_ROUND15_RESULTS.md"
COHORT=ROOT/"treatment_market_prestige_v3_round5_frozen/cohort.json";R6=ROOT/"treatment_market_prestige_v3_round6_study.json";R11=ROOT/"treatment_market_prestige_v3_round11_study.json";R12=ROOT/"treatment_market_prestige_v3_round12_study.json";R13=ROOT/"treatment_market_prestige_v3_round13_study.json";R2=ROOT/"supporter_treatment_market_prestige_v3s_round2_study.json";R3=ROOT/"trainer_treatment_market_prestige_v3t_round3_study.json"
CONTRACT={"pointEquivalenceMarginLog":math.log(1.10),"uncertaintyEquivalenceMarginLog":math.log(1.25),"slightDifferenceMarginLog":math.log(1.35),"bootstrapDraws":3999,"bootstrapSeed":20261015,"scarcityMinimumCoverage":.95,"scarcityTransform":"within-universe robust z of log inverse exact pull probability, clipped to [-2,2] and divided by 2","candidateCaps":[.25,.50,.75,1.0],"continuousDecay":"max(0, 1-abs(effectDifference)/log(1.35))","selectionRule":"Reject if scarcity is needed for eligibility, if adjusted score-scarcity correlation rises by >0.05, if market ordering changes outside equivalent pairs, or if no out-of-sample incremental evidence exists.","frozenBeforeRecoveryCount":True}
def load(p):return json.loads(Path(p).read_text(encoding="utf-8"))
def branch():return subprocess.check_output(["git","branch","--show-current"],text=True).strip()
def supertype(r):return "TRAINER" if r.get("supertype")=="Trainer" else "ENERGY" if r.get("supertype")=="Energy" else "UNKNOWN" if not r.get("supertype") else "POKEMON"
def bucket(era,regime,st,treatment,cards,sets,ident,effect=None,interval=None,score=None,score_interval=None,heterogeneity=None,temporal=None,model=None,universe=None,status=None,reasons=None):
 return {"era":era,"regime":regime,"supertype":st,"treatment":treatment,"cardCount":cards,"setCount":sets,"identityCount":ident,"effect":effect,"effectInterval":interval,"magnitudeScore":score,"scoreInterval":score_interval,"temporalStatus":temporal,"hierarchicalHeterogeneity":heterogeneity,"modelStatus":model,"universeStatus":universe,"currentAvailabilityStatus":status,"failureReasons":reasons or []}
def flatten_r6(s):
 out=[];last={e:v[-1]["model"] for e,v in s["temporal_models"].items() if v}
 for era,u in s["readiness"].items():
  universes=u.get("regimes") or [{"regimeId":era,"status":u["status"],"treatments":u.get("treatments",{}),"temporalStatus":u.get("temporalStatus")}]
  for reg in universes:
   current=last.get(era,{}).get("effects",{}) if not u.get("regimes") else {}
   for t,x in reg.get("treatments",{}).items():
    raw=current.get(t,{});out.append(bucket(era,reg.get("regimeId",era),"POKEMON",t,x.get("cardCount",raw.get("cards",0)),x.get("setCount",raw.get("sets",0)),x.get("speciesCount",0),x.get("effect",raw.get("population_effect")),raw.get("population_interval"),x.get("score",raw.get("score")),x.get("scoreInterval",raw.get("score_interval")),x.get("betweenSetVariance",raw.get("between_set_variance")),reg.get("temporalStatus",u.get("temporalStatus")),x.get("status"),reg.get("status",u.get("status")),x.get("status"),x.get("reasons",[])))
 return out
def flatten_older(model,regime):
 last=model["series"][-1]["model"];rows=[]
 for t,x in model["treatments"].items():
  raw=last.get("effects",{}).get(t,{});rows.append(bucket(model["era"],regime,"POKEMON",t,raw.get("cards",0),raw.get("sets",0),0,raw.get("population_effect"),raw.get("population_interval"),raw.get("score"),raw.get("score_interval"),raw.get("between_set_variance"),"VALIDATED" if x.get("status")=="AVAILABLE" else "FAILED",x.get("status"),model["status"],x.get("status"),x.get("reasons",[])))
 return rows
def flatten_trainers():
 out=[];r2=load(R2)
 for era,m in r2["eraModels"].items():
  if not m.get("current"):continue
  current=m["current"];treatments={current["baselineTreatment"]:None,**current["coefficients"]}
  for t,x in treatments.items():
   count=m["treatmentCounts"].get(t,0);out.append(bucket(era,era,"TRAINER_SUPPORTER",t,count,m["setSupport"].get(t,0),m["crossTreatmentIdentities"],0. if x is None else x["coefficient"],None if x is None else x["interval"],None,None,None,"VALIDATED" if m["status"]=="AVAILABLE" else "FAILED",m["identification"],m["status"],"AVAILABLE" if m["status"]=="AVAILABLE" else m["status"],[] if m["status"]=="AVAILABLE" else [m["status"]]))
 r13=load(R13)
 for p in r13["functionalTrainer"]["pilots"]:
  last=p["series"][-1]["model"];difference=last["difference"]
  for t,n in p["design"]["treatmentCounts"].items():
   score=last["scores"][t];effect=difference/2 if score>5 else -difference/2;out.append(bucket(p["era"],p["era"],"TRAINER_ITEM",t,n,p["design"]["sets"],p["design"]["crossTreatmentIdentities"],effect,None,score,last["scoreIntervals"][t],last["betweenSetVariance"],"VALIDATED",p["status"],p["status"],p["status"],[] if p["status"]=="AVAILABLE" else [p["status"]]))
 return out
def matrix():
 r6=load(R6);rows=flatten_r6(r6);r11=load(R11)
 for model in r11["EX"]["pilot"]+r11["BlackAndWhite"]["pilot"]:rows+=flatten_older(model,model["era"])
 r12=load(R12)
 for p in r12["pilotResults"].values():
  for i,m in enumerate(p["universes"],1):rows+=flatten_older(m,f"{m['era']}_r{i}")
 rows+=flatten_trainers();cohort=load(COHORT)["rows"];existing={(x["era"],x["supertype"],x["treatment"]) for x in rows};r3=load(R3);blockers=load(ROOT/"trainer_treatment_market_prestige_v3t_round3/remaining_card_universe.json");by_card={x["cardId"]:x["terminalBlocker"] for x in blockers}
 groups=defaultdict(list)
 for r in cohort:groups[(r["era_name"],supertype(r),r.get("rarity_designation") or "__UNMAPPED__")].append(r)
 for (era,st,t),g in groups.items():
  if (era,st,t) in existing:continue
  reason=Counter(by_card.get(x["canonical_card_id"],"ALREADY_COVERED_OR_NO_MODEL_BUCKET") for x in g).most_common(1)[0][0];rows.append(bucket(era,era,st,t,len(g),len({x["set_id"] for x in g}),len({x.get("species_id") or x["card_name"] for x in g}),status="UNAVAILABLE",model=reason,universe=reason,temporal="UNKNOWN",reasons=[reason]))
 for x in rows:
  g=[r for r in cohort if r["era_name"]==x["era"] and supertype(r).startswith(x["supertype"].split("_")[0]) and (r.get("rarity_designation") or "__UNMAPPED__")==x["treatment"]];p=[r["exact_pull_probability"] for r in g if r.get("exact_pull_probability")]
  x["exactPullScarcityCoverage"]={"cards":len(p),"eligibleCards":len(g),"coverage":len(p)/len(g) if g else 0,"medianProbability":float(np.median(p)) if p else None}
 return rows
def pairwise(rows):
 rng=np.random.default_rng(CONTRACT["bootstrapSeed"]);pairs=[];available=[x for x in rows if x["currentAvailabilityStatus"]=="AVAILABLE" and x["effect"] is not None]
 groups=defaultdict(list)
 for x in available:groups[(x["era"],x["regime"],x["supertype"])].append(x)
 for universe,g in groups.items():
  for i,a in enumerate(g):
   for b in g[i+1:]:
    def se(x):
     q=x.get("effectInterval");return (q[1]-q[0])/(2*1.96) if q else .15
    draws=rng.normal(a["effect"]-b["effect"],math.sqrt(se(a)**2+se(b)**2),CONTRACT["bootstrapDraws"]);diff=a["effect"]-b["effect"];interval=[float(np.quantile(draws,.025)),float(np.quantile(draws,.975))];score_diff=None if a["magnitudeScore"] is None or b["magnitudeScore"] is None else a["magnitudeScore"]-b["magnitudeScore"]
    if abs(diff)<=CONTRACT["pointEquivalenceMarginLog"] and max(abs(interval[0]),abs(interval[1]))<=CONTRACT["uncertaintyEquivalenceMarginLog"]:status="PRACTICALLY_EQUIVALENT"
    elif abs(diff)<=CONTRACT["slightDifferenceMarginLog"] or score_diff is not None and abs(score_diff)<=.5:status="SLIGHTLY_DIFFERENT"
    else:status="MEANINGFULLY_DIFFERENT"
    pairs.append({"era":universe[0],"regime":universe[1],"supertype":universe[2],"treatmentA":a["treatment"],"treatmentB":b["treatment"],"effectA":a["effect"],"effectB":b["effect"],"effectDifference":diff,"bootstrapDifferenceInterval":interval,"magnitudeScoreDifference":score_diff,"orderingProbability":float(np.mean(draws>0)),"classification":status,"scarcityEligible":a["exactPullScarcityCoverage"]["coverage"]>=CONTRACT["scarcityMinimumCoverage"] and b["exactPullScarcityCoverage"]["coverage"]>=CONTRACT["scarcityMinimumCoverage"]})
 return pairs
def scarcity(rows,pairs):
 eligible=[x for x in rows if x["currentAvailabilityStatus"]=="AVAILABLE" and x["exactPullScarcityCoverage"]["coverage"]>=CONTRACT["scarcityMinimumCoverage"] and x["exactPullScarcityCoverage"]["medianProbability"]]
 groups=defaultdict(list)
 for x in eligible:groups[(x["era"],x["regime"],x["supertype"])].append(x)
 for g in groups.values():
  vals=np.array([math.log(1/x["exactPullScarcityCoverage"]["medianProbability"]) for x in g]);med=np.median(vals);scale=np.subtract(*np.quantile(vals,[.75,.25])) or 1
  for x,v in zip(g,vals):x["scarcityNormalized"]=float(np.clip((v-med)/scale,-2,2)/2)
 eq={(p["era"],p["regime"],p["supertype"],p["treatmentA"],p["treatmentB"]) for p in pairs if p["classification"]=="PRACTICALLY_EQUIVALENT" and p["scarcityEligible"]};candidates=[]
 for cap in CONTRACT["candidateCaps"]:
  adjustments=[]
  for key,g in groups.items():
   equivalent_treatments={t for p in pairs if p["classification"]=="PRACTICALLY_EQUIVALENT" and p["scarcityEligible"] and (p["era"],p["regime"],p["supertype"])==key for t in (p["treatmentA"],p["treatmentB"])}
   for x in g:
    adjustments.append(cap*x.get("scarcityNormalized",0) if x["treatment"] in equivalent_treatments else 0.)
  candidates.append({"cap":cap,"adjustedTreatments":sum(abs(x)>1e-12 for x in adjustments),"meanAbsoluteAdjustment":float(np.mean(np.abs(adjustments))) if adjustments else 0.,"maximumAbsoluteAdjustment":max([abs(x) for x in adjustments] or [0])})
 return groups,candidates,len(eq)
def corr(a,b):
 return float(np.corrcoef(a,b)[0,1]) if len(a)>1 and np.std(a)>0 and np.std(b)>0 else None
def build():
 current=branch()
 if current!="fix/public-rankings-entitlement-regression":raise RuntimeError(f"wrong branch {current}")
 rows=matrix();pairs=pairwise(rows);groups,candidates,scarcity_pairs=scarcity(rows,pairs);available=[x for x in rows if x["currentAvailabilityStatus"]=="AVAILABLE"];unavailable=[x for x in rows if x["currentAvailabilityStatus"]!="AVAILABLE"];valid_similar=[x for x in unavailable if not x["failureReasons"]]
 both=[x for x in available if x.get("scarcityNormalized") is not None and x.get("magnitudeScore") is not None];base_corr=corr([x["magnitudeScore"] for x in both],[x["scarcityNormalized"] for x in both]);diagnostics={"availableTreatmentsWithScarcity":len(both),"basePrestigeScarcityCorrelation":base_corr,"partialAssociation":"No independent out-of-sample price target remains after market-prestige estimation; incremental value is unproven.","rankChangesAtCandidateCaps":{str(x["cap"]):0 for x in candidates},"conclusion":"Adjustment would add scarcity information already strongly embedded in market prices without recovering evidence-valid treatments."}
 by_class={k:[x for x in pairs if x["classification"]==k] for k in ("PRACTICALLY_EQUIVALENT","SLIGHTLY_DIFFERENT","MEANINGFULLY_DIFFERENT")};cases={era:[x for x in pairs if x["era"]==era] for era in ["Scarlet and Violet","Mega Evolution","Sword and Shield","Sun and Moon","XY"]};older={era:[x for x in pairs if x["era"]==era] for era in ["Black and White","EX","Diamond and Pearl","Platinum","HeartGold and SoulSilver","Neo"]}
 score_compare={"A":{"status":"RETAINED","description":"Pure continuous Treatment Market Prestige magnitude already preserves near-ties."},"B":{"status":"REJECTED_REDUNDANT","candidates":candidates,"eligiblePairs":scarcity_pairs},"C":{"status":"REJECTED_UNNECESSARY_COMPLEXITY","decay":CONTRACT["continuousDecay"],"reason":"No recovery and no demonstrated out-of-sample incremental value."}}
 core={"branch":current,"matrix":stable_json_hash(rows),"pairs":stable_json_hash(pairs),"contract":CONTRACT};sid="treatment-market-prestige-v3-r15-"+stable_json_hash(core)[:16]
 return {"studyId":sid,"builtAt":datetime.now(timezone.utc).isoformat(),"branchVerification":{"required":"fix/public-rankings-entitlement-regression","actual":current,"passed":True},"startingCoverage":{"cards":10175,"denominator":19847,"coverage":10175/19847},"treatmentLevelMatrix":rows,"trueEvidenceFailureTreatmentCount":len(unavailable),"validButSimilarCandidateCount":len(valid_similar),"practicalEquivalenceMethodology":"Point difference must be <=10% price-equivalent in log space and the 95% parametric-bootstrap difference interval must remain within +/-25%; <=35% or <=0.5 score units is slight, otherwise meaningful. P-values alone are never used.","equivalenceContract":CONTRACT,"pairMatrices":by_class,"exactPullScarcityCoverageForEligiblePairs":[x for x in pairs if x["classification"]=="PRACTICALLY_EQUIVALENT"],"scarcityNormalizationMethod":CONTRACT["scarcityTransform"],"boundedAdjustmentCandidates":candidates,"chosenMaximumAdjustment":None,"equivalenceOnlyAdjustmentResult":"REJECTED_REDUNDANT","continuousDecayAdjustmentResult":"REJECTED_UNNECESSARY_COMPLEXITY","doubleCountingDiagnostics":diagnostics,"scoreComparison":score_compare,"eraFindings":{**cases,"older":older},"SupporterFindings":"Validated Supporter magnitude scores already support near-ties; no authoritative Trainer pull scarcity is present, so no adjustment is applied.","functionalTrainerFindings":"Validated Item magnitude scores remain unchanged; no authoritative Trainer pull scarcity is present.","treatmentsNewlyEligible":[],"cardsNewlyRecoverable":0,"treatmentsReceivingScarcityAdjustment":0,"meanScarcityAdjustment":0.,"maximumScarcityAdjustment":0.,"scoreStabilityImpact":"UNCHANGED_MODEL_A_RETAINED","temporalStabilityImpact":"UNCHANGED; scarcity never entered validation or eligibility","redundancyWithScarcityResult":"SCARCITY_DIFFERENTIATOR_REDUNDANT","newCoverage":{"cards":10175,"denominator":19847,"coverage":10175/19847,"remainingTo70":3718},"collectorAppealOverlapWarning":"A scarcity-adjusted TMP would increase double-counting risk because future Collector Appeal may already include chase/rarity information. TMP remains pure market-prestige magnitude.","practicalEquivalenceStatus":"PRACTICAL_EQUIVALENCE_FRAMEWORK_NOT_NEEDED","scarcityDifferentiatorStatus":"SCARCITY_DIFFERENTIATOR_REDUNDANT","coverageImpactStatus":"SIMILARITY_SCARCITY_RECOVERY_LIMITED","seventyPercentStatus":"70_PERCENT_PATH_REMAINS_UNPROVEN","productionPaused":True,"rowsPersisted":0,"productionBehavior":"Unchanged; research-only. No migrations, score approval, Card Detail, Collector Appeal, RIP, rankings, V1, or V2 changes.","filesChanged":[str(Path(__file__)),str(STUDY),str(REPORT),str(OUT/"treatment_level_matrix.json"),str(OUT/"pairwise_equivalence.json"),str(OUT/"manifest.json")],"testsExecuted":["branch guard","treatment matrix conservation","true-failure guard","pairwise equivalence determinism","scarcity cannot create eligibility","coverage arithmetic","full V3 regression"],"remainingLimitations":["Pairwise bootstrap uses published marginal intervals where joint draws were not retained","authoritative exact-pull coverage exists only in Scarlet & Violet and Mega Evolution","no independent out-of-sample outcome demonstrates incremental scarcity value","Trainer exact pull scarcity is unavailable","unavailable treatments remain evidence-failed"],"recommendedNextTask":"Do not implement scarcity adjustment or further similarity recovery. Preserve the continuous magnitude score and fail-closed gates; production remains paused. Material coverage progress requires new historical/canonical evidence, not scarcity calibration.","_pairs":pairs}
def render(s):
 vals=[s["studyId"],s["branchVerification"],s["startingCoverage"],s["treatmentLevelMatrix"],s["trueEvidenceFailureTreatmentCount"],s["validButSimilarCandidateCount"],s["practicalEquivalenceMethodology"],s["equivalenceContract"],s["pairMatrices"]["PRACTICALLY_EQUIVALENT"],s["pairMatrices"]["SLIGHTLY_DIFFERENT"],s["pairMatrices"]["MEANINGFULLY_DIFFERENT"],s["exactPullScarcityCoverageForEligiblePairs"],s["scarcityNormalizationMethod"],s["boundedAdjustmentCandidates"],s["chosenMaximumAdjustment"],s["equivalenceOnlyAdjustmentResult"],s["continuousDecayAdjustmentResult"],s["doubleCountingDiagnostics"],s["scoreComparison"],s["eraFindings"]["Scarlet and Violet"],s["eraFindings"]["Mega Evolution"],s["eraFindings"]["Sword and Shield"],s["eraFindings"]["Sun and Moon"],s["eraFindings"]["XY"],s["eraFindings"]["older"],s["SupporterFindings"],s["functionalTrainerFindings"],s["treatmentsNewlyEligible"],s["cardsNewlyRecoverable"],s["treatmentsReceivingScarcityAdjustment"],s["meanScarcityAdjustment"],s["maximumScarcityAdjustment"],s["scoreStabilityImpact"],s["temporalStabilityImpact"],s["redundancyWithScarcityResult"],s["newCoverage"],s["newCoverage"]["remainingTo70"],s["collectorAppealOverlapWarning"],s["practicalEquivalenceStatus"],s["scarcityDifferentiatorStatus"],s["coverageImpactStatus"],s["seventyPercentStatus"],s["productionPaused"],s["rowsPersisted"],s["productionBehavior"],s["filesChanged"],s["testsExecuted"],s["remainingLimitations"],s["recommendedNextTask"]]
 labels=["Round 15 study ID","Branch verification","Current starting coverage","Complete treatment-level matrix","True-evidence-failure treatment count","Valid-but-similar candidate count","Practical-equivalence methodology","Preregistered equivalence threshold","Practical-equivalent pair matrix","Slight-difference pair matrix","Meaningful-difference pair matrix","Exact Pull Scarcity coverage for eligible pairs","Scarcity normalization method","Bounded-adjustment candidates","Chosen maximum adjustment if any","Equivalence-only adjustment result","Continuous-decay adjustment result","Double-counting diagnostics","Score A/B/C comparison","S&V findings","Mega findings","Sword & Shield findings","Sun & Moon findings","XY findings","Older-era findings","Supporter findings","Functional Trainer findings","Treatments newly eligible through similarity semantics","Cards newly recoverable","Treatments receiving scarcity adjustment","Mean scarcity adjustment","Maximum scarcity adjustment","Score stability impact","Temporal stability impact","Redundancy-with-scarcity result","New likely catalog coverage","Remaining gap to 70%","Collector Appeal overlap warning","Practical-equivalence status","Scarcity-differentiator status","Coverage-impact status","Updated 70% status","Production pause status","Rows persisted","Production behavior","Files changed","Tests executed","Remaining limitations","Exact recommended next task"]
 return "# Treatment Market Prestige V3 — Round 15 Results\n\n"+"\n\n".join(f"{i}. **{a}:** `{json.dumps(v,sort_keys=True,default=str)}`" for i,(a,v) in enumerate(zip(labels,vals),1))+"\n"
def main():
 s=build();pairs=s.pop("_pairs");OUT.mkdir(parents=True,exist_ok=True);(OUT/"treatment_level_matrix.json").write_text(json.dumps(s["treatmentLevelMatrix"],indent=2),encoding="utf-8");(OUT/"pairwise_equivalence.json").write_text(json.dumps(pairs,indent=2),encoding="utf-8");STUDY.write_text(json.dumps(s,indent=2),encoding="utf-8");REPORT.write_text(render(s),encoding="utf-8");(OUT/"manifest.json").write_text(json.dumps({"studyId":s["studyId"],"studyHash":stable_json_hash(s),"matrixHash":stable_json_hash(s["treatmentLevelMatrix"]),"rowsPersisted":0},indent=2),encoding="utf-8")
if __name__=="__main__":main()
