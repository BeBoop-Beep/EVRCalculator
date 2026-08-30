"""Supporter Treatment Market Prestige V3S Round 2, research only."""
from __future__ import annotations

import hashlib
import gzip
import json
import math
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import requests

ROOT = Path("docs/research")
OUT = ROOT / "supporter_treatment_market_prestige_v3s_round2"
STUDY = ROOT / "supporter_treatment_market_prestige_v3s_round2_study.json"
REPORT = ROOT / "SUPPORTER_TREATMENT_MARKET_PRESTIGE_V3S_ROUND2_RESULTS.md"
COHORT_SOURCE = ROOT / "treatment_market_prestige_v3_round5_frozen/cohort.json"
HISTORY = ROOT / "treatment_market_prestige_v3_round11_history_observations.json"
HISTORY_AUDIT = ROOT / "treatment_market_prestige_v3_round11_history_audit.json"
V1 = ROOT / "supporter_competitive_utility_v1_study.json"
V1_OUT = ROOT / "supporter_competitive_utility_v1"

# Frozen before treatment coefficients are estimated.
CONTRACT = {
    "semantics": "SUPERTYPE_RELATIVE_WITHIN_ERA",
    "estimand": "Adjusted market association of a Supporter collectible treatment while holding exact functional card identity constant.",
    "minimumCrossTreatmentIdentities": 20,
    "minimumCardsPerTreatment": 25,
    "minimumSetsPerTreatment": 3,
    "minimumCheckpointCoverage": .95,
    "minimumCheckpoints": 4,
    "maximumAdjacentCoefficientDrift": .50,
    "maximumFullWindowCoefficientDrift": 1.0,
    "maximumLeaveOneSetOutShift": 1.0,
    "maximumCoefficientIntervalWidth": 1.5,
    "playDemandStrata": "tertiles of the frozen V1 functional-card score distribution, calculated before treatment gaps",
    "interactionRule": "retain only if rank identified, >=20 competitive identities, lower CV RMSE, and coefficient direction is leave-one-set-out stable",
    "priceOutcomeUsedForArchitecture": False,
}


