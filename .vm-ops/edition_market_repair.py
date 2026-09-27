"""Explicit edition recovery under the shared VM lock; no automatic retries.

This does not enable the old shadow cron, bypass quality, or relabel current
prices. The deployed SQL function requires exact-date source/raw-V2 parity.
"""
from __future__ import annotations
import argparse,fcntl,hashlib,importlib.util,json,os,shlex,subprocess,sys,time
from datetime import date,datetime,timezone
from pathlib import Path

APP=Path('/home/ubuntu/repos/EVRCalculator')
STATE=Path('/home/ubuntu/state/db-safety')
LANE=STATE/'edition-market'

def emit(**data):print(json.dumps(data,default=str,sort_keys=True),flush=True)
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result

def body(args,guard):
    source=Path(args.source).resolve()
    if source.parent!=LANE/'sources':raise RuntimeError('unexpected_source_location')
    os.chdir(source);sys.path.insert(0,str(source))
    from dotenv import load_dotenv
    load_dotenv(APP/'backend/.env',override=False)
    if os.environ.get('SUPABASE_URL','').rstrip('/')!='https://zwxzxuuawalvwioadhmf.supabase.co':
        raise RuntimeError('unexpected_database_project')
    from backend.db.clients.supabase_client import create_service_role_client
    from backend.db.services.pokemon_edition_history import read_edition_history_batch,refresh_edition_history_for_markets
    from backend.db.services.market_publication_gate import enforce_market_publication_gate
    from backend.scripts import build_pokemon_explore_set_value_snapshot as builder
    client=create_service_role_client()
    day=date.fromisoformat(args.market_date).isoformat()
    roots=client.table('pokemon_edition_split_root_sets_v2').select('set_id,profile').order('set_id').execute().data or []
    if len(roots)!=10:raise RuntimeError('edition_root_membership_changed')
    if args.phase=='read-proof':
        rows=read_edition_history_batch(client,[r['set_id'] for r in roots[:4]],start_date='1999-01-01',end_date=day)
        summary={}
        for row in rows:
            if row.get('certified_on_date'):
                key=row['set_id']+':'+row['market_scope']
                summary[key]=max(summary.get(key,''),row['market_date'])
        emit(stage='paged_read_verified',row_count=len(rows),certified_latest=summary,mutations=False)
        return 0
    gate=enforce_market_publication_gate(client,commit=True,market_date=day,mode='required',
         entry_point='bounded edition Market recovery')
    emit(stage='market_quality',allowed=gate.decision.allowed,status=gate.decision.status,market_date=gate.decision.market_date)
    if not gate.proceed or not gate.decision.allowed:return gate.exit_code or 3
    if args.phase=='history':
        receipts=[]
        for root in roots:
            result=refresh_edition_history_for_markets(client,[{'id':root['set_id'],'market_scope':'first_edition'}],market_date=day)[0]
            receipts.append(result)
            guard.atomic_write(LANE/(day+'.history.json'),json.dumps({'market_date':day,'receipts':receipts},default=str)+'\n')
            emit(stage='history_root',**result)
            time.sleep(.5)
        emit(stage='history_day_complete',market_date=day,roots=len(receipts),scopes=sum(r['scope_count'] for r in receipts),certified_scopes=sum(r['certified_scope_count'] for r in receipts))
        return 0
    # The standard canonical builder retains its normal Market contract. Save a
    # rollback artifact before publishing; never log full payloads or secrets.
    old=client.table('pokemon_explore_set_value_snapshot_latest').select('*').eq('tcg','pokemon').eq('scope','market').limit(1).execute().data or []
    if len(old)!=1:raise RuntimeError('expected_single_Market_snapshot')
    if old[0]['market_date']>day:raise RuntimeError('refusing_snapshot_date_regression')
    backup=LANE/(day+'.snapshot-before.json')
    if not backup.exists():guard.atomic_write(backup,json.dumps(old[0],default=str)+'\n')
    os.environ['PUBLICATION_BUILD_SHA']=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    row=builder.build(client=client,market_date=day,commit=True)
    actual=client.table('pokemon_explore_set_value_snapshot_latest').select('market_date,payload_json,updated_at').eq('tcg','pokemon').eq('scope','market').single().execute().data
    if actual['market_date']!=day:raise RuntimeError('persisted_snapshot_date_mismatch')
    entries=actual['payload_json']['sets']
    scopes=[r for r in entries if r.get('marketScope') in ('first_edition','unlimited','shadowless')]
    if len(scopes)!=21:raise RuntimeError('persisted_edition_membership_mismatch')
    for r in scopes:
        if r.get('certificationStatus')=='CERTIFIED' and (r.get('setValueAsOf')!=day or r.get('valueStatus')!='current'):
            raise RuntimeError('persisted_edition_not_current:'+r['marketKey'])
    proof={'market_date':day,'updated_at':actual['updated_at'],'edition_markets':[
        {k:r.get(k) for k in ('name','marketKey','marketScope','setValueAsOf','historyEndDate','valueStatus','currentSetValue','certificationStatus')} for r in scopes],
        'publisher_sha':os.environ['PUBLICATION_BUILD_SHA'],'status':'verified_published'}
    guard.atomic_write(LANE/(day+'.publication.json'),json.dumps(proof,default=str)+'\n')
    emit(stage='publication_verified',**proof)
    return 0

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',required=True)
    parser.add_argument('--market-date',required=True,type=date.fromisoformat)
    parser.add_argument('--phase',required=True,choices=['read-proof','history','publish'])
    parser.add_argument('--body',action='store_true')
    args=parser.parse_args();args.market_date=args.market_date.isoformat()
    LANE.mkdir(parents=True,exist_ok=True,mode=0o700)
    guard=module('edition_guard',STATE/'db_workload_guard.py')
    try:
        if args.body:return body(args,guard)
        shared=module('edition_resources',STATE/'collection_recovery.py')
        shared.LANE=LANE
        config=guard.load(STATE/'price-projection/authorization.json')
        if config.get('enabled') is not True or not shared.expected_hold(config,STATE/'hold.json'):
            raise RuntimeError('incident_state_changed')
        with (STATE/'worker.lock').open('a') as lock:
            deadline=time.monotonic()+180
            while True:
                try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);break
                except BlockingIOError:
                    if time.monotonic()>deadline:raise RuntimeError('shared_worker_busy')
                    time.sleep(.5)
            pressure=shared.make_pressure(guard,config)
            command=shlex.join(['/usr/bin/timeout','--foreground','--signal=TERM','--kill-after=20s','900s',sys.executable,str(Path(__file__).resolve()),
                '--source',args.source,'--market-date',args.market_date,'--phase',args.phase,'--body'])
            started=datetime.now(timezone.utc).isoformat()
            rc=guard.run_command(command,state=LANE,pressure=pressure,interval=20)
            receipt={'phase':args.phase,'market_date':args.market_date,'exit_code':rc,'started_at':started,
                     'finished_at':datetime.now(timezone.utc).isoformat(),'global_hold_preserved':(STATE/'hold.json').exists()}
            guard.atomic_write(LANE/(args.market_date+'.'+args.phase+'.execution.json'),json.dumps(receipt)+'\n')
            emit(**receipt)
            return rc
    except Exception as exc:
        emit(status='edition_repair_failed',error_type=type(exc).__name__,error_code=getattr(exc,'code',None))
        # Server-returned errors contain no credentials; retain the diagnostic
        # privately on the VM for bounded follow-up inspection.
        guard.atomic_write(LANE/(args.market_date+'.'+args.phase+'.error.json'),json.dumps({'error_type':type(exc).__name__,'error':str(exc)[:3000]})+'\n')
        return 1

if __name__=='__main__':raise SystemExit(main())
