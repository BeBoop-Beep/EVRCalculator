"""Independent, serialized Market publication; never re-enables unrelated jobs.

The price cohort must be complete and current before any builders run. Exact
counts protect this boundary from the same API pagination defect as histories.
"""
from __future__ import annotations
import argparse,fcntl,hashlib,importlib.util,json,os,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
from zoneinfo import ZoneInfo

APP=Path('/home/ubuntu/repos/EVRCalculator')
STATE=Path('/home/ubuntu/state/db-safety')
LANE=STATE/'market-publication'
SCRIPT=STATE/'market_publication_recovery.py'
MARKER='# INDEX_SOURCE_GATED_MARKET_PUBLICATION_V1'

def emit(**data):print(json.dumps(data,default=str,sort_keys=True),flush=True)
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result

def source_ready(batch,jobs,projections):
    if not batch or batch.get('status')!='complete' or not batch.get('promoted_at'):return False
    expected=int(batch.get('expected_set_count') or 0)
    if expected<=0 or int(batch.get('succeeded_set_count') or 0)!=expected:return False
    if int(batch.get('failed_set_count') or 0) or int(batch.get('missing_set_count') or 0):return False
    latest={}
    for job in jobs:
        if job.get('status')!='completed' or not job.get('completed_at') or not job.get('set_id'):return False
        key=job['set_id']
        completed=datetime.fromisoformat(job['completed_at'].replace('Z','+00:00'))
        if key not in latest or completed>latest[key]:latest[key]=completed
    if len(latest)!=expected:return False
    by_id={row['set_id']:row for row in projections}
    if len(by_id)!=len(projections):return False
    for root,completed in latest.items():
        row=by_id.get(root,{})
        if row.get('status')!='complete' or not row.get('source_completed_at') or not row.get('completed_at'):return False
        if datetime.fromisoformat(row['source_completed_at'].replace('Z','+00:00'))<completed:return False
        if datetime.fromisoformat(row['completed_at'].replace('Z','+00:00'))<completed:return False
    return True

def read_complete(client,table,fields,day):
    rows=[];expected=None
    for _ in range(100):
        query=client.table(table).select(fields,count='exact').eq('market_date',day)
        if table=='scrape_jobs':query=query.eq('status','completed')
        response=query.order('id').range(len(rows),len(rows)+255).execute()
        count=getattr(response,'count',None);page=response.data
        if type(count) is not int or count<0 or not isinstance(page,list):raise RuntimeError('missing_exact_source_count')
        if expected is None:expected=count
        if count!=expected:raise RuntimeError('source_membership_changed_during_read')
        if not page and len(rows)<expected:raise RuntimeError('source_response_truncated')
        rows.extend(page)
        if len({r['id'] for r in rows})!=len(rows):raise RuntimeError('duplicate_source_page')
        if len(rows)>expected:raise RuntimeError('source_count_exceeded')
        if len(rows)==expected:return rows
    raise RuntimeError('source_read_budget_exceeded')

def validate_snapshot(payload,day):
    scopes=[r for r in payload.get('sets',[]) if r.get('marketScope') in ('first_edition','unlimited','shadowless')]
    if not scopes:raise RuntimeError('edition_markets_missing')
    keys=[r['marketKey'] for r in scopes]
    if len(keys)!=len(set(keys)):raise RuntimeError('duplicate_edition_market')
    for row in scopes:
        if row.get('certificationStatus')=='CERTIFIED':
            if row.get('setValueAsOf')!=day or row.get('valueStatus')!='current':raise RuntimeError('certified_edition_stale')
        elif row.get('valueStatus')!='unavailable' or row.get('currentSetValue') is not None:
            raise RuntimeError('uncertified_edition_exposed')
    return scopes

def prepare_cron(text):
    token=str(SCRIPT)
    if token in text or MARKER in text:
        if text.count(token)!=1 or MARKER not in text:raise RuntimeError('conflicting_market_schedule')
        return text
    return text.rstrip()+'\n\n'+MARKER+'\n3-59/5 * * * * '+str(APP/'.venv/bin/python')+' '+token+' --tick >> '+str(LANE/'cron.log')+' 2>&1\n'