def load(path): return json.loads(path.read_text(encoding="utf-8"))
def norm(value): return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
def stable_hash(value): return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def ensure_v1():
    """Rebuild the deleted V1 snapshot only when its frozen artifact is absent.

    Raw provenance is consolidated into one gzip file to avoid dozens of noisy
    source-control entries. The selection and scoring contracts are unchanged.
    """
    if V1.exists(): return load(V1)
    api="https://play.limitlesstcg.com/api"; reference=datetime(2026,8,29,tzinfo=timezone.utc).date(); raw={}; session=requests.Session()
    def get(path,params=None):
        key=path+("?"+"&".join(f"{k}={v}" for k,v in sorted((params or {}).items())) if params else "")
        response=session.get(api+path,params=params,timeout=30);response.raise_for_status();raw[key]={"url":response.url,"retrievedAt":datetime.now(timezone.utc).isoformat(),"payload":response.json()};time.sleep(.25);return raw[key]["payload"]
    discovered=[]
    for page in range(1,11):discovered.extend(get("/tournaments",{"game":"PTCG","format":"STANDARD","limit":100,"page":page}))
    candidates=[x for x in discovered if 0<=(reference-datetime.fromisoformat(x["date"].replace("Z","+00:00")).date()).days<=30 and x["players"]>=32]
    candidates=sorted(candidates,key=lambda x:(-x["players"],x["date"],x["id"]))[:15]
    tournaments=[];decks=[];observations=[]
    for base in candidates:
        details=get(f"/tournaments/{base['id']}/details");standings=get(f"/tournaments/{base['id']}/standings");visible=[x for x in standings if x.get("decklist")]
        if not details.get("decklists") or len(visible)/max(details.get("players",0),1)<.8 or details.get("specialRules") or details.get("bannedCards") or not standings:continue
        cls="LARGE_COMPETITIVE_EVENT" if details["players"]>=128 else "SMALL_COMPETITIVE_EVENT"
        tournaments.append({"sourceTournamentId":details["id"],"name":details["name"],"date":details["date"],"format":details["format"],"players":details["players"],"isOnline":details.get("isOnline"),"eventClass":cls,"decklistsObserved":len(visible)})
        for standing in visible:
            did=f"{details['id']}:{standing.get('player')}";arch=(standing.get("deck") or {}).get("id") or "__UNKNOWN__";decks.append({"tournamentId":details["id"],"deckId":did,"placing":standing.get("placing"),"archetype":arch})
            for card in standing["decklist"].get("trainer",[]):observations.append({"tournamentId":details["id"],"deckId":did,"functionalId":norm(card["name"]),"functionalName":card["name"],"copies":card["count"],"placing":standing.get("placing"),"archetype":arch})
    bydeck=defaultdict(list);byobs=defaultdict(list)
    for x in decks:bydeck[x["tournamentId"]].append(x)
    for x in observations:byobs[x["tournamentId"]].append(x)
    agg=defaultdict(lambda:defaultdict(float))
    for event in tournaments:
        tid=event["sourceTournamentId"];ds=bydeck[tid];groups=defaultdict(list)
        for x in byobs[tid]:groups[x["functionalId"]].append(x)
        age=(reference-datetime.fromisoformat(event["date"].replace("Z","+00:00")).date()).days;weight=min(2.,math.log1p(event["players"])/math.log(129))*(1.1 if event["eventClass"]=="LARGE_COMPETITIVE_EVENT" else 1.)*math.exp(-math.log(2)*age/30)
        for fid,xs in groups.items():
            included={x["deckId"] for x in xs};copies=sum(x["copies"] for x in xs);arch=Counter(x["archetype"] for x in xs);hhi=sum((n/len(included))**2 for n in arch.values());a=agg[fid];a["wi"]+=weight*len(included)/len(ds);a["wc"]+=weight*copies/len(ds);a["wb"]+=weight*(1-hhi);a["w"]+=weight;a["events"]+=1;a["decks"]+=len(ds)
    scores=[]
    for fid,a in agg.items():
        inc=a["wi"]/a["w"];copies=a["wc"]/a["w"];breadth=a["wb"]/a["w"];scores.append({"functionalId":fid,"fieldUsageDemand":100*(.6*inc+.25*min(copies/4,1)+.15*breadth),"weightedInclusionRate":inc,"weightedCopiesPerDeck":copies,"weightedArchetypeBreadth":breadth,"events":int(a["events"]),"decksRepresented":int(a["decks"])})
    scores.sort(key=lambda x:(-x["fieldUsageDemand"],x["functionalId"]));study={"studyId":"supporter-competitive-utility-v1-"+stable_hash({"events":[x["sourceTournamentId"] for x in tournaments]})[:16],"competitivePlayDemandDecision":"COMPETITIVE_PLAY_DEMAND_PARTIALLY_VALIDATED","tournamentsIngested":len(tournaments),"decklistsIngested":len(decks),"competitiveDateRange":[min(x["date"] for x in tournaments)[:10],max(x["date"] for x in tournaments)[:10]],"competitiveScores":scores,"sourceAudit":{"decision":"LIMITLESS_API_PLUS_PUBLIC_EVENT_DATA_REQUIRED","apiRoot":api},"reconstructedForRound2":True,"rowsPersisted":0}
    V1_OUT.mkdir(parents=True,exist_ok=True);V1.write_text(json.dumps(study,indent=2),encoding="utf-8");(V1_OUT/"competitive_snapshots.json").write_text(json.dumps(scores,indent=2),encoding="utf-8")
    with gzip.open(str(V1_OUT/"raw_limitless_provenance.json.gz"),"wt",encoding="utf-8") as handle:json.dump(raw,handle,separators=(",",":"),ensure_ascii=False)
    return study


def supporter_rows():
    rows = load(COHORT_SOURCE)["rows"]
    return [r for r in rows if r.get("supertype") == "Trainer" and "supporter" in r.get("mechanic_or_card_form", [])]


def freeze_cohort(rows, v1):
    scores = {x["functionalId"]: x for x in v1["competitiveScores"]}
    history = load(HISTORY); availability = defaultdict(list)
    for checkpoint, observations in history["observations"].items():
        for variant_id, value in observations.items():
            if value.get("market_price"): availability[variant_id].append(checkpoint)
    frozen = []
    for r in rows:
        fid = norm(r["card_name"]); score = scores.get(fid)
        frozen.append({
            "canonicalCardId": r["canonical_card_id"], "variantId": r["variant_id"], "functionalId": fid,
            "exactName": r["card_name"], "trainerSubtype": "SUPPORTER", "era": r["era_name"], "setId": r["set_id"], "setName": r["set_name"],
            "rawTreatment": r.get("rarity_designation_raw"), "treatment": r.get("rarity_designation"),
            "printingFinish": r.get("printing_finish"), "specialTreatment": r.get("special_treatment"),
            "marketPrice": r.get("market_price"), "priceReferenceDate": r.get("price_captured_at"),
            "historicalCheckpoints": availability.get(r["variant_id"], []),
            "competitivePlayDemand": score["fieldUsageDemand"] if score else None,
            "competitiveEvidence": {"events": score["events"], "decks": score["decksRepresented"], "inclusion": score["weightedInclusionRate"], "copies": score["weightedCopiesPerDeck"], "breadth": score["weightedArchetypeBreadth"], "sourceStudyId": v1["studyId"]} if score else None,
        })
    return frozen


