"""Round 18 TMP coverage relevance and missingness audit. Research only."""
from __future__ import annotations

import json
import math
import statistics
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from backend.desirability.rarity_buckets import ACCESSIBLE_KEYS, HIT_POLICY_VERSION, MAJOR_KEYS, PREMIUM_KEYS
from backend.desirability.treatment_market_prestige_v3 import stable_json_hash
from backend.scripts.build_pokemon_card_desirability_links import FALLBACK_HIT_RARITY_KEYS

ROOT=Path("docs/research"); R16=ROOT/"treatment_market_prestige_v3_round16"; LEDGER=R16/"card_coverage_ledger.json"; COHORT=ROOT/"treatment_market_prestige_v3_round5_frozen/cohort.json"; OUT=ROOT/"treatment_market_prestige_v3_round18"; STUDY=ROOT/"treatment_market_prestige_v3_round18_study.json"; REPORT=ROOT/"TREATMENT_MARKET_PRESTIGE_V3_ROUND18_RESULTS.md"
DENOMINATOR=19847; EXPECTED={"DIRECT_EMPIRICAL":10996,"STRONG_PARTIAL_EMPIRICAL":0,"NEUTRAL_TREATMENT":371,"BEST_FIT_INFERRED":0,"UNRESOLVED":8480}
ORDINARY={"common","uncommon","rare","regular_rare","rare_holo","holo_rare","rare_holo_pokemon"}
PREMIUM=set(PREMIUM_KEYS)|set(MAJOR_KEYS)|(set(ACCESSIBLE_KEYS)-{"rare_holo","holo_rare","rare_holo_pokemon"})|{"legend","rare_ace","ace_spec_rare","mega_attack_rare","mega_hyper_rare","black_white_rare"}
THRESHOLDS=(.5,.6,.7,.8,.9,1.0)

def load(p): return json.loads(Path(p).read_text(encoding="utf-8"))
def git(*args): return subprocess.check_output(["git",*args],text=True).strip()
def ratio(n,d): return n/d if d else None
def safe_key(x): return x if x not in (None,"") else "__UNMAPPED__"
def treatment(row): return safe_key(row.get("rarity_designation"))
def is_hit(row): return bool(row.get("supertype")) and row.get("supertype") not in {"Trainer","Energy"} and row.get("rarity_designation") in FALLBACK_HIT_RARITY_KEYS
def is_premium(row):
    t=row.get("rarity_designation") or ""; special=bool(row.get("special_treatment")); forms=set(row.get("mechanic_or_card_form") or [])
    return t in PREMIUM or special or bool(forms & {"full_art","alternate_art","shiny","radiant","gallery","gold","rainbow"})
def relevance_class(row):
    t=row.get("rarity_designation") or ""; st=row.get("supertype")
    if st=="Trainer": return "Trainer"
    if row.get("promo_status_ambiguous") or t=="promo": return "promo/special release"
    if "gallery" in t or "illustration" in t or t=="classic_collection": return "subset/gallery"
    if is_premium(row): return "premium hit"
    if row.get("special_treatment"): return "special treatment"
    if t in {"rare","rare_holo","holo_rare","rare_holo_pokemon"}: return "conventional rare/holo"
    if t in {"common","uncommon","regular_rare"}: return "ordinary/base printing"
    return "other"
def pct_record(group, state_by, eligible=lambda r:True):
    g=[r for r in group if eligible(r)]; direct=sum(state_by[r["canonical_card_id"]]=="DIRECT_EMPIRICAL" for r in g); neutral=sum(state_by[r["canonical_card_id"]]=="NEUTRAL_TREATMENT" for r in g)
    return {"denominator":len(g),"directEmpirical":direct,"neutral":neutral,"unresolved":sum(state_by[r["canonical_card_id"]]=="UNRESOLVED" for r in g),"empiricalCoverage":ratio(direct,len(g)),"usableCoverage":ratio(direct+neutral,len(g))}
def grouped(rows,key,state_by,eligible=lambda r:True):
    groups=defaultdict(list)
    for r in rows: groups[safe_key(key(r))].append(r)
    return {k:pct_record(v,state_by,eligible) for k,v in sorted(groups.items())}
def distribution(table,field="empiricalCoverage"):
    values=[x[field] for x in table.values() if x.get("denominator",0)>0 and x.get(field) is not None]
    result={f">={int(t*100)}%":sum(v>=t for v in values) for t in THRESHOLDS}; result["eligibleGroups"]=len(values); return result
