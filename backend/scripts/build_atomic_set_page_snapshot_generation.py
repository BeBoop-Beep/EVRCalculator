"""Stage and validate a complete set-page generation without activating it."""
from __future__ import annotations
import argparse,json,os,sys,time,uuid
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from backend.db.services.collector_appeal_current_service import PUBLIC_CONTRACT_KEY,build_public_collector_appeal_contract,load_set_collector_appeal_for_model
from backend.db.services.explore_rip_statistics_service import get_rip_statistics_targets_payload
from backend.scripts.pokemon_snapshot_builders import build_set_page_snapshot_row
from backend.scripts.pokemon_explore_rankings_publisher import publish_explore_rip_rankings_snapshot
from backend.db.services.rankings_publication_lifecycle import source_run_fingerprint
MODEL_RUN_ID="0efa3c8f-918d-49d7-ad5e-3ae37278058f"

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--write-stage',action='store_true'); ap.add_argument('--publish-coordinated',action='store_true'); ap.add_argument('--collector-model-run-id',default=MODEL_RUN_ID); args=ap.parse_args(); started=time.perf_counter()
 load_dotenv(ROOT/'backend'/'.env'); c=create_client(os.environ['SUPABASE_URL'],os.environ['SUPABASE_SERVICE_ROLE_KEY'])
 existing=[]; start=0
 while True:
  page=c.table('pokemon_set_page_snapshot_latest').select('set_id').order('set_id').range(start,start+24).execute().data or []; existing+=page
  if len(page)<25: break
  start+=25
 set_ids=[r['set_id'] for r in existing]
 sets=[]
 for i in range(0,len(set_ids),50):
  sets += c.table('sets').select('*').in_('id',set_ids[i:i+50]).execute().data or []
 by_id={str(r['id']):r for r in sets}
 if set(by_id)!=set(set_ids): raise RuntimeError('fresh generation set membership could not be resolved')
 rankings_payload=get_rip_statistics_targets_payload(limit=250,include_rankings_top_chase=False)
 if (rankings_payload.get('meta') or {}).get('desirabilityBundleStatus')!='ok':
  raise RuntimeError('canonical Rankings cohort failed to build completely')
 ranked=[r for r in rankings_payload.get('targets') or [] if (r.get('overallRipV12') or {}).get('rank') is not None]
 frozen_runs={str(r.get('set_id') or r.get('target_id')):str(r.get('calculation_run_id')) for r in ranked}
 if len(frozen_runs)!=22 or any(not value or value=='None' for value in frozen_runs.values()):
  raise RuntimeError('refusing non-22 or incomplete frozen calculation-run cohort')
 frozen_fingerprint=source_run_fingerprint(frozen_runs)
 collector=load_set_collector_appeal_for_model(args.collector_model_run_id,set_ids,client=c)
 staged=[]
 for set_id in set_ids:
  copied=build_set_page_snapshot_row(by_id[set_id],client=c,rankings_payload=rankings_payload); payload=dict(copied['payload_json']); payload.pop(PUBLIC_CONTRACT_KEY,None)
  contract=build_public_collector_appeal_contract(collector.get(set_id))
  if contract: payload[PUBLIC_CONTRACT_KEY]=contract
  copied['payload_json']=payload
  copied['created_at']=copied.get('created_at') or copied.get('source_updated_at')
  copied['updated_at']=copied.get('updated_at') or copied.get('source_updated_at')
  staged.append(copied)
 summary={'expectedSets':len(set_ids),'collectorRows':len(collector),'scored':sum(x.get('score_status')=='scored' for x in collector.values()),'unavailable':sum(x.get('score_status')=='unavailable' for x in collector.values()),'collectorModelRunId':args.collector_model_run_id,'frozenSourceRunFingerprint':frozen_fingerprint,'frozenSourceRuns':frozen_runs}
 if not args.write_stage: print(json.dumps({**summary,'mode':'dry-run'},indent=2)); return
 current=c.table('pokemon_set_page_snapshot_current_generation').select('generation_id').eq('scope','pokemon').single().execute().data
 gid=str(uuid.uuid4())
 c.table('pokemon_set_page_snapshot_generations').insert({'id':gid,'expected_set_ids':set_ids,'expected_set_count':len(set_ids),'collector_model_run_id':args.collector_model_run_id,'collector_contract_version':'public_collector_appeal_contract_v1','expected_collector_row_count':len(collector),'previous_generation_id':current['generation_id'],'diagnostics_json':{'builder':'build_atomic_set_page_snapshot_generation.py','sourceMode':'fresh_canonical_rebuild','frozenSourceRunFingerprint':frozen_fingerprint,'frozenSourceRuns':frozen_runs}}).execute()
 for i in range(0,len(staged),5):
  c.table('pokemon_set_page_snapshot_generation_rows').upsert([{'generation_id':gid,**r} for r in staged[i:i+5]],on_conflict='generation_id,set_id').execute()
 report=c.rpc('validate_pokemon_set_page_snapshot_generation',{'p_generation_id':gid}).execute().data
 publication=None
 if args.publish_coordinated:
  if not report.get('passed'): raise RuntimeError('refusing coordinated publication of invalid generation')
  publish_explore_rip_rankings_snapshot(c,commit=False,set_page_generation_id=gid,source_rankings_payload=rankings_payload)
  publication=publish_explore_rip_rankings_snapshot(c,commit=True,set_page_generation_id=gid,source_rankings_payload=rankings_payload)
 print(json.dumps({**summary,'generationId':gid,'validation':report,'rankingsPublication':publication and publication.get('publicationId'),'buildSeconds':round(time.perf_counter()-started,3)},indent=2))
if __name__=='__main__': main()
