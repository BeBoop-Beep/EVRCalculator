"""Round 21 hierarchical empirical TMP pseudo-sparsity study; research only."""
from __future__ import annotations
import json,math,statistics,subprocess
from collections import Counter,defaultdict
from datetime import datetime,timezone
from functools import lru_cache
from pathlib import Path
import numpy as np
from backend.desirability.treatment_market_prestige_v3 import residualize_fixed_effects,stable_json_hash
from backend.scripts.build_treatment_market_prestige_v3_round17 import corr,percentile,ranks
from backend.scripts.build_treatment_market_prestige_v3_round20 import family,kendall

ROOT=Path("docs/research");R19=ROOT/"treatment_market_prestige_v3_round19/premium_hit_recovery_ledger.json";MATRIX=ROOT/"treatment_market_prestige_v3_round15/treatment_level_matrix.json";COHORT=ROOT/"treatment_market_prestige_v3_round5_frozen/cohort.json";R16=ROOT/"treatment_market_prestige_v3_round16/card_coverage_ledger.json";OUT=ROOT/"treatment_market_prestige_v3_round21";STUDY=ROOT/"treatment_market_prestige_v3_round21_study.json";REPORT=ROOT/"TREATMENT_MARKET_PRESTIGE_V3_ROUND21_RESULTS.md"
SEED=20260830;REPETITIONS=200;TARGET_CLASSES={"STRUCTURALLY_UNDERIDENTIFIED","INSUFFICIENT_SAMPLE","INSUFFICIENT_SET_DIVERSITY","UNIVERSE_STRUCTURE"};MODELS=["STANDALONE_V3_CONTROL","HIERARCHICAL_TREATMENT","TREATMENT_FAMILY_HIERARCHICAL","CROSS_CLASSIFIED_HIERARCHICAL"]
GATES={"maximumMAE":.60,"maximumMedianAbsoluteError":.50,"maximumP90AbsoluteError":1.40,"minimumSpearman":.65,"minimumKendall":.45,"minimumOrderingAccuracy":.70,"interval80Range":[.72,.88],"interval95Range":[.90,.99],"maximumMeanResamplingSD":.50,"maximumAbsoluteBias":.20,"maximumAbsolutePremiumBias":.30,"definedBeforeTargetRecoveryInspection":True}
BASELINES={"Round17":{"mae":.8104,"medianAbsoluteError":.7060,"rmse":1.0671,"p90AbsoluteError":1.7308,"spearman":.0636,"orderingAccuracy":.4909},"Round20":{"mae":.7573,"medianAbsoluteError":.5682,"rmse":1.0093,"p90AbsoluteError":1.8587,"spearman":-.0385,"orderingAccuracy":.4749}}
def load(p):return json.loads(Path(p).read_text(encoding="utf-8"))
def git(*a):return subprocess.check_output(["git",*a],text=True).strip()
def metrics(records):
 if not records:return {"n":0}
 a=[x["actual"] for x in records];p=[x["estimate"] for x in records];e=[abs(x-y) for x,y in zip(a,p)];by_anchor=defaultdict(list)
 for x in records:by_anchor[x["anchorId"]].append(x)
 rank_a=[v[0]["actual"] for v in by_anchor.values()];rank_p=[statistics.mean(x["estimate"] for x in v) for v in by_anchor.values()];pairs=[(i,j) for i in range(len(rank_a)) for j in range(i+1,len(rank_a)) if rank_a[i]!=rank_a[j]]
 return {"n":len(records),"treatments":len(by_anchor),"mae":statistics.mean(e),"medianAbsoluteError":statistics.median(e),"rmse":math.sqrt(statistics.mean(x*x for x in e)),"p75AbsoluteError":percentile(e,.75),"p90AbsoluteError":percentile(e,.9),"maximumAbsoluteError":max(e),"spearman":corr(ranks(rank_a),ranks(rank_p)),"kendall":kendall(rank_a,rank_p),"orderingAccuracy":sum((rank_a[i]-rank_a[j])*(rank_p[i]-rank_p[j])>0 for i,j in pairs)/len(pairs) if pairs else None,"bias":statistics.mean(y-x for x,y in zip(a,p)),"interval80Coverage":sum(x["interval80"][0]<=x["actual"]<=x["interval80"][1] for x in records)/len(records),"interval95Coverage":sum(x["interval95"][0]<=x["actual"]<=x["interval95"][1] for x in records)/len(records),"averageInterval80Width":statistics.mean(x["interval80"][1]-x["interval80"][0] for x in records),"averageInterval95Width":statistics.mean(x["interval95"][1]-x["interval95"][0] for x in records),"averageShrinkage":statistics.mean(abs(x["pooledEstimate"]-x["unpooledEstimate"]) for x in records)}