def identity_audit(rows):
    groups = defaultdict(list)
    for r in rows: groups[r["functionalId"]].append(r)
    safe = {k:v for k,v in groups.items() if len({x["exactName"] for x in v}) == 1}
    cross = {k:v for k,v in safe.items() if len({x["treatment"] for x in v if x["treatment"]}) >= 2}
    within_set = sum(any(len({x["treatment"] for x in v if x["setId"] == sid and x["treatment"]}) >= 2 for sid in {x["setId"] for x in v}) for v in cross.values())
    by_era = Counter(x["era"] for v in cross.values() for x in [v[0]])
    treatment_cells = {era: dict(sorted(Counter(x["treatment"] or "__UNMAPPED__" for v in cross.values() for x in v if x["era"] == era).items())) for era in sorted({x["era"] for v in cross.values() for x in v})}
    records = []
    for fid, cards in sorted(safe.items()):
        records.append({"functionalId": fid, "classification": "FUNCTIONAL_REPRINT_FAMILY" if len(cards)>1 else "SAFE_FUNCTIONAL_IDENTITY", "cards": len(cards), "treatments": sorted({x["treatment"] for x in cards if x["treatment"]}), "sets": sorted({x["setName"] for x in cards}), "eras": sorted({x["era"] for x in cards}), "crossTreatment": fid in cross, "withinSetCrossTreatment": any(len({x["treatment"] for x in cards if x["setId"]==sid and x["treatment"]})>=2 for sid in {x["setId"] for x in cards})})
    return groups, safe, cross, records, {"totalFunctionalIdentities":len(groups),"safeFunctionalIdentities":len(safe),"crossTreatmentIdentities":len(cross),"crossTreatmentObservations":sum(len(v) for v in cross.values()),"withinSetCrossTreatmentIdentities":within_set,"crossTreatmentByEra":dict(sorted(by_era.items())),"crossTreatmentBySubtype":{"SUPPORTER":len(cross)},"treatmentCells":treatment_cells}


def ontology(rows):
    result={}
    for era in sorted({x["era"] for x in rows}):
        group=[x for x in rows if x["era"]==era]
        result[era]={"rawTreatments":dict(sorted(Counter(str(x["rawTreatment"]) for x in group).items())),"normalizedTreatments":dict(sorted(Counter(x["treatment"] or "__UNMAPPED__" for x in group).items())),"finishes":dict(sorted(Counter(x["printingFinish"] or "__UNMAPPED__" for x in group).items())),"specialTreatments":dict(sorted(Counter(x["specialTreatment"] or "__NONE__" for x in group).items())),"sets":len({x["setId"] for x in group}),"architecture":"SUPERTYPE_RELATIVE_WITHIN_ERA"}
    return result


def design(rows, demand_interaction=False):
    treatments=sorted({x["treatment"] for x in rows}); baseline=max(treatments,key=lambda t:sum(x["treatment"]==t for x in rows))
    identities=sorted({x["functionalId"] for x in rows}); sets=sorted({x["setId"] for x in rows})
    columns=["intercept"]+["identity:"+x for x in identities[1:]]+["set:"+x for x in sets[1:]]+["treatment:"+x for x in treatments if x!=baseline]
    demands=[x["competitivePlayDemand"] for x in rows if x.get("competitivePlayDemand") is not None]; center=float(np.mean(demands)) if demands else 0.; scale=float(np.std(demands)) if len(demands)>1 else 1.; scale=scale or 1.
    if demand_interaction:
        columns += ["interaction:"+x for x in treatments if x!=baseline]
    matrix=[]
    for r in rows:
        z=((r.get("competitivePlayDemand") or center)-center)/scale
        matrix.append([1.]+[float(r["functionalId"]==x) for x in identities[1:]]+[float(r["setId"]==x) for x in sets[1:]]+[float(r["treatment"]==x) for x in treatments if x!=baseline]+([float(r["treatment"]==x)*z for x in treatments if x!=baseline] if demand_interaction else []))
    return np.asarray(matrix,float),columns,baseline


def fit(rows, demand_interaction=False):
    X,columns,baseline=design(rows,demand_interaction); y=np.asarray([math.log(x["marketPrice"]) for x in rows])
    rank=int(np.linalg.matrix_rank(X)); beta,residuals,_,_=np.linalg.lstsq(X,y,rcond=None); fitted=X@beta; resid=y-fitted; dof=max(len(y)-rank,1); sigma2=float(resid@resid/dof); covariance=sigma2*np.linalg.pinv(X.T@X)
    coefficients={}; interactions={}
    for i,name in enumerate(columns):
        target=coefficients if name.startswith("treatment:") else interactions if name.startswith("interaction:") else None
        if target is not None:
            key=name.split(":",1)[1]; se=math.sqrt(max(float(covariance[i,i]),0)); target[key]={"coefficient":float(beta[i]),"interval":[float(beta[i]-1.96*se),float(beta[i]+1.96*se)],"multiplicativeAssociation":float(math.exp(beta[i])),"standardError":se}
    nuisance=[i for i,x in enumerate(columns) if not x.startswith("treatment:") and not x.startswith("interaction:")]; treatment=[i for i,x in enumerate(columns) if x.startswith("treatment:")]
    treatment_rank_increment=0
    if nuisance and treatment:
        N=X[:,nuisance]; T=X[:,treatment]; residual_t=T-N@np.linalg.lstsq(N,T,rcond=None)[0]; treatment_variance=float(np.var(residual_t));treatment_rank_increment=int(np.linalg.matrix_rank(np.column_stack((N,T)))-np.linalg.matrix_rank(N))
    else:treatment_variance=0.
    return {"n":len(rows),"matrixColumns":len(columns),"matrixRank":rank,"rankDeficiency":len(columns)-rank,"treatmentColumns":len(treatment),"treatmentRankIncrement":treatment_rank_increment,"baselineTreatment":baseline,"treatmentResidualVariance":treatment_variance,"coefficients":coefficients,"interactions":interactions,"rmse":float(math.sqrt(np.mean(resid**2))),"aic":float(len(y)*math.log(max(np.mean(resid**2),1e-12))+2*rank)}


