"""Stage and validate a complete set-page generation without activating it."""
from __future__ import annotations
import argparse,json,os,sys,time,uuid
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from backend.db.services.collector_appeal_current_service import PUBLIC_CONTRACT_KEY,build_public_collector_appeal_contract,build_public_collector_appeal_contract_from_v5,load_canonical_v5_collector_appeal,load_set_collector_appeal_for_model
from backend.desirability.collector_appeal import COLLECTOR_APPEAL_V5_VERSION
from backend.db.services.explore_rip_statistics_service import get_rip_statistics_targets_payload
from backend.scripts.pokemon_snapshot_builders import build_set_page_snapshot_row
from backend.scripts.pokemon_explore_rankings_publisher import publish_explore_rip_rankings_snapshot
from backend.db.services.rankings_publication_lifecycle import source_run_fingerprint
from backend.scripts.snapshot_query_retry import run_snapshot_operation_with_retry
MODEL_RUN_ID="0efa3c8f-918d-49d7-ad5e-3ae37278058f"

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--write-stage',action='store_true'); ap.add_argument('--publish-coordinated',action='store_true'); ap.add_argument('--collector-authority',choices=('canonical-v5','model-run'),default='canonical-v5'); ap.add_argument('--collector-model-run-id'); args=ap.parse_args(); started=time.perf_counter()
 load_dotenv(ROOT/'backend'/'.env'); c=create_client(os.environ['SUPABASE_URL'],os.environ['SUPABASE_SERVICE_ROLE_KEY'])
 existing=[]; start=0
 while True:
  page=c.table('pokemon_set_page_snapshot_latest').select('*').order('set_id').range(start,start+24).execute().data or []; existing+=page
  if len(page)<25: break
  start+=25
 existing_full_rows=existing
 # FULL_GENERATION_EXPECTED_SET_IDS: the semantic membership authority for a
 # coordinated global generation is the CURRENT live public set-page universe
 # (pokemon_set_page_snapshot_latest), read fresh at build time. This is
 # intentionally NOT a hardcoded count (e.g. 210) because that count drifts as
 # sets are catalogued. Until an explicit, authorized removal contract exists,
 # every currently-public set is preserved by default: a coordinated
 # generation may only ADD set pages, mirroring the production
 # activate_pokemon_set_page_snapshot_generation live-membership guard.
 full_set_ids=[r['set_id'] for r in existing]
 sets=[]
 for i in range(0,len(full_set_ids),50):
  sets += c.table('sets').select('*').in_('id',full_set_ids[i:i+50]).execute().data or []
 by_id={str(r['id']):r for r in sets}
 if set(by_id)!=set(full_set_ids): raise RuntimeError('fresh generation set membership could not be resolved')
 rankings_payload=get_rip_statistics_targets_payload(limit=250,include_rankings_top_chase=False)
 if (rankings_payload.get('meta') or {}).get('desirabilityBundleStatus')!='ok':
  raise RuntimeError('canonical Rankings cohort failed to build completely')
 ranked=[r for r in rankings_payload.get('targets') or [] if (r.get('overallRipV12') or {}).get('rank') is not None]
 frozen_runs={str(r.get('set_id') or r.get('target_id')):str(r.get('calculation_run_id')) for r in ranked}
 if len(frozen_runs)!=22 or any(not value or value=='None' for value in frozen_runs.values()):
  raise RuntimeError('refusing non-22 or incomplete frozen calculation-run cohort')
 fresh_set_ids=sorted(frozen_runs)
 fresh_by_id={set_id:by_id[set_id] for set_id in fresh_set_ids if set_id in by_id}
 if len(fresh_by_id)!=22: raise RuntimeError('frozen 22-set cohort identity could not be resolved')
 set_ids=sorted(full_set_ids)
 carry_forward_set_ids=sorted(sid for sid in full_set_ids if sid not in frozen_runs)
 if len(fresh_set_ids)+len(carry_forward_set_ids)!=len(set_ids):
  raise RuntimeError('full-generation membership accounting failed to reconcile fresh + carry-forward sets')
 frozen_fingerprint=source_run_fingerprint(frozen_runs)
 # Collector authority is only required/loaded for the 22 fresh-rebuild sets.
 # Carry-forward sets keep whatever Collector data is already embedded in
 # their existing (unmodified) payload_json -- we never fabricate Collector
 # scores for sets that legitimately lack simulation support.
 if args.collector_authority=='model-run':
  if not args.collector_model_run_id: raise RuntimeError('--collector-model-run-id is required for model-run authority')
  collector=load_set_collector_appeal_for_model(args.collector_model_run_id,fresh_set_ids,client=c); collector_version=next(iter(collector.values()),{}).get('model_version'); collector_fingerprint=args.collector_model_run_id
 else:
  v5=load_canonical_v5_collector_appeal(fresh_set_ids); collector=v5['payloads']; collector_version=COLLECTOR_APPEAL_V5_VERSION; collector_fingerprint=(v5['identity'] or {}).get('formulaFingerprint')
 scored=sum(((x.get('score_status')=='scored') if args.collector_authority=='model-run' else ((x.get('collectorAppeal') or {}).get('score') is not None)) for x in collector.values())
 if scored!=len(fresh_set_ids): raise RuntimeError('canonical Collector authority is incomplete for frozen cohort')
 summary={'fullGenerationExpectedSetCount':len(set_ids),'freshRebuiltSetCount':len(fresh_set_ids),'carriedForwardSetCount':len(carry_forward_set_ids),'collectorRows':len(collector),'scored':scored,'unavailable':len(collector)-scored,'collectorAuthority':args.collector_authority,'collectorVersion':collector_version,'collectorAuthorityFingerprint':collector_fingerprint,'collectorModelRunId':args.collector_model_run_id,'frozenSourceRunFingerprint':frozen_fingerprint,'frozenSourceRuns':frozen_runs}
 latest_by_id={str(r['set_id']):r for r in existing_full_rows}
 def build_fresh_row(fresh_client,set_id):
  copied=build_set_page_snapshot_row(by_id[set_id],client=fresh_client,rankings_payload=rankings_payload); payload=dict(copied['payload_json']); payload.pop(PUBLIC_CONTRACT_KEY,None)
  contract=build_public_collector_appeal_contract(collector.get(set_id)) if args.collector_authority=='model-run' else build_public_collector_appeal_contract_from_v5(collector.get(set_id))
  if not contract: raise RuntimeError('missing canonical Collector authority for set '+set_id)
  ca=contract.get('collectorAppeal') or {}
  if args.collector_authority=='canonical-v5' and (ca.get('version')!=COLLECTOR_APPEAL_V5_VERSION or ca.get('modelRunId') is not None): raise RuntimeError('canonical V5 authority validation failed')
  payload[PUBLIC_CONTRACT_KEY]=contract; copied['payload_json']=payload
  copied['created_at']=copied.get('created_at') or copied.get('source_updated_at'); copied['updated_at']=copied.get('updated_at') or copied.get('source_updated_at')
  return copied
 def build_carry_forward_row(set_id):
  # Safe carry-forward: copy the set's ACTUAL existing public page content
  # verbatim. Never rewrite source_updated_at/created_at/updated_at to fake
  # freshness -- a carried-forward row must remain honestly historical.
  source_row=latest_by_id.get(set_id)
  if not source_row: raise RuntimeError('missing existing snapshot row to carry forward for set '+set_id)
  return dict(source_row)
 def build_row(fresh_client,set_id):
  return build_fresh_row(fresh_client,set_id) if set_id in frozen_runs else build_carry_forward_row(set_id)
 if not args.write_stage:
  for set_id in set_ids:
   run_snapshot_operation_with_retry(lambda fresh_client,set_id=set_id: build_row(fresh_client,set_id),operation_name='dry-run atomic set-page generation row',set_id=set_id)
  print(json.dumps({**summary,'mode':'dry-run'},indent=2)); return
 current=c.table('pokemon_set_page_snapshot_current_generation').select('generation_id').eq('scope','pokemon').single().execute().data
 identity={'builder':'build_atomic_set_page_snapshot_generation.py','sourceMode':'full_generation_fresh_plus_carry_forward','collectorAuthority':args.collector_authority,'collectorVersion':collector_version,'collectorAuthorityFingerprint':collector_fingerprint,'frozenSourceRunFingerprint':frozen_fingerprint,'frozenSourceRuns':frozen_runs,'rebuiltFreshSetIds':fresh_set_ids,'carriedForwardSetIds':carry_forward_set_ids,'carryForwardSourceGenerationId':current['generation_id']}
 building=c.table('pokemon_set_page_snapshot_generations').select('*').eq('status','building').limit(1).execute().data or []
 resumable=bool(building and building[0].get('expected_set_ids')==set_ids and str(building[0].get('collector_model_run_id'))==args.collector_model_run_id and (building[0].get('diagnostics_json') or {})==identity)
 if building and not resumable:
  c.table('pokemon_set_page_snapshot_generations').update({'status':'failed','diagnostics_json':{**(building[0].get('diagnostics_json') or {}),'failure':'frozen authority changed; generation is not resumable'}}).eq('id',building[0]['id']).execute()
 gid=str(building[0]['id']) if resumable else str(uuid.uuid4())
 if not resumable:
  c.table('pokemon_set_page_snapshot_generations').insert({'id':gid,'expected_set_ids':set_ids,'expected_set_count':len(set_ids),'collector_model_run_id':args.collector_model_run_id,'collector_contract_version':'public_collector_appeal_contract_v1','expected_collector_row_count':len(collector),'previous_generation_id':current['generation_id'],'diagnostics_json':identity}).execute()
 completed={str(r['set_id']) for r in (c.table('pokemon_set_page_snapshot_generation_rows').select('set_id').eq('generation_id',gid).execute().data or [])}
 try:
  for set_id in set_ids:
   if set_id in completed: continue
   def build_and_persist(fresh_client,set_id=set_id):
    copied=build_row(fresh_client,set_id)
    fresh_client.table('pokemon_set_page_snapshot_generation_rows').upsert({'generation_id':gid,**copied},on_conflict='generation_id,set_id').execute()
   run_snapshot_operation_with_retry(build_and_persist,operation_name='build atomic set-page generation row',set_id=set_id)
 except Exception as exc:
  c.table('pokemon_set_page_snapshot_generations').update({'status':'failed','diagnostics_json':{**identity,'failedSetId':set_id,'errorType':type(exc).__name__,'error':str(exc)[:500]}}).eq('id',gid).execute()
  raise
 report=c.rpc('validate_pokemon_set_page_snapshot_generation',{'p_generation_id':gid}).execute().data
 publication=None
 if args.publish_coordinated:
  if not report.get('passed'): raise RuntimeError('refusing coordinated publication of invalid generation')
  publish_explore_rip_rankings_snapshot(c,commit=False,set_page_generation_id=gid,source_rankings_payload=rankings_payload)
  publication=publish_explore_rip_rankings_snapshot(c,commit=True,set_page_generation_id=gid,source_rankings_payload=rankings_payload)
 print(json.dumps({**summary,'generationId':gid,'validation':report,'rankingsPublication':publication and publication.get('publicationId'),'buildSeconds':round(time.perf_counter()-started,3)},indent=2))
if __name__=='__main__': main()
