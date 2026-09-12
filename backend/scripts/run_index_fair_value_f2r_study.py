"""Target-blind same-set market appraisal rescue study for inDex Fair Value."""
from __future__ import annotations

import csv, hashlib, json, math, sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT=Path(__file__).resolve().parents[2]
F1=ROOT/"backend/artifacts/index_fair_value/index_fair_value_f1_dataset.json"
F2=ROOT/"backend/artifacts/index_fair_value/index_fair_value_f2_oof_predictions.csv"
OUT=ROOT/"backend/artifacts/index_fair_value"
EXPECTED="0e7b04f1119ce525fbe387b50b523ac580aa7a14c758e5d16487a334969825d9"
SEED=20260912
BANDS=[(-math.inf,5,"under_5"),(5,10,"5_to_under_10"),(10,25,"10_to_under_25"),(25,50,"25_to_under_50"),(50,100,"50_to_under_100"),(100,250,"100_to_under_250"),(250,math.inf,"250_plus")]
METHODS=("C0_set_median","C1_set_treatment_median","C2_scarcity_neighbor_5","C3_appeal_scarcity_neighbor_5","C4_robust_weighted_10","O1_median_set_offset","O2_trimmed_set_offset","O3_shrunk_set_offset","R1_local_residual_10")

def dump(name:str,value:Any)->None:(OUT/name).write_text(json.dumps(value,indent=2,ensure_ascii=False,default=lambda x:float(x) if isinstance(x,np.floating) else int(x))+'\n',encoding='utf-8')
def band(x:float)->str:return next(label for lo,hi,label in BANDS if lo<=x<hi)
def stable_int(value:str)->int:return int(hashlib.sha256(value.encode()).hexdigest()[:16],16)
def weighted_median(values:np.ndarray,weights:np.ndarray)->float:
    order=np.argsort(values);v=values[order];w=weights[order];return float(v[np.searchsorted(np.cumsum(w),np.sum(w)/2)])
def trimmed_mean(values:np.ndarray,frac:float=.1)->float:
    x=np.sort(values);cut=int(len(x)*frac);return float(np.mean(x[cut:len(x)-cut])) if cut and len(x)>2*cut else float(np.mean(x))
def metrics(actual:Iterable[float],predicted:Iterable[float])->dict[str,Any]:
    a=np.asarray(list(actual),float);p=np.maximum(np.asarray(list(predicted),float),.01);e=p-a;ape=abs(e)/a;la=np.log(a);lp=np.log(p)
    tlog=np.sum((la-la.mean())**2);td=np.sum((a-a.mean())**2);rho=spearmanr(a,p).statistic if len(a)>2 and len(set(p))>1 else None
    return {"n":len(a),"medianActual":float(np.median(a)),"medianPredicted":float(np.median(p)),"meanBiasDollars":float(np.mean(e)),"medianAbsoluteDollarError":float(np.median(abs(e))),"meanAbsoluteDollarError":float(np.mean(abs(e))),"rmseDollars":float(np.sqrt(np.mean(e**2))),"MdAPE":float(np.median(ape)*100),"oosR2Log":float(1-np.sum((lp-la)**2)/tlog) if tlog else None,"r2Dollars":float(1-np.sum(e**2)/td) if td else None,"spearman":None if rho is None or np.isnan(rho) else float(rho),**{f"within{x}Pct":float(np.mean(ape<=x/100)*100) for x in (10,20,30,50)}}

def load()->pd.DataFrame:
    payload=json.loads(F1.read_text(encoding='utf-8'))
    if payload['manifest']['datasetFingerprint']!=EXPECTED:raise RuntimeError('INDEX_FAIR_VALUE_F2R_BLOCKED: dataset drift')
    df=pd.DataFrame([x for x in payload['rows'] if x['eligible_v1_strict']]).sort_values('canonical_card_id').reset_index(drop=True)
    f2=pd.read_csv(F2);struct=f2[f2.model=='ModelC'][['canonical_card_id','predicted_price']].rename(columns={'predicted_price':'structural_price'})
    df=df.merge(struct,on='canonical_card_id',validate='one_to_one');df['price']=df.target_market_price_usd.astype(float);df['log_price']=np.log(df.price);df['structural_log']=np.log(df.structural_price);df['structural_residual']=df.log_price-df.structural_log
    for c in ['collector_appeal','negative_log10_pull_probability','age_days']:df[c]=df[c].astype(float)
    return df