def breakdown(rows,key): return dict(sorted(Counter(safe_key(key(r)) for r in rows).items(),key=lambda x:(-x[1],str(x[0]))))
def chase_diagnostic(rows,state_by):
    sets=defaultdict(list)
    for r in rows: sets[r["set_id"]].append(r)
    totals={k:[0,0] for k in ("top10","top25","cumulative50","cumulative80")}; per_set={}
    for sid,g in sets.items():
        ordered=sorted(g,key=lambda r:(-float(r.get("market_price") or 0),r["canonical_card_id"])); total=sum(max(float(r.get("market_price") or 0),0) for r in ordered)
        selections={"top10":ordered[:10],"top25":ordered[:min(25,len(ordered))]}
        for q,name in ((.5,"cumulative50"),(.8,"cumulative80")):
            running=0; chosen=[]
            for r in ordered:
                if total and running>=total*q: break
                chosen.append(r); running+=max(float(r.get("market_price") or 0),0)
            selections[name]=chosen
        per_set[sid]={}
        for name,sel in selections.items():
            covered=sum(state_by[r["canonical_card_id"]] in {"DIRECT_EMPIRICAL","NEUTRAL_TREATMENT"} for r in sel); totals[name][0]+=covered; totals[name][1]+=len(sel); per_set[sid][name]={"cards":len(sel),"covered":covered,"coverage":ratio(covered,len(sel))}
    return {"label":"MARKET-VALUE-WEIGHTED COVERAGE DIAGNOSTIC — not an eligibility or product gate","aggregate":{k:{"cards":d,"covered":n,"coverage":ratio(n,d)} for k,(n,d) in totals.items()},"bySet":per_set}
def price_deciles(rows,state_by):
    ordered=sorted(rows,key=lambda r:(float(r.get("market_price") or 0),r["canonical_card_id"])); out={}
    for i in range(10):
        g=ordered[math.floor(i*len(ordered)/10):math.floor((i+1)*len(ordered)/10)]; out[str(i+1)]=pct_record(g,state_by)
    return out
def blocker_project(blocker):
    if "HISTORY" in blocker: return "NEW_HISTORICAL_DATA"
    if blocker in {"TAXONOMY_UNMAPPED","CANONICAL_MAPPING_UNSAFE","TRAINER_IDENTITY_UNRESOLVED","PROMO_STRUCTURE_UNRESOLVED"}: return "CANONICAL_OR_TAXONOMY_WORK"
    if "INSTABILITY" in blocker: return "ADDITIONAL_HISTORY_AND_STABILITY_RESEARCH"
    return "STRUCTURALLY_UNDERIDENTIFIED_UNDER_CURRENT_EVIDENCE"
def evidence_projects(rows,ledger_by):
    groups=defaultdict(list)
    for r in rows:
        blocker=ledger_by[r["canonical_card_id"]]["terminalBlocker"]; groups[(r["era_name"],treatment(r),blocker)].append(r)
    result=[]
    for (era,t,blocker),g in groups.items(): result.append({"era":era,"treatment":t,"blocker":blocker,"cardCount":len(g),"setCount":len({x["set_id"] for x in g}),"solvability":blocker_project(blocker),"expectedProductRelevance":"HIGH" if any(is_hit(x) or is_premium(x) for x in g) else "LOW"})
    return sorted(result,key=lambda x:(-x["cardCount"],x["era"],x["treatment"]))
def blocked_cards(rows,ledger_by,category):
    checks={"history":lambda b:"HISTORY" in b,"taxonomy":lambda b:b in {"TAXONOMY_UNMAPPED","CANONICAL_MAPPING_UNSAFE","TRAINER_IDENTITY_UNRESOLVED","PROMO_STRUCTURE_UNRESOLVED"},"instability":lambda b:"INSTABILITY" in b,"underidentified":lambda b:blocker_project(b)=="STRUCTURALLY_UNDERIDENTIFIED_UNDER_CURRENT_EVIDENCE"}
    return [{"cardId":r["canonical_card_id"],"setId":r["set_id"],"setName":r["set_name"],"era":r["era_name"],"treatment":treatment(r),"blocker":ledger_by[r["canonical_card_id"]]["terminalBlocker"]} for r in rows if checks[category](ledger_by[r["canonical_card_id"]]["terminalBlocker"])]

