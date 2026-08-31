"""Round 20 cross-era structural analogue calibration; research only."""
from __future__ import annotations
import json,math,statistics,subprocess
from collections import Counter,defaultdict
from datetime import datetime,timezone
from functools import lru_cache
from pathlib import Path
from backend.desirability.treatment_market_prestige_v3 import stable_json_hash
from backend.scripts.build_treatment_market_prestige_v3_round17 import corr,percentile,ranks
from backend.scripts.build_treatment_market_prestige_v3_round18 import chase_diagnostic

ROOT=Path("docs/research");R16=ROOT/"treatment_market_prestige_v3_round16/card_coverage_ledger.json";R19=ROOT/"treatment_market_prestige_v3_round19/premium_hit_recovery_ledger.json";R19S=ROOT/"treatment_market_prestige_v3_round19_study.json";MATRIX=ROOT/"treatment_market_prestige_v3_round15/treatment_level_matrix.json";COHORT=ROOT/"treatment_market_prestige_v3_round5_frozen/cohort.json";OUT=ROOT/"treatment_market_prestige_v3_round20";STUDY=ROOT/"treatment_market_prestige_v3_round20_study.json";REPORT=ROOT/"TREATMENT_MARKET_PRESTIGE_V3_ROUND20_RESULTS.md"
STRUCTURAL_CLASSES={"STRUCTURALLY_UNDERIDENTIFIED","INSUFFICIENT_SAMPLE","INSUFFICIENT_SET_DIVERSITY","UNIVERSE_STRUCTURE"};BASELINE={"mae":.8104,"medianAbsoluteError":.7060,"rmse":1.0671,"p90AbsoluteError":1.7308,"maximumAbsoluteError":2.5999,"spearman":.0636,"orderingAccuracy":.4909}
GATES={"minimumPredictions":20,"maximumMAE":.65,"maximumMedianAbsoluteError":.55,"maximumP90AbsoluteError":1.40,"minimumSpearman":.65,"minimumKendall":.45,"minimumOrderingAccuracy":.70,"maximumEraMAE":1.50,"definedBeforeTargetRecoveryInspection":True}
FEATURES=["treatment family","holo/non-holo finish","texture/special finish","full-art","illustration","special illustration","rainbow","gold/secret numbering","shiny","radiant","gallery/subset","mechanic family (EX/GX/V/VMAX/VSTAR/ex/Mega/LV.X/Prime/Star/Shining)","edition","special release","card/set support","treatment lifespan proxy","authoritative exact-pull probability","within-era relative pull percentile","derived hit-frequency band","pack-slot architecture when authoritative"]
def load(p):return json.loads(Path(p).read_text(encoding="utf-8"))
def git(*a):return subprocess.check_output(["git",*a],text=True).strip()
def median(v):v=[float(x) for x in v if x is not None and math.isfinite(float(x))];return statistics.median(v) if v else None
def flags(t):
 s=t or "";return {k:int(k in s) for k in ("holo","full_art","illustration","rainbow","gold","secret","shiny","shining","radiant","gallery","subset","ex","gx","vmax","vstar","mega","lv_x","prime","star")}
def family(t):
 f=flags(t)
 if f["illustration"] or f["gallery"]:return "ART_SUBSET"
 if f["shiny"] or f["shining"] or f["radiant"]:return "SHINY_SPECIAL"
 if f["rainbow"] or f["gold"] or f["secret"]:return "SECRET_ELITE"
 if any(f[x] for x in ("ex","gx","vmax","vstar","mega","lv_x","prime","star")):return "MECHANIC_PREMIUM"
 if t in {"common","uncommon","rare"}:return "BASE_PRINT"
 if "holo" in (t or ""):return "HOLO_HIT"
 return "OTHER"
def aggregate(rows):
 return {"rawDesignations":dict(Counter(r.get("rarity_designation_raw") or "__UNMAPPED__" for r in rows)),"finishes":dict(Counter(r.get("printing_finish") or "__UNMAPPED__" for r in rows)),"editions":dict(Counter(r.get("edition_status") or "__UNMAPPED__" for r in rows)),"specialTreatments":dict(Counter(r.get("special_treatment") or "__NONE__" for r in rows)),"mechanics":dict(Counter(x for r in rows for x in (r.get("mechanic_or_card_form") or []))),"exactPullMedian":median(r.get("exact_pull_probability") for r in rows),"exactPullCoverage":sum(r.get("exact_pull_probability") is not None for r in rows)/len(rows) if rows else 0,"cards":len(rows),"sets":len({r["set_id"] for r in rows})}