def peer_pool(df:pd.DataFrame,row:pd.Series,mode:str)->pd.DataFrame:
    peers=df[(df.root_set_id==row.root_set_id)&(df.canonical_card_id!=row.canonical_card_id)].copy()
    if mode=='related_family':peers=peers[peers.card_name!=row.card_name]
    z=(peers.negative_log10_pull_probability-row.negative_log10_pull_probability).abs()
    a=(peers.collector_appeal-row.collector_appeal).abs()/25
    t=(peers.treatment_key!=row.treatment_key).astype(float);r=(peers.rarity_label!=row.rarity_label).astype(float)
    peers['d_scarcity']=z;peers['distance']=z+a+t*.75+r*.25
    if mode.startswith('drop_nearest_'):
        n=int(mode.rsplit('_',1)[1]);peers=peers.sort_values(['distance','canonical_card_id']).iloc[n:]
    elif mode.startswith('random_'):
        frac=float(mode.split('_')[1])/100;rng=np.random.RandomState((SEED+stable_int(str(row.canonical_card_id)))%(2**32-1));drop=set(rng.choice(peers.index,size=int(len(peers)*frac),replace=False));peers=peers[~peers.index.isin(drop)]
    return peers

def predict(row:pd.Series,peers:pd.DataFrame,method:str)->tuple[float|None,int,str]:
    n=len(peers);status='HIGH_CONTEXT' if n>=20 else 'MEDIUM_CONTEXT' if n>=10 else 'LOW_CONTEXT' if n>=5 else 'UNAVAILABLE'
    if n<3:return None,n,'UNAVAILABLE'
    logs=peers.log_price.to_numpy()
    if method=='C0_set_median':value=float(np.median(logs))
    elif method=='C1_set_treatment_median':
        same=peers[peers.treatment_key==row.treatment_key];value=float(np.median((same if len(same)>=3 else peers).log_price))
    elif method=='C2_scarcity_neighbor_5':value=float(np.median(peers.nsmallest(min(5,n),'d_scarcity').log_price))
    elif method=='C3_appeal_scarcity_neighbor_5':value=float(np.median(peers.nsmallest(min(5,n),'distance').log_price))
    elif method=='C4_robust_weighted_10':
        near=peers.nsmallest(min(10,n),'distance');w=1/(near.distance.to_numpy()+.1);value=weighted_median(near.log_price.to_numpy(),w)
    elif method.startswith('O'):
        residual=peers.structural_residual.to_numpy()
        if method=='O1_median_set_offset':offset=float(np.median(residual))
        elif method=='O2_trimmed_set_offset':offset=trimmed_mean(residual)
        else:offset=(n/(n+10))*float(np.median(residual))
        value=float(row.structural_log+offset)
    else:
        near=peers.nsmallest(min(10,n),'distance');w=1/(near.distance.to_numpy()+.1);offset=weighted_median(near.structural_residual.to_numpy(),w);value=float(row.structural_log+offset)
    return math.exp(value),n,status

def run_mode(df:pd.DataFrame,mode:str,methods:tuple[str,...]=METHODS)->pd.DataFrame:
    out=[]
    for _,row in df.iterrows():
        peers=peer_pool(df,row,mode)
        for method in methods:
            value,n,status=predict(row,peers,method)
            out.append({'canonical_card_id':row.canonical_card_id,'card_variant_id':row.card_variant_id,'card_name':row.card_name,'set_name':row.set_name,'root_set_id':row.root_set_id,'era':row.era,'treatment_key':row.treatment_key,'rarity_label':row.rarity_label,'collector_appeal':row.collector_appeal,'pull_probability':row.pull_probability,'age_days':row.age_days,'actual_price':row.price,'structural_price':row.structural_price,'predicted_price':value,'method':method,'stress_mode':mode,'peer_count':n,'context_status':status})
    return pd.DataFrame(out)

def summarize(rows:pd.DataFrame)->dict[str,Any]:
    out={}
    for method,g in rows.dropna(subset=['predicted_price']).groupby('method'):
        out[method]={'global':metrics(g.actual_price,g.predicted_price),'priceBands':{b:metrics(x.actual_price,x.predicted_price) for b,x in g.assign(price_band=g.actual_price.map(band)).groupby('price_band')},'coverage':{'eligible':len(g),'unavailable':int((rows.method==method).sum()-len(g))}}
    return out

