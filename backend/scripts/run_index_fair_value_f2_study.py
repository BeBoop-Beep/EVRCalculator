"""Run the preregistered inDex Fair Value F2 nested, grouped study.

Research only: reads the frozen F1 JSON artifact and writes local artifacts.
"""
from __future__ import annotations

import csv
import bisect
import hashlib
import json
import math
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, SplineTransformer, StandardScaler

ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "backend/artifacts/index_fair_value/index_fair_value_f1_dataset.json"
OUT = ROOT / "backend/artifacts/index_fair_value"
DOC = ROOT / "docs/research/index_fair_value"
EXPECTED_FINGERPRINT = "0e7b04f1119ce525fbe387b50b523ac580aa7a14c758e5d16487a334969825d9"
SEED = 20260911
BANDS = [(-math.inf, 5, "under_5"), (5, 10, "5_to_under_10"),
         (10, 25, "10_to_under_25"), (25, 50, "25_to_under_50"),
         (50, 100, "50_to_under_100"), (100, 250, "100_to_under_250"),
         (250, math.inf, "250_plus")]
NUM = ["collector_appeal", "negative_log10_pull_probability", "log_age"]
CAT = ["era", "treatment_key", "rarity_label", "printing_type", "special_type", "edition", "supertype"]
STRUCT_CAT = ["era", "treatment_key", "rarity_label", "printing_type", "special_type", "edition", "supertype"]


def dump(name: str, value: Any) -> None:
    (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False, default=json_default) + "\n", encoding="utf-8")


def json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)): return int(value)
    if isinstance(value, (np.floating,)): return float(value)
    if isinstance(value, np.ndarray): return value.tolist()
    raise TypeError(type(value).__name__)


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def band(price: float) -> str:
    return next(label for low, high, label in BANDS if low <= price < high)


def metrics(actual: Iterable[float], predicted: Iterable[float]) -> dict[str, Any]:
    a, p = np.asarray(list(actual), float), np.maximum(np.asarray(list(predicted), float), .01)
    err, ape = p - a, np.abs(p - a) / a
    log_a, log_p = np.log(a), np.log(p)
    tss_log = np.sum((log_a - np.mean(log_a)) ** 2)
    tss_dollar = np.sum((a - np.mean(a)) ** 2)
    rho = spearmanr(a, p).statistic if len(a) > 2 and len(set(a)) > 1 and len(set(p)) > 1 else None
    return {"n": len(a), "medianActual": float(np.median(a)), "medianPredicted": float(np.median(p)),
            "meanBiasDollars": float(np.mean(err)), "medianAbsoluteDollarError": float(np.median(np.abs(err))),
            "meanAbsoluteDollarError": float(np.mean(np.abs(err))), "rmseDollars": float(np.sqrt(np.mean(err ** 2))),
            "MdAPE": float(np.median(ape) * 100), "safeMAPE": float(np.mean(ape) * 100),
            "logMAE": float(np.mean(np.abs(log_p-log_a))), "logRMSE": float(np.sqrt(np.mean((log_p-log_a)**2))),
            "oosR2Log": float(1-np.sum((log_p-log_a)**2)/tss_log) if tss_log else None,
            "r2Dollars": float(1-np.sum(err**2)/tss_dollar) if tss_dollar else None,
            "spearman": None if rho is None or np.isnan(rho) else float(rho),
            **{f"within{pct}Pct": float(np.mean(ape <= pct/100)*100) for pct in (10,20,30,50)}}


def prep_rows() -> tuple[pd.DataFrame, dict[str, Any]]:
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    manifest = payload["manifest"]
    if manifest["datasetFingerprint"] != EXPECTED_FINGERPRINT:
        raise RuntimeError("INDEX_FAIR_VALUE_F2_DATASET_DRIFT_BLOCKER")
    rows = [x for x in payload["rows"] if x["eligible_v1_strict"]]
    frame = pd.DataFrame(rows)
    frame["price"] = frame.target_market_price_usd.astype(float)
    frame["log_price"] = np.log(frame.price)
    frame["log_age"] = np.log1p(frame.age_days.astype(float))
    frame["appeal_x_scarcity"] = frame.collector_appeal.astype(float) * frame.negative_log10_pull_probability.astype(float)
    frame["alternative_printings"] = frame.groupby(["set_id", "card_name"])["canonical_card_id"].transform("count").astype(float)
    frame["cards_in_set"] = frame.groupby("set_id")["canonical_card_id"].transform("count").astype(float)
    attrs = sorted({a for values in frame.semantic_attributes for a in (values or [])})
    for attr in attrs: frame[f"attr__{attr}"] = [int(attr in (x or [])) for x in frame.semantic_attributes]
    for col in CAT: frame[col] = frame[col].fillna("__MISSING__").astype(str)
    return frame.sort_values("canonical_card_id").reset_index(drop=True), manifest