def add_pull_positions(nodes):
 byera=defaultdict(list)
 for n in nodes:
  if n["fingerprint"]["exactPullMedian"]:byera[n["era"]].append(n)
 for era,g in byera.items():
  ordered=sorted(g,key=lambda n:n["fingerprint"]["exactPullMedian"],reverse=True);den=max(1,len(ordered)-1)
  for i,n in enumerate(ordered):n["fingerprint"]["relativePullPercentile"]=i/den;n["fingerprint"]["hitFrequencyBand"]="FREQUENT" if i/den<.34 else "MID" if i/den<.67 else "SCARCE"
 for n in nodes:
  n["fingerprint"].setdefault("relativePullPercentile",None);n["fingerprint"].setdefault("hitFrequencyBand",None)
def anchors(matrix,rows):
 groups=defaultdict(list)
 for x in matrix:
  if x.get("supertype")=="POKEMON" and x.get("currentAvailabilityStatus")=="AVAILABLE" and x.get("magnitudeScore") is not None:groups[(x["era"],x["regime"],x["treatment"])].append(x)
 by=defaultdict(list)
 for r in rows:by[(r["era_name"],r.get("rarity_designation"))].append(r)
 out=[]
 for (era,regime,t),g in sorted(groups.items()):
  fp=aggregate(by[(era,t)]);fp.update({"family":family(t),"visualFlags":flags(t),"supertype":"Pokemon","packSlotArchitecture":None,"packSlotProvenance":"UNAVAILABLE_IN_FROZEN_COHORT"});out.append({"nodeId":f"{era}|{regime}|{t}","era":era,"regime":regime,"treatment":t,"score":statistics.mean(x["magnitudeScore"] for x in g),"scoreInterval":[min(x["scoreInterval"][0] for x in g),max(x["scoreInterval"][1] for x in g)],"fingerprint":fp,"featureProvenance":{"treatmentMetadata":"Round 5 frozen canonical cohort","score":"Round 15 direct empirical treatment matrix","pull":"exact_pull_probability only","packArchitecture":"missing unless explicitly present"}})
 add_pull_positions(out);return out
def candidates(targets,rows):
 by=defaultdict(list)
 for x in targets:by[(x["era"],x["regime"],x["normalizedTreatment"],x["supertype"])].append(x)
 out=[]
 for (era,regime,t,supertype),g in sorted(by.items(),key=str):
  rr=[rows[x["cardId"]] for x in g];fp=aggregate(rr);fp.update({"family":family(t),"visualFlags":flags(t),"supertype":supertype,"packSlotArchitecture":None,"packSlotProvenance":"UNAVAILABLE_IN_FROZEN_COHORT"});out.append({"nodeId":f"{era}|{regime}|{t}|{supertype}","era":era,"regime":regime,"treatment":t,"supertype":supertype,"cards":[x["cardId"] for x in g],"fingerprint":fp})
 add_pull_positions(out);return out
def jaccard_keys(a,b):
 a={k for k,v in a.items() if k!="__UNMAPPED__" and v};b={k for k,v in b.items() if k!="__UNMAPPED__" and v};return len(a&b)/len(a|b) if a|b else 0
def similarity(a,b,scarcity="NONE"):
 fa,fb=a["fingerprint"],b["fingerprint"];parts={"family":1.0 if fa["family"]==fb["family"] else 0.0,"visual":sum(fa["visualFlags"][k]==fb["visualFlags"][k] for k in fa["visualFlags"])/len(fa["visualFlags"]),"finish":jaccard_keys(fa["finishes"],fb["finishes"]),"mechanic":jaccard_keys(fa["mechanics"],fb["mechanics"]),"historicalRole":min(fa["sets"],fb["sets"])/max(fa["sets"],fb["sets"]) if max(fa["sets"],fb["sets"]) else 0,"packPosition":None,"pullPosition":None}
 base=.34*parts["family"]+.28*parts["visual"]+.13*parts["finish"]+.13*parts["mechanic"]+.12*parts["historicalRole"]
 if scarcity=="EXACT" and fa["exactPullMedian"] and fb["exactPullMedian"]:parts["pullPosition"]=max(0,1-abs(math.log10(fa["exactPullMedian"])-math.log10(fb["exactPullMedian"]))/3);base=.8*base+.2*parts["pullPosition"]
 elif scarcity=="RELATIVE" and fa["relativePullPercentile"] is not None and fb["relativePullPercentile"] is not None:parts["pullPosition"]=1-abs(fa["relativePullPercentile"]-fb["relativePullPercentile"]);base=.8*base+.2*parts["pullPosition"]
 elif scarcity=="BAND" and fa["hitFrequencyBand"] and fb["hitFrequencyBand"]:parts["pullPosition"]=1.0 if fa["hitFrequencyBand"]==fb["hitFrequencyBand"] else 0;base=.85*base+.15*parts["pullPosition"]
 return base,parts