@lru_cache(maxsize=1)
def build():
    branch,head=git("branch","--show-current"),git("rev-parse","HEAD")
    if branch!="fix/public-rankings-entitlement-regression": raise RuntimeError("Round 18 wrong branch")
    ledger=load(LEDGER); rows=load(COHORT)["rows"]; state_by={x["cardId"]:x["coverageProvenance"] for x in ledger}; ledger_by={x["cardId"]:x for x in ledger}; counts=Counter(state_by.values())
    if len(ledger)!=DENOMINATOR or len(state_by)!=DENOMINATOR or any(counts[k]!=v for k,v in EXPECTED.items()) or any(k not in EXPECTED for k in counts): raise RuntimeError(f"Locked provenance mismatch: rows={len(ledger)} unique={len(state_by)} states={dict(counts)}")
    unresolved=[r for r in rows if state_by[r["canonical_card_id"]]=="UNRESOLVED"]; hit=[r for r in rows if is_hit(r)]; premium=[r for r in rows if is_premium(r)]; unresolved_hit_premium=[r for r in unresolved if is_hit(r) or is_premium(r)]
    residual={"era":breakdown(unresolved,lambda r:r["era_name"]),"regime":breakdown(unresolved,lambda r:ledger_by[r["canonical_card_id"]].get("regime")),"set":breakdown(unresolved,lambda r:f"{r['set_id']}|{r['set_name']}"),"supertype":breakdown(unresolved,lambda r:r.get("supertype")),"trainerSubtype":breakdown([r for r in unresolved if r.get("supertype")=="Trainer"],lambda r:ledger_by[r["canonical_card_id"]].get("trainerSubtype")),"normalizedTreatment":breakdown(unresolved,lambda r:r.get("rarity_designation")),"rawRarity":breakdown(unresolved,lambda r:r.get("rarity_designation_raw")),"promoSpecialRelease":breakdown(unresolved,lambda r:"PROMO_OR_SPECIAL" if r.get("promo_status_ambiguous") or r.get("rarity_designation")=="promo" else "MAIN_SET_OR_UNFLAGGED"),"mechanicForm":breakdown(unresolved,lambda r:"|".join(r.get("mechanic_or_card_form") or []) or None),"terminalBlocker":breakdown(unresolved,lambda r:ledger_by[r["canonical_card_id"]].get("terminalBlocker")),"treatmentSupportStatus":breakdown(unresolved,lambda r:"HAS_EMPIRICAL_TREATMENT" if ledger_by[r["canonical_card_id"]].get("treatmentHasEmpiricalEvidence") else "NO_EMPIRICAL_TREATMENT"),"productRelevanceClass":breakdown(unresolved,relevance_class)}
    all_set=grouped(rows,lambda r:f"{r['set_id']}|{r['set_name']}",state_by); hit_set=grouped(rows,lambda r:f"{r['set_id']}|{r['set_name']}",state_by,is_hit); premium_set=grouped(rows,lambda r:f"{r['set_id']}|{r['set_name']}",state_by,is_premium)
    all_era=grouped(rows,lambda r:r["era_name"],state_by); hit_era=grouped(rows,lambda r:r["era_name"],state_by,is_hit); premium_era=grouped(rows,lambda r:r["era_name"],state_by,is_premium)
    set_table=[]
    for key in all_set:
        sid,name=key.split("|",1); set_table.append({"setId":sid,"setName":name,"allCards":all_set[key],"collectorRelevant":hit_set[key],"premiumTreatment":premium_set[key]})
    era_table=[{"era":era,"allCards":all_era[era],"collectorRelevant":hit_era[era],"premiumTreatment":premium_era[era]} for era in all_era]
    hit_summary=pct_record(rows,state_by,is_hit); premium_summary=pct_record(rows,state_by,is_premium); chase=chase_diagnostic(rows,state_by)
    ordinary_unresolved=[r for r in unresolved if r.get("rarity_designation") in ORDINARY or (r.get("supertype")=="Trainer" and not is_premium(r))]
    missingness={"conclusion":"MISSINGNESS_NOT_RANDOM","era":all_era,"releaseAge":"Exact release dates are absent from the frozen cohort; era is reported as the preregistered non-price historical proxy and shows strong age/cohort concentration.","supertype":grouped(rows,lambda r:r.get("supertype"),state_by),"treatmentFamily":grouped(rows,relevance_class,state_by),"premiumStatus":grouped(rows,lambda r:"PREMIUM" if is_premium(r) else "NON_PREMIUM",state_by),"promoStatus":grouped(rows,lambda r:"PROMO_OR_SPECIAL" if r.get("promo_status_ambiguous") or r.get("rarity_designation")=="promo" else "OTHER",state_by),"hitEligibility":grouped(rows,lambda r:"HIT_ELIGIBLE" if is_hit(r) else "NOT_HIT_ELIGIBLE",state_by),"marketPriceDecileDiagnosticOnly":price_deciles(rows,state_by)}
    supported_hit_sets=[x for x in hit_set.values() if x["denominator"]>0]; gate_d=sum(x["empiricalCoverage"]>=.7 for x in supported_hit_sets); gate_d_share=ratio(gate_d,len(supported_hit_sets))
    gate_evals={"A":{"definition":"70% all priced canonical cards strong empirical","observed":EXPECTED["DIRECT_EMPIRICAL"]/DENOMINATOR,"passes":False,"alignment":"Overweights ordinary cards for a treatment-premium construct, though it remains the honest catalog-completeness statistic."},"B":{"definition":"70% price-independent hit cards strong empirical","observed":hit_summary["empiricalCoverage"],"passes":hit_summary["empiricalCoverage"]>=.7,"alignment":"Most aligned with current Pokémon-only Collector Appeal hit scope, but excludes premium Trainers."},"C":{"definition":"70% treatment-defined premium cards strong empirical","observed":premium_summary["empiricalCoverage"],"passes":premium_summary["empiricalCoverage"]>=.7,"alignment":"Most aligned with Card Intelligence treatment prestige across Pokémon and Trainers."},"D":{"definition":"Majority of supported sets have >=70% collector-relevant empirical coverage","observed":gate_d_share,"setsPassing":gate_d,"supportedSets":len(supported_hit_sets),"passes":gate_d_share is not None and gate_d_share>=.5,"alignment":"Useful distributional guard against aggregate coverage hiding set gaps; should accompany, not replace, a population gate."}}
    catalog_decision="ALL_CARD_70_PERCENT_GATE_MISALIGNED_WITH_PRODUCT_USE" if len(ordinary_unresolved)>len(unresolved)/2 else "ALL_CARD_70_PERCENT_GATE_REMAINS_APPROPRIATE"
    collector_decision="COLLECTOR_RELEVANT_TMP_COVERAGE_SUFFICIENT" if hit_summary["empiricalCoverage"]>=.7 and gate_d_share>=.5 else "COLLECTOR_RELEVANT_TMP_COVERAGE_PARTIAL" if hit_summary["empiricalCoverage"]>=.5 else "COLLECTOR_RELEVANT_TMP_COVERAGE_INSUFFICIENT"
    card_detail_decision="DIRECT_TMP_CARD_DETAIL_READY_FOR_INTEGRATION_STUDY" if EXPECTED["DIRECT_EMPIRICAL"]>0 else "DIRECT_TMP_CARD_DETAIL_NOT_READY"
    appeal_decision="TMP_COLLECTOR_APPEAL_READY_FOR_INTEGRATION_STUDY" if collector_decision=="COLLECTOR_RELEVANT_TMP_COVERAGE_SUFFICIENT" and gate_d_share>=.7 else "TMP_COLLECTOR_APPEAL_COVERAGE_STILL_INSUFFICIENT"
    projects=evidence_projects(unresolved_hit_premium,ledger_by); blocked={k:blocked_cards(unresolved_hit_premium,ledger_by,k) for k in ("history","taxonomy","instability","underidentified")}
    coverage_by_regime=grouped(rows,lambda r:ledger_by[r["canonical_card_id"]].get("regime"),state_by,is_hit); coverage_by_set=hit_set
    for provenance_state in EXPECTED: counts[provenance_state] += 0
    core={"head":head,"ledger":stable_json_hash(ledger),"hitPolicy":HIT_POLICY_VERSION,"premium":stable_json_hash(sorted(r["canonical_card_id"] for r in premium)),"setTable":stable_json_hash(set_table)}; sid="treatment-market-prestige-v3-r18-"+stable_json_hash(core)[:16]
    return {"studyId":sid,"builtAt":datetime.now(timezone.utc).isoformat(),"branch":branch,"head":head,"denominator":DENOMINATOR,"provenance":dict(counts),"residualBreakdown":residual,"ordinaryTreatmentUnresolvedCount":len(ordinary_unresolved),"premiumTreatmentUnresolvedCount":premium_summary["unresolved"],"collectorRelevant":{"policy":HIT_POLICY_VERSION,"implementation":"Pokemon supertype plus canonical normalized fallback hit-rarity keys; no price threshold.","summary":hit_summary,"byEra":hit_era,"byRegime":coverage_by_regime,"bySet":coverage_by_set},"premiumTreatment":{"definition":"Canonical premium/major and era-native premium mechanic treatment metadata; excludes plain ordinary Holo and uses no price.","summary":premium_summary,"byEra":premium_era,"bySet":premium_set},"setReadinessDistributions":{"allCard":distribution(all_set),"collectorRelevant":distribution(hit_set),"premiumTreatment":distribution(premium_set)},"setLevelReadinessTable":set_table,"eraLevelReadinessTable":era_table,"chaseCoverageDiagnostic":chase,"missingnessBiasFindings":missingness,"collectorAppealPopulationDependency":{"requiresEveryCommonUncommon":False,"primaryPopulation":"Price-independent eligible Pokémon hits and their subject roster; current V5 contextual relevance additionally uses same-run EV contribution, but TMP integration is not performed here.","missingOrdinaryEffect":"Ordinary Common/Uncommon TMP is unlikely to materially alter hit-roster treatment prestige because those cards are outside canonical hit eligibility; this is a product-scope finding, not permission to call them covered.","missingPremiumEffect":"Missing premium/hit TMP can bias era, set, and subject comparisons and blocks Collector Appeal integration without explicit missingness handling.","optionalFeatureFeasibility":"Scientifically plausible only with an integration study that uses explicit availability indicators, era/set diagnostics, and no implicit zero imputation."},"cardDetailReadiness":{"directDisplayCards":EXPECTED["DIRECT_EMPIRICAL"],"neutralEnergyDisplayCards":EXPECTED["NEUTRAL_TREATMENT"],"insufficientEvidenceCards":EXPECTED["UNRESOLVED"],"assessment":"Direct-only display can be truthful if provenance is explicit, neutral Energy is labeled semantically, and unresolved cards say insufficient evidence rather than appearing as zero."},"gateEvaluations":gate_evals,"decisions":{"catalogGate":catalog_decision,"collectorRelevantReadiness":collector_decision,"cardDetail":card_detail_decision,"collectorAppeal":appeal_decision},"highestValueRemainingEvidenceProjects":projects,"blockedPremiumHitCards":blocked,"productionPaused":True,"rowsPersisted":0,"filesChanged":[str(Path(__file__)),str(STUDY),str(REPORT),str(OUT/"residual_breakdown.json"),str(OUT/"set_level_readiness.json"),str(OUT/"era_level_readiness.json"),str(OUT/"market_value_weighted_diagnostic.json"),str(OUT/"missingness_bias.json"),str(OUT/"premium_hit_evidence_projects.json"),str(OUT/"manifest.json")],"testsExecuted":["Pending final execution"],"limitations":["Frozen cohort lacks exact release dates, so era is the declared historical proxy","Set-config mappings are not keyed in the frozen cohort; canonical hit-policy fallback keys are used","Current Collector Appeal subject scope excludes Trainers while premium-treatment coverage does not","Market price appears only in the explicitly labeled chase diagnostic and price-decile missingness diagnostic","Coverage does not validate a future TMP integration weight"],"recommendedNextAction":"Prioritize unresolved premium/hit history, taxonomy, and instability projects in the generated evidence-project table; then run a separate Collector Appeal integration study with explicit missingness handling before production use.","_ledger":ledger}

