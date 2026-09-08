"""C4 research-only Collector roster and generalized desirable-frequency study."""
from __future__ import annotations
import hashlib, json, math, statistics, sys
from collections import Counter, defaultdict
from pathlib import Path
from dotenv import load_dotenv

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from backend.desirability.collector_appeal_inputs import load_pull_rate_model
from backend.desirability.opening_appeal import union_probability_from_cards
from backend.desirability.rarity_buckets import HIT_BUCKETS, HIT_POLICY_VERSION, classify_rarity
from backend.scripts.research_collector_c3b_playability_lift import paged,pranks,spearman,summary

C3B_ARTIFACT=ROOT/'backend/artifacts/collector_c3b_card_appeal_shadow_v2.json'
VERSION='collector_c4_collector_roster_research_v1'; GROUP_VERSION='collector_group_contract_v1'
ROSTER_K=(2.0,3.0,4.5,6.0);THRESHOLDS=(50.0,55.0,60.0);WINNER_K=6.0;COVERAGE_FLOOR=.25

def group_keys(row):
 t=row['subject_type']
 if t in {'pokemon','trainer'}:
  return [(t,x.strip()) for x in str(row.get('subject_identity') or '').split(' + ') if x.strip()]
 if t=='neutral_functional' and row.get('playability_functional_identity'):
  return [('neutral_functional',row['playability_functional_identity'])]
 if t=='neutral_functional' and row.get('subject_identity')=='mechanical_pokemon_non_species_neutral_subject':
  return [('neutral_functional','exception:'+row['pokemon_tcg_api_card_id'])]
 return []
def representative(values,method):
 vals=sorted(values,reverse=True)
 if not vals:return None
 if method=='max':return vals[0]
 if method=='mean':return statistics.mean(vals)
 if method=='top2_mean':return statistics.mean(vals[:2])
 raise ValueError(method)
def raw_mass(values):return sum(math.sqrt(max((v-50)/50,0)) for v in values)
def roster_score(values,k):
 raw=raw_mass(values);return 100*(1-math.exp(-raw/k)) if raw>0 else 0.0
def desirable_frequency(cards):
 dedup={x['canonical_card_id']:x for x in cards}
 return union_probability_from_cards(list(dedup.values()))
def hit_eligible_cards(cards):return [row for row in cards if row.get('hit_eligibility') is True]
def build_groups(cards,method):
 groups=defaultdict(list)
 for row in cards:
  for kind,key in group_keys(row):groups[(kind,key)].append(row)
 return [{'key':f'{kind}:{key}','type':kind,'identity':key,'appeal':representative([x['final_card_collector_appeal'] for x in rows],method),'cards':rows} for (kind,key),rows in groups.items()]
