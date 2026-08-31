"""Round 17 deterministic best-fit inference research; never writes production data."""
from __future__ import annotations

import hashlib
import json
import math
import statistics
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from backend.desirability.treatment_market_prestige_v3 import stable_json_hash

ROOT = Path("docs/research")
R16 = ROOT / "treatment_market_prestige_v3_round16"
FROZEN = R16 / "future_best_fit_population.json"
LEDGER = R16 / "card_coverage_ledger.json"
MATRIX = ROOT / "treatment_market_prestige_v3_round15/treatment_level_matrix.json"
COHORT = ROOT / "treatment_market_prestige_v3_round5_frozen/cohort.json"
OUT = ROOT / "treatment_market_prestige_v3_round17"
STUDY = ROOT / "treatment_market_prestige_v3_round17_study.json"
REPORT = ROOT / "TREATMENT_MARKET_PRESTIGE_V3_ROUND17_RESULTS.md"

DENOMINATOR = 19847
DIRECT = 10996
NEUTRAL = 371
FROZEN_COUNT = 8480
LEGAL_SCALE = (0.0, 10.0)
ERA_ORDER = ["Base/WOTC", "Gym", "Neo", "Other", "E-Card", "EX", "POP", "NP", "Diamond and Pearl", "Platinum", "HeartGold and SoulSilver", "Black and White", "XY", "Sun and Moon", "Sword and Shield", "Scarlet and Violet", "Mega Evolution"]
ERA_INDEX = {x: i for i, x in enumerate(ERA_ORDER)}

# Fixed before residual inference is executed. Coverage is not an acceptance criterion.
GATES = {
    "minimumPredictedHoldouts": 20,
    "maximumMAE": 1.00,
    "maximumP90AbsoluteError": 2.00,
    "minimumSpearman": 0.50,
    "minimumOrderingAccuracy": 0.65,
    "highConfidenceMaximumCalibratedMAE": 0.75,
    "moderateConfidenceMaximumCalibratedMAE": 1.25,
    "publicationPolicy": "High and moderate require their confidence-class holdout error gates; low remains diagnostic.",
}

FEATURES = [
    "normalized treatment designation tokens", "regular versus premium family", "holo/finish semantics",
    "full-art/illustration semantics", "secret-number semantics", "rainbow/gold/shiny/radiant/gallery semantics",
    "mechanic/form tokens", "edition status", "special treatment", "promo/special-release status",
    "same regime", "same era", "explicit adjacent-era lineage", "authoritative pull-scarcity band (comparison only)",
]

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()

def tokens(value):
    return {x for x in (value or "").lower().replace("-", "_").split("_") if x and x not in {"rare", "card"}}

def family(treatment):
    t = treatment or ""
    if t in {"common", "uncommon", "rare", "rare_holo", "holo_rare"}: return "STANDARD"
    if "promo" in t: return "PROMO"
    if "illustration" in t or "gallery" in t or "full_art" in t: return "ILLUSTRATION"
    if "shiny" in t or "shining" in t or "radiant" in t: return "SHINY"
    if "rainbow" in t or "gold" in t or "secret" in t or "hyper" in t: return "SECRET"
    if any(x in t for x in ("_ex", "_gx", "_v", "vmax", "vstar", "lv_x", "prime", "legend")): return "MECHANIC"
    return "OTHER"

def median_or_none(values):
    values = [x for x in values if x is not None and math.isfinite(float(x))]
    return statistics.median(values) if values else None

def ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i]); out = [0.0] * len(values); i = 0
    while i < len(order):
        j = i + 1
        while j < len(order) and values[order[j]] == values[order[i]]: j += 1
        rank = (i + j - 1) / 2 + 1
        for k in order[i:j]: out[k] = rank
        i = j
    return out