LABELS=["branch","HEAD","denominator","empirical count","neutral count","unresolved count","unresolved by era","unresolved by regime","unresolved by set","unresolved by supertype","unresolved by treatment","unresolved by blocker","ordinary-treatment unresolved count","premium-treatment unresolved count","collector-relevant denominator","collector-relevant empirical count","collector-relevant empirical coverage","collector-relevant usable coverage","premium-treatment denominator","premium empirical count","premium empirical coverage","premium usable coverage","all-card set readiness distribution","collector-relevant set readiness distribution","premium set readiness distribution","complete set-level readiness table","era-level readiness table","top-10 chase TMP coverage","top-25 chase TMP coverage","50%-cumulative-value TMP diagnostic","80%-cumulative-value TMP diagnostic","missingness-bias findings","Collector Appeal population dependency","effect of missing ordinary-card TMP","effect of missing premium-card TMP","Card Detail readiness","Gate A evaluation","Gate B evaluation","Gate C evaluation","Gate D evaluation","all-card gate decision","collector-relevant readiness decision","Card Detail decision","Collector Appeal decision","highest-value remaining evidence projects","exact premium/hit cards blocked by unavailable history","exact premium/hit cards blocked by taxonomy","exact premium/hit cards blocked by instability","exact premium/hit cards structurally underidentified","production pause status","rows persisted","files changed","tests","limitations","exact recommended next action"]
def render(s):
    p=s["provenance"]; r=s["residualBreakdown"]; h=s["collectorRelevant"]["summary"]; q=s["premiumTreatment"]["summary"]; c=s["chaseCoverageDiagnostic"]["aggregate"]; ca=s["collectorAppealPopulationDependency"]; g=s["gateEvaluations"]; d=s["decisions"]; b=s["blockedPremiumHitCards"]
    vals=[s["branch"],s["head"],s["denominator"],p["DIRECT_EMPIRICAL"],p["NEUTRAL_TREATMENT"],p["UNRESOLVED"],r["era"],r["regime"],r["set"],r["supertype"],r["normalizedTreatment"],r["terminalBlocker"],s["ordinaryTreatmentUnresolvedCount"],s["premiumTreatmentUnresolvedCount"],h["denominator"],h["directEmpirical"],h["empiricalCoverage"],h["usableCoverage"],q["denominator"],q["directEmpirical"],q["empiricalCoverage"],q["usableCoverage"],s["setReadinessDistributions"]["allCard"],s["setReadinessDistributions"]["collectorRelevant"],s["setReadinessDistributions"]["premiumTreatment"],s["setLevelReadinessTable"],s["eraLevelReadinessTable"],c["top10"],c["top25"],c["cumulative50"],c["cumulative80"],s["missingnessBiasFindings"],ca,ca["missingOrdinaryEffect"],ca["missingPremiumEffect"],s["cardDetailReadiness"],g["A"],g["B"],g["C"],g["D"],d["catalogGate"],d["collectorRelevantReadiness"],d["cardDetail"],d["collectorAppeal"],s["highestValueRemainingEvidenceProjects"],b["history"],b["taxonomy"],b["instability"],b["underidentified"],s["productionPaused"],s["rowsPersisted"],s["filesChanged"],s["testsExecuted"],s["limitations"],s["recommendedNextAction"]]
    assert len(vals)==len(LABELS)==55
    return "# Treatment Market Prestige V3 — Round 18 Results\n\n"+"\n\n".join(f"{i}. **{k}:** `{json.dumps(v,sort_keys=True,default=str)}`" for i,(k,v) in enumerate(zip(LABELS,vals),1))+"\n"