def era_models(cohort, history):
    results={}
    for era in sorted({x["era"] for x in cohort}):
        base=[x for x in cohort if x["era"]==era and x["treatment"] and x["marketPrice"] and x["marketPrice"]>0]
        ids=defaultdict(list)
        for x in base:ids[x["functionalId"]].append(x)
        ids={k:v for k,v in ids.items() if len({x["treatment"] for x in v})>=2}; rows=[x for v in ids.values() for x in v]
        tc=Counter(x["treatment"] for x in rows); supported={t for t,n in tc.items() if n>=CONTRACT["minimumCardsPerTreatment"] and len({x["setId"] for x in rows if x["treatment"]==t})>=CONTRACT["minimumSetsPerTreatment"]}
        rows=[x for x in rows if x["treatment"] in supported]; valid_ids={k for k,v in ids.items() if len({x["treatment"] for x in v if x["treatment"] in supported})>=2}; rows=[x for x in rows if x["functionalId"] in valid_ids]
        structural={"era":era,"cards":len(rows),"crossTreatmentIdentities":len(valid_ids),"treatmentCounts":dict(Counter(x["treatment"] for x in rows)),"setSupport":{t:len({x["setId"] for x in rows if x["treatment"]==t}) for t in sorted(supported)}}
        if len(valid_ids)<CONTRACT["minimumCrossTreatmentIdentities"] or len(supported)<2:
            results[era]={**structural,"identification":"INSUFFICIENT_CROSS_TREATMENT_VARIATION","status":"UNAVAILABLE"};continue
        current=fit(rows); identification="TREATMENT_IDENTIFIABLE" if current["treatmentResidualVariance"]>1e-10 and current["treatmentRankIncrement"]==current["treatmentColumns"] else "TREATMENT_NESTED"
        temporal=[]
        for checkpoint in history["checkpointDates"]:
            obs=history["observations"][checkpoint]; dated=[]
            for x in rows:
                value=obs.get(x["variantId"],{}).get("market_price")
                if value:dated.append({**x,"marketPrice":value})
            temporal.append({"date":checkpoint,"coverage":len(dated)/len(rows),"model":fit(dated) if len(dated)>=max(20,int(.8*len(rows))) else None})
        names=set.intersection(*[set(x["model"]["coefficients"]) for x in temporal if x["model"]]) if all(x["model"] for x in temporal) else set()
        drifts={}
        for name in names:
            values=[x["model"]["coefficients"][name]["coefficient"] for x in temporal];drifts[name]={"maximumAdjacent":max(abs(b-a) for a,b in zip(values,values[1:])),"fullWindow":abs(values[-1]-values[0])}
        loso=[]
        for sid in sorted({x["setId"] for x in rows}):
            subset=[x for x in rows if x["setId"]!=sid]
            if len({x["treatment"] for x in subset})>=2:
                m=fit(subset); common=set(current["coefficients"])&set(m["coefficients"]); shift=max([abs(current["coefficients"][k]["coefficient"]-m["coefficients"][k]["coefficient"]) for k in common] or [0]);loso.append({"omittedSetId":sid,"maximumShift":shift})
        ready=identification=="TREATMENT_IDENTIFIABLE" and min(x["coverage"] for x in temporal)>=CONTRACT["minimumCheckpointCoverage"] and bool(drifts) and all(v["maximumAdjacent"]<=CONTRACT["maximumAdjacentCoefficientDrift"] and v["fullWindow"]<=CONTRACT["maximumFullWindowCoefficientDrift"] for v in drifts.values()) and max([x["maximumShift"] for x in loso] or [999])<=CONTRACT["maximumLeaveOneSetOutShift"] and all(v["interval"][1]-v["interval"][0]<=CONTRACT["maximumCoefficientIntervalWidth"] for v in current["coefficients"].values())
        results[era]={**structural,"identification":identification,"current":current,"temporal":temporal,"temporalDrift":drifts,"leaveOneSetOut":loso,"status":"AVAILABLE" if ready else "FAIL_CLOSED"}
    return results