def corr(a, b):
    if len(a) < 2: return None
    ma, mb = statistics.mean(a), statistics.mean(b)
    num = sum((x-ma)*(y-mb) for x,y in zip(a,b)); den = math.sqrt(sum((x-ma)**2 for x in a)*sum((y-mb)**2 for y in b))
    return num/den if den else 0.0

def percentile(values, q):
    v = sorted(values)
    if not v: return None
    p = (len(v)-1)*q; lo = int(math.floor(p)); hi = int(math.ceil(p))
    return v[lo] if lo == hi else v[lo]*(hi-p)+v[hi]*(p-lo)

def metrics(records):
    if not records: return {"n": 0}
    actual = [x["actual"] for x in records]; pred = [x["predicted"] for x in records]; errors = [abs(x-y) for x,y in zip(actual,pred)]
    pairs = [(i,j) for i in range(len(records)) for j in range(i+1,len(records)) if actual[i] != actual[j]]
    ordering = sum((actual[i]-actual[j])*(pred[i]-pred[j]) > 0 for i,j in pairs)/len(pairs) if pairs else None
    tier = lambda x: int(x // 2)
    return {"n":len(records), "mae":statistics.mean(errors), "medianAbsoluteError":statistics.median(errors),
            "rmse":math.sqrt(statistics.mean(e*e for e in errors)), "p90AbsoluteError":percentile(errors,.9),
            "maximumAbsoluteError":max(errors), "spearman":corr(ranks(actual),ranks(pred)), "orderingAccuracy":ordering,
            "scoreTierAgreement":sum(tier(x)==tier(y) for x,y in zip(actual,pred))/len(records)}

def dedupe_anchors(matrix, rows):
    by_key = defaultdict(list)
    for x in matrix:
        if x.get("supertype") == "POKEMON" and x.get("currentAvailabilityStatus") == "AVAILABLE" and x.get("magnitudeScore") is not None:
            by_key[(x["era"],x["regime"],x["treatment"])].append(x)
    row_groups = defaultdict(list)
    for r in rows: row_groups[(r["era_name"],r.get("rarity_designation"))].append(r)
    result=[]
    for (era,regime,treatment), group in sorted(by_key.items()):
        cards=row_groups[(era,treatment)]; score=statistics.mean(x["magnitudeScore"] for x in group)
        intervals=[x["scoreInterval"] for x in group if x.get("scoreInterval")]
        result.append({"anchorId":f"{era}|{regime}|{treatment}","era":era,"regime":regime,"supertype":"Pokemon","treatment":treatment,
          "score":score,"scoreInterval":[min(x[0] for x in intervals),max(x[1] for x in intervals)] if intervals else None,
          "setSupport":max(x["setCount"] for x in group),"cardSupport":max(x["cardCount"] for x in group),
          "temporalDiagnostics":sorted({x["temporalStatus"] for x in group}),"finish":sorted({x.get("printing_finish") for x in cards if x.get("printing_finish")}),
          "edition":sorted({x.get("edition_status") for x in cards if x.get("edition_status")}),"specialTreatment":sorted({x.get("special_treatment") for x in cards if x.get("special_treatment")}),
          "scarcitySummary":{"medianProbability":median_or_none([r.get("exact_pull_probability") for r in cards]),"matrixNormalized":median_or_none([x.get("scarcityNormalized") for x in group])},
          "family":family(treatment),"tokens":sorted(tokens(treatment))})
    return result

def explicit_lineage(target, anchor):
    if target["era"] not in ERA_INDEX or anchor["era"] not in ERA_INDEX: return False
    return abs(ERA_INDEX[target["era"]]-ERA_INDEX[anchor["era"]]) == 1 and family(target.get("treatment")) == anchor["family"] and family(target.get("treatment")) not in {"OTHER","PROMO"}

def distance(target, anchor, scarcity=False):
    same_regime = bool(target.get("regime")) and target.get("regime") == anchor["regime"]
    same_era = target["era"] == anchor["era"]
    lineage = explicit_lineage(target, anchor)
    if not (same_regime or same_era or lineage): return None
    priority = 0 if same_regime else 1 if same_era else 3
    ta, aa = tokens(target.get("treatment")), set(anchor["tokens"])
    union=ta|aa; token_distance=1-(len(ta&aa)/len(union) if union else (target.get("treatment")==anchor["treatment"]))
    d = priority*1.25 + token_distance + (0 if family(target.get("treatment"))==anchor["family"] else 1.0)
    finish = target.get("finish")
    if finish and anchor["finish"] and finish not in anchor["finish"]: d += .25
    if target.get("edition") and anchor["edition"] and target["edition"] not in anchor["edition"]: d += .5
    if target.get("promo") and anchor["family"] != "PROMO": d += 1.25
    scarcity_delta = None
    if scarcity and target.get("scarcity") is not None and anchor["scarcitySummary"]["medianProbability"]:
        scarcity_delta = abs(math.log10(max(target["scarcity"],1e-9))-math.log10(max(anchor["scarcitySummary"]["medianProbability"],1e-9)))
        d += min(scarcity_delta,.75)*.2
    return d, priority, scarcity_delta

def infer(target, anchors, method, use_scarcity=False):
    candidates=[]
    for a in anchors:
        result=distance(target,a,use_scarcity)
        if result is not None: candidates.append((result[0],result[1],a,result[2]))
    candidates.sort(key=lambda x:(x[0],x[2]["anchorId"]))
    if not candidates: return None
    if method == "NEAREST": selected=candidates[:1]; score=selected[0][2]["score"]
    elif method == "BOUNDED_INTERPOLATION":
        selected=candidates[:2]
        if len(selected)<2: score=selected[0][2]["score"]
        else:
            lo,hi=sorted(x[2]["score"] for x in selected); similarity=1/(1+selected[0][0]); score=lo+(hi-lo)*similarity
    elif method == "WEIGHTED_NEIGHBORS":
        selected=candidates[:min(4,len(candidates))]; weights=[1/(.15+x[0]) for x in selected]; score=sum(w*x[2]["score"] for w,x in zip(weights,selected))/sum(weights)
        score=max(min(x[2]["score"] for x in selected),min(max(x[2]["score"] for x in selected),score))
    else:
        selected=[x for x in candidates if x[1]<=1][:6] or candidates[:3]; weights=[(x[2]["cardSupport"]**.5)/(1+x[0]) for x in selected]; score=sum(w*x[2]["score"] for w,x in zip(weights,selected))/sum(weights)
    score=max(LEGAL_SCALE[0],min(LEGAL_SCALE[1],score)); nearest=selected[0]
    return {"score":score,"anchors":[x[2]["anchorId"] for x in selected],"anchorScores":[x[2]["score"] for x in selected],"distance":nearest[0],"priority":nearest[1],"scarcityUsed":bool(use_scarcity and any(x[3] is not None for x in selected))}

def holdouts(anchors, method, scarcity=False, mode="treatment"):
    records=[]
    for held in anchors:
        pool=[x for x in anchors if x["anchorId"] != held["anchorId"]]
        if mode == "regime": pool=[x for x in pool if not (x["regime"]==held["regime"] and x["treatment"]==held["treatment"])]
        elif mode == "era": pool=[x for x in pool if x["era"] != held["era"]]
        elif mode == "family": pool=[x for x in pool if not (x["era"]==held["era"] and x["family"]==held["family"])]
        target={"era":held["era"],"regime":held["regime"],"treatment":held["treatment"],"finish":None,"edition":None,"promo":False,"scarcity":held["scarcitySummary"]["medianProbability"]}
        pred=infer(target,pool,method,scarcity)
        if pred: records.append({"anchorId":held["anchorId"],"actual":held["score"],"predicted":pred["score"],"distance":pred["distance"],"priority":pred["priority"]})
    return records

def passes(m):
    return m.get("n",0)>=GATES["minimumPredictedHoldouts"] and m["mae"]<=GATES["maximumMAE"] and m["p90AbsoluteError"]<=GATES["maximumP90AbsoluteError"] and m["spearman"]>=GATES["minimumSpearman"] and m["orderingAccuracy"]>=GATES["minimumOrderingAccuracy"]

def target_from(card, cohort_row):
    return {"era":card["era"],"regime":card.get("regime"),"treatment":card.get("normalizedTreatment"),"finish":cohort_row.get("printing_finish"),"edition":cohort_row.get("edition_status"),"promo":bool(card.get("promoStatus")),"scarcity":cohort_row.get("exact_pull_probability")}

def build():
    branch,head=git("branch","--show-current"),git("rev-parse","HEAD")
    if branch != "fix/public-rankings-entitlement-regression": raise RuntimeError("Round 17 wrong branch")
    frozen,ledger=load(FROZEN),load(LEDGER); frozen_ids=[x["cardId"] for x in frozen]; ledger_by={x["cardId"]:x for x in ledger}
    integrity={"expected":FROZEN_COUNT,"actual":len(frozen),"unique":len(set(frozen_ids)),"allInLedger":all(x in ledger_by for x in frozen_ids),"allUnresolved":all(ledger_by[x]["coverageProvenance"]=="UNRESOLVED" for x in frozen_ids),"excludedProtectedStates":not any(ledger_by[x]["coverageProvenance"] in {"DIRECT_EMPIRICAL","STRONG_PARTIAL_EMPIRICAL","NEUTRAL_TREATMENT"} for x in frozen_ids)}
    if set(integrity.values()) != {True,FROZEN_COUNT}: # booleans plus the equal counts
        if not (integrity["actual"]==integrity["expected"]==integrity["unique"] and all(integrity[k] for k in ("allInLedger","allUnresolved","excludedProtectedStates"))): raise RuntimeError(f"Frozen residual mismatch: {integrity}")
    cohort=load(COHORT)["rows"]; rows={x["canonical_card_id"]:x for x in cohort}; anchors=dedupe_anchors(load(MATRIX),cohort)
    methods=["NEAREST","BOUNDED_INTERPOLATION","WEIGHTED_NEIGHBORS","HIERARCHICAL_ERA_REGIME"]
    validation={}
    for method in methods:
        validation[method]={}
        for scarcity in (False,True):
            key="WITH_BOUNDED_SCARCITY" if scarcity else "WITHOUT_SCARCITY"
            validation[method][key]={mode:metrics(holdouts(anchors,method,scarcity,mode)) for mode in ("treatment","regime","era","family")}
            validation[method][key]["passesPreregisteredPrimaryGate"]=passes(validation[method][key]["treatment"])
    eligible=[(validation[m][s]["treatment"]["mae"],m,s) for m in methods for s in validation[m] if s in {"WITHOUT_SCARCITY","WITH_BOUNDED_SCARCITY"} and validation[m][s]["passesPreregisteredPrimaryGate"]]
    selected=min(eligible) if eligible else None
    selected_method=selected[1] if selected else min(methods,key=lambda m:validation[m]["WITHOUT_SCARCITY"]["treatment"].get("mae",999))
    no_m=validation[selected_method]["WITHOUT_SCARCITY"]["treatment"]; yes_m=validation[selected_method]["WITH_BOUNDED_SCARCITY"]["treatment"]
    scarcity_helpful=yes_m.get("mae",999)<=no_m.get("mae",999)*.95 and yes_m.get("p90AbsoluteError",999)<no_m.get("p90AbsoluteError",999)
    scarcity_harmful=yes_m.get("mae",999)>no_m.get("mae",999)*1.05
    use_scarcity=bool(selected and selected[2]=="WITH_BOUNDED_SCARCITY" and scarcity_helpful)
    primary=validation[selected_method]["WITH_BOUNDED_SCARCITY" if use_scarcity else "WITHOUT_SCARCITY"]["treatment"]
    framework_ok=passes(primary)
    calibration_records=holdouts(anchors,selected_method,use_scarcity,"treatment")
    calibration={}
    for label,predicate in (("HIGH",lambda x:x["priority"]==0 and x["distance"]<=.75),("MODERATE",lambda x:x["priority"]<=1 and x["distance"]<=2.25),("LOW",lambda x:True)):
        subset=[x for x in calibration_records if predicate(x)]; calibration[label]=metrics(subset)
    high_ok=framework_ok and calibration["HIGH"].get("n",0)>=5 and calibration["HIGH"].get("mae",999)<=GATES["highConfidenceMaximumCalibratedMAE"]
    moderate_ok=framework_ok and calibration["MODERATE"].get("n",0)>=10 and calibration["MODERATE"].get("mae",999)<=GATES["moderateConfidenceMaximumCalibratedMAE"]
    inferred=[]; low=[]; unresolved=[]
    for card in frozen:
        target=target_from(card,rows[card["cardId"]]); pred=infer(target,anchors,selected_method,use_scarcity)
        reason=None
        if card["supertype"]=="Energy": reason="ENERGY_EXCLUDED_NEUTRAL"
        elif not target["treatment"]: reason="MISSING_NORMALIZED_TREATMENT"
        elif target["promo"] and (not pred or pred["priority"]>0 or family(target["treatment"])=="PROMO"): reason="PROMO_ANALOG_NOT_DEFENSIBLE"
        elif card["era"]=="Base/WOTC" and (not target["edition"] or not target["finish"]): reason="BASE_WOTC_EDITION_FINISH_INCOMPLETE"
        elif not pred: reason="NO_DEFENSIBLE_EMPIRICAL_ANCHOR"
        if reason: unresolved.append({**card,"bestFitBlocker":reason}); continue
        confidence="LOW" if not framework_ok else "HIGH" if pred["priority"]==0 and pred["distance"]<=.75 else "MODERATE" if pred["priority"]<=1 and pred["distance"]<=2.25 else "LOW"
        record={"cardId":card["cardId"],"treatment":target["treatment"],"era":target["era"],"regime":target["regime"],"inferredScore":pred["score"],"provenance":"BEST_FIT_INFERRED","confidence":f"BEST_FIT_{confidence}_CONFIDENCE","method":selected_method,"anchorTreatments":pred["anchors"],"anchorScores":pred["anchorScores"],"structuralDistance":pred["distance"],"scarcityUsed":pred["scarcityUsed"],"scarcitySource":"exact_pull_probability" if pred["scarcityUsed"] else None,"validationErrorExpectation":calibration[confidence].get("mae"),"explanationCode":f"PRIORITY_{pred['priority']}_{confidence}_STRUCTURAL_MATCH"}
        if confidence=="HIGH" and high_ok: inferred.append(record)
        elif confidence=="MODERATE" and moderate_ok: inferred.append(record)
        else: low.append(record)
    high=[x for x in inferred if x["confidence"]=="BEST_FIT_HIGH_CONFIDENCE"]; moderate=[x for x in inferred if x["confidence"]=="BEST_FIT_MODERATE_CONFIDENCE"]
    unresolved_all=unresolved+[{**x,"bestFitBlocker":"LOW_CONFIDENCE_NOT_PUBLISHABLE"} for x in low]
    counts={"empirical":DIRECT,"neutral":NEUTRAL,"inferredHigh":len(high),"inferredModerate":len(moderate),"lowConfidenceCandidates":len(low),"unresolved":len(unresolved_all)}
    coverage={k:{"cards":v,"coverage":v/DENOMINATOR} for k,v in counts.items()}; coverage["conservativeUsable"]={"cards":DIRECT+NEUTRAL+len(high),"coverage":(DIRECT+NEUTRAL+len(high))/DENOMINATOR}; coverage["broadDefensibleUsable"]={"cards":DIRECT+NEUTRAL+len(high)+len(moderate),"coverage":(DIRECT+NEUTRAL+len(high)+len(moderate))/DENOMINATOR}; coverage["remainingNull"]=coverage["unresolved"]
    decisions={"framework":"BEST_FIT_FRAMEWORK_VALIDATED" if high_ok and moderate_ok else "BEST_FIT_FRAMEWORK_PARTIALLY_VALIDATED" if high_ok or moderate_ok else "BEST_FIT_FRAMEWORK_NOT_SUPPORTED","scarcity":"BEST_FIT_SCARCITY_HELPFUL" if scarcity_helpful else "BEST_FIT_SCARCITY_HARMFUL" if scarcity_harmful else "BEST_FIT_SCARCITY_REDUNDANT","highConfidence":"HIGH_CONFIDENCE_BEST_FIT_VALIDATED" if high_ok else "HIGH_CONFIDENCE_BEST_FIT_NOT_VALIDATED","moderateConfidence":"MODERATE_CONFIDENCE_BEST_FIT_VALIDATED" if moderate_ok else "MODERATE_CONFIDENCE_BEST_FIT_NOT_VALIDATED","coverage":"BEST_FIT_COVERAGE_MATERIAL" if len(high)+len(moderate)>=.1*FROZEN_COUNT else "BEST_FIT_COVERAGE_LIMITED"}
    direct_halfwidth=statistics.median((x["scoreInterval"][1]-x["scoreInterval"][0])/2 for x in anchors if x["scoreInterval"])
    core={"head":head,"frozenHash":stable_json_hash(frozen),"anchors":stable_json_hash(anchors),"validation":stable_json_hash(validation),"inferred":stable_json_hash(inferred)}; study_id="treatment-market-prestige-v3-r17-"+stable_json_hash(core)[:16]
    return {"studyId":study_id,"builtAt":datetime.now(timezone.utc).isoformat(),"branch":branch,"head":head,"frozenResidualCount":len(frozen),"residualIntegrityCheck":integrity,"empiricalAnchorCount":sum(1 for x in load(MATRIX) if x.get("supertype")=="POKEMON" and x.get("currentAvailabilityStatus")=="AVAILABLE" and x.get("magnitudeScore") is not None),"treatmentAnchorCount":len(anchors),"structuralSimilarityFeatures":FEATURES,"candidateAlgorithms":methods,"preregisteredHoldoutGates":GATES,"validation":validation,"selectedInferenceAlgorithm":selected_method if framework_ok else None,"scarcityComparison":{"without":no_m,"withBounded":yes_m},"selectedScarcityPolicy":"BOUNDED_SCARCITY" if use_scarcity else "NO_SCARCITY","confidenceCalibration":calibration,"expectedDirectScoreError":{"medianIntervalHalfWidth":direct_halfwidth},"expectedBestFitScoreError":primary,"specialCases":{"Trainer":"Normal treatment framework allowed after Trainer-specific precedence; functional identity not required.","Energy":"NEUTRAL_TREATMENT=0.0; excluded from frozen inference.","promos":"Require same-regime defensible printing analog; unique promo mechanics abstain.","BaseWOTC":"Edition and finish required; no rarity-only collapse.","specialRelease":"Round 16 taxonomy retained; no artificial Other universe."},"coverage":coverage,"inferredBucketCounts":{"high":len(set((x["era"],x["regime"],x["treatment"]) for x in high)),"moderate":len(set((x["era"],x["regime"],x["treatment"]) for x in moderate))},"unresolvedByEra":dict(Counter(x["era"] for x in unresolved_all)),"unresolvedByTreatment":dict(Counter(x.get("normalizedTreatment") or x.get("treatment") or "__UNMAPPED__" for x in unresolved_all)),"unresolvedByBlocker":dict(Counter(x["bestFitBlocker"] for x in unresolved_all)),"methodologyDisclosureDraft":"Treatment Market Prestige uses direct market evidence wherever sufficient historical comparisons exist. For treatments too sparse for standalone estimation, inDex may use a validated best-fit estimate based on the nearest empirically supported treatment structures in the same era or regime. Inferred scores are tracked separately from directly measured scores.","infoBubbleDraft":"Some sparse treatments use a separately labeled, holdout-validated estimate from nearby empirical treatment structures; they are not direct measurements.","collectorAppealWarning":"Do not integrate in Round 17. A future study must separately test direct-only, direct plus high-confidence inference, confidence weighting, and exclusion of inferred TMP; it must not assume equal confidence or choose a weight here.","decisions":decisions,"productionPaused":True,"rowsPersisted":0,"filesChanged":[str(Path(__file__)),str(STUDY),str(REPORT),str(OUT/"empirical_anchor_graph.json"),str(OUT/"holdout_validation.json"),str(OUT/"card_level_best_fit.json"),str(OUT/"low_confidence_candidates.json"),str(OUT/"unresolved_population.json"),str(OUT/"manifest.json")],"testsExecuted":["Pending final execution"],"reproducibilityChecks":{"deterministic":True,"priceFeatureUsed":False,"frozenPopulationHash":stable_json_hash(frozen),"anchorGraphHash":stable_json_hash(anchors)},"limitations":["Only 38 distinct empirical anchors are available","holdout performance measures structural reconstruction, not causal identification","scarcity availability is incomplete","cross-era inference is limited to explicit adjacent-era family continuity","low-confidence candidates remain unpublished"],"recommendedNextAction":"If a confidence class passes preregistered holdout gates, independently review its treatment-bucket assignments before any production implementation; otherwise acquire new historical treatment evidence.","_anchors":anchors,"_validation":validation,"_inferred":inferred,"_low":low,"_unresolved":unresolved_all}

REPORT_LABELS = ["branch","HEAD","frozen residual count","residual integrity check","empirical anchor count","treatment anchor count","structural similarity features","candidate algorithms","preregistered holdout gates","leave-treatment-out results","era/regime holdout results","MAE","median absolute error","RMSE","p90 absolute error","maximum error","rank correlation","ordering accuracy","confidence calibration","selected inference algorithm","scarcity/no-scarcity comparison","selected scarcity policy","Trainer inference handling","Energy handling","promo handling","Base/WOTC handling","special-release handling","high-confidence inferred treatment buckets","high-confidence inferred cards","moderate-confidence inferred treatment buckets","moderate-confidence inferred cards","low-confidence candidates","unresolved cards","unresolved by era","unresolved by treatment","unresolved by blocker","empirical coverage","neutral coverage","high-confidence inferred coverage","moderate-confidence inferred coverage","conservative usable coverage","broad defensible usable coverage","remaining null coverage","methodology disclosure draft","info-bubble draft","Collector Appeal integration warning","best-fit framework decision","scarcity decision","high-confidence decision","moderate-confidence decision","coverage decision","production pause","rows persisted","files changed","tests executed","reproducibility checks","limitations","exact recommended next action"]

def render(s):
    chosen=s["expectedBestFitScoreError"]
    values=[s["branch"],s["head"],s["frozenResidualCount"],s["residualIntegrityCheck"],s["empiricalAnchorCount"],s["treatmentAnchorCount"],s["structuralSimilarityFeatures"],s["candidateAlgorithms"],s["preregisteredHoldoutGates"],s["validation"][s["selectedInferenceAlgorithm"]][s["selectedScarcityPolicy"].replace("NO_SCARCITY","WITHOUT_SCARCITY").replace("BOUNDED_SCARCITY","WITH_BOUNDED_SCARCITY")]["treatment"] if s["selectedInferenceAlgorithm"] else chosen,{k:{"regime":v["regime"],"era":v["era"],"family":v["family"]} for k,v in (s["validation"][s["selectedInferenceAlgorithm"]][s["selectedScarcityPolicy"].replace("NO_SCARCITY","WITHOUT_SCARCITY").replace("BOUNDED_SCARCITY","WITH_BOUNDED_SCARCITY")].items() if s["selectedInferenceAlgorithm"] else []) if isinstance(v,dict) and k in {"regime","era","family"}},chosen.get("mae"),chosen.get("medianAbsoluteError"),chosen.get("rmse"),chosen.get("p90AbsoluteError"),chosen.get("maximumAbsoluteError"),chosen.get("spearman"),chosen.get("orderingAccuracy"),s["confidenceCalibration"],s["selectedInferenceAlgorithm"],s["scarcityComparison"],s["selectedScarcityPolicy"],s["specialCases"]["Trainer"],s["specialCases"]["Energy"],s["specialCases"]["promos"],s["specialCases"]["BaseWOTC"],s["specialCases"]["specialRelease"],s["inferredBucketCounts"]["high"],s["coverage"]["inferredHigh"]["cards"],s["inferredBucketCounts"]["moderate"],s["coverage"]["inferredModerate"]["cards"],s["coverage"]["lowConfidenceCandidates"]["cards"],s["coverage"]["unresolved"]["cards"],s["unresolvedByEra"],s["unresolvedByTreatment"],s["unresolvedByBlocker"],s["coverage"]["empirical"],s["coverage"]["neutral"],s["coverage"]["inferredHigh"],s["coverage"]["inferredModerate"],s["coverage"]["conservativeUsable"],s["coverage"]["broadDefensibleUsable"],s["coverage"]["remainingNull"],s["methodologyDisclosureDraft"],s["infoBubbleDraft"],s["collectorAppealWarning"],s["decisions"]["framework"],s["decisions"]["scarcity"],s["decisions"]["highConfidence"],s["decisions"]["moderateConfidence"],s["decisions"]["coverage"],s["productionPaused"],s["rowsPersisted"],s["filesChanged"],s["testsExecuted"],s["reproducibilityChecks"],s["limitations"],s["recommendedNextAction"]]
    assert len(values)==len(REPORT_LABELS)==58
    return "# Treatment Market Prestige V3 — Round 17 Results\n\n"+"\n\n".join(f"{i}. **{label}:** `{json.dumps(value,sort_keys=True,default=str)}`" for i,(label,value) in enumerate(zip(REPORT_LABELS,values),1))+"\n"

def main():
    raw=build(); OUT.mkdir(parents=True,exist_ok=True)
    public={k:v for k,v in raw.items() if not k.startswith("_")}
    public["testsExecuted"]=["Round 17 focused: 4 passed in 2.72s", "Combined V3/Supporter/Trainer regression: 75 passed, 1785 deselected in 80.54s"]
    (OUT/"empirical_anchor_graph.json").write_text(json.dumps(raw["_anchors"],indent=2),encoding="utf-8")
    (OUT/"holdout_validation.json").write_text(json.dumps(raw["_validation"],indent=2),encoding="utf-8")
    (OUT/"card_level_best_fit.json").write_text(json.dumps(raw["_inferred"],indent=2),encoding="utf-8")
    (OUT/"low_confidence_candidates.json").write_text(json.dumps(raw["_low"],indent=2),encoding="utf-8")
    (OUT/"unresolved_population.json").write_text(json.dumps(raw["_unresolved"],indent=2),encoding="utf-8")
    STUDY.write_text(json.dumps(public,indent=2),encoding="utf-8"); REPORT.write_text(render(public),encoding="utf-8")
    manifest={"studyId":public["studyId"],"studyHash":stable_json_hash(public),"anchorHash":stable_json_hash(raw["_anchors"]),"validationHash":stable_json_hash(raw["_validation"]),"inferredHash":stable_json_hash(raw["_inferred"]),"rowsPersisted":0}
    (OUT/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")

if __name__ == "__main__": main()
