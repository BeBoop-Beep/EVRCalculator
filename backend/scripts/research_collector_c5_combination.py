"""C5 research-only combination study over frozen C4 D and generalized F."""
from __future__ import annotations
import hashlib,json,math,statistics,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from backend.desirability.collector_appeal import (collector_appeal_v4_frequency_index,collector_appeal_v4_modifier_points,compute_collector_appeal_v4,COLLECTOR_APPEAL_V4_FORMULA_EXPRESSION)
from backend.scripts.research_collector_c3b_playability_lift import pranks,spearman,summary

C4=ROOT/'backend/artifacts/collector_c4_set_components_shadow_v1.json';VERSION='collector_appeal_c5_generalized_d_f_research_v1';MISSING='collector_appeal_unavailable_no_generalized_frequency'
POSITIVE_LAMBDAS=(.10,.20,.30,.40);SIGNED_CAPS=((2.0,1.0),(4.0,2.0),(6.0,3.0));WEIGHTS=((.90,.10),(.80,.20));WINNER='signed_up2_down1'
def clamp(x):return max(0.0,min(100.0,x))
def score_v4(d,f):
 v=compute_collector_appeal_v4(d/100 if d is not None else None,f);return None if v is None else v*100
def positive_headroom(d,f,lam):
 i=collector_appeal_v4_frequency_index(f);return None if d is None or i is None else d+lam*i*(100-d)
def signed(d,f,up,down):
 i=collector_appeal_v4_frequency_index(f)
 if d is None or i is None:return None
 z=2*i-1;return clamp(d+(up*z if z>=0 else down*z))
def weighted(d,f,wd,wf):
 i=collector_appeal_v4_frequency_index(f);return None if d is None or i is None else wd*d+wf*i*100
def ranks(values):
 order=sorted(values,key=values.get,reverse=True);out={};i=0
 while i<len(order):
  j=i+1
  while j<len(order) and values[order[j]]==values[order[i]]:j+=1
  rank=(i+1+j)/2
  for key in order[i:j]:out[key]=rank
  i=j
 return out
def diagnostics(values,dvals,fvals):
 rd,rc=ranks(dvals),ranks(values);moves={k:abs(rc[k]-rd[k]) for k in values};sv=summary(moves)
 dorder=sorted(dvals,key=dvals.get);inversions=sum(values[dorder[i]]>values[dorder[i+1]] for i in range(len(dorder)-1))
 return {'distribution':summary(values),'spearmanVsD':spearman(values,dvals),'spearmanVsF':spearman(values,fvals),'rankMovement':{'medianAbsolute':sv['median'],'maximum':sv['max'],'atLeast3':sum(x>=3 for x in moves.values()),'atLeast5':sum(x>=5 for x in moves.values()),'atLeast10':sum(x>=10 for x in moves.values()),'topGainers':sorted(({'setId':k,'ranksGained':rd[k]-rc[k]} for k in values),key=lambda x:x['ranksGained'],reverse=True)[:5],'topDecliners':sorted(({'setId':k,'ranksLost':rc[k]-rd[k]} for k in values),key=lambda x:x['ranksLost'],reverse=True)[:5]},'nearestDNeighborInversions':inversions,'ceilingCount':sum(x>=100 for x in values.values()),'floorCount':sum(x<=0 for x in values.values())}
def hypothetical():
 fs={'low':1/16,'neutral':1/8,'high':1/4};out={}
 for d in (50,70,80,90,95,99):
  out[str(d)]={label:{'F':f,'index':collector_appeal_v4_frequency_index(f),'v4':score_v4(d,f),'preferred':signed(d,f,2,1),'preferredModifier':signed(d,f,2,1)-d,'positive20':positive_headroom(d,f,.2),'weighted90_10':weighted(d,f,.9,.1)} for label,f in fs.items()}
 pairs=[('sameD',90,1/16,90,1/4),('strongerRosterModeratelyLowerF',92,1/8,88,1/4),('excellentTerrible',98,1/32,90,1/8),('moderateExcellent',70,1/4,90,1/8)]
 return {'grid':out,'pairs':[{'case':n,'a':{'D':da,'F':fa,'score':signed(da,fa,2,1)},'b':{'D':db,'F':fb,'score':signed(db,fb,2,1)}} for n,da,fa,db,fb in pairs]}