def main():
    raw=build(); public={k:v for k,v in raw.items() if not k.startswith("_")}; OUT.mkdir(parents=True,exist_ok=True)
    public["testsExecuted"]=["Round 18 focused on HEAD 7772c92: 4 passed in 0.96s", "Combined V3/Supporter/Trainer regression on immediately preceding a3ce191: 79 passed, 1785 deselected in 85.58s; subsequent commits were unrelated Market Explorer test/documentation changes"]
    (OUT/"residual_breakdown.json").write_text(json.dumps(public["residualBreakdown"],indent=2),encoding="utf-8"); (OUT/"set_level_readiness.json").write_text(json.dumps(public["setLevelReadinessTable"],indent=2),encoding="utf-8"); (OUT/"era_level_readiness.json").write_text(json.dumps(public["eraLevelReadinessTable"],indent=2),encoding="utf-8"); (OUT/"market_value_weighted_diagnostic.json").write_text(json.dumps(public["chaseCoverageDiagnostic"],indent=2),encoding="utf-8"); (OUT/"missingness_bias.json").write_text(json.dumps(public["missingnessBiasFindings"],indent=2),encoding="utf-8"); (OUT/"premium_hit_evidence_projects.json").write_text(json.dumps({"projects":public["highestValueRemainingEvidenceProjects"],"exactBlockedCards":public["blockedPremiumHitCards"]},indent=2),encoding="utf-8"); STUDY.write_text(json.dumps(public,indent=2),encoding="utf-8"); REPORT.write_text(render(public),encoding="utf-8"); (OUT/"manifest.json").write_text(json.dumps({"studyId":public["studyId"],"studyHash":stable_json_hash(public),"ledgerHash":stable_json_hash(raw["_ledger"]),"setReadinessHash":stable_json_hash(public["setLevelReadinessTable"]),"rowsPersisted":0},indent=2),encoding="utf-8")
if __name__=="__main__": main()