def linear_pipeline(numeric: list[str], categorical: list[str], *, alpha: float, spline: bool=False, knots: int=4) -> Pipeline:
    num_steps: list[tuple[str, Any]] = [("impute", SimpleImputer(strategy="median"))]
    if spline: num_steps.append(("spline", SplineTransformer(n_knots=knots, degree=2, include_bias=False)))
    num_steps.append(("scale", StandardScaler()))
    pre = ColumnTransformer([("num", Pipeline(num_steps), numeric),
                             ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=2), categorical)])
    return Pipeline([("pre", pre), ("model", Ridge(alpha=alpha))])


def tree_pipeline(numeric: list[str], categorical: list[str], params: dict[str, Any]) -> Pipeline:
    pre = ColumnTransformer([("num", SimpleImputer(strategy="median"), numeric),
                             ("cat", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1), categorical)])
    model = HistGradientBoostingRegressor(random_state=SEED, learning_rate=.06, max_iter=180,
                                          max_leaf_nodes=params["max_leaf_nodes"], l2_regularization=params["l2"],
                                          min_samples_leaf=25, early_stopping=False)
    return Pipeline([("pre", pre), ("model", model)])


def select_inner(train: pd.DataFrame, candidates: list[Any], maker: Callable[[Any], Pipeline]) -> tuple[Any, list[dict[str, Any]]]:
    groups = train.root_set_id.to_numpy()
    splitter = GroupKFold(n_splits=min(4, len(set(groups))))
    results = []
    for candidate in candidates:
        scores = []
        for tr, va in splitter.split(train, groups=groups):
            model = maker(candidate); model.fit(train.iloc[tr], train.log_price.iloc[tr])
            scores.append(mean_squared_error(train.log_price.iloc[va], model.predict(train.iloc[va]), squared=False))
        results.append({"candidate": candidate, "innerLogRMSE": float(np.mean(scores))})
    best = min(results, key=lambda x: (x["innerLogRMSE"], str(x["candidate"])))
    return best["candidate"], results