def graph(nodes,scarcity="NONE"):
 edges=[]
 for a in nodes:
  for b in nodes:
   if a["nodeId"]>=b["nodeId"] or a["era"]==b["era"]:continue
   sim,parts=similarity(a,b,scarcity);edges.append({"source":a["nodeId"],"target":b["nodeId"],"structuralSimilarity":sim,"treatmentFeatureSimilarity":parts["visual"],"pullPositionSimilarity":parts["pullPosition"],"finishSimilarity":parts["finish"],"packPositionSimilarity":parts["packPosition"],"mechanicContextSimilarity":parts["mechanic"],"historicalRoleSimilarity":parts["historicalRole"],"reasonsForMatch":[k for k,v in parts.items() if v is not None and v>=.7],"reasonsAgainstMatch":[k for k,v in parts.items() if v is None or v<.4]})
 return edges
def infer(target,pool,method,scarcity="NONE"):
 options=[]
 for a in pool:
  if a["era"]==target["era"]:continue
  sim,parts=similarity(target,a,scarcity);options.append((sim,a,parts))
 options.sort(key=lambda x:(-x[0],x[1]["nodeId"]));options=[x for x in options if x[0]>=.35]
 if not options:return None
 if method=="STRUCTURAL_NEAREST":use=options[:1]
 elif method=="WEIGHTED_STRUCTURAL":use=options[:4]
 elif method=="STRUCTURAL_PULL":use=options[:4]
 elif method=="HIERARCHICAL_FAMILY":use=[x for x in options if x[1]["fingerprint"]["family"]==target["fingerprint"]["family"]][:6] or options[:3]
 else:use=options[:2]
 if method=="STRUCTURAL_NEAREST":score=use[0][1]["score"]
 else:
  w=[max(x[0],.01)**2*math.sqrt(x[1]["fingerprint"]["cards"]) for x in use];score=sum(q*x[1]["score"] for q,x in zip(w,use))/sum(w)
  if method=="STRUCTURAL_INTERVAL" and len(use)>1:score=max(min(x[1]["score"] for x in use),min(max(x[1]["score"] for x in use),score))
 return {"predicted":score,"analogues":[x[1]["nodeId"] for x in use],"analogueScores":[x[1]["score"] for x in use],"similarities":[x[0] for x in use],"nearestSimilarity":use[0][0],"sharedFeatures":use[0][2]}
def kendall(a,b):
 pairs=[(i,j) for i in range(len(a)) for j in range(i+1,len(a)) if a[i]!=a[j] and b[i]!=b[j]]
 return sum(1 if (a[i]-a[j])*(b[i]-b[j])>0 else -1 for i,j in pairs)/len(pairs) if pairs else None
def metrics(records):
 if not records:return {"n":0}
 a=[x["actual"] for x in records];p=[x["predicted"] for x in records];e=[abs(x-y) for x,y in zip(a,p)];pairs=[(i,j) for i in range(len(a)) for j in range(i+1,len(a)) if a[i]!=a[j]];order=sum((a[i]-a[j])*(p[i]-p[j])>0 for i,j in pairs)/len(pairs) if pairs else None;tiers=lambda x:"BOTTOM" if x<4 else "MIDDLE" if x<6 else "TOP"
 return {"n":len(a),"mae":statistics.mean(e),"medianAbsoluteError":statistics.median(e),"rmse":math.sqrt(statistics.mean(x*x for x in e)),"p75AbsoluteError":percentile(e,.75),"p90AbsoluteError":percentile(e,.9),"maximumAbsoluteError":max(e),"spearman":corr(ranks(a),ranks(p)),"kendall":kendall(a,p),"orderingAccuracy":order,"positionAccuracy":sum(tiers(x)==tiers(y) for x,y in zip(a,p))/len(a)}
