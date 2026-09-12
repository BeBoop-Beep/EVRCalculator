"""Freeze and execute the D1 eBay Browse research pilot (research artifacts only)."""
from __future__ import annotations
import base64, hashlib, json, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from backend.scripts.index_fair_value_ebay_supply import VERSION, aggregate, build_query, classify_listing

ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'backend/artifacts/index_fair_value'; N=70
def dump(name,obj): (OUT/name).write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def env():
    out={}
    for line in (ROOT/'frontend/.env.local').read_text(encoding='utf-8').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            k,v=line.split('=',1);out[k.strip()]=v.strip().strip('"').strip("'")
    return out
def token(cfg):
    basic=base64.b64encode(f"{cfg['EBAY_CLIENT_ID']}:{cfg['EBAY_CLIENT_SECRET']}".encode()).decode()
    req=urllib.request.Request('https://api.ebay.com/identity/v1/oauth2/token',data=b'grant_type=client_credentials&scope=https%3A%2F%2Fapi.ebay.com%2Foauth%2Fapi_scope',headers={'Authorization':f'Basic {basic}','Content-Type':'application/x-www-form-urlencoded'})
    return json.load(urllib.request.urlopen(req,timeout=30))['access_token']
def choose():
    rows=pd.DataFrame(json.loads((OUT/'index_fair_value_f1_dataset.json').read_text(encoding='utf-8'))['rows']);rows=rows[rows.eligible_v1_strict].copy()
    bins=[0,5,10,25,50,100,250,float('inf')];rows['band']=pd.cut(rows.target_market_price_usd,bins,right=False,labels=False)
    picks=[]
    for _,g in rows.groupby('band'):
        g=g.sort_values(['collector_appeal','canonical_card_id']); idx=sorted(set(round(x) for x in pd.Series(range(10)).map(lambda i:i*(len(g)-1)/9)))
        picks.extend(g.iloc[idx].to_dict('records'))
    return sorted(picks,key=lambda x:x['canonical_card_id'])[:N]
def main():
    cards=choose(); members=[]
    for x in cards:
        member={k:x.get(k) for k in ('canonical_card_id','card_variant_id','card_name','card_number','set_name','era','treatment_key','collector_appeal','pull_probability','target_market_price_usd')};member['query']=build_query(x);members.append(member)
    cohort={'version':VERSION,'frozenBeforeQuery':True,'size':len(cards),'membershipFingerprint':hashlib.sha256('|'.join(x['canonical_card_id'] for x in cards).encode()).hexdigest(),'cards':members};dump('ebay_pilot_cohort.json',cohort)
    tok=token(env()); observations=[]; cards_out=[]; start=time.perf_counter(); errors=[]
    for card in cards:
        q=build_query(card); params=urllib.parse.urlencode({'q':q['query'],'category_ids':q['category_id'],'limit':q['limit'],'filter':q['filters']}); url='https://api.ebay.com/buy/browse/v1/item_summary/search?'+params
        req=urllib.request.Request(url,headers={'Authorization':f'Bearer {tok}','X-EBAY-C-MARKETPLACE-ID':'EBAY_US','Accept':'application/json'}); t=time.perf_counter()
        try: data=json.load(urllib.request.urlopen(req,timeout=30))
        except Exception as exc: errors.append({'canonical_card_id':card['canonical_card_id'],'error_type':type(exc).__name__});continue
        latency=round((time.perf_counter()-t)*1000); local=[]
        for item in data.get('itemSummaries',[]):
            c=classify_listing(card,item); price=(item.get('price') or {}).get('value'); seller=(item.get('seller') or {}).get('username')
            c.update({'price':float(price) if price else None,'shipping':None,'seller_id':seller,'buying_options':item.get('buyingOptions',[])});local.append(c)
        counts={s:sum(x['match_state']==s for x in local) for s in ('EXACT_MATCH','LIKELY_MATCH','AMBIGUOUS','WRONG_CARD','LOT_OR_BUNDLE','GRADED','RAW_NON_NM','NON_ENGLISH','ACCESSORY','SEALED_PRODUCT','OTHER')}
        agg=aggregate(local); cards_out.append({'canonical_card_id':card['canonical_card_id'],'query_total_estimate':data.get('total'),'returned_count':len(local),'latency_ms':latency,'counts':counts,'metrics':agg}); observations.extend([dict({'canonical_card_id':card['canonical_card_id']},**x) for x in local])
    elapsed=time.perf_counter()-start; total=len(observations); accepted=sum(x['match_state']=='EXACT_MATCH' and x['raw_condition_state']=='RAW_ELIGIBLE_CONDITION' for x in observations); ambiguous=sum(x['match_state'] in {'LIKELY_MATCH','AMBIGUOUS'} for x in observations)
    sample=[]
    for state in ('EXACT_MATCH','LIKELY_MATCH','AMBIGUOUS','WRONG_CARD','LOT_OR_BUNDLE','GRADED','NON_ENGLISH','ACCESSORY','SEALED_PRODUCT'):
        sample.extend([{'canonical_card_id':x['canonical_card_id'],'match_state':state,'title':x['evidence']['title'],'condition':x['evidence']['condition']} for x in observations if x['match_state']==state][:5])
    result={'version':VERSION,'status':'completed' if not errors else 'partial','marketplace':'EBAY_US','observed_at':datetime.now(timezone.utc).isoformat(),'captured_at':datetime.now(timezone.utc).isoformat(),'api_calls':len(cards_out),'cards_attempted':len(cards),'results_returned':total,'exact_accepted':accepted,'likely_matches':sum(x['match_state']=='LIKELY_MATCH' for x in observations),'ambiguous_results':ambiguous,'rejected_results':total-accepted,'cards_zero_exact':sum(x['metrics']['exact_match_listing_count']==0 for x in cards_out),'average_exact_listings_per_card':accepted/len(cards_out) if cards_out else 0,'mean_latency_ms':sum(x['latency_ms'] for x in cards_out)/len(cards_out) if cards_out else None,'rate_limit_events':0,'errors':errors,'manual_review_sample':sample,'card_results':cards_out};dump('ebay_pilot_results.json',result)
    quality={'version':VERSION,'acceptedRule':'EXACT_MATCH + RAW_ELIGIBLE_CONDITION','acceptedCount':accepted,'coveragePct':100*sum(x['metrics']['exact_match_listing_count']>0 for x in cards_out)/len(cards_out),'ambiguityRatePct':100*ambiguous/total if total else None,'lotBundleRejectionRatePct':100*sum(x['match_state']=='LOT_OR_BUNDLE' for x in observations)/total if total else None,'gradedContaminationPct':100*sum(x['match_state']=='GRADED' for x in observations)/total if total else None,'wrongCardContaminationPct':100*sum(x['match_state']=='WRONG_CARD' for x in observations)/total if total else None,'automatedPrecisionEstimate':None,'manualReviewRequired':True,'reason':'No title-only classifier may self-certify precision; sampled human labels are required.'};dump('ebay_match_quality_report.json',quality)
    print(json.dumps({'result':{k:v for k,v in result.items() if k!='card_results'},'quality':quality},indent=2))
if __name__=='__main__':main()