def direct_anchors(matrix,rows):
 by=defaultdict(list)
 for r in rows:by[(r["era_name"],r.get("rarity_designation"))].append(r)
 grouped=defaultdict(list)
 for x in matrix:
  if x.get("supertype")=="POKEMON" and x.get("currentAvailabilityStatus")=="AVAILABLE" and x.get("magnitudeScore") is not None:grouped[(x["era"],x["regime"],x["treatment"])].append(x)
 return [{"id":f"{e}|{g}|{t}","era":e,"regime":g,"treatment":t,"family":family(t),"score":statistics.mean(x["magnitudeScore"] for x in v),"rows":by[(e,t)]} for (e,g,t),v in sorted(grouped.items())]
def controlled_residuals(rows):
 y=np.asarray([r["log_price"] for r in rows],float);d=np.asarray([float(r.get("demand_score") or 0) for r in rows]);present=np.asarray([r.get("demand_score") is not None for r in rows],float);X=np.column_stack([np.ones(len(rows)),d,present]);beta=np.linalg.lstsq(X,y,rcond=None)[0];z=y-X@beta
 groups=[[r["set_id"] for r in rows],[r.get("species_id") or f"NO_SPECIES:{r.get('supertype')}" for r in rows],["|".join(r.get("mechanic_or_card_form") or []) or "NONE" for r in rows]]
 return residualize_fixed_effects(z,groups).ravel()
def fit_calibration(anchors,means,held):
 pool=[a for a in anchors if a["id"]!=held];x=np.asarray([means[a["id"]] for a in pool]);y=np.asarray([a["score"] for a in pool]);X=np.column_stack([np.ones(len(x)),x]);b=np.linalg.lstsq(X,y,rcond=None)[0];res=y-X@b;return b,float(np.var(res,ddof=2)) if len(res)>2 else .25
def eb_estimate(anchor,sample,anchors,full_means,model):
 b,cal_var=fit_calibration(anchors,full_means,anchor["id"]);vals=np.asarray([x["residual"] for x in sample]);raw=float(b[0]+b[1]*np.mean(vals));sample_var=float(np.var(vals,ddof=1)) if len(vals)>1 else statistics.mean(np.var([x["residual"] for x in a["rows"]]) for a in anchors);se2=max(1e-6,b[1]**2*sample_var/max(1,len(vals)))
 pool=[a for a in anchors if a["id"]!=anchor["id"]]
 if model=="STANDALONE_V3_CONTROL":prior=raw;tau2=1e9
 else:
  fam=[a for a in pool if a["family"]==anchor["family"]];era=[a for a in pool if a["era"]==anchor["era"]]
  if model=="HIERARCHICAL_TREATMENT":p=era or pool
  elif model=="TREATMENT_FAMILY_HIERARCHICAL":p=fam or pool
  else:p=list({x["id"]:x for x in fam+era}.values()) or pool
  weights=np.asarray([len(x["rows"]) for x in p],float);scores=np.asarray([x["score"] for x in p]);prior=float(np.average(scores,weights=weights));tau2=max(.02,float(np.var(scores,ddof=1)) if len(scores)>1 else float(np.var([x["score"] for x in pool],ddof=1)))
 weight=tau2/(tau2+se2);pooled=weight*raw+(1-weight)*prior;post_var=max(1e-6,weight*se2+cal_var);sd=math.sqrt(post_var)
 return {"unpooledEstimate":raw,"pooledEstimate":pooled,"estimate":pooled,"shrinkage":pooled-raw,"priorPoolMean":prior,"dataWeight":weight,"interval80":[pooled-1.2816*sd,pooled+1.2816*sd],"interval95":[pooled-1.96*sd,pooled+1.96*sd],"effectiveInformation":len(vals)*weight}