def main(output):
 c4=json.loads(C4.read_text(encoding='utf-8'));complete=[x for x in c4['sets'] if x['frequency']['card_gt50']['value'] is not None];d={x['set_id']:x['collectorRosterDesirability'] for x in complete};f={x['set_id']:x['frequency']['card_gt50']['value'] for x in complete}
 candidates={'d_only':dict(d),'v4_signed_up4_down2':{k:score_v4(d[k],f[k]) for k in d}}
 for lam in POSITIVE_LAMBDAS:candidates[f'positive_headroom_{lam:.2f}']={k:positive_headroom(d[k],f[k],lam) for k in d}
 for up,down in SIGNED_CAPS:candidates[f'signed_up{up:g}_down{down:g}']={k:signed(d[k],f[k],up,down) for k in d}
 for wd,wf in WEIGHTS:candidates[f'weighted_{int(wd*100)}_{int(wf*100)}']={k:weighted(d[k],f[k],wd,wf) for k in d}
 metrics={name:diagnostics(vals,d,f) for name,vals in candidates.items()};winner=candidates[WINNER];rw,rD,rF=ranks(winner),ranks(d),ranks(f)
 rows=[]
 for x in c4['sets']:
  sid=x['set_id'];fv=x['frequency']['card_gt50']['value']
  if fv is None:
   rows.append({'set_id':sid,'set_name':x['set_name'],'generalizedD':x['collectorRosterDesirability'],'generalizedF':None,'frequencyIndex':None,'collectorAppeal':None,'status':'unavailable','reason':MISSING})
   continue
  oldca=score_v4(x['oldUniversalSetDesirability'],x['oldPokemonOnlyF']) if x.get('oldUniversalSetDesirability') is not None and x.get('oldPokemonOnlyF') is not None else None
  rows.append({'set_id':sid,'set_name':x['set_name'],'generalizedD':d[sid],'generalizedF':fv,'frequencyIndex':collector_appeal_v4_frequency_index(fv),'collectorAppeal':winner[sid],'modifierPoints':winner[sid]-d[sid],'rank':rw[sid],'dRank':rD[sid],'fRank':rF[sid],'candidates':{k:v[sid] for k,v in candidates.items()},'oldUniversalD':x.get('oldUniversalSetDesirability'),'oldPokemonOnlyF':x.get('oldPokemonOnlyF'),'reconstructedOldV4':oldca,'status':'available','reason':None})
 # Fixed-input robustness: score deltas; ranks are recomputed independently per perturbation.
 perturb={}
 for label,factor in [('F-20%',.8),('F-10%',.9),('F+10%',1.1),('F+20%',1.2)]:
  vals={k:signed(d[k],min(1,f[k]*factor),2,1) for k in d};perturb[label]={'scoreDelta':summary({k:vals[k]-winner[k] for k in d}),'rankSpearman':spearman(vals,winner),'maxAbsoluteRankMove':max(abs(ranks(vals)[k]-rw[k]) for k in d)}
 for delta in (-2,-1,1,2):
  vals={k:signed(clamp(d[k]+delta),f[k],2,1) for k in d};perturb[f'D{delta:+}']={'scoreDelta':summary({k:vals[k]-winner[k] for k in d}),'rankSpearman':spearman(vals,winner),'maxAbsoluteRankMove':max(abs(ranks(vals)[k]-rw[k]) for k in d)}
 threshold={}
 for t in (50,55,60):
  ft={x['set_id']:x['frequency'][f'card_gt{t}']['value'] for x in complete};vals={k:signed(d[k],ft[k],2,1) for k in d};threshold[str(t)]={'spearmanVsPrimary':spearman(vals,winner),'scoreDelta':summary({k:vals[k]-winner[k] for k in d}),'maxAbsoluteRankMove':max(abs(ranks(vals)[k]-rw[k]) for k in d)}
 config={'version':VERSION,'winner':WINNER,'formula':'sF = canonical V4 fixed log2 frequency index; z = 2*sF-1; m = 2*z if z>=0 else 1*z; CA = clamp(D+m,0,100)','frequencyTransformSource':COLLECTOR_APPEAL_V4_FORMULA_EXPRESSION,'frequencyTransform':{'zero':'one desirable hit per 16 packs or worse','neutral':'one per 8 packs','one':'one per 4 packs or better'},'modifier':{'up':2,'down':1},'dFingerprint':c4['collectorRosterFormulaFingerprint'],'fFingerprint':c4['generalizedFrequencyFormulaFingerprint'],'supported':'C4 F status available only','missingReason':MISSING,'dualPath':False,'playabilitySeparateTerm':False,'price':False,'artist':False,'treatment':False,'energy':False}
 fp=hashlib.sha256(json.dumps(config,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 for row in rows:row.update({'c3bFingerprint':c4['configuration']['sourceC3bFingerprint'],'c4DFingerprint':c4['collectorRosterFormulaFingerprint'],'c4FFingerprint':c4['generalizedFrequencyFormulaFingerprint'],'c5Fingerprint':fp})
 report={'decision':'COLLECTOR_APPEAL_COMBINATION_READY','configuration':config,'formulaFingerprint':fp,'candidateMetrics':metrics,'dominanceAndPairs':hypothetical(),'perturbationSensitivity':perturb,'thresholdCarryThrough':threshold,'dualPathConclusion':'not_scored_not_required; D+F represents roster quality and delivery frequency without an identified residual construct requiring P','supportedCount':len(complete),'unavailableCount':len(rows)-len(complete),'rows':rows}
 output.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8');print(json.dumps({k:v for k,v in report.items() if k not in {'rows','candidateMetrics'}},indent=2));return 0
if __name__=='__main__':
 import argparse;p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'backend/artifacts/collector_c5_combination_shadow_v1.json');raise SystemExit(main(p.parse_args().output))
