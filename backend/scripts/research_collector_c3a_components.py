"""Reproducible, price-independent C3A component research; never promotes scores."""
import hashlib, json, math, statistics, sys
from datetime import date
from collections import defaultdict
from pathlib import Path
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

TRAINER_RUN='a0d52164-f6a5-4016-8b1b-8f01740db5f9'
OLD_TRAINER_RUN='4f1fdb9d-863c-430c-a9ff-ddef0966155d'
LIMITLESS_RUN='9947aaf7-8647-484f-8c9c-2cec59792cdb'
ARTIST_12M='1806d3a4-ae67-46fb-9e42-0bf64e7af6cb'; ARTIST_5Y='25a9ffbf-5069-44eb-9939-643dc297326f'
VERSION='collector_c3a_component_research_v1'

def paged(factory):
    out=[];start=0
    while True:
        part=factory().range(start,start+999).execute().data;out+=part
        if len(part)<1000:return out
        start+=1000
def pranks(values):
    out={k:0.0 for k,v in values.items() if v == 0}
    ordered=sorted(((k,v) for k,v in values.items() if v != 0),key=lambda x:(x[1],x[0]));n=max(len(ordered),1);i=0
    while i < len(ordered):
        j=i+1
        while j < len(ordered) and ordered[j][1] == ordered[i][1]:j+=1
        tied_rank=(i+j+1)/2
        for k,_ in ordered[i:j]:out[k]=100*tied_rank/n
        i=j
    return out
def spearman(a,b):
    keys=set(a)&set(b)
    if len(keys)<2:return None
    ra=pranks({k:a[k] for k in keys});rb=pranks({k:b[k] for k in keys});ma=sum(ra.values())/len(keys);mb=sum(rb.values())/len(keys)
    num=sum((ra[k]-ma)*(rb[k]-mb) for k in keys);den=math.sqrt(sum((ra[k]-ma)**2 for k in keys)*sum((rb[k]-mb)**2 for k in keys))
    return num/den if den else None
def summary(scores):
    vals=sorted(scores.values()); n=len(vals)
    at=lambda p: vals[min(n-1,int((n-1)*p))] if n else None
    return {'count':n,'min':at(0),'p10':at(.1),'p25':at(.25),'median':at(.5),'p75':at(.75),'p90':at(.9),'p95':at(.95),'max':at(1),'mean':sum(vals)/n if n else None}
def examples(scores,names,n=10):
    order=sorted(scores,key=lambda k:scores[k],reverse=True)
    return {'top':[{'name':names.get(k,k),'score':scores[k]} for k in order[:n]],'bottom':[{'name':names.get(k,k),'score':scores[k]} for k in order[-n:]]}

def trainer(supabase):
    entities=paged(lambda:supabase.table('pokemon_collector_entity_reference').select('id,display_name').eq('entity_type','trainer').eq('active',True));names={x['id']:x['display_name'] for x in entities}
    rows=supabase.table('pokemon_collector_entity_observations').select('collector_entity_id,normalized_observation_score,raw_row_json').eq('source_run_id',TRAINER_RUN).execute().data
    raw={x['collector_entity_id']:(x['normalized_observation_score'] or 0) for x in rows}; trends=pranks({k:math.log1p(v) for k,v in raw.items()})
    pollrun=supabase.table('pokemon_collector_source_runs').select('id,raw_payload_json').eq('source_name','official_pokemon_trainer_polls').eq('status','success').order('completed_at',desc=True).limit(1).execute().data[0]
    pollrows=supabase.table('pokemon_collector_entity_observations').select('collector_entity_id,raw_value').eq('source_run_id',pollrun['id']).eq('match_status','matched').execute().data
    poll=pranks({x['collector_entity_id']:float(x['raw_value']) for x in pollrows}); b=dict(trends);c=dict(trends)
    for k,p in poll.items(): b[k]=.8*trends[k]+.2*p; c[k]=trends[k]+.1*(p-trends[k])*(len(poll)/(len(poll)+20))
    old=supabase.table('pokemon_collector_entity_observations').select('collector_entity_id,normalized_observation_score').eq('source_run_id',OLD_TRAINER_RUN).execute().data
    oldscore={x['collector_entity_id']:(x['normalized_observation_score'] or 0) for x in old}
    focus=['Iono','Cynthia','Lillie','Marnie','Red','Skyla','Penny','Steven','Professor Juniper','Ghetsis'];byname={v:k for k,v in names.items()}
    return {'sourceRuns':[TRAINER_RUN,pollrun['id'],OLD_TRAINER_RUN],'pollContext':pollrun['raw_payload_json'].get('context'),'candidates':{
      'A_trends_only_log_percentile':{'distribution':summary(trends),'examples':examples(trends,names)},
      'B_trends_80_poll_20_represented_only':{'distribution':summary(b),'pollEntityCount':len(poll),'maxAbsolutePollMovement':max(abs(b[k]-trends[k]) for k in poll)},
      'C_shrunken_poll_prior_represented_only':{'distribution':summary(c),'pollEntityCount':len(poll),'maxAbsolutePollMovement':max(abs(c[k]-trends[k]) for k in poll)}},
      'repeatCaptureRankStability52EntityOverlap':spearman(raw,oldscore),'unknownShare':0,'focusExamples':{x:{'A':trends.get(byname.get(x)),'B':b.get(byname.get(x)),'C':c.get(byname.get(x))} for x in focus},
      'recommendation':'A_trends_only_log_percentile','rationale':'Sparse game-specific poll adds context-limited movement without demonstrated construct-validity gain; retain poll as a sensitivity annotation.'}