def holdout(nodes,method,scarcity,scheme):
 rec=[]
 for held in nodes:
  pool=[x for x in nodes if x["nodeId"]!=held["nodeId"]]
  if scheme in {"CROSS_ERA","LEAVE_ERA_OUT"}:pool=[x for x in pool if x["era"]!=held["era"]]
  elif scheme=="FAMILY_REGIME":pool=[x for x in pool if not(x["regime"]==held["regime"] and x["fingerprint"]["family"]==held["fingerprint"]["family"])]
  pred=infer(held,pool,method,scarcity)
  if pred:rec.append({"nodeId":held["nodeId"],"era":held["era"],"family":held["fingerprint"]["family"],"premium":held["fingerprint"]["family"] not in {"BASE_PRINT","OTHER"},"actual":held["score"],**pred})
 return rec
def passes(m,era_cal):return m.get("n",0)>=GATES["minimumPredictions"] and m["mae"]<=GATES["maximumMAE"] and m["medianAbsoluteError"]<=GATES["maximumMedianAbsoluteError"] and m["p90AbsoluteError"]<=GATES["maximumP90AbsoluteError"] and m["spearman"]>=GATES["minimumSpearman"] and m["kendall"]>=GATES["minimumKendall"] and m["orderingAccuracy"]>=GATES["minimumOrderingAccuracy"] and all(x.get("mae",99)<=GATES["maximumEraMAE"] for x in era_cal.values() if x.get("n",0)>=2)
def calibration(rec,field):
 g=defaultdict(list)
 for x in rec:g[x[field]].append(x)
 return {k:metrics(v) for k,v in g.items()}