def main()->int:
    OUT.mkdir(parents=True,exist_ok=True);df=load()
    contract={'version':'index_fair_value_f2r_peer_contract_v1','datasetFingerprint':EXPECTED,'structuralSource':'F2 Model C whole-root-set-held OOF predictions','f2ModelDReconstruction':{'peerPrices':'outer-training roots only','targetOwnPriceExcluded':True,'heldOutTargetRootPeerPricesAvailable':False,'aggregation':'training-only era + Treatment + rarity median with fallbacks','sameSetTargetBlindAlreadyTested':False},'primaryValidation':'hide one target canonical card; permit other current prices in its root set','antiLeakage':['exclude target canonical_card_id','one selected canonical variant per row','no target history, set total, rank, or target-containing aggregate','related same-name family removed in stress test'],'peerDefinitions':{'P1':'same root + Treatment','P2':'same root + nearest scarcity','P3':'same root + nearest scarcity and Appeal','P4':'robust weighted same-root Treatment/scarcity/Appeal','P5':'cross-set same-era fallback only; represented by F2 B3/D and not retuned'},'methods':list(METHODS),'minimumPeers':{'3':'LOW_CONTEXT boundary','5':'LOW_CONTEXT','10':'MEDIUM_CONTEXT','20':'HIGH_CONTEXT','under3':'UNAVAILABLE'},'seed':SEED}
    contract['contractFingerprint']=hashlib.sha256(json.dumps(contract,sort_keys=True,separators=(',',':')).encode()).hexdigest();dump('index_fair_value_f2r_peer_contract.json',contract)
    primary=run_mode(df,'target_only');summary=summarize(primary)
    # Selection is lexicographic on price-band positive R2 count, global MdAPE, then MAE.
    ranking=[]
    for method,res in summary.items():ranking.append((sum(1 for x in res['priceBands'].values() if x['r2Dollars'] is not None and x['r2Dollars']>0),-res['global']['MdAPE'],-res['global']['meanAbsoluteDollarError'],method))
    best=max(ranking)[3];best_rows=primary[primary.method==best]
    stress={}
    for mode in ('target_only','drop_nearest_1','drop_nearest_3','related_family','random_10','random_20'):
        rows=best_rows if mode=='target_only' else run_mode(df,mode,(best,));stress[mode]=summarize(rows)[best]
    dump('index_fair_value_f2r_leave_many_out_results.json',{'selectedMethod':best,'results':stress})
    dump('index_fair_value_f2r_price_band_results.json',summary)
    dump('index_fair_value_f2r_set_results.json',{m:{str(k):metrics(g.actual_price,g.predicted_price) for k,g in primary[primary.method==m].groupby('set_name')} for m in METHODS})
    primary.to_csv(OUT/'index_fair_value_f2r_target_blind_predictions.csv',index=False,quoting=csv.QUOTE_MINIMAL)
    best_rows=best_rows.copy();best_rows['gap']=best_rows.actual_price-best_rows.predicted_price;best_rows['abs_gap']=abs(best_rows.gap);best_rows['pct_error']=(best_rows.predicted_price-best_rows.actual_price)/best_rows.actual_price*100
    gaps={'definition':'Market Price - target-blind Fair Value; missing-variable diagnostic only','selectedMethod':best,'bySet':{str(k):{'n':len(g),'medianGap':float(g.gap.median())} for k,g in best_rows.groupby('set_name')},'byTreatment':{str(k):{'n':len(g),'medianGap':float(g.gap.median())} for k,g in best_rows.groupby('treatment_key')},'byBand':{str(k):{'n':len(g),'medianGap':float(g.gap.median())} for k,g in best_rows.assign(price_band=best_rows.actual_price.map(band)).groupby('price_band')},'largest':best_rows.nlargest(50,'abs_gap').to_dict('records')};dump('index_fair_value_f2r_gap_diagnostics.json',gaps)
    f2models=json.loads((OUT/'index_fair_value_f2_model_results.json').read_text(encoding='utf-8'));f2base=json.loads((OUT/'index_fair_value_f2_baseline_results.json').read_text(encoding='utf-8'))
    comparison={'B3':f2base['B3']['global'],'B7':f2base['B7']['global'],'F2_Model_C':f2models['C']['global'],'F2_Model_D':f2models['D']['global'],'F2R_best':summary[best]['global']}
    positive=sum(1 for x in summary[best]['priceBands'].values() if x['r2Dollars'] is not None and x['r2Dollars']>0)
    ready=positive>=4 and summary[best]['global']['MdAPE']<=25 and summary[best]['global']['within30Pct']>=55 and stress['related_family']['global']['MdAPE']<=30
    decision={'version':'index_fair_value_f2r_decision_v1','status':'INDEX_FAIR_VALUE_MARKET_ANCHORED_CANDIDATE_READY' if ready else 'INDEX_FAIR_VALUE_NEEDS_NEW_MARKET_DATA','selectedMethod':best if ready else None,'bestDiagnosticMethod':best,'comparison':comparison,'positivePriceBands':positive,'allBandFailureResolved':positive==7,'f3Ready':ready,'reason':'Passes target-blind local appraisal gate.' if ready else 'Market anchoring does not pass the frozen within-band, relative-error, and related-family stress gates.'};dump('index_fair_value_f2r_decision.json',decision)
    article={'version':'index_fair_value_article_evidence_f2r_v1','preservesF2Failure':True,'sources':{'structuralFailure':'index_fair_value_f2_model_results.json','marketAnchored':'index_fair_value_f2r_target_blind_predictions.csv','bands':'index_fair_value_f2r_price_band_results.json','stress':'index_fair_value_f2r_leave_many_out_results.json','gaps':'index_fair_value_f2r_gap_diagnostics.json'},'articleWritten':False};dump('index_fair_value_f2r_article_evidence.json',article)
    print(json.dumps({'decision':decision,'bestBands':summary[best]['priceBands'],'stress':stress},indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