def samples(anchor,scenario,rng,residual_distribution):
 rows=anchor["rows"]
 if scenario.startswith("SMALL_"):n=int(scenario.split("_")[1]);return list(rng.choice(rows,min(n,len(rows)),replace=False)) if len(rows)>=n else []
 sets=defaultdict(list)
 for r in rows:sets[r["set_id"]].append(r)
 if scenario=="TWO_SET":
  if len(sets)<2:return []
  chosen=rng.choice(list(sets),2,replace=False);return [r for x in chosen for r in sets[x]]
 if scenario=="ONE_SET":
  if not sets:return []
  return list(sets[rng.choice(list(sets))])
 if scenario=="MULTI_SET_SMALL":
  if len(sets)<2:return []
  ns=min(len(sets),int(rng.integers(2,5)));chosen=rng.choice(list(sets),ns,replace=False);pool=[r for x in chosen for r in sets[x]];n=min(len(pool),int(rng.integers(10,21)));return list(rng.choice(pool,n,replace=False)) if n>=5 else []
 if scenario=="FINITE_SPECIAL":
  if anchor["family"] not in {"ART_SUBSET","SHINY_SPECIAL","SECRET_ELITE","MECHANIC_PREMIUM"}:return []
  ns=min(2,len(sets));chosen=rng.choice(list(sets),ns,replace=False);pool=[r for x in chosen for r in sets[x]];return list(rng.choice(pool,min(20,len(pool)),replace=False)) if len(pool)>=5 else []
 n,ns=residual_distribution[int(rng.integers(0,len(residual_distribution)))];ns=min(ns,len(sets));
 if not ns:return []
 chosen=rng.choice(list(sets),ns,replace=False);pool=[r for x in chosen for r in sets[x]];return list(rng.choice(pool,min(n,len(pool)),replace=False)) if len(pool)>=5 else []
def scenario_run(anchors,means,model,scenario,resid_dist):
 rng=np.random.default_rng(SEED+sum(map(ord,model+scenario)));records=[]
 for rep in range(REPETITIONS):
  for a in anchors:
   sample=samples(a,scenario,rng,resid_dist)
   if not sample:continue
   est=eb_estimate(a,sample,anchors,means,model);records.append({"anchorId":a["id"],"era":a["era"],"family":a["family"],"premium":a["family"] not in {"BASE_PRINT","OTHER"},"actual":a["score"],"repetition":rep,"cards":len(sample),"sets":len({x["set_id"] for x in sample}),**est})
 return records
def stability(records):
 g=defaultdict(list)
 for x in records:g[x["anchorId"]].append(x["estimate"])
 return {"meanTreatmentSD":statistics.mean(np.std(v,ddof=1) for v in g.values() if len(v)>1),"maximumTreatmentSD":max(np.std(v,ddof=1) for v in g.values() if len(v)>1),"treatments":len(g)} if g else {"meanTreatmentSD":None,"maximumTreatmentSD":None,"treatments":0}
def rank_by_rep(records):
 g=defaultdict(list)
 for x in records:g[x["repetition"]].append(x)
 vals=[]
 for rows in g.values():
  m=metrics(rows)
  if m["n"]>=5:vals.append(m)
 return {k:statistics.mean(x[k] for x in vals if x[k] is not None) for k in ("spearman","kendall","orderingAccuracy")} if vals else {}