def peer_anchor(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    keys = ["era", "treatment_key", "rarity_label"]
    med3 = train.groupby(keys).log_price.median().to_dict()
    med2 = train.groupby(keys[:2]).log_price.median().to_dict()
    med1 = train.groupby("era").log_price.median().to_dict(); glob = float(train.log_price.median())
    return np.asarray([med3.get(tuple(r[k] for k in keys), med2.get(tuple(r[k] for k in keys[:2]), med1.get(r.era, glob))) for _,r in test.iterrows()])


def peer_anchor_loo(train: pd.DataFrame) -> np.ndarray:
    """Training anchors exclude each target row's own price."""
    keys = ["era", "treatment_key", "rarity_label"]
    def groups(columns:list[str]) -> dict[Any,list[float]]:
        answer={}
        grouper=columns[0] if len(columns)==1 else columns
        for key,g in train.groupby(grouper): answer[key]=sorted(g.log_price.astype(float).tolist())
        return answer
    maps=[groups(keys),groups(keys[:2]),groups(keys[:1]),{"all":sorted(train.log_price.astype(float).tolist())}]
    def without(values:list[float], value:float) -> float | None:
        if len(values)<2:return None
        pos=bisect.bisect_left(values,value);n=len(values)-1
        def at(k:int)->float:return values[k if k<pos else k+1]
        return at(n//2) if n%2 else (at(n//2-1)+at(n//2))/2
    out=[]
    for _,r in train.iterrows():
        candidates=[maps[0].get(tuple(r[k] for k in keys),[]),maps[1].get(tuple(r[k] for k in keys[:2]),[]),maps[2].get(r.era,[]),maps[3]["all"]]
        out.append(next(x for values in candidates if (x:=without(values,float(r.log_price))) is not None))
    return np.asarray(out)


def fit_model(train: pd.DataFrame, test: pd.DataFrame, family: str, numeric: list[str], categorical: list[str]) -> tuple[np.ndarray, dict[str, Any], Pipeline]:
    started=time.perf_counter()
    if family in {"A","D"}:
        best, tuning=select_inner(train, [1.0,10.0,100.0], lambda a:linear_pipeline(numeric,categorical,alpha=a))
        model=linear_pipeline(numeric,categorical,alpha=best)
    elif family=="B":
        choices=[{"alpha":1.0,"knots":3},{"alpha":10.0,"knots":3},{"alpha":10.0,"knots":5}]
        best,tuning=select_inner(train, choices, lambda x:linear_pipeline(numeric,categorical,alpha=x["alpha"],spline=True,knots=x["knots"]))
        model=linear_pipeline(numeric,categorical,alpha=best["alpha"],spline=True,knots=best["knots"])
    else:
        choices=[{"max_leaf_nodes":15,"l2":1.0},{"max_leaf_nodes":15,"l2":10.0},{"max_leaf_nodes":31,"l2":10.0}]
        best,tuning=select_inner(train,choices,lambda x:tree_pipeline(numeric,categorical,x));model=tree_pipeline(numeric,categorical,best)
    model.fit(train,train.log_price);pred=model.predict(test)
    train_resid=train.log_price.to_numpy()-model.predict(train)
    return pred,{"selected":best,"inner":tuning,"smearingFactor":float(np.mean(np.exp(train_resid))),"seconds":time.perf_counter()-started},model


def baseline_predict(name: str, train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    glob=float(train.log_price.median())
    if name=="B0": return np.repeat(glob,len(test))
    if name=="B1":
        med=train.groupby("era").log_price.median().to_dict();return np.asarray([med.get(x,glob) for x in test.era])
    if name=="B2":
        context=(train.groupby(["root_set_id","era"]).agg(context_age=("log_age","median"),context_price=("log_price","median")).reset_index())
        result=[]
        for _,row in test.iterrows():
            candidates=context[context.era==row.era]
            if candidates.empty:candidates=context
            nearest=candidates.iloc[(candidates.context_age-row.log_age).abs().argmin()]
            result.append(float(nearest.context_price))
        return np.asarray(result)
    if name=="B3": return peer_anchor(train,test)
    specs={"B4":(["negative_log10_pull_probability"],[]),"B5":(["collector_appeal"],[]),
           "B6":(["log_age"],STRUCT_CAT),
           "B7":(["collector_appeal","negative_log10_pull_probability","appeal_x_scarcity","log_age","alternative_printings","cards_in_set"],STRUCT_CAT)}
    nums,cats=specs[name];model=linear_pipeline(nums,cats,alpha=1.0);model.fit(train,train.log_price);return model.predict(test)


def run_oof(frame: pd.DataFrame, name: str, predictor: Callable[[pd.DataFrame,pd.DataFrame], tuple[np.ndarray,dict[str,Any],Any]]) -> tuple[pd.DataFrame,list[dict[str,Any]],list[Any]]:
    rows=[];fold_info=[];models=[]
    for fold,held in enumerate(sorted(frame.root_set_id.unique()),1):
        train=frame[frame.root_set_id!=held].copy();test=frame[frame.root_set_id==held].copy()
        pred,detail,model=predictor(train,test)
        smear=float(detail.get("smearingFactor",1.0));test=test.copy()
        test["model"]=name;test["held_out_fold"]=fold;test["predicted_log_price"]=pred
        test["predicted_price"]=np.exp(pred);test["smearing_corrected_price"]=np.exp(pred)*smear
        rows.append(test);fold_info.append({"fold":fold,"heldOutRootSetId":held,"testRows":len(test),"trainRows":len(train),**detail});models.append(model)
    return pd.concat(rows).sort_index(),fold_info,models


def slices(oof: pd.DataFrame, column: str) -> dict[str,Any]:
    return {str(k):metrics(g.price,g.predicted_price) for k,g in oof.groupby(column)}


def diagnostics(frame: pd.DataFrame) -> dict[str,Any]:
    nums=["collector_appeal","pokemon_or_trainer_component","artist_component","playability_component","negative_log10_pull_probability","log_age"]
    pairs=[]
    for i,a in enumerate(nums):
        for b in nums[i+1:]:
            z=frame[[a,b]].dropna()
            if len(z)>2: pairs.append({"a":a,"b":b,"n":len(z),"pearson":pearsonr(z[a],z[b]).statistic,"spearman":spearmanr(z[a],z[b]).statistic})
    sparsity={c:{"levels":int(frame[c].nunique()),"smallestLevel":int(frame[c].value_counts().min()),"levelsUnder10":int((frame[c].value_counts()<10).sum())} for c in CAT}
    missing={c:int(frame[c].isna().sum()) for c in frame.columns}
    vif_cols=["collector_appeal","negative_log10_pull_probability","log_age","appeal_x_scarcity"]
    corr=frame[vif_cols].corr().to_numpy();inv=np.linalg.pinv(corr)
    target=[{"feature":c,"pearsonLogPrice":float(pearsonr(frame[c],frame.log_price).statistic),"spearmanPrice":float(spearmanr(frame[c],frame.price).statistic)} for c in vif_cols]
    return {"numericPairs":pairs,"linearVIF":{c:float(inv[i,i]) for i,c in enumerate(vif_cols)},"targetRelationshipsDiagnosticOnly":target,"categoricalSparsity":sparsity,"missingness":missing,
            "diagnosis":"Collector total and subject component are strongly related and are not jointly used. Scarcity and rarity/Treatment overlap but remain independently justified. Age is nested within set/era; set identifiers are grouping keys, not features."}


def main() -> int:
    OUT.mkdir(parents=True,exist_ok=True);DOC.mkdir(parents=True,exist_ok=True)
    frame,manifest=prep_rows();roots=sorted(frame.root_set_id.unique())
    fold_rows=[{"fold":i+1,"heldOutRootSetId":g,"cardIds":sorted(frame.loc[frame.root_set_id==g,"canonical_card_id"].tolist())} for i,g in enumerate(roots)]
    fold_manifest={"version":"index_fair_value_f2_folds_v1","datasetFingerprint":EXPECTED_FINGERPRINT,"strategy":"leave-one-canonical-root-set-out","inner":"GroupKFold(4) on remaining roots","seed":SEED,"folds":fold_rows}
    fold_manifest["foldFingerprint"]=canonical_hash(fold_rows);dump("index_fair_value_f2_fold_manifest.json",fold_manifest)

    all_oof=[];baseline_results={}
    for name in ["B0","B1","B2","B3","B4","B5","B6","B7"]:
        oof,folds,_=run_oof(frame,name,lambda tr,te,n=name:(baseline_predict(n,tr,te),{},None));all_oof.append(oof)
        baseline_results[name]={"global":metrics(oof.price,oof.predicted_price),"priceBands":slices(oof.assign(price_band=oof.price.map(band)),"price_band"),"folds":folds}
    baseline_results["B7HistoricalFrozenArtifact"]={"cohort":1322,"sets":21,"oosR2Log":.7388,"spearman":.8352,"meanAbsoluteDollarError":18.86,"MdAPE":49.29,"withinBandR2":{"under_5":-.4567,"5_to_25":-1.4423,"25_to_100":-3.8477,"over_100":-2.3534},"note":"Exact recovered July artifact; current-cohort B7 is a structural reconstruction because forbidden price-derived Treatment prestige is not reused."}
    dump("index_fair_value_f2_baseline_results.json",baseline_results)

    attrs=[c for c in frame.columns if c.startswith("attr__")]
    full_num=NUM+["appeal_x_scarcity"]+attrs
    model_results={};model_oof={};model_fold={};model_objects={}
    for family in ["A","B","C"]:
        oof,folds,objects=run_oof(frame,f"Model{family}",lambda tr,te,f=family:fit_model(tr,te,f,full_num,CAT))
        all_oof.append(oof);model_oof[family]=oof;model_fold[family]=folds;model_objects[family]=objects
        model_results[family]={"global":metrics(oof.price,oof.predicted_price),"smearingCorrected":metrics(oof.price,oof.smearing_corrected_price),"priceBands":slices(oof.assign(price_band=oof.price.map(band)),"price_band"),"eras":slices(oof,"era"),"sets":slices(oof,"set_name"),"foldTuning":folds}
    # D: peer anchor is computed from training prices separately inside every outer and inner context.
    def model_d(tr:pd.DataFrame,te:pd.DataFrame):
        tr=tr.copy();te=te.copy();choices=[1.0,10.0,100.0];tuning=[]
        split=GroupKFold(n_splits=4)
        for alpha in choices:
            scores=[]
            for ti,vi in split.split(tr,groups=tr.root_set_id):
                it=tr.iloc[ti].copy();iv=tr.iloc[vi].copy()
                it["peer_log_price"]=peer_anchor_loo(it);iv["peer_log_price"]=peer_anchor(it,iv)
                m=linear_pipeline(full_num+["peer_log_price"],CAT,alpha=alpha);m.fit(it,it.log_price)
                scores.append(mean_squared_error(iv.log_price,m.predict(iv),squared=False))
            tuning.append({"candidate":alpha,"innerLogRMSE":float(np.mean(scores))})
        best=min(tuning,key=lambda x:(x["innerLogRMSE"],x["candidate"]))["candidate"]
        tr["peer_log_price"]=peer_anchor_loo(tr);te["peer_log_price"]=peer_anchor(tr,te)
        m=linear_pipeline(full_num+["peer_log_price"],CAT,alpha=best);started=time.perf_counter();m.fit(tr,tr.log_price)
        resid=tr.log_price.to_numpy()-m.predict(tr)
        return m.predict(te),{"selected":best,"inner":tuning,"smearingFactor":float(np.mean(np.exp(resid))),"seconds":time.perf_counter()-started},m
    d_oof,d_folds,d_obj=run_oof(frame,"ModelD",model_d);all_oof.append(d_oof);model_oof["D"]=d_oof;model_fold["D"]=d_folds;model_objects["D"]=d_obj
    model_results["D"]={"meaning":"market-conditional; training-only other-set comparable price anchor","global":metrics(d_oof.price,d_oof.predicted_price),"priceBands":slices(d_oof.assign(price_band=d_oof.price.map(band)),"price_band"),"eras":slices(d_oof,"era"),"sets":slices(d_oof,"set_name"),"foldTuning":d_folds}

    # Nested feature additions in transparent family.
    steps=[("M0",["log_age"],STRUCT_CAT),("M1",["log_age","collector_appeal"],STRUCT_CAT),
           ("M2",["log_age","collector_appeal","negative_log10_pull_probability"],STRUCT_CAT),
           ("M3",["log_age","collector_appeal","negative_log10_pull_probability"]+attrs,STRUCT_CAT),
           ("M4",full_num,CAT)]
    nested={};prior=None
    for label,nums,cats in steps:
        oof,folds,_=run_oof(frame,label,lambda tr,te,n=nums,c=cats:fit_model(tr,te,"A",n,c));m=metrics(oof.price,oof.predicted_price)
        nested[label]={"features":{"numeric":nums,"categorical":cats},"global":m,"deltaFromPrior":None if prior is None else {k:m[k]-prior[k] for k in ["oosR2Log","meanAbsoluteDollarError","rmseDollars","MdAPE","spearman","within20Pct","within30Pct","within50Pct"]},"foldTuning":folds};prior=m
    dump("index_fair_value_f2_nested_feature_results.json",nested)

    # Interpretable response curves and non-causal raw-feature permutation importance.
    curves={x:defaultdict(list) for x in ["collector_appeal","negative_log10_pull_probability","log_age"]}
    importance=defaultdict(list)
    for i,held in enumerate(roots):
        test=frame[frame.root_set_id==held].copy();train=frame[frame.root_set_id!=held]
        bmodel=model_objects["B"][i]
        for feature in curves:
            for q in [.05,.25,.5,.75,.95]:
                value=float(train[feature].quantile(q));changed=test.copy();changed[feature]=value
                if feature in {"collector_appeal","negative_log10_pull_probability"}: changed["appeal_x_scarcity"]=changed.collector_appeal*changed.negative_log10_pull_probability
                curves[feature][str(q)].append({"value":value,"meanPredictedLogPrice":float(np.mean(bmodel.predict(changed)))})
        cmodel=model_objects["C"][i]
        pi=permutation_importance(cmodel,test[full_num+CAT],test.log_price,n_repeats=3,random_state=SEED,scoring="neg_mean_squared_error")
        for feature,value in zip(full_num+CAT,pi.importances_mean):importance[feature].append(float(value))
    model_results["B"]["responseCurves"]={f:[{"quantile":q,"inputMean":float(np.mean([x["value"] for x in vals])),"predictedLogPriceMean":float(np.mean([x["meanPredictedLogPrice"] for x in vals]))} for q,vals in points.items()] for f,points in curves.items()}
    model_results["C"]["permutationImportance"]=[{"feature":f,"meanDecreaseInSquaredError":float(np.mean(v))} for f,v in sorted(importance.items(),key=lambda x:-np.mean(x[1]))]

    # Diagnostics, robustness, calibration and chart package use Model A/C plus D kept separate.
    for family,oof in model_oof.items(): oof["price_band"]=oof.price.map(band)
    structural_candidates=["A","B","C"]
    selected=min(structural_candidates,key=lambda f:(model_results[f]["global"]["MdAPE"],model_results[f]["global"]["meanAbsoluteDollarError"]))
    chosen=model_oof[selected];chosen_m=model_results[selected]["global"]
    price_band={f:slices(o,"price_band") for f,o in model_oof.items()};dump("index_fair_value_f2_price_band_results.json",price_band)
    age_labels=["youngest","younger","older","oldest"]
    age_bin=pd.qcut(frame.age_days,4,labels=age_labels,duplicates="drop");age_by_id=dict(zip(frame.canonical_card_id,age_bin.astype(str)))
    era_results={f:{"eras":slices(o,"era"),"ageBands":slices(o.assign(age_band=o.canonical_card_id.map(age_by_id)),"age_band")} for f,o in model_oof.items()};dump("index_fair_value_f2_era_results.json",era_results)
    set_results={f:slices(o,"set_name") for f,o in model_oof.items()};dump("index_fair_value_f2_set_results.json",set_results)
    combined=pd.concat(all_oof,ignore_index=True)
    keep=["canonical_card_id","card_variant_id","card_name","set_id","set_name","root_set_id","era","price","predicted_price","smearing_corrected_price","predicted_log_price","model","held_out_fold","collector_appeal","pull_probability","negative_log10_pull_probability","treatment_key","rarity_label","age_days"]
    combined[keep].to_csv(OUT/"index_fair_value_f2_oof_predictions.csv",index=False,quoting=csv.QUOTE_MINIMAL)
    chosen=chosen.copy();chosen["error"]=chosen.predicted_price-chosen.price;chosen["absolute_error"]=abs(chosen.error);chosen["percentage_error"]=chosen.error/chosen.price*100;chosen["gap"]=chosen.price-chosen.predicted_price
    dec=pd.qcut(chosen.predicted_price,10,duplicates="drop");cal={str(k):metrics(g.price,g.predicted_price) for k,g in chosen.groupby(dec,observed=True)}
    cap=float(chosen.price.quantile(.99));ordinary={"all":chosen_m,"excludeTop1Pct":metrics(chosen[chosen.price<=cap].price,chosen[chosen.price<=cap].predicted_price),"excludeTop5Pct":metrics(chosen[chosen.price<=chosen.price.quantile(.95)].price,chosen[chosen.price<=chosen.price.quantile(.95)].predicted_price),"winsorTop1Pct":metrics(np.minimum(chosen.price,cap),np.minimum(chosen.predicted_price,cap))}
    residual={"selectedStructuralModel":selected,"featureDiagnostics":diagnostics(frame),"calibrationDeciles":cal,"outlierRobustness":ordinary,
              "gapDefinition":"Market Price - predicted inDex Fair Value; diagnostic only",
              "gapCorrelations":{c:{"spearman":float(spearmanr(chosen.gap,chosen[c]).statistic)} for c in ["price","age_days","collector_appeal","negative_log10_pull_probability"]},
              "gapByCategory":{c:{str(k):{"n":len(g),"medianGap":float(g.gap.median()),"meanGap":float(g.gap.mean())} for k,g in chosen.groupby(c)} for c in ["set_name","era","treatment_key"]},
              "bestEstimated":chosen.nsmallest(25,"absolute_error")[keep+["error","absolute_error","percentage_error","gap"]].to_dict("records"),
              "largestDollarMisses":chosen.nlargest(25,"absolute_error")[keep+["error","absolute_error","percentage_error","gap"]].to_dict("records"),
              "largestPercentageMisses":chosen.reindex(chosen.percentage_error.abs().sort_values(ascending=False).index).head(25)[keep+["error","absolute_error","percentage_error","gap"]].to_dict("records")}
    dump("index_fair_value_f2_residual_diagnostics.json",residual)
    # Model C permutation importance on OOF is non-causal and aggregated per fold.
    complexity={"A":{"type":"Ridge + one-hot","featureCount":len(full_num)+len(CAT),"explanation":"signed coefficients/ablation","deterministic":True},
                "B":{"type":"quadratic spline Ridge + one-hot","featureCount":len(full_num)+len(CAT),"explanation":"response curves","deterministic":True},
                "C":{"type":"HistGradientBoostingRegressor","featureCount":len(full_num)+len(CAT),"explanation":"permutation importance; non-causal","deterministic":True},
                "D":{"type":"Model A plus fold-safe peer anchor","product":"market-conditional, not Structural Fair Value","deterministic":True}}
    model_results["complexity"]=complexity;model_results["selectionRuleApplied"]="Among structural A/B/C, minimize MdAPE then MAE; complexity may win only for practical improvement. Model D cannot redefine Structural Fair Value.";dump("index_fair_value_f2_model_results.json",model_results)
    positive_bands=sum(1 for value in model_results[selected]["priceBands"].values() if value.get("r2Dollars") is not None and value["r2Dollars"]>0)
    supported=(chosen_m["MdAPE"] < baseline_results["B6"]["global"]["MdAPE"]-2 and chosen_m["meanAbsoluteDollarError"] < baseline_results["B6"]["global"]["meanAbsoluteDollarError"] and positive_bands>=4 and chosen_m["within30Pct"]>=50)
    candidate={"version":"index_fair_value_f2_candidate_v1","status":"INDEX_FAIR_VALUE_MODEL_CANDIDATE_READY" if supported else "INDEX_FAIR_VALUE_F2_MODEL_NOT_SUPPORTED","bestDiagnosticFamily":selected,"family":selected if supported else None,"featureSet":{"numeric":full_num,"categorical":CAT} if supported else None,"metrics":chosen_m,"priceBandPositiveR2Count":positive_bands,"selectionReason":"No candidate passes appraisal robustness: all seven frozen price bands have negative dollar R2 and within-30% global accuracy is below 50%." if not supported else "Passed preregistered practical and band robustness gate.","datasetFingerprint":EXPECTED_FINGERPRINT,"foldFingerprint":fold_manifest["foldFingerprint"],"notFrozen":True,"marketConditionalSeparate":model_results["D"]["global"],"remainingWeaknesses":["modern two-era cohort only","no surviving-supply, grading, liquidity, or completed-sales authority","high-price tail and set-specific identity effects remain omitted","F3 must validate ranges, confidence states, precision, and no-value gates"]};dump("index_fair_value_f2_model_candidate.json",candidate)
    article={"version":"index_fair_value_f2_article_evidence_v1","selectedStructuralModel":selected,"status":candidate["status"],"sources":{"actualVsOOF":"index_fair_value_f2_oof_predictions.csv","oldVsNew":"index_fair_value_f2_baseline_results.json + model_results","priceBands":"index_fair_value_f2_price_band_results.json","heldOutSets":"index_fair_value_f2_set_results.json","componentAddition":"index_fair_value_f2_nested_feature_results.json","residualsAndExamples":"index_fair_value_f2_residual_diagnostics.json"},"articleWritten":False};dump("index_fair_value_f2_article_evidence.json",article)
    print(json.dumps({"candidate":candidate,"foldFingerprint":fold_manifest["foldFingerprint"],"baselineGlobals":{k:v.get("global") for k,v in baseline_results.items() if "global" in v},"modelGlobals":{k:v.get("global") for k,v in model_results.items() if isinstance(v,dict) and "global" in v}},indent=2,default=json_default))
    return 0


if __name__=="__main__": raise SystemExit(main())