def playability(supabase):
    rows=paged(lambda:supabase.table('pokemon_playability_event_observations').select('*').eq('source_run_id',LIMITLESS_RUN)); refs=paged(lambda:supabase.table('pokemon_card_functional_reference').select('id,display_name,supertype'));names={x['id']:x['display_name'] for x in refs};types={x['id']:x['supertype'] for x in refs}
    by=defaultdict(list)
    for x in rows:
        if x.get('functional_reference_id'):by[x['functional_reference_id']].append(x)
    global_fields={x['event_external_id']:x['field_deck_count'] for x in rows};global_dates={x['event_external_id']:date.fromisoformat(x['event_date']) for x in rows};latest=max(global_dates.values())
    def build(exclude=None):
        eligible_fields={k:v for k,v in global_fields.items() if k!=exclude}; den=sum(eligible_fields.values())
        f={}
        for k,group in by.items():
            g=[x for x in group if x['event_external_id']!=exclude]
            if not g or not den:continue
            appearances=sum(x['deck_appearance_count'] for x in g);copies=sum(x['copy_count'] for x in g);top=sum(x['top_cut_deck_count'] for x in g);by_event={x['event_external_id']:x for x in g}
            shares={e:(by_event[e]['deck_appearance_count']/field if e in by_event else 0) for e,field in eligible_fields.items()};weights={e:math.exp(-math.log(2)*(latest-global_dates[e]).days/30) for e in eligible_fields}
            f[k]={'inclusion':appearances/den,'equalEventInclusion':sum(shares.values())/len(shares),'recencyInclusion':sum(shares[e]*weights[e] for e in shares)/sum(weights.values()),'copiesPerUsingDeck':copies/max(appearances,1),'weightedCopies':copies/den,'eventBreadth':len({x['event_external_id'] for x in g})/len(eligible_fields),'topCut':top/max(32*len(eligible_fields),1),'decks':appearances,'events':len({x['event_external_id'] for x in g})}
        ranks={name:pranks({k:v[name] for k,v in f.items()}) for name in ('inclusion','equalEventInclusion','recencyInclusion','copiesPerUsingDeck','weightedCopies','eventBreadth','topCut')}
        a={k:.60*ranks['inclusion'][k]+.25*ranks['copiesPerUsingDeck'][k]+.15*ranks['eventBreadth'][k] for k in f}
        b={k:.45*ranks['inclusion'][k]+.15*ranks['copiesPerUsingDeck'][k]+.15*ranks['eventBreadth'][k]+.15*ranks['topCut'][k]+.10*ranks['weightedCopies'][k] for k in f}
        c={k:b[k]*(1-math.exp(-f[k]['decks']/20))*(.5+.5*min(f[k]['events']/3,1)) for k in f}
        d={k:.45*ranks['equalEventInclusion'][k]+.15*ranks['copiesPerUsingDeck'][k]+.15*ranks['eventBreadth'][k]+.15*ranks['topCut'][k]+.10*ranks['weightedCopies'][k] for k in f}
        e={k:.45*ranks['recencyInclusion'][k]+.15*ranks['copiesPerUsingDeck'][k]+.15*ranks['eventBreadth'][k]+.15*ranks['topCut'][k]+.10*ranks['weightedCopies'][k] for k in f}
        return f,a,b,c,d,e
    f,a,b,c,d,e=build();largest=max(rows,key=lambda x:x['field_deck_count'])['event_external_id'];_,_,b_removed,_,_,_=build(largest)
    universe=len(refs);type_stats={t:{'functionsWithEvidence':sum(types.get(k)==t for k in f),'medianCandidateB':statistics.median([b[k] for k in f if types.get(k)==t])} for t in sorted(set(types.values())- {None}) if any(types.get(k)==t for k in f)}
    neutral_names=['Rare Candy','Ultra Ball','Buddy-Buddy Poffin','Switch','Crushing Hammer','Artazon','Area Zero Underdepths','Jamming Tower',"Team Rocket's Great Ball"]
    return {'sourceRuns':[LIMITLESS_RUN],'functionalUniverse':universe,'functionsWithEvidence':len(f),'unknownShare':1-len(f)/universe,'featureDistributions':{x:summary({k:v[x] for k,v in f.items()}) for x in ('inclusion','equalEventInclusion','recencyInclusion','copiesPerUsingDeck','weightedCopies','eventBreadth','topCut','decks','events')},
      'candidates':{'A_60inclusion_25copies_15eventBreadth':summary(a),'B_balanced_topcut':summary(b),'C_confidence_shrunk_B':summary(c),'D_equal_event_weight_B':summary(d),'E_30day_recency_weight_B':summary(e)},
      'ablation':{'A_vs_B_spearman':spearman(a,b),'B_vs_C_spearman':spearman(b,c),'B_vs_equalEventD_spearman':spearman(b,d),'B_vs_recencyE_spearman':spearman(b,e),'copiesVsInclusionSpearman':spearman({k:v['copiesPerUsingDeck'] for k,v in f.items()},{k:v['inclusion'] for k,v in f.items()})},
      'largestEventRemoved':{'eventId':largest,'candidateBRankSpearman':spearman(b,b_removed)},'supertypeDiagnostics':type_stats,'examples':examples(c,names),
      'unavailableFeature':'Archetype breadth/concentration cannot be derived from the accepted event-card aggregate rows; event breadth is explicitly only a proxy.',
      'confidencePolicy':{'knownMinimum':'at least 3 events or 20 using decks','belowMinimum':'unknown/insufficient; never negative','zeroAppearance':'unknown, not zero appeal'},
      'neutralFunctionalExamples':{name:max((c[k] for k in c if names.get(k)==name),default=None) for name in neutral_names},
      'windowRecommendation':'Store 30-day momentum and 90-day stability separately; this single accepted run cannot validate biweekly temporal stability.',
      'recommendation':'C_confidence_shrunk_B_research_candidate'}