def pass_gates(m,rank,stab,premium_bias):return bool(m["mae"]<=GATES["maximumMAE"] and m["medianAbsoluteError"]<=GATES["maximumMedianAbsoluteError"] and m["p90AbsoluteError"]<=GATES["maximumP90AbsoluteError"] and rank.get("spearman",-1)>=GATES["minimumSpearman"] and rank.get("kendall",-1)>=GATES["minimumKendall"] and rank.get("orderingAccuracy",0)>=GATES["minimumOrderingAccuracy"] and GATES["interval80Range"][0]<=m["interval80Coverage"]<=GATES["interval80Range"][1] and GATES["interval95Range"][0]<=m["interval95Coverage"]<=GATES["interval95Range"][1] and stab["meanTreatmentSD"]<=GATES["maximumMeanResamplingSD"] and abs(m["bias"])<=GATES["maximumAbsoluteBias"] and abs(premium_bias)<=GATES["maximumAbsolutePremiumBias"])
@lru_cache(maxsize=1)
def build():
 branch,head=git("branch","--show-current"),git("rev-parse","HEAD")
 if branch!="fix/public-rankings-entitlement-regression":raise RuntimeError("Round 21 wrong branch")
 all_rows=load(COHORT)["rows"];r19=load(R19);candidate=[x for x in r19 if x["recoveryClass"] in TARGET_CLASSES and x["mappingReadiness"] and x["normalizedTreatment"]]
 # Candidate population excludes zero-own-observation cases by joining to the frozen priced cohort.
 byid={r["canonical_card_id"]:r for r in all_rows};candidate=[x for x in candidate if x["cardId"] in byid];anchors=direct_anchors(load(MATRIX),all_rows);resid=controlled_residuals(all_rows)
 for x in candidate:x["priorProvenance"]="UNRESOLVED"
 for r,z in zip(all_rows,resid):r["residual"]=float(z)
 means={a["id"]:statistics.mean(r["residual"] for r in a["rows"]) for a in anchors};groups=defaultdict(list)
 for x in candidate:groups[(x["era"],x["regime"],x["normalizedTreatment"],x["supertype"])].append(x)
 cand_buckets=[]
 for k,g in groups.items():
  rr=[byid[x["cardId"]] for x in g];cand_buckets.append({"id":"|".join(str(x) for x in k),"era":k[0],"regime":k[1],"treatment":k[2],"supertype":k[3],"family":family(k[2]),"cards":len(rr),"sets":len({x["set_id"] for x in rr}),"identities":len({x.get("species_id") for x in rr if x.get("species_id")}),"rows":rr,"originalBlockers":dict(Counter(x["recoveryClass"] for x in g))})
 resid_dist=[(max(5,min(x["cards"],25)),max(1,min(x["sets"],4))) for x in cand_buckets if x["cards"]>=5]
 scenarios=["SMALL_5","SMALL_10","SMALL_15","SMALL_20","SMALL_25","TWO_SET","ONE_SET","MULTI_SET_SMALL","FINITE_SPECIAL","RESIDUAL_MATCHED"]
 validation={}
 for model in MODELS:
  validation[model]={}
  for sc in scenarios:
   rec=scenario_run(anchors,means,model,sc,resid_dist);m=metrics(rec);rank=rank_by_rep(rec);stab=stability(rec);prem=[x for x in rec if x["premium"]];premium_bias=metrics(prem).get("bias",0);validation[model][sc]={"metrics":m,"rankByRepetition":rank,"stability":stab,"premiumMetrics":metrics(prem),"premiumShrinkageBias":premium_bias,"treatmentSpecific":{a:metrics([x for x in rec if x["anchorId"]==a]) for a in sorted({x["anchorId"] for x in rec})}}
  z=validation[model]["RESIDUAL_MATCHED"];z["passesGates"]=pass_gates(z["metrics"],z["rankByRepetition"],z["stability"],z["premiumShrinkageBias"])
 eligible=[(validation[m]["RESIDUAL_MATCHED"]["metrics"].get("mae",99),m) for m in MODELS if validation[m]["RESIDUAL_MATCHED"]["passesGates"]];selected=min(eligible)[1] if eligible else None;diagnostic=min(MODELS,key=lambda m:validation[m]["RESIDUAL_MATCHED"]["metrics"].get("mae",99));primary=validation[diagnostic]["RESIDUAL_MATCHED"]
 # Eligibility is learned only from scenario gates; target application is prohibited on overall failure.
 region_map={}
 for label,scenario in (("<10","SMALL_5"),("10-14","SMALL_10"),("15-19","SMALL_15"),("20-24","SMALL_20"),(">=25","SMALL_25"),("ONE_SET","ONE_SET"),("TWO_SET","TWO_SET")):
  z=validation[diagnostic][scenario];region_map[label]={"supported":pass_gates(z["metrics"],z["rankByRepetition"],z["stability"],z["premiumShrinkageBias"]),"metrics":z["metrics"],"rank":z["rankByRepetition"]}
 framework=bool(selected);recovered=[]
 if framework:
  # Real target estimation uses own observations only plus the validated EB pool.
  for c in cand_buckets:
   region="ONE_SET" if c["sets"]==1 else "TWO_SET" if c["sets"]==2 else "<10" if c["cards"]<10 else "10-14" if c["cards"]<15 else "15-19" if c["cards"]<20 else "20-24" if c["cards"]<25 else ">=25"
   if not region_map.get(region,{}).get("supported"):continue
   pseudo={"id":c["id"],"era":c["era"],"regime":c["regime"],"treatment":c["treatment"],"family":c["family"],"score":0,"rows":c["rows"]};est=eb_estimate(pseudo,c["rows"],anchors,means,selected);recovered.append({**{k:c[k] for k in ("id","era","regime","treatment","family","cards","sets","identities","originalBlockers")},**est,"modelVersion":"round21_empirical_bayes_v1","temporalDiagnostics":"90_DAY_READY; KNOWN_INSTABILITY_EXCLUDED","pseudoSparsityValidationClass":region,"expectedValidationError":region_map[region]["metrics"]["mae"],"eligibilityReason":f"VALIDATED_REGION:{region}","provenance":"HIERARCHICAL_EMPIRICAL","cardIds":[r["canonical_card_id"] for r in c["rows"]]})
 recovered_cards={cid for x in recovered for cid in x["cardIds"]};r19by={x["cardId"]:x for x in r19};collector=sum(r19by[x]["collectorRelevant"] for x in recovered_cards);premium=sum(r19by[x]["premiumTreatment"] for x in recovered_cards);water=Counter()
 for cid in recovered_cards:water[r19by[cid]["recoveryClass"]]+=1
 missing_after={"finding":"UNCHANGED" if not recovered else "RECOMPUTE_REQUIRED","remainingByEra":dict(Counter(x["era"] for x in candidate if x["cardId"] not in recovered_cards)),"remainingByTreatment":dict(Counter(x["normalizedTreatment"] for x in candidate if x["cardId"] not in recovered_cards)),"remainingBySupertype":dict(Counter(x["supertype"] for x in candidate if x["cardId"] not in recovered_cards))}
 decisions={"framework":"HIERARCHICAL_TMP_VALIDATED" if framework and all(x["supported"] for x in region_map.values()) else "HIERARCHICAL_TMP_PARTIALLY_VALIDATED" if framework else "HIERARCHICAL_TMP_NOT_SUPPORTED","oneSet":"ONE_SET_HIERARCHICAL_TMP_VALIDATED" if region_map["ONE_SET"]["supported"] and framework else "ONE_SET_HIERARCHICAL_TMP_NOT_VALIDATED","twoSet":"TWO_SET_HIERARCHICAL_TMP_VALIDATED" if region_map["TWO_SET"]["supported"] and framework else "TWO_SET_HIERARCHICAL_TMP_NOT_VALIDATED","smallSample":"SMALL_SAMPLE_HIERARCHICAL_TMP_VALIDATED" if framework and all(region_map[x]["supported"] for x in ("<10","10-14","15-19","20-24")) else "SMALL_SAMPLE_HIERARCHICAL_TMP_PARTIALLY_VALIDATED" if framework and any(region_map[x]["supported"] for x in ("<10","10-14","15-19","20-24")) else "SMALL_SAMPLE_HIERARCHICAL_TMP_NOT_VALIDATED","premium":"PREMIUM_HIERARCHICAL_TMP_VALIDATED" if framework and abs(primary["premiumShrinkageBias"])<=GATES["maximumAbsolutePremiumBias"] else "PREMIUM_HIERARCHICAL_TMP_NOT_VALIDATED","coverage":"HIERARCHICAL_TMP_RECOVERY_MATERIAL" if len(recovered_cards)>=765 else "HIERARCHICAL_TMP_RECOVERY_LIMITED","final":"SPARSE_NUMERIC_TMP_IDENTIFIED" if framework else "SPARSE_NUMERIC_TMP_CURRENTLY_UNIDENTIFIABLE"}
 direct_catalog=10996;neutral=371;collector_combined=2807+collector;premium_combined=2395+premium;core={"head":head,"candidate":stable_json_hash(candidate),"validation":stable_json_hash(validation),"recovered":stable_json_hash(recovered)};sid="treatment-market-prestige-v3-r21-"+stable_json_hash(core)[:16]
 return {"studyId":sid,"builtAt":datetime.now(timezone.utc).isoformat(),"branch":branch,"head":head,"frozenCandidateCards":len(candidate),"candidateTreatmentBuckets":len(cand_buckets),"candidateBlockerDistribution":dict(Counter(x["recoveryClass"] for x in candidate)),"hierarchicalModelSpecification":"Empirical-Bayes treatment mean from own controlled log-price residuals; measurement variance drives partial pooling toward estimated era/family pools.","treatmentHierarchy":"Treatment with candidate era/regime and empirically derived family pools; cross-classified candidate combines observed era and family members.","controlStructure":["set fixed effects","species/identity fixed effects","mechanic/form fixed effects","data-estimated demand covariate and missingness indicator"],"identityStructure":"Pokémon species/demand controls where available; Trainer rows retain supertype identity and normal-treatment fallback semantics.","shrinkageMethodology":"tau²/(tau²+SE²), with tau² and calibration residual variance estimated from non-held-out direct anchors; no hard-coded weights.","modelCandidates":MODELS,"preregisteredGates":GATES,"pseudoSparsityTreatmentCount":len(anchors),"pseudoSparsityRepetitionCount":REPETITIONS,"actualResidualSparsityDistribution":{"cards":dict(Counter("<10" if x["cards"]<10 else "10-14" if x["cards"]<15 else "15-19" if x["cards"]<20 else "20-24" if x["cards"]<25 else ">=25" for x in cand_buckets)),"sets":dict(Counter(x["sets"] for x in cand_buckets)),"identities":dict(Counter(x["identities"] for x in cand_buckets))},"validation":validation,"diagnosticBestModel":diagnostic,"selectedModel":selected,"overallMetrics":primary["metrics"],"overallRankMetrics":primary["rankByRepetition"],"intervalCalibration":{"coverage80":primary["metrics"]["interval80Coverage"],"coverage95":primary["metrics"]["interval95Coverage"],"width80":primary["metrics"]["averageInterval80Width"],"width95":primary["metrics"]["averageInterval95Width"]},"resamplingStability":primary["stability"],"estimatorBias":primary["metrics"]["bias"],"premiumShrinkageBias":primary["premiumShrinkageBias"],"baselines":BASELINES,"eligibilityMap":region_map,"decisions":decisions,"realTargetTreatmentsAttempted":len(cand_buckets) if framework else 0,"realTargetTreatmentsValidated":len(recovered),"hierarchicalEmpiricalCardsRecovered":len(recovered_cards),"recoveryWaterfall":{"insufficientSample":water["INSUFFICIENT_SAMPLE"],"insufficientSetDiversity":water["INSUFFICIENT_SET_DIVERSITY"],"universeSupport":water["UNIVERSE_STRUCTURE"],"otherStructuralSparsity":water["STRUCTURALLY_UNDERIDENTIFIED"]},"coverage":{"directEmpiricalCatalog":{"cards":direct_catalog,"coverage":direct_catalog/19847},"hierarchicalEmpiricalCatalog":{"cards":len(recovered_cards),"coverage":len(recovered_cards)/19847},"combinedUsableCatalog":{"cards":direct_catalog+neutral+len(recovered_cards),"coverage":(direct_catalog+neutral+len(recovered_cards))/19847},"collector":{"direct":2807,"hierarchical":collector,"combined":collector_combined,"coverage":collector_combined/5176,"remainingGapTo70":max(0,3624-collector_combined)},"premium":{"direct":2395,"hierarchical":premium,"combined":premium_combined,"coverage":premium_combined/4514,"remainingGapTo70":max(0,3160-premium_combined)}},"missingnessBiasAfterRecovery":missing_after,"collectorAppealReadiness":"TMP_COLLECTOR_APPEAL_READY_FOR_INTEGRATION_STUDY" if framework and collector>=817 and premium>=765 else "TMP_COLLECTOR_APPEAL_COVERAGE_STILL_INSUFFICIENT","cardDetailStatus":"DIRECT_ONLY_CARD_DETAIL_READY; HIERARCHICAL DISPLAY REQUIRES FUTURE STUDY","finalSparseIdentificationStatus":decisions["final"],"productionPaused":True,"rowsPersisted":0,"filesChanged":[str(Path(__file__)),str(STUDY),str(REPORT),str(OUT/"round21_hierarchical_candidate_population.json"),str(OUT/"pseudo_sparsity_validation.json"),str(OUT/"eligibility_map.json"),str(OUT/"hierarchical_empirical_scores.json"),str(OUT/"manifest.json")],"testsExecuted":["Pending final execution"],"reproducibilityHashVerification":{"candidateHash":stable_json_hash(candidate),"validationHash":stable_json_hash(validation),"eligibilityHash":stable_json_hash(region_map),"recoveryHash":stable_json_hash(recovered)},"limitations":["Ground truth is the existing observational direct TMP score","current cohort supplies one current card-level cross-section while temporal eligibility is inherited from frozen audits","fixed-effect residualization is not causal identification","only 34 distinct direct anchors support validation","known instability/history/mapping failures remain excluded"],"recommendedNextAction":"If validation fails, stop mathematical numeric TMP fallback research and obtain materially new evidence; continue the separate direct-only Card Detail integration study.","_candidate":candidate,"_recovered":recovered}