def body(day,guard):
    os.chdir(APP);sys.path.insert(0,str(APP))
    from dotenv import load_dotenv
    load_dotenv(APP/'backend/.env',override=False)
    if os.environ.get('SUPABASE_URL','').rstrip('/')!='https://zwxzxuuawalvwioadhmf.supabase.co':raise RuntimeError('wrong_project')
    from backend.db.clients.supabase_client import create_service_role_client
    client=create_service_role_client()
    batches=client.table('pokemon_scrape_batches').select('id,status,promoted_at,expected_set_count,succeeded_set_count,failed_set_count,missing_set_count').eq('market_date',day).limit(2).execute().data or []
    if len(batches)!=1 or batches[0].get('status')!='complete':
        emit(stage='waiting_for_complete_scrape',market_date=day);return 3
    jobs=read_complete(client,'scrape_jobs','id,set_id,status,completed_at',day)
    projections=read_complete(client,'price_storage_v2_shadow_queue','id,set_id,status,source_completed_at,completed_at',day)
    if not source_ready(batches[0],jobs,projections):
        emit(stage='waiting_for_price_projection',market_date=day,source_sets=len({r['set_id'] for r in jobs}),projected_sets=sum(r['status']=='complete' for r in projections));return 3
    fingerprint=hashlib.sha256(json.dumps({'jobs':jobs,'projection':projections},sort_keys=True).encode()).hexdigest()
    code=hashlib.sha256((APP/'backend/db/services/pokemon_edition_history.py').read_bytes()+(APP/'backend/scripts/build_pokemon_explore_set_value_snapshot.py').read_bytes()).hexdigest()
    previous=guard.load(LANE/(day+'.complete.json'))
    if previous.get('source_fingerprint')==fingerprint and previous.get('code_fingerprint')==code:
        emit(stage='already_verified_current',market_date=day);return 0
    def checkpoint(stage,**extra):
        value={'market_date':day,'stage':stage,'checked_at':datetime.now(timezone.utc).isoformat(),**extra}
        guard.atomic_write(LANE/(day+'.progress.json'),json.dumps(value,default=str)+'\n');emit(**value)
    from backend.scripts.repair_missing_market_set_value_history import repair_missing_market_set_values
    checkpoint('repairing_missing_market_roots')
    repair=repair_missing_market_set_values(client,market_date=day,commit=True,max_passes=1,sleep_seconds=0)
    if not repair.get('ok'):raise RuntimeError('market_root_materialization_incomplete')
    checkpoint('market_root_coverage',missing_before=repair['missing_before_count'],missing_after=repair['missing_after_count'])
    # Use the canonical index CLI, including rollout preparation and Market
    # quality checks; never insert an ad-hoc READY row or disable a gate.
    checkpoint('publishing_canonical_market_index')
    env=os.environ.copy();env['MARKET_PUBLICATION_GATE_MODE']='required'
    subprocess.run([sys.executable,'backend/scripts/build_pokemon_market_index_history.py','--market-date',day,'--commit'],env=env,check=True)
    from backend.db.services.market_publication_gate import enforce_market_publication_gate
    gate=enforce_market_publication_gate(client,commit=True,market_date=day,mode='required',entry_point='independent Market publication')
    if not gate.proceed or not gate.decision.allowed:return gate.exit_code or 3
    checkpoint('publishing_market_and_edition_histories')
    from backend.scripts.build_pokemon_explore_set_value_snapshot import build
    row=build(client=client,market_date=day,commit=True)
    actual=client.table('pokemon_explore_set_value_snapshot_latest').select('market_date,updated_at,payload_json').eq('tcg','pokemon').eq('scope','market').single().execute().data
    if actual['market_date']!=day:raise RuntimeError('market_date_readback_mismatch')
    scopes=validate_snapshot(actual['payload_json'],day)
    checkpoint('verified_published',source_fingerprint=fingerprint,code_fingerprint=code,
        updated_at=actual['updated_at'],edition_markets=len(scopes),certified_current=sum(r.get('valueStatus')=='current' for r in scopes),
        unavailable=sum(r.get('valueStatus')=='unavailable' for r in scopes))
    guard.atomic_write(LANE/(day+'.complete.json'),json.dumps({'status':'complete','market_date':day,'source_fingerprint':fingerprint,'code_fingerprint':code,'verified_at':datetime.now(timezone.utc).isoformat()})+'\n')
    return 0

def tick(guard):
    config=guard.load(LANE/'authorization.json')
    if config.get('enabled') is not True:return 75
    with (STATE/'worker.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return 75
        policy=module('market_resource_policy',STATE/'collection_recovery.py');policy.LANE=LANE
        if not policy.expected_hold(config,STATE/'hold.json'):return 75
        day=datetime.now(ZoneInfo('America/Phoenix')).date().isoformat()
        import shlex
        command=shlex.join(['/usr/bin/timeout','--foreground','--signal=TERM','--kill-after=20s','900s',sys.executable,str(SCRIPT),'--body','--market-date',day])
        return guard.run_command(command,state=LANE,pressure=policy.make_pressure(guard,config),interval=20)

def main():
    p=argparse.ArgumentParser();m=p.add_mutually_exclusive_group(required=True)
    m.add_argument('--tick',action='store_true');m.add_argument('--body',action='store_true');p.add_argument('--market-date')
    args=p.parse_args();LANE.mkdir(parents=True,exist_ok=True,mode=0o700)
    guard=module('market_guard',STATE/'db_workload_guard.py')
    try:
        return tick(guard) if args.tick else body(args.market_date,guard)
    except Exception as exc:
        value={'status':'failed','error_type':type(exc).__name__,'message':str(exc)[:2000],'time':datetime.now(timezone.utc).isoformat()}
        guard.atomic_write(LANE/'last_error.json',json.dumps(value)+'\n')
        emit(status='market_publication_failed',error_type=type(exc).__name__)
        return 1

if __name__=='__main__':raise SystemExit(main())