def main(output):
 load_dotenv(ROOT/'backend/.env',override=False);from backend.db.clients.supabase_client import supabase
 c3b=json.loads(C3B_ARTIFACT.read_text(encoding='utf-8'));cards=c3b['shadowRows'];byset=defaultdict(list)
 for row in hit_eligible_cards(cards):byset[row['set_id']].append(row)
 sets=paged(lambda:supabase.table('sets').select('id,name,canonical_key'));setmeta={str(x['id']):x for x in sets}
 pull=load_pull_rate_model(supabase)
 all_cards=paged(lambda:supabase.table('pokemon_canonical_cards').select('id,set_id,supertype,rarity,catalog_role,opening_eligible,canonical_review_status').eq('catalog_role','main').eq('opening_eligible',True).eq('canonical_review_status','approved'))
 energy=Counter(str(x['set_id']) for x in all_cards if str(x.get('supertype') or '').casefold()=='energy' and classify_rarity(x.get('rarity')).bucket in HIT_BUCKETS)
 # Exact reproducibility baseline: read existing public Universal authority, never recompute or write it.
 try:
  from backend.db.services.universal_set_desirability_service import get_universal_desirability_bundle
  old=get_universal_desirability_bundle(force_refresh=True).get('payloads') or {}
 except Exception as exc:
  old={};old_error=str(exc)
 else:old_error=None
 results=[];rep_scores=defaultdict(dict);k_scores=defaultdict(dict);simple_scores=defaultdict(dict)
 for sid,hit_cards in byset.items():
  rarity_model=pull.get(sid) or {};modeled={}
  for card in hit_cards:
   model=rarity_model.get(classify_rarity(card.get('rarity')).normalized_key)
   modeled[card['canonical_card_id']]={**card,'pull_probability':model['probability'],'slot_group':model['slot_group']} if model else {**card,'pull_probability':None,'slot_group':None}
  candidates={m:build_groups(hit_cards,m) for m in ('max','mean','top2_mean')}
  for method,groups in candidates.items():rep_scores[method][sid]=roster_score([g['appeal'] for g in groups],WINNER_K)
  groups=candidates['max'];appeals=[g['appeal'] for g in groups]
  for k in ROSTER_K:k_scores[str(k)][sid]=roster_score(appeals,k)
  positive=[x for x in appeals if x>50];simple_scores['positive_mean'][sid]=statistics.mean(positive) if positive else 0
  simple_scores['top5_mean'][sid]=statistics.mean(sorted(appeals,reverse=True)[:5]) if appeals else 0
  fdata={}
  for threshold in THRESHOLDS:
   group_eligible={c['canonical_card_id'] for g in groups if g['appeal']>threshold for c in g['cards']}
   card_eligible={c['canonical_card_id'] for c in hit_cards if c['final_card_collector_appeal']>threshold}
   for policy,eligible in [('card',card_eligible),('group',group_eligible)]:
    desirable=[modeled[cid] for cid in eligible];covered=[x for x in desirable if x['pull_probability'] is not None]
    total_mass=sum(max(modeled[cid]['final_card_collector_appeal']-50,0) for cid in eligible)
    covered_mass=sum(max(x['final_card_collector_appeal']-50,0) for x in covered);share=covered_mass/total_mass if total_mass else None
    value=desirable_frequency(covered) if covered and share is not None and share>=COVERAGE_FLOOR else None
    fdata[f'{policy}_gt{int(threshold)}']={'eligibleCards':len(eligible),'modeledCards':len(covered),'unmodeledCards':len(eligible)-len(covered),'coveredDesirableMassShare':share,'value':value,'status':'available' if value is not None else 'unavailable','slotCount':len({x['slot_group'] for x in covered if x.get('slot_group')})}
  old_eligible={c['canonical_card_id'] for c in hit_cards if c['subject_type']=='pokemon' and c['subject_appeal_raw']>50}
  old_modeled=[modeled[cid] for cid in old_eligible if modeled[cid]['pull_probability'] is not None]
  old_total=sum(max(modeled[cid]['subject_appeal_raw']-50,0) for cid in old_eligible);old_covered=sum(max(x['subject_appeal_raw']-50,0) for x in old_modeled)
  old_share=old_covered/old_total if old_total else None;old_f=desirable_frequency(old_modeled) if old_modeled and old_share is not None and old_share>=COVERAGE_FLOOR else None
  multi=[x for x in hit_cards if len(group_keys(x))>1]
  result={'set_id':sid,'set_name':(setmeta.get(sid) or {}).get('name'),'set_key':(setmeta.get(sid) or {}).get('canonical_key'),'hitPolicyVersion':HIT_POLICY_VERSION,
   'c3bVersion':c3b['configuration']['version'],'c3bFingerprint':c3b['formulaFingerprint'],'groupContractVersion':GROUP_VERSION,'groupRepresentative':'max',
   'totalHitEligibleCards':len(hit_cards),'c3bScoredHitEligibleCards':sum(x['final_card_collector_appeal'] is not None for x in hit_cards),'distinctGroupCount':len(groups),
   'pokemonGroupCount':sum(g['type']=='pokemon' for g in groups),'trainerGroupCount':sum(g['type']=='trainer' for g in groups),'neutralFunctionalGroupCount':sum(g['type']=='neutral_functional' for g in groups),'excludedEnergyCount':energy[sid],
   'multiSubjectCardCount':len(multi),'rawMass':raw_mass(appeals),'saturationK':WINNER_K,'collectorRosterDesirability':roster_score(appeals,WINNER_K),
   'representativeCandidates':{m:{'rawMass':raw_mass([g['appeal'] for g in gs]),'score':roster_score([g['appeal'] for g in gs],WINNER_K)} for m,gs in candidates.items()},
   'kSensitivity':{str(k):roster_score(appeals,k) for k in ROSTER_K},'aggregationAlternatives':{'positiveMean':simple_scores['positive_mean'][sid],'top5Mean':simple_scores['top5_mean'][sid]},
   'frequency':fdata,'topCollectorGroups':[dict({k:g[k] for k in ('key','type','identity','appeal')},cardCount=len(g['cards'])) for g in sorted(groups,key=lambda x:x['appeal'],reverse=True)[:10]],
   'topPlayabilityMembershipEffects':[{'cardId':x['canonical_card_id'],'card':x['card_name'],'groupKeys':[f'{a}:{b}' for a,b in group_keys(x)],'lift':x['applied_lift'],'appeal':x['final_card_collector_appeal'],'hitEligible':x['hit_eligibility']} for x in sorted(hit_cards,key=lambda x:x['applied_lift'],reverse=True) if x['applied_lift']>0][:10],
   'oldUniversalSetDesirability':(old.get(sid) or {}).get('score'),'oldPokemonOnlyF':old_f,'oldPokemonOnlyFCoveredDemandShare':old_share}
  results.append(result)
 config={'version':VERSION,'sourceC3bFingerprint':c3b['formulaFingerprint'],'cohortVersion':'pokemon_collector_c3b_eligible_cohort_v1 + hit policy','groupVersion':GROUP_VERSION,'representative':'max','rosterFormula':'100*(1-exp(-sum(sqrt(max((groupAppeal-50)/50,0)))/6.0))','k':WINNER_K,'fEligibility':'card-level appeal > 50','fThreshold':50,'fUnion':'add mutually-exclusive slots; multiply miss probabilities across slots; globally deduplicate canonical card ids','fCoverageFloor':COVERAGE_FLOOR,'energy':False,'price':False,'artist':False,'treatment':False}
 fingerprint=hashlib.sha256(json.dumps(config,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 roster_fingerprint=hashlib.sha256(json.dumps({k:config[k] for k in ('version','sourceC3bFingerprint','cohortVersion','groupVersion','representative','rosterFormula','k','energy','price','artist','treatment')},sort_keys=True,separators=(',',':')).encode()).hexdigest()
 frequency_fingerprint=hashlib.sha256(json.dumps({k:config[k] for k in ('version','sourceC3bFingerprint','cohortVersion','groupVersion','fEligibility','fThreshold','fUnion','fCoverageFloor','energy','price','artist','treatment')},sort_keys=True,separators=(',',':')).encode()).hexdigest()
 diagnostics={'setCount':len(results),'groupTaxonomy':{t:sum(x[t+'GroupCount'] for x in results) for t in ('pokemon','trainer','neutralFunctional')},'multiSubjectCards':sum(x['multiSubjectCardCount'] for x in results),
  'representativeRankCorrelations':{'maxVsMean':spearman(rep_scores['max'],rep_scores['mean']),'maxVsTop2':spearman(rep_scores['max'],rep_scores['top2_mean'])},
  'aggregationRankCorrelations':{'massVsPositiveMean':spearman(k_scores[str(WINNER_K)],simple_scores['positive_mean']),'massVsTop5Mean':spearman(k_scores[str(WINNER_K)],simple_scores['top5_mean'])},
  'kRankCorrelations':{f'6.0vs{k}':spearman(k_scores[str(WINNER_K)],k_scores[str(k)]) for k in ROSTER_K},
  'rosterVsGroupCountSpearman':spearman(k_scores[str(WINNER_K)],{x['set_id']:x['distinctGroupCount'] for x in results}),
  'newVsOldUniversalSpearman':spearman(k_scores[str(WINNER_K)],{x['set_id']:x['oldUniversalSetDesirability'] for x in results if x['oldUniversalSetDesirability'] is not None}),
  'newVsOldPokemonFSpearman':spearman({x['set_id']:x['frequency']['card_gt50']['value'] for x in results if x['frequency']['card_gt50']['value'] is not None},{x['set_id']:x['oldPokemonOnlyF'] for x in results if x['oldPokemonOnlyF'] is not None}),
  'cardVsGroupFrequencyDifferences':{key:sum(1 for x in results if x['frequency'][f'card_{key}']['value'] != x['frequency'][f'group_{key}']['value']) for key in ('gt50','gt55','gt60')},
  'frequencyAvailability':{key:sum(x['frequency'][key]['status']=='available' for x in results) for key in results[0]['frequency']} if results else {},'oldAuthorityReadError':old_error}
 report={'decisions':{'collectorRoster':'COLLECTOR_ROSTER_READY','generalizedFrequency':'GENERALIZED_DESIRABLE_FREQUENCY_READY'},'configuration':config,'formulaFingerprint':fingerprint,'collectorRosterFormulaFingerprint':roster_fingerprint,'generalizedFrequencyFormulaFingerprint':frequency_fingerprint,'diagnostics':diagnostics,'sets':sorted(results,key=lambda x:(x['set_name'] or '',x['set_id']))}
 output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8');print(json.dumps({'formulaFingerprint':fingerprint,'diagnostics':diagnostics},indent=2));return 0
if __name__=='__main__':
 import argparse;p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'backend/artifacts/collector_c4_set_components_shadow_v1.json');raise SystemExit(main(p.parse_args().output))