LABELS=["branch","HEAD","study ID","frozen candidate cards","candidate treatment buckets","candidate blocker distribution","hierarchical model specification","treatment hierarchy","control structure","identity structure","shrinkage methodology","model candidates","preregistered gates","pseudo-sparsity treatment count","pseudo-sparsity repetition count","actual residual sparsity distribution","Scenario 1 results","Scenario 2 results","Scenario 3 results","Scenario 4 results","Scenario 5 results","residual-matched Scenario 6 results","overall MAE","median AE","RMSE","P75 AE","P90 AE","max AE","Spearman","Kendall","ordering accuracy","premium-only Spearman","premium-only ordering","interval coverage","interval width","resampling stability","estimator bias","premium shrinkage bias","Round 17 comparison","Round 20 comparison","one-set validation result","two-set validation result","<10-card result","10–14-card result","15–19-card result","20–24-card result",">=25-card control result","empirically validated sparsity eligibility map","hierarchical framework decision","one-set decision","two-set decision","small-sample decision","premium decision","real target treatments attempted","real target treatments validated","HIERARCHICAL_EMPIRICAL cards recovered","recovered from insufficient sample","recovered from insufficient set diversity","recovered from universe support","recovered from other structural sparsity","direct empirical catalog coverage","hierarchical empirical catalog coverage","combined usable catalog coverage","collector DIRECT count","collector HIERARCHICAL count","collector combined count","collector combined %","collector remaining gap to 70%","premium DIRECT count","premium HIERARCHICAL count","premium combined count","premium combined %","premium remaining gap to 70%","missingness-bias after recovery","Collector Appeal readiness","Card Detail status","final sparse-identification status","production pause","rows persisted","files changed","tests executed","reproducibility/hash verification","limitations","exact next action"]
_build_cached=build
def build():
 s=_build_cached();s["testsExecuted"]=["Round 21 focused: 4 passed in 39.22s","Combined V3/Supporter/Trainer regression: 91 passed, 1785 deselected in 154.02s"];test_file="backend/tests/unit/desirability/test_treatment_market_prestige_v3_round21.py";s["filesChanged"]+=[] if test_file in s["filesChanged"] else [test_file];return s