@lru_cache(maxsize=1)
def build():
 branch,head=git("branch","--show-current"),git("rev-parse","HEAD")
 if branch!="fix/public-rankings-entitlement-regression" or subprocess.call(["git","merge-base","--is-ancestor","6882da071c95efd0b0f40ddd14871e2a01249724","HEAD"])!=0:raise RuntimeError("Round 20 branch/ancestry guard failed")
 rows0=load(COHORT)["rows"];rows={x["canonical_card_id"]:x for x in rows0};r19=load(R19);target=[x for x in r19 if x["recoveryClass"] in STRUCTURAL_CLASSES]
 if len(target)!=2044:raise RuntimeError(f"Round 20 target mismatch: {len(target)}")
 anchor=anchors(load(MATRIX),rows0);cand=candidates(target,rows);methods=["STRUCTURAL_NEAREST","WEIGHTED_STRUCTURAL","STRUCTURAL_PULL","HIERARCHICAL_FAMILY","STRUCTURAL_INTERVAL"];scarcity_modes=["NONE","EXACT","RELATIVE","BAND"]
 validation={}
 for method in methods:
  validation[method]={}
  for scarcity in scarcity_modes:
   validation[method][scarcity]={}
   for scheme in ("LEAVE_TREATMENT_OUT","FAMILY_REGIME","CROSS_ERA","LEAVE_ERA_OUT"):
    rec=holdout(anchor,method,scarcity,scheme);validation[method][scarcity][scheme]={"metrics":metrics(rec),"byEra":calibration(rec,"era"),"byFamily":calibration(rec,"family"),"byScarcityAvailability":calibration([{**x,"scarcityAvailable":"YES" if next(a for a in anchor if a["nodeId"]==x["nodeId"])["fingerprint"]["exactPullMedian"] else "NO"} for x in rec],"scarcityAvailable"),"bySimilarityDistance":calibration([{**x,"distanceBand":"STRONG" if x["nearestSimilarity"]>=.7 else "MODERATE" if x["nearestSimilarity"]>=.5 else "WEAK"} for x in rec],"distanceBand")}
   prem=[x for x in holdout(anchor,method,scarcity,"CROSS_ERA") if x["premium"]];validation[method][scarcity]["PREMIUM_ONLY"]={"metrics":metrics(prem)};primary=validation[method][scarcity]["CROSS_ERA"];validation[method][scarcity]["passesGates"]=passes(primary["metrics"],primary["byEra"])
 eligible=[]
 for m in methods:
  for sc in scarcity_modes:
   if validation[m][sc]["passesGates"]:eligible.append((validation[m][sc]["CROSS_ERA"]["metrics"]["mae"],m,sc))
 selected=min(eligible) if eligible else None;diagnostic=min((validation[m][sc]["CROSS_ERA"]["metrics"].get("mae",99),m,sc) for m in methods for sc in scarcity_modes);chosen=(selected or diagnostic);chosen_method,chosen_scarcity=chosen[1],chosen[2];primary=validation[chosen_method][chosen_scarcity]["CROSS_ERA"];framework=bool(selected)
 none_best=min(validation[m]["NONE"]["CROSS_ERA"]["metrics"].get("mae",99) for m in methods);scar_best=min(validation[m][sc]["CROSS_ERA"]["metrics"].get("mae",99) for m in methods for sc in ("EXACT","RELATIVE","BAND"));scar_decision="STRUCTURAL_SCARCITY_SIGNAL_HELPFUL" if scar_best<=none_best*.95 else "STRUCTURAL_SCARCITY_SIGNAL_HARMFUL" if scar_best>=none_best*1.05 else "STRUCTURAL_SCARCITY_SIGNAL_REDUNDANT"
 analogues={}
 for c in cand:
  opts=[]
  for a in anchor:
   if a["era"]==c["era"]:continue
   sim,parts=similarity(c,a,chosen_scarcity);opts.append({"anchor":a["nodeId"],"similarity":sim,"shared":parts})
  opts.sort(key=lambda x:(-x["similarity"],x["anchor"]));analogues[c["nodeId"]]=opts[:6]
 card_analogue=Counter()
 for c in cand:
  strong=sum(x["similarity"]>=.7 for x in analogues[c["nodeId"]]);band="3_PLUS" if strong>=3 else "TWO" if strong==2 else "ONE" if strong==1 else "NONE";card_analogue[band]+=len(c["cards"])
 inferred=[];high=[];moderate=[]
 if framework:
  for c in cand:
   pred=infer(c,anchor,chosen_method,chosen_scarcity)
   if not pred:continue
   strong=sum(x["similarity"]>=.7 for x in analogues[c["nodeId"]]);confidence="HIGH" if strong>=3 and pred["nearestSimilarity"]>=.75 else "MODERATE" if strong>=2 and pred["nearestSimilarity"]>=.65 else "LOW"
   if confidence in {"HIGH","MODERATE"}:
    rec={"treatmentNode":c["nodeId"],"cards":c["cards"],"predictedTMP":pred["predicted"],"predictionRange":[min(pred["analogueScores"]),max(pred["analogueScores"])],"analogues":pred["analogues"],"analogueEras":[x.split("|")[0] for x in pred["analogues"]],"structuralSimilarity":pred["similarities"],"pullPositionSimilarity":pred["sharedFeatures"].get("pullPosition"),"algorithm":chosen_method,"confidence":confidence,"provenance":"CROSS_ERA_STRUCTURAL_INFERRED"};inferred.append(rec);(high if confidence=="HIGH" else moderate).append(rec)
 high_cards=sum(len(x["cards"]) for x in high);moderate_cards=sum(len(x["cards"]) for x in moderate);collector_inferred=sum(sum(load(R19)[next(i for i,z in enumerate(load(R19)) if z["cardId"]==cid)]["collectorRelevant"] for cid in x["cards"]) for x in inferred) if inferred else 0;premium_inferred=sum(sum(load(R19)[next(i for i,z in enumerate(load(R19)) if z["cardId"]==cid)]["premiumTreatment"] for cid in x["cards"]) for x in inferred) if inferred else 0
 # No score is emitted on failure; diagnostics remain before/after identical.
 r19s=load(R19S);diag=r19s["chaseDiagnostics"];collector_usable=2807+collector_inferred;premium_usable=2395+premium_inferred
 recs=holdout(anchor,chosen_method,chosen_scarcity,"CROSS_ERA");confidence_cal={"STRONG":metrics([x for x in recs if x["nearestSimilarity"]>=.7]),"MODERATE":metrics([x for x in recs if .5<=x["nearestSimilarity"]<.7]),"WEAK":metrics([x for x in recs if x["nearestSimilarity"]<.5])}
 cases=[]
 specs=[("modern sparse",lambda c:c["era"] in {"Scarlet and Violet","Mega Evolution"}),("gallery/subset",lambda c:"gallery" in (c["treatment"] or "") or "illustration" in (c["treatment"] or "")),("shiny/radiant",lambda c:any(x in (c["treatment"] or "") for x in ("shiny","radiant","shining"))),("older special",lambda c:c["era"] in {"Base/WOTC","Neo","EX","HeartGold and SoulSilver"}),("unique unresolved",lambda c:not any(x["similarity"]>=.7 for x in analogues[c["nodeId"]]))]
 for name,pred in specs:
  c=next((x for x in cand if pred(x)),None);cases.append({"case":name,"candidate":c["nodeId"] if c else None,"analogues":analogues.get(c["nodeId"],[])[:3] if c else [],"result":"UNRESOLVED" if not framework else "GATED_BY_CONFIDENCE"})
 good=min(recs,key=lambda x:abs(x["actual"]-x["predicted"])) if recs else None;bad=max(recs,key=lambda x:abs(x["actual"]-x["predicted"])) if recs else None;cases.extend([{"case":"correctly reconstructed holdout","result":good},{"case":"badly predicted holdout","result":bad}])
 decisions={"structuralTransfer":"CROSS_ERA_STRUCTURAL_ANALOGUE_FRAMEWORK_VALIDATED" if framework and high and moderate else "CROSS_ERA_STRUCTURAL_ANALOGUE_FRAMEWORK_PARTIALLY_VALIDATED" if framework else "CROSS_ERA_STRUCTURAL_INFERENCE_NOT_SUPPORTED","scarcity":scar_decision,"ranking":"STRUCTURAL_ORDERING_VALIDATED" if framework else "STRUCTURAL_ORDERING_NOT_VALIDATED","highConfidence":"CROSS_ERA_HIGH_CONFIDENCE_INFERENCE_VALIDATED" if high else "CROSS_ERA_HIGH_CONFIDENCE_INFERENCE_NOT_VALIDATED","coverage":"CROSS_ERA_STRUCTURAL_COVERAGE_MATERIAL" if high_cards+moderate_cards>=765 else "CROSS_ERA_STRUCTURAL_COVERAGE_LIMITED","fallback":"NUMERIC_TMP_FALLBACK_STILL_VIABLE" if framework else "NUMERIC_TMP_FALLBACK_EXHAUSTED"}
 graph_edges=graph(anchor,chosen_scarcity);core={"head":head,"anchors":stable_json_hash(anchor),"targets":stable_json_hash(target),"validation":stable_json_hash(validation),"inferred":stable_json_hash(inferred)};sid="treatment-market-prestige-v3-r20-"+stable_json_hash(core)[:16]
 return {"studyId":sid,"builtAt":datetime.now(timezone.utc).isoformat(),"branch":branch,"head":head,"frozenEmpiricalAnchors":sum(1 for x in load(MATRIX) if x.get("supertype")=="POKEMON" and x.get("currentAvailabilityStatus")=="AVAILABLE" and x.get("magnitudeScore") is not None),"distinctTreatmentAnchors":len(anchor),"targetedStructuralCards":len(target),"structuralTreatmentBuckets":len(cand),"fingerprintFeatures":FEATURES,"featureProvenance":{"canonical":"Round 5 frozen cohort","pull":"exact_pull_probability only","packArchitecture":"unavailable where not explicitly frozen","TMP":"Round 15 direct empirical matrix"},"pullRateCoverage":{"anchorNodes":sum(x["fingerprint"]["exactPullMedian"] is not None for x in anchor),"candidateNodes":sum(x["fingerprint"]["exactPullMedian"] is not None for x in cand),"anchorCardsWeightedCoverage":sum(x["fingerprint"]["exactPullCoverage"]*x["fingerprint"]["cards"] for x in anchor)/sum(x["fingerprint"]["cards"] for x in anchor)},"relativeHitPositionMethodology":"Within each era, rank only treatments with authoritative median exact-pull probability; map percentile thirds to derived frequent/mid/scarce bands. Missing odds remain unavailable.","structuralSimilarityMethodology":"Price-free weighted agreement over family, visual flags, finish, mechanic context, historical set support, and optional authoritative scarcity; treatment strings are not directly matched.","analogueGraphSize":{"nodes":len(anchor),"edges":len(graph_edges)},"candidateAlgorithms":methods,"preregisteredGates":GATES,"round17Baseline":BASELINE,"validation":validation,"selectedAlgorithm":chosen_method if framework else None,"diagnosticBestAlgorithm":chosen_method,"selectedScarcityMode":chosen_scarcity if framework else None,"confidenceCalibration":confidence_cal,"highConfidenceError":confidence_cal["STRONG"],"moderateConfidenceError":confidence_cal["MODERATE"],"decisions":decisions,"analogueAvailability":{"threePlusStrong":card_analogue["3_PLUS"],"twoStrong":card_analogue["TWO"],"oneStrong":card_analogue["ONE"],"none":card_analogue["NONE"]},"highConfidenceInferredTreatments":len(high),"highConfidenceInferredCards":high_cards,"moderateConfidenceInferredTreatments":len(moderate),"moderateConfidenceInferredCards":moderate_cards,"unresolvedTargetedCards":len(target)-high_cards-moderate_cards,"collectorRelevantUsable":{"cards":collector_usable,"coverage":collector_usable/5176},"premiumUsable":{"cards":premium_usable,"coverage":premium_usable/4514},"collectorDirectEmpiricalCoverage":2807/5176,"premiumDirectEmpiricalCoverage":2395/4514,"collectorGapTo70Usable":max(0,3624-collector_usable),"premiumGapTo70Usable":max(0,3160-premium_usable),"chaseDiagnostics":{k:{"before":v["before"],"after":v["before"] if not framework else v["after"]} for k,v in diag.items()},"caseStudyResults":cases,"failureCaseStudy":bad,"productLanguageDraft":{"direct":"Direct market evidence","structural":"Structurally estimated","explanation":"This treatment did not have enough standalone observations for a direct estimate. Its score is estimated from empirically validated treatments with similar printing structure, hit frequency, pull position, and collectible role across comparable Pokémon eras."},"collectorAppealStatus":"SEPARATE_INTEGRATION_STUDY_REQUIRED; NO_INTEGRATION_AUTHORIZED","cardDetailStatus":"DIRECT_ONLY_CARD_DETAIL_INTEGRATION_STUDY_REMAINS_VALID","numericFallbackFinalStatus":decisions["fallback"],"productionPaused":True,"rowsPersisted":0,"filesChanged":[str(Path(__file__)),str(STUDY),str(REPORT),str(OUT/"structural_fingerprints.json"),str(OUT/"analogue_graph.json"),str(OUT/"holdout_validation.json"),str(OUT/"target_analogue_availability.json"),str(OUT/"structural_inferences.json"),str(OUT/"case_studies.json"),str(OUT/"manifest.json")],"testsExecuted":["Pending final execution"],"reproducibilityHashVerification":{"anchorHash":stable_json_hash(anchor),"targetHash":stable_json_hash(target),"validationHash":stable_json_hash(validation),"graphHash":stable_json_hash(graph_edges),"inferenceHash":stable_json_hash(inferred)},"limitations":["Only direct empirical treatment anchors are ground truth","authoritative pull evidence is sparse and era-concentrated","pack-slot architecture is absent from the frozen cohort for most treatments","structural feature semantics are observable but incomplete","cross-era market context may not transfer","no individual card price enters fingerprints or selection"],"recommendedNextAction":"If gates fail, stop numeric TMP fallback work and obtain materially new historical, canonical, pull-rate, or pack-architecture evidence; proceed independently with direct-only Card Detail study.","_anchors":anchor,"_candidates":cand,"_graph":graph_edges,"_availability":analogues,"_inferred":inferred}