def artist(supabase):
    data={}
    for label,rid in [('12m',ARTIST_12M),('5y',ARTIST_5Y)]:
        rows=supabase.table('pokemon_collector_entity_observations').select('collector_entity_id,raw_entity_name,normalized_observation_score').eq('source_run_id',rid).execute().data
        data[label]={x['collector_entity_id']:(x['normalized_observation_score'] or 0) for x in rows};names={x['collector_entity_id']:x['raw_entity_name'] for x in rows}
    candidates={}
    for label,vals in data.items():
        candidates[label+'_raw_percentile']=pranks(vals);candidates[label+'_log_percentile']=pranks({k:math.log1p(v) for k,v in vals.items()})
    blend={k:.4*candidates['12m_log_percentile'][k]+.6*candidates['5y_log_percentile'][k] for k in data['12m']};candidates['40_60_log_percentile_blend']=blend
    return {'sourceRuns':[ARTIST_12M,ARTIST_5Y],'candidateDistributions':{k:summary(v) for k,v in candidates.items()},'horizonRankSpearman':spearman(data['12m'],data['5y']),
      'blendExamples':examples(blend,names),'classification':'experimental_auxiliary_signal','recommendation':'defer_from_V1_keep_research_only',
      'rationale':'One-third zero/nonzero switching and top-end concentration are too horizon-sensitive for a V1 lift; log/rank saturation is suitable only for continued shadow tests.'}

def main():
    load_dotenv(ROOT/'backend/.env',override=False);from backend.db.clients.supabase_client import supabase
    report={'scoringVersion':VERSION,'status':'research_shadow','trainerAppeal':trainer(supabase),'playability':playability(supabase),'artistCurrentInterest':artist(supabase)}
    config={'trainer':['log1p','positive-only percentile','poll represented-only'],'playability':['A baseline','B top-cut balanced','C confidence shrinkage','D equal-event sensitivity','E 30-day recency sensitivity'],'artist':['positive-only raw percentile','positive-only log percentile','40/60 horizon blend']};report['configuration']=config;report['formulaFingerprint']=hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
    print(json.dumps(report,indent=2,ensure_ascii=False));return 0
if __name__=='__main__':raise SystemExit(main())