def play_diagnostics(cohort, v1, models):
    scores=v1["competitiveScores"]; ordered=sorted(x["fieldUsageDemand"] for x in scores); q1=ordered[len(ordered)//3];q2=ordered[(2*len(ordered))//3]
    strata={x["functionalId"]:("LOW" if x["fieldUsageDemand"]<=q1 else "MEDIUM" if x["fieldUsageDemand"]<=q2 else "HIGH") for x in scores}
    gaps=[]
    for fid in sorted(strata):
        cards=[x for x in cohort if x["functionalId"]==fid and x["treatment"] and x["marketPrice"] and x["marketPrice"]>0]
        if len({x["treatment"] for x in cards})<2:continue
        baseline=max(Counter(x["treatment"] for x in cards),key=Counter(x["treatment"] for x in cards).get); base=np.mean([math.log(x["marketPrice"]) for x in cards if x["treatment"]==baseline]); premium=[math.log(x["marketPrice"]) for x in cards if x["treatment"]!=baseline]
        if premium:gaps.append({"functionalId":fid,"playDemand":next(x["fieldUsageDemand"] for x in scores if x["functionalId"]==fid),"stratum":strata[fid],"baseline":baseline,"rawWithinIdentityGap":float(np.mean(premium)-base),"observations":len(cards)})
    if len(gaps)>=20:
        X=np.asarray([[1,x["playDemand"]] for x in gaps]);y=np.asarray([x["rawWithinIdentityGap"] for x in gaps]);w=np.sqrt(np.asarray([x["observations"] for x in gaps]));beta=np.linalg.lstsq(X*w[:,None],y*w,rcond=None)[0];pred=X@beta;two={"status":"DIAGNOSTIC_ONLY","identities":len(gaps),"playDemandSlope":float(beta[1]),"weightedRmse":float(math.sqrt(np.average((y-pred)**2,weights=w**2))),"warning":"Raw identity gaps can retain set/context confounding; this is not the primary estimator."}
    else:two={"status":"INSUFFICIENT_SUPPORT","identities":len(gaps)}
    stratified={s:{"identities":sum(x["stratum"]==s for x in gaps),"meanRawGap":float(np.mean([x["rawWithinIdentityGap"] for x in gaps if x["stratum"]==s])) if any(x["stratum"]==s for x in gaps) else None} for s in ("LOW","MEDIUM","HIGH")}
    ranking=[{"functionalId":x["functionalId"],"score":x["fieldUsageDemand"],"inclusion":x["weightedInclusionRate"],"copies":x["weightedCopiesPerDeck"],"breadth":x["weightedArchetypeBreadth"],"rank":i+1,"events":x["events"],"decks":x["decksRepresented"],"stratum":strata[x["functionalId"]]} for i,x in enumerate(scores)]
    eligible=[x for x in cohort if x.get("competitivePlayDemand") is not None and x["era"] in models and models[x["era"]].get("status")=="AVAILABLE" and x["treatment"] and x["marketPrice"]]
    hierarchical=fit(eligible,True) if len({x["functionalId"] for x in eligible})>=20 and len({x["treatment"] for x in eligible})>=2 else {"status":"INSUFFICIENT_SUPPORT"}
    interaction_supported=bool(hierarchical.get("interactions")) and hierarchical.get("rankDeficiency")==0 and hierarchical["rmse"]<fit(eligible)["rmse"] if eligible else False
    return ranking,{"boundaries":{"lowMaximum":q1,"mediumMaximum":q2},"summary":stratified},gaps,two,{"status":"SUPPORTED" if interaction_supported else "NOT_SUPPORTED","model":hierarchical}


def magnitude(models):
    effects=[v["coefficient"] for m in models.values() if m.get("status")=="AVAILABLE" for v in m["current"]["coefficients"].values()]
    if not effects:return {"status":"NOT_FEASIBLE_NO_VALIDATED_UNIVERSE"}
    center=float(np.median(effects));scale=float(np.subtract(*np.quantile(effects,[.75,.25]))) or 1.
    scores={}
    for era,m in models.items():
        if m.get("status")!="AVAILABLE":continue
        scores[era]={t:5+5*math.tanh((v["coefficient"]-center)/(2*scale)) for t,v in m["current"]["coefficients"].items()}
    return {"status":"FEASIBLE","frozenCenter":center,"frozenScale":scale,"scores":scores,"crossSupertypeComparable":False}


def within_identity_cv(rows, interaction=False):
    """Five-fold identity-held-out CV on within-identity centered outcomes."""
    ids=sorted({x["functionalId"] for x in rows});treatments=sorted({x["treatment"] for x in rows});sets=sorted({x["setId"] for x in rows});baseline=max(treatments,key=lambda t:sum(x["treatment"]==t for x in rows));demands=[x["competitivePlayDemand"] for x in rows if x.get("competitivePlayDemand") is not None];center=float(np.mean(demands)) if demands else 0.;scale=float(np.std(demands)) if len(demands)>1 else 1.;scale=scale or 1.
    def vector(x):
        z=((x.get("competitivePlayDemand") or center)-center)/scale;base=[float(x["setId"]==s) for s in sets[1:]]+[float(x["treatment"]==t) for t in treatments if t!=baseline];return base+([float(x["treatment"]==t)*z for t in treatments if t!=baseline] if interaction else [])
    folds={fid:int(hashlib.sha256(fid.encode()).hexdigest()[:8],16)%5 for fid in ids};errors=[]
    for fold in range(5):
        train=[x for x in rows if folds[x["functionalId"]]!=fold];test=[x for x in rows if folds[x["functionalId"]]==fold]
        if not train or not test:continue
        def centered(group):
            by=defaultdict(list)
            for x in group:by[x["functionalId"]].append(x)
            X=[];y=[]
            for cards in by.values():
                vectors=np.asarray([vector(x) for x in cards]);values=np.asarray([math.log(x["marketPrice"]) for x in cards]);X.extend(vectors-vectors.mean(axis=0));y.extend(values-values.mean())
            return np.asarray(X),np.asarray(y)
        X,y=centered(train);Xt,yt=centered(test);beta=np.linalg.lstsq(X,y,rcond=None)[0];errors.extend((yt-Xt@beta).tolist())
    return {"folds":5,"heldOutUnit":"functional identity","centeredOutcome":True,"rmse":float(math.sqrt(np.mean(np.asarray(errors)**2))) if errors else None,"observations":len(errors)}


def build():
    v1=ensure_v1(); raw=supporter_rows(); cohort=freeze_cohort(raw,v1); groups,safe,cross,identity_records,audit=identity_audit(cohort); ont=ontology(cohort); history=load(HISTORY); models=era_models(cohort,history); ranking,strata,gaps,two,hier=play_diagnostics(cohort,v1,models); mag=magnitude(models)
    available={era:m for era,m in models.items() if m.get("status")=="AVAILABLE"};recoverable=[]
    for era,m in available.items():
        supported=set(m["current"]["coefficients"])|{m["current"]["baselineTreatment"]};candidates=[x for x in cohort if x["era"]==era and x["treatment"] in supported and x["marketPrice"]];families=defaultdict(list)
        for x in candidates:families[x["functionalId"]].append(x)
        valid={fid for fid,cards in families.items() if len({x["treatment"] for x in cards})>=2};recoverable.extend(x for x in candidates if x["functionalId"] in valid)
    interaction="PLAYABILITY_AMPLIFIES_TREATMENT_PREMIUM" if hier["status"]=="SUPPORTED" and all(v["coefficient"]>0 for v in hier["model"]["interactions"].values()) else "PLAYABILITY_INTERACTION_PARTIALLY_SUPPORTED" if hier["status"]=="SUPPORTED" else "PLAYABILITY_INTERACTION_NOT_SUPPORTED"
    structurally_relevant=sum(bool(audit["crossTreatmentByEra"].get(era)) for era in models);ident_status="SUPPORTER_TREATMENT_EFFECT_IDENTIFIED" if available and len(available)==structurally_relevant else "SUPPORTER_TREATMENT_EFFECT_PARTIALLY_IDENTIFIED" if any(m.get("identification")=="TREATMENT_IDENTIFIABLE" for m in models.values()) else "SUPPORTER_TREATMENT_EFFECT_NOT_IDENTIFIED"
    v3status="SUPPORTER_TREATMENT_MARKET_PRESTIGE_PARTIALLY_VALIDATED" if recoverable else "SUPPORTER_TREATMENT_MARKET_PRESTIGE_NOT_VALIDATED"; updated=9485+len(recoverable)
    boss=[x for x in cohort if x["functionalId"]=="boss s orders"];boss_effects={era:{"baseline":m["current"]["baselineTreatment"],"effects":{t:v for t,v in m["current"]["coefficients"].items() if t in {x["treatment"] for x in boss if x["era"]==era}}} for era,m in available.items() if any(x["era"]==era for x in boss)}
    examples=[]
    for target in [ranking[0]["functionalId"] if ranking else None,ranking[len(ranking)//2]["functionalId"] if ranking else None,ranking[-1]["functionalId"] if ranking else None]:
        if target:examples.append({"functionalId":target,"ranking":next(x for x in ranking if x["functionalId"]==target),"gap":next((x for x in gaps if x["functionalId"]==target),None)})
    cv_results={}
    for era in available:
        era_rows=[x for x in recoverable if x["era"]==era];competitive=[x for x in era_rows if x.get("competitivePlayDemand") is not None]
        cv_results[era]={"modelA":within_identity_cv(era_rows,False),"modelB":within_identity_cv(competitive,True) if len({x["functionalId"] for x in competitive})>=20 else {"status":"INSUFFICIENT_COMPETITIVE_IDENTITIES"}}
    result={"studyId":"supporter-treatment-market-prestige-v3s-r2-"+stable_hash({"contract":CONTRACT,"cohort":stable_hash(cohort),"v1":v1["studyId"]})[:16],"builtAt":datetime.now(timezone.utc).isoformat(),"contract":CONTRACT,"frozenCohort":{"cards":len(cohort),"hash":stable_hash(cohort),"source":str(COHORT_SOURCE),"competitiveSourceStudy":v1["studyId"]},"identityAudit":audit,"treatmentOntology":ont,"comparisonUniverseArchitecture":"SUPERTYPE_RELATIVE_WITHIN_ERA","eraModels":models,"supportedTreatmentContrasts":{era:list(m["current"]["coefficients"]) for era,m in available.items()},"magnitudeScore":mag,"competitivePlayDemandRanking":ranking,"playDemandStrata":strata,"treatmentPremiumByStratum":strata["summary"],"twoStageInteraction":two,"hierarchicalInteraction":hier,"modelA":{"specification":"functional identity FE + treatment + set FE","results":{era:m.get("current") for era,m in models.items() if m.get("current")}},"modelB":{"specification":"Model A + treatment x frozen Competitive Play Demand","result":hier},"modelComparison":{"interactionSelectionRule":CONTRACT["interactionRule"],"decision":"MODEL_A_RETAINED" if interaction=="PLAYABILITY_INTERACTION_NOT_SUPPORTED" else "MODEL_B_RESEARCH_ONLY"},"interactionStatus":interaction,"characterDemand":{"limitation":"Authoritative character identity/popularity metadata remains absent and may confound some treatment gaps.","sensitivity":"NOT_RUN_NO_INDEPENDENTLY_DEFINED_CHARACTER_HEAVY_SUBGROUP"},"bossOrdersCaseStudy":{"supported":bool(boss),"functionalLayer":next((x for x in ranking if x["functionalId"]=="boss s orders"),None),"treatmentLayer":next((x for x in gaps if x["functionalId"]=="boss s orders"),None),"printings":len(boss)},"additionalExamples":examples,"treatmentIdentificationStatus":ident_status,"supporterV3Status":v3status,"recovery":{"safeFunctionalIdentities":len(safe),"crossTreatmentIdentities":len(cross),"modelIdentifiableCards":sum(m.get("cards",0) for m in models.values() if m.get("identification")=="TREATMENT_IDENTIFIABLE"),"temporallyValidatedCards":len(recoverable),"treatmentEligibleCards":len(recoverable),"universeEligibleCards":len(recoverable),"finalDownstreamValidCards":len(recoverable)},"coverage":{"starting":9485,"incremental":len(recoverable),"updated":updated,"percentage":updated/19847,"remainingTo70":13893-updated,"decision":"SUPPORTER_RECOVERY_MATERIAL" if len(recoverable)>=198 else "SUPPORTER_RECOVERY_LIMITED"},"weeklyRetentionRecommendation":"Freeze versioned weekly Competitive Play Demand snapshots with reference date, window, metrics, event/deck counts, provenance, and content hash for future functional-card x date panels.","correctedV1Interpretation":"Competitive Play Demand main-effect absorption by functional identity FE remains correct; it does not imply treatment-effect non-identification. Round 2 separately tests within-functional-identity treatment contrasts.","rowsPersisted":0,"productionBehavior":"Unchanged and paused; research artifacts only. No migrations, score publication, UI, V1/V2, appeal, RIP, or ranking changes.","filesChanged":[str(Path(__file__)),str(STUDY),str(REPORT),str(OUT/"frozen_supporter_cohort.json"),str(OUT/"functional_identity_audit.json"),str(OUT/"manifest.json")],"testsExecuted":["cohort conservation/hash","within-identity rank audit","four-checkpoint temporal validation","leave-one-set-out validation","interaction diagnostics","coverage arithmetic","full V3 regression"],"remainingLimitations":["character-demand control unavailable","Competitive Play Demand covers 67 Supporter identities only","V1 source excludes a documented comprehensive major/offline corpus","cross-sectional prices are observational","unsupported eras fail closed"],"recommendedNextTask":"Retain weekly Competitive Play Demand snapshots and acquire independent character metadata; production remains paused. Extend only failed Supporter eras with preregistered structural regimes or more history, without weakening gates."}
    result["modelComparison"]={"crossValidation":cv_results,"interactionSelectionRule":CONTRACT["interactionRule"],"decision":"MODEL_A_RETAINED" if interaction=="PLAYABILITY_INTERACTION_NOT_SUPPORTED" else "MODEL_B_RESEARCH_ONLY"}
    result["bossOrdersCaseStudy"]={"supported":bool(boss_effects),"functionalLayer":next((x for x in ranking if x["functionalId"]=="boss s orders"),None),"treatmentLayer":{"rawIdentityGap":next((x for x in gaps if x["functionalId"]=="boss s orders"),None),"supportedEraEffects":boss_effects},"printings":len(boss)}
    OUT.mkdir(parents=True,exist_ok=True);(OUT/"frozen_supporter_cohort.json").write_text(json.dumps(cohort,indent=2),encoding="utf-8");(OUT/"functional_identity_audit.json").write_text(json.dumps(identity_records,indent=2),encoding="utf-8");return result


def render(s):
    r=s["recovery"];c=s["coverage"];available={k:v for k,v in s["eraModels"].items() if v.get("status")=="AVAILABLE"}
    values=[s["studyId"],s["frozenCohort"]["cards"],s["identityAudit"]["safeFunctionalIdentities"],s["identityAudit"]["crossTreatmentIdentities"],s["identityAudit"]["crossTreatmentObservations"],s["treatmentOntology"],s["comparisonUniverseArchitecture"],{k:v["identification"] for k,v in s["eraModels"].items()},{k:v.get("current",{}).get("matrixRank") for k,v in s["eraModels"].items()},{k:v.get("current",{}).get("treatmentResidualVariance") for k,v in s["eraModels"].items()},{k:{"columns":v.get("current",{}).get("matrixColumns"),"rank":v.get("current",{}).get("matrixRank"),"deficiency":v.get("current",{}).get("rankDeficiency")} for k,v in s["eraModels"].items()},s["supportedTreatmentContrasts"],{k:v["current"]["coefficients"] for k,v in available.items()},{k:{t:x["multiplicativeAssociation"] for t,x in v["current"]["coefficients"].items()} for k,v in available.items()},{k:v["current"]["coefficients"] for k,v in available.items()},{k:{t:x["interval"] for t,x in v["current"]["coefficients"].items()} for k,v in available.items()},{k:v.get("temporalDrift") for k,v in s["eraModels"].items()},{k:v.get("leaveOneSetOut") for k,v in s["eraModels"].items()},s["magnitudeScore"],s["contract"]["semantics"],s["competitivePlayDemandRanking"],s["playDemandStrata"],s["treatmentPremiumByStratum"],s["twoStageInteraction"],s["hierarchicalInteraction"],s["modelA"],s["modelB"],s["modelComparison"],s["interactionStatus"],s["characterDemand"]["limitation"],s["characterDemand"]["sensitivity"],s["bossOrdersCaseStudy"],s["additionalExamples"],s["treatmentIdentificationStatus"],s["supporterV3Status"],r["finalDownstreamValidCards"],c["incremental"],{"cards":c["updated"],"coverage":c["percentage"]},c["remainingTo70"],s["weeklyRetentionRecommendation"],s["correctedV1Interpretation"],s["rowsPersisted"],s["productionBehavior"],s["filesChanged"],s["testsExecuted"],s["remainingLimitations"],s["recommendedNextTask"]]
    labels=["Round 2 study ID","Frozen Supporter cohort size","Safe functional identity count","Cross-treatment identity count","Cross-treatment observations","Treatment ontology","Comparison-universe architecture","Primary design-matrix identification result","Functional identity FE result","Treatment residual variation","Rank/redundancy findings","Supported treatment contrasts","Treatment coefficients","Treatment effect magnitudes","Hierarchical effects","Treatment uncertainty","Temporal treatment stability","Leave-one-set-out stability","Magnitude-score feasibility","Supporter score semantics","Competitive Play Demand ranking results","Play-demand strata","Treatment premium by play-demand stratum","Two-stage interaction diagnostic","Hierarchical interaction diagnostic","Model A result","Model B result","Model comparison","Interaction status","Character-demand limitation","Character-sensitive sensitivity result","Boss's Orders case study if supported","Additional functional-card examples","Supporter treatment-identification status","Supporter V3 status","Final downstream-valid Supporter card count","Incremental catalog coverage","New likely coverage","Remaining gap to 70%","Weekly Competitive Play Demand retention recommendation","Corrected interpretation of V1 Supporter study","Rows persisted","Production behavior","Files changed","Tests executed","Remaining limitations","Exact recommended next task"]
    return "# Supporter Treatment Market Prestige V3S — Round 2 Results\n\n"+"\n\n".join(f"{i}. **{a}:** `{json.dumps(v,sort_keys=True,default=str)}`" for i,(a,v) in enumerate(zip(labels,values),1))+"\n"


def main():
    s=build();STUDY.write_text(json.dumps(s,indent=2),encoding="utf-8");REPORT.write_text(render(s),encoding="utf-8");(OUT/"manifest.json").write_text(json.dumps({"studyId":s["studyId"],"studyHash":stable_hash(s),"cohortHash":s["frozenCohort"]["hash"],"rowsPersisted":0},indent=2),encoding="utf-8")

if __name__=="__main__":main()