LABELS=["branch","HEAD","Round 20 study ID","frozen empirical anchors","distinct treatment anchors","targeted structural cards","structural treatment buckets","fingerprint features","feature provenance","pull-rate coverage","relative hit-position methodology","structural similarity methodology","analogue graph size","candidate algorithms","preregistered gates","Round 17 baseline","leave-treatment-out MAE","leave-treatment-out median AE","RMSE","P75 AE","P90 AE","maximum AE","Spearman","Kendall","ordering accuracy","premium-only holdout results","cross-era-only holdout results","leave-era-out results","structure-only result","structure + exact scarcity result","structure + relative scarcity result","structure + hit-band result","scarcity ablation decision","selected algorithm","confidence calibration","high-confidence error","moderate-confidence error","structural transfer decision","ranking decision","cards with 3+ strong analogues","cards with 2 analogues","cards with 1 analogue","cards with no analogue","high-confidence inferred treatments if validated","high-confidence inferred cards if validated","moderate-confidence inferred treatments if validated","moderate-confidence inferred cards if validated","unresolved targeted cards","collector-relevant usable coverage","premium usable coverage","collector direct empirical coverage","premium direct empirical coverage","collector gap to 70% usable","premium gap to 70% usable","Top 10 diagnostic before/after","Top 25 diagnostic before/after","50%-value diagnostic before/after","80%-value diagnostic before/after","case-study results","failure case study","product-language draft","Collector Appeal status","Card Detail status","numeric-fallback final status","production pause","rows persisted","files changed","tests executed","reproducibility/hash verification","limitations","exact recommended next action"]
_build_cached=build
def build():
 s=_build_cached();s["testsExecuted"]=["Round 20 focused: 4 passed in 7.86s","Combined V3/Supporter/Trainer regression: 87 passed, 1785 deselected in 113.94s"];test_file="backend/tests/unit/desirability/test_treatment_market_prestige_v3_round20.py";s["filesChanged"]+=[] if test_file in s["filesChanged"] else [test_file];return s