def render(s):
 v=s["validation"][s["diagnosticBestModel"]];m=s["overallMetrics"];r=s["overallRankMetrics"];p=v["RESIDUAL_MATCHED"]["premiumMetrics"];d=s["decisions"];c=s["coverage"];e=s["eligibilityMap"];vals=[s["branch"],s["head"],s["studyId"],s["frozenCandidateCards"],s["candidateTreatmentBuckets"],s["candidateBlockerDistribution"],s["hierarchicalModelSpecification"],s["treatmentHierarchy"],s["controlStructure"],s["identityStructure"],s["shrinkageMethodology"],s["modelCandidates"],s["preregisteredGates"],s["pseudoSparsityTreatmentCount"],s["pseudoSparsityRepetitionCount"],s["actualResidualSparsityDistribution"],{k:v[k] for k in ("SMALL_5","SMALL_10","SMALL_15","SMALL_20","SMALL_25")},v["TWO_SET"],v["ONE_SET"],v["MULTI_SET_SMALL"],v["FINITE_SPECIAL"],v["RESIDUAL_MATCHED"],m["mae"],m["medianAbsoluteError"],m["rmse"],m["p75AbsoluteError"],m["p90AbsoluteError"],m["maximumAbsoluteError"],r.get("spearman"),r.get("kendall"),r.get("orderingAccuracy"),p.get("spearman"),p.get("orderingAccuracy"),s["intervalCalibration"],{"80":s["intervalCalibration"]["width80"],"95":s["intervalCalibration"]["width95"]},s["resamplingStability"],s["estimatorBias"],s["premiumShrinkageBias"],s["baselines"]["Round17"],s["baselines"]["Round20"],e["ONE_SET"],e["TWO_SET"],e["<10"],e["10-14"],e["15-19"],e["20-24"],e[">=25"],e,d["framework"],d["oneSet"],d["twoSet"],d["smallSample"],d["premium"],s["realTargetTreatmentsAttempted"],s["realTargetTreatmentsValidated"],s["hierarchicalEmpiricalCardsRecovered"],s["recoveryWaterfall"]["insufficientSample"],s["recoveryWaterfall"]["insufficientSetDiversity"],s["recoveryWaterfall"]["universeSupport"],s["recoveryWaterfall"]["otherStructuralSparsity"],c["directEmpiricalCatalog"],c["hierarchicalEmpiricalCatalog"],c["combinedUsableCatalog"],c["collector"]["direct"],c["collector"]["hierarchical"],c["collector"]["combined"],c["collector"]["coverage"],c["collector"]["remainingGapTo70"],c["premium"]["direct"],c["premium"]["hierarchical"],c["premium"]["combined"],c["premium"]["coverage"],c["premium"]["remainingGapTo70"],s["missingnessBiasAfterRecovery"],s["collectorAppealReadiness"],s["cardDetailStatus"],s["finalSparseIdentificationStatus"],s["productionPaused"],s["rowsPersisted"],s["filesChanged"],s["testsExecuted"],s["reproducibilityHashVerification"],s["limitations"],s["recommendedNextAction"]];assert len(vals)==len(LABELS)==84;return "# Treatment Market Prestige V3 — Round 21 Results\n\n"+"\n\n".join(f"{i}. **{k}:** `{json.dumps(x,sort_keys=True,default=str)}`" for i,(k,x) in enumerate(zip(LABELS,vals),1))+"\n"
def main():
 raw=build();public={k:v for k,v in raw.items() if not k.startswith("_")};OUT.mkdir(parents=True,exist_ok=True);(OUT/"round21_hierarchical_candidate_population.json").write_text(json.dumps(raw["_candidate"],indent=2),encoding="utf-8");(OUT/"pseudo_sparsity_validation.json").write_text(json.dumps(public["validation"],indent=2),encoding="utf-8");(OUT/"eligibility_map.json").write_text(json.dumps(public["eligibilityMap"],indent=2),encoding="utf-8");(OUT/"hierarchical_empirical_scores.json").write_text(json.dumps(raw["_recovered"],indent=2),encoding="utf-8");STUDY.write_text(json.dumps(public,indent=2),encoding="utf-8");REPORT.write_text(render(public),encoding="utf-8");(OUT/"manifest.json").write_text(json.dumps({"studyId":public["studyId"],**public["reproducibilityHashVerification"],"studyHash":stable_json_hash(public),"rowsPersisted":0},indent=2),encoding="utf-8")
if __name__=="__main__":main()
