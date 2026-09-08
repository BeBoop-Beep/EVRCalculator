"""C3A.5 price-independent Trainer horizon and shared Subject Appeal research."""
import hashlib,json,math,sys
from pathlib import Path
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from backend.scripts.research_collector_c3a_components import pranks,spearman,summary,examples,playability

OLD12='a0d52164-f6a5-4016-8b1b-8f01740db5f9';NEW12='b3997343-1363-45aa-b1b0-9a6de1ce3793';NEW5='648e5375-47cb-4972-b01d-faceb6348d1d'
OVERRIDES=ROOT/'backend/config/pokemon_collector_trainer_query_overrides_v1.json';VERSION='collector_c3a5_subject_contract_research_v1'
def paged(factory):
 out=[];start=0
 while True:
  part=factory().range(start,start+999).execute().data;out+=part
  if len(part)<1000:return out
  start+=1000
def load_run(sb,rid):
 rows=sb.table('pokemon_collector_entity_observations').select('collector_entity_id,raw_entity_name,external_entity_key,normalized_observation_score,raw_row_json').eq('source_run_id',rid).execute().data
 return {x['collector_entity_id']:{**x,'value':float(x['normalized_observation_score'] or 0)} for x in rows}
def set_overlap(a,b,n):
 aa=set(sorted(a,key=a.get,reverse=True)[:n]);bb=set(sorted(b,key=b.get,reverse=True)[:n]);return len(aa&bb),len(aa|bb),len(aa&bb)/n
def concentration(v,n):
 vals=sorted(v.values(),reverse=True);return sum(vals[:n])/sum(vals) if sum(vals) else 0
def transformed_distribution(values):
 vals=sorted(values.values());positive=[x for x in vals if x>0];med=positive[len(positive)//2] if positive else 0
 # Fixed monotonic saturation, not fitted to an outcome. Median positive maps near 50.
 scale=med/max(math.log(2),1e-9) if med else 1
 return {k:100*(1-math.exp(-v/scale)) if v>0 else 0 for k,v in values.items()}
def main():
 load_dotenv(ROOT/'backend/.env',override=False);from backend.db.clients.supabase_client import supabase
 d0,d12,d5=load_run(supabase,OLD12),load_run(supabase,NEW12),load_run(supabase,NEW5);names={k:v['raw_entity_name'] for k,v in d12.items()};raw12={k:v['value'] for k,v in d12.items()};raw5={k:v['value'] for k,v in d5.items()};p12=pranks(raw12);p5=pranks(raw5);blend4060={k:.4*p12[k]+.6*p5[k] for k in p12};blend2575={k:.25*p12[k]+.75*p5[k] for k in p12}
 shared={k for k in raw12 if raw12[k]>0 and raw5[k]>0};switch=[k for k in raw12 if (raw12[k]>0)!=(raw5[k]>0)];delta={k:blend4060[k]-p12[k] for k in p12}
 override=json.loads(OVERRIDES.read_text(encoding='utf-8'));byname={v:k for k,v in names.items()};audit=[]
 for name,reason in override['overrides'].items():
  k=byname[name];before=d0[k];after=d12[k]
  audit.append({'trainer':name,'ambiguityReason':reason,'originalQuery':before['external_entity_key'],'testedAlternative':after['external_entity_key'],'selectedCanonicalQuery':after['external_entity_key'],'selectionRule':override['selectionRule'],'beforeScore':before['value'],'afterScore':after['value'],'beforeStatus':before['raw_row_json']['sourceStatus'],'afterStatus':after['raw_row_json']['sourceStatus']})
 pokemon=paged(lambda:supabase.table('pokemon_desirability_composite_scores').select('pokemon_reference_id,pokemon_name,desirability_score,desirability_rank').eq('scoring_version','pokemon_desirability_composite_v1').eq('fan_popularity_snapshot_id',2));pokemon_raw={str(x['pokemon_reference_id']):float(x['desirability_score']) for x in pokemon};pokemon_names={str(x['pokemon_reference_id']):x['pokemon_name'] for x in pokemon};pokemon_pct=pranks(pokemon_raw);pokemon_sat=transformed_distribution(pokemon_raw);trainer_sat=transformed_distribution(blend4060)
 combined=list(pokemon_pct.values())+list(blend4060.values());observed_median=sorted(combined)[len(combined)//2]
 config={'trainerRuns':[NEW12,NEW5],'trainerTransform':'positive-only within-horizon percentile','trainerBlend':{'12m':.4,'5y':.6},'pokemonSource':{'scoringVersion':'pokemon_desirability_composite_v1','fanSnapshotId':2},'subjectCandidates':['raw preservation','within-domain positive percentile','fixed exponential saturation'],'neutralCandidates':[50,'combined observed median'],'missing':'unavailable, no negative adjustment','artistEnabled':False}
 report={'scoringVersion':VERSION,'status':'research_shadow','configuration':config,'formulaFingerprint':hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest(),
  'queryAudit':{'entitiesAudited':len(d12),'overrides':audit,'overrideCount':len(audit),'old12Run':OLD12,'corrected12Run':NEW12},
  'trainerHorizons':{'fiveYearRun':NEW5,'fullCohortSpearman':spearman(raw12,raw5),'sharedNonzeroCount':len(shared),'sharedNonzeroSpearman':spearman({k:raw12[k] for k in shared},{k:raw5[k] for k in shared}),'zeroNonzeroSwitchCount':len(switch),'zeroNonzeroSwitchShare':len(switch)/len(raw12),'top25':set_overlap(p12,p5,25),'bottomQuartile':set_overlap({k:-p12[k] for k in p12},{k:-p5[k] for k in p5},68),'top5Concentration12m':concentration(raw12,5),'top10Concentration12m':concentration(raw12,10),'top5Concentration5y':concentration(raw5,5),'top10Concentration5y':concentration(raw5,10),
   'candidates':{'A_12m':summary(p12),'B_5y':summary(p5),'C_40_60':summary(blend4060),'D_25_75':summary(blend2575)},'A_vsB':spearman(p12,p5),'A_vsC':spearman(p12,blend4060),'B_vsC':spearman(p5,blend4060),'largestMovers':[{'name':names[k],'rankDeltaCMinusA':delta[k],'A':p12[k],'B':p5[k],'C':blend4060[k]} for k in sorted(delta,key=lambda k:abs(delta[k]),reverse=True)[:20]],'examplesC':examples(blend4060,names)},
  'subjectContractCandidates':{'rawScale':{'pokemon':summary(pokemon_raw),'trainer':summary(blend4060),'interpretation':'preserve source output; cross-domain magnitude assumed'},'withinDomainPercentile':{'pokemon':summary(pokemon_pct),'trainer':summary(blend4060),'interpretation':'score is relative standing in the subject domain; zero evidence remains zero'},'boundedSaturation':{'pokemon':summary(pokemon_sat),'trainer':summary(trainer_sat),'interpretation':'fixed monotonic saturation with positive-domain median near 50'}},
  'subjectExamples':{'pokemonRaw':examples(pokemon_raw,pokemon_names,8),'pokemonPercentile':examples(pokemon_pct,pokemon_names,8),'trainerRaw':examples(blend4060,names,8)},
  'neutralPolicies':{'semanticMidpoint':50.0,'combinedObservedMedian':observed_median,'meaning':'No named-subject preference credited or penalized; never means undesirable.'},'playabilityFrozen':playability(supabase)}
 print(json.dumps(report,indent=2,ensure_ascii=False));return 0
if __name__=='__main__':raise SystemExit(main())