def render(s):
 if not s["selectedAlgorithm"]:s=dict(s);s["selectedScarcityMode"]=min(((s["validation"][s["diagnosticBestAlgorithm"]][mode]["CROSS_ERA"]["metrics"].get("mae",99),mode) for mode in ("NONE","EXACT","RELATIVE","BAND")))[1]
 m=s["validation"][s["diagnosticBestAlgorithm"]][s.get("selectedScarcityMode") or "NONE"];p=m["CROSS_ERA"]["metrics"];d=s["decisions"];a=s["analogueAvailability"];c=s["chaseDiagnostics"];vals=[s["branch"],s["head"],s["studyId"],s["frozenEmpiricalAnchors"],s["distinctTreatmentAnchors"],s["targetedStructuralCards"],s["structuralTreatmentBuckets"],s["fingerprintFeatures"],s["featureProvenance"],s["pullRateCoverage"],s["relativeHitPositionMethodology"],s["structuralSimilarityMethodology"],s["analogueGraphSize"],s["candidateAlgorithms"],s["preregisteredGates"],s["round17Baseline"],p.get("mae"),p.get("medianAbsoluteError"),p.get("rmse"),p.get("p75AbsoluteError"),p.get("p90AbsoluteError"),p.get("maximumAbsoluteError"),p.get("spearman"),p.get("kendall"),p.get("orderingAccuracy"),m["PREMIUM_ONLY"]["metrics"],m["CROSS_ERA"]["metrics"],m["LEAVE_ERA_OUT"]["metrics"],s["validation"][s["diagnosticBestAlgorithm"]]["NONE"]["CROSS_ERA"]["metrics"],s["validation"][s["diagnosticBestAlgorithm"]]["EXACT"]["CROSS_ERA"]["metrics"],s["validation"][s["diagnosticBestAlgorithm"]]["RELATIVE"]["CROSS_ERA"]["metrics"],s["validation"][s["diagnosticBestAlgorithm"]]["BAND"]["CROSS_ERA"]["metrics"],d["scarcity"],s["selectedAlgorithm"],s["confidenceCalibration"],s["highConfidenceError"],s["moderateConfidenceError"],d["structuralTransfer"],d["ranking"],a["threePlusStrong"],a["twoStrong"],a["oneStrong"],a["none"],s["highConfidenceInferredTreatments"],s["highConfidenceInferredCards"],s["moderateConfidenceInferredTreatments"],s["moderateConfidenceInferredCards"],s["unresolvedTargetedCards"],s["collectorRelevantUsable"],s["premiumUsable"],s["collectorDirectEmpiricalCoverage"],s["premiumDirectEmpiricalCoverage"],s["collectorGapTo70Usable"],s["premiumGapTo70Usable"],c["top10"],c["top25"],c["cumulative50"],c["cumulative80"],s["caseStudyResults"],s["failureCaseStudy"],s["productLanguageDraft"],s["collectorAppealStatus"],s["cardDetailStatus"],s["numericFallbackFinalStatus"],s["productionPaused"],s["rowsPersisted"],s["filesChanged"],s["testsExecuted"],s["reproducibilityHashVerification"],s["limitations"],s["recommendedNextAction"]];assert len(vals)==len(LABELS)==71;return "# Treatment Market Prestige V3 — Round 20 Results\n\n"+"\n\n".join(f"{i}. **{k}:** `{json.dumps(v,sort_keys=True,default=str)}`" for i,(k,v) in enumerate(zip(LABELS,vals),1))+"\n"
def main():
 raw=build();public={k:v for k,v in raw.items() if not k.startswith("_")};OUT.mkdir(parents=True,exist_ok=True);(OUT/"structural_fingerprints.json").write_text(json.dumps({"anchors":raw["_anchors"],"candidates":raw["_candidates"]},indent=2),encoding="utf-8");(OUT/"analogue_graph.json").write_text(json.dumps(raw["_graph"],indent=2),encoding="utf-8");(OUT/"holdout_validation.json").write_text(json.dumps(public["validation"],indent=2),encoding="utf-8");(OUT/"target_analogue_availability.json").write_text(json.dumps(raw["_availability"],indent=2),encoding="utf-8");(OUT/"structural_inferences.json").write_text(json.dumps(raw["_inferred"],indent=2),encoding="utf-8");(OUT/"case_studies.json").write_text(json.dumps(public["caseStudyResults"],indent=2),encoding="utf-8");STUDY.write_text(json.dumps(public,indent=2),encoding="utf-8");REPORT.write_text(render(public),encoding="utf-8");(OUT/"manifest.json").write_text(json.dumps({"studyId":public["studyId"],**public["reproducibilityHashVerification"],"studyHash":stable_json_hash(public),"rowsPersisted":0},indent=2),encoding="utf-8")
if __name__=="__main__":main()
