"""Resume only the canonical staged price projection, never public builders.

Collection and projection have independent failure state and one shared host
admission lock. All existing source-cohort and projection verdicts are retained.
"""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ROOT=Path('/home/ubuntu/repos/EVRCalculator')
STATE=Path('/home/ubuntu/state/db-safety')
LANE=STATE/'price-projection'
SCRIPT=STATE/'price_projection_recovery.py'
PYTHON=ROOT/'.venv/bin/python'
MARKER='# INDEX_BOUNDED_PRICE_PROJECTION_V1'
VERSION='2026-09-26.price-projection-v1'


def emit(**value):
    print(json.dumps(value,sort_keys=True,default=str),flush=True)


def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def acquire(lock,wait_seconds=0):
    deadline=time.monotonic()+max(0,min(float(wait_seconds),180))
    while True:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            if time.monotonic()>=deadline:return False
            time.sleep(.5)


def prepare_cron(text):
    token=str(SCRIPT)
    if token in text or MARKER in text:
        if text.count(token)!=1 or MARKER not in text:
            raise RuntimeError('conflicting_projection_schedule')
        return text
    command='sleep 25; '+str(PYTHON)+' '+token+' --tick >> '+str(LANE/'cron.log')+' 2>&1'
    return text.rstrip()+'\n\n'+MARKER+'\n* * * * * '+command+'\n'


def public_ready(batch,after):
    return bool(batch and batch.get('status')=='complete' and batch.get('promoted_at')
                and after.get('ready') is True
                and int(after.get('expected_set_count') or 0)==int(batch.get('expected_set_count') or -1)
                and int(after.get('complete_set_count') or 0)==int(batch.get('expected_set_count') or -1))


def result_code(report):
    after=report.get('after') or {}
    process=report.get('process_result') or {}
    if after.get('error') or after.get('reason_code')=='price_projection_authority_unavailable':return 1
    if int(process.get('failed') or 0)>0:return 1
    if int(after.get('terminal_failed_set_count') or 0)>0 and int(process.get('processed') or 0)==0:return 1
    return 0


def pressure_callback(guard,shared,config):
    from dotenv import dotenv_values
    import httpx
    key=dotenv_values(ROOT/'backend/.env',interpolate=False).get('SUPABASE_SERVICE_ROLE_KEY')
    baseline={}
    def check():
        metrics={}
        try:
            if not shared.expected_hold(config,STATE/'hold.json'):
                reason='global_hold_changed_operator_review_required'
            elif not key:
                reason='metrics_credential_missing'
            else:
                with httpx.Client(timeout=8) as client:
                    response=client.get('https://zwxzxuuawalvwioadhmf.supabase.co/customer/v1/privileged/metrics',auth=('service_role',key))
                    response.raise_for_status()
                metrics=shared.parse_metrics(response.text)
                reason=shared.physical_pressure(metrics)
                if reason is None and baseline:reason=shared.transition_reason(baseline,metrics)
                if not baseline:baseline.update(metrics)
        except Exception as exc:
            reason='resource_probe_'+type(exc).__name__
        result={'checked_at':datetime.now(timezone.utc).isoformat(),'metrics':metrics,'stop_reason':reason}
        guard.atomic_write(LANE/'latest_resources.json',json.dumps(result)+'\n')
        if reason:guard.atomic_write(LANE/'last_stop_evidence.json',json.dumps(result)+'\n')
        return reason
    return check


def tick(guard,shared,wait_seconds=0):
    config=guard.load(LANE/'authorization.json')
    if config.get('enabled') is not True:return 75
    with (STATE/'worker.lock').open('a') as lock:
        if not acquire(lock,wait_seconds):return 75
        now=datetime.now(ZoneInfo('America/Phoenix'))
        if (now.hour,now.minute)<(1,5):return 0
        command=shlex.join(['/usr/bin/timeout','--foreground','--signal=TERM','--kill-after=20s','240s',
                           str(PYTHON),str(SCRIPT),'--body','--market-date',now.date().isoformat()])
        return guard.run_command(command,state=LANE,pressure=pressure_callback(guard,shared,config),interval=20)


def body(day,guard):
    if day!=datetime.now(ZoneInfo('America/Phoenix')).date().isoformat():
        raise RuntimeError('refusing_wrong_execution_date')
    os.chdir(ROOT);sys.path.insert(0,str(ROOT))
    from dotenv import load_dotenv
    load_dotenv(ROOT/'backend/.env',override=False)
    from backend.db.clients.supabase_client import create_service_role_client
    from backend.db.services.price_storage_v2_projection_gate import evaluate_price_projection_gate,advance_price_projection_once
    client=create_service_role_client()
    before=evaluate_price_projection_gate(client,day)
    if before.error:raise RuntimeError('projection_authority_unreadable')
    if not before.expected_set_count:
        emit(stage='projection_waiting_for_completed_scrapes',market_date=day)
        return 0
    report=({'before':before.to_dict(),'after':before.to_dict(),'process_result':None}
            if before.ready else advance_price_projection_once(client,day,process_limit=1))
    rows=client.table('pokemon_scrape_batches').select('id,status,promoted_at,expected_set_count').eq('market_date',day).limit(1).execute().data or []
    after=report.get('after') or {}
    summary={'market_date':day,'checked_at':datetime.now(timezone.utc).isoformat(),
             'projection':report,'batch_id':rows[0]['id'] if rows else None,
             'public_source_cohort_ready':public_ready(rows[0] if rows else None,after)}
    guard.atomic_write(LANE/(day+'.progress.json'),json.dumps(summary,default=str)+'\n')
    emit(**summary)
    return result_code(report)


def install(guard,shared):
    LANE.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (STATE/'worker.lock').open('a') as lock:
        if not acquire(lock,180):raise RuntimeError('active_worker_admission_timeout')
        hold=STATE/'hold.json'
        if not hold.is_file():raise RuntimeError('expected_incident_hold_missing')
        current=subprocess.check_output(['crontab','-l'],text=True,timeout=5)
        if sum(l.startswith('# CODE_RED_DISABLED ') for l in current.splitlines())!=14:
            raise RuntimeError('legacy_schedule_state_changed')
        if sum('collection_recovery.py --tick' in l and not l.lstrip().startswith('#') for l in current.splitlines())!=1:
            raise RuntimeError('independent_collection_schedule_missing')
        config={'version':VERSION,'enabled':True,'max_sets_per_tick':1,
                'approved_incident_hold_sha256':hashlib.sha256(hold.read_bytes()).hexdigest(),
                'authorized_at':datetime.now(timezone.utc).isoformat()}
        reason=pressure_callback(guard,shared,config)()
        if reason:raise RuntimeError(reason)
        updated=prepare_cron(current)
        backup=Path('/home/ubuntu/ops-backups/crontab.code-red-db-load-shed.backup')
        stamp=str(time.time_ns())
        guard.atomic_write(LANE/('crontab.before.'+stamp),current)
        previous=backup.read_text() if backup.exists() else None
        if previous is not None:guard.atomic_write(LANE/('restore-backup.before.'+stamp),previous)
        guard.atomic_write(SCRIPT,Path(__file__).read_text())
        guard.atomic_write(LANE/'authorization.json',json.dumps(config)+'\n')
        try:
            subprocess.run(['crontab','-'],input=updated,text=True,check=True,timeout=5)
            if subprocess.check_output(['crontab','-l'],text=True,timeout=5)!=updated:
                raise RuntimeError('cron_install_verification_failed')
            guard.atomic_write(backup,updated)
        except Exception:
            guard.atomic_write(LANE/'authorization.json',json.dumps({**config,'enabled':False})+'\n')
            subprocess.run(['crontab','-'],input=current,text=True,check=True,timeout=5)
            if previous is not None:guard.atomic_write(backup,previous)
            raise
        emit(status='projection_schedule_installed',max_sets_per_tick=1,global_hold_preserved=True,collection_schedule_unchanged=True)
    return 0


def main():
    p=argparse.ArgumentParser();m=p.add_mutually_exclusive_group(required=True)
    m.add_argument('--install',action='store_true');m.add_argument('--tick',action='store_true');m.add_argument('--body',action='store_true')
    p.add_argument('--market-date');p.add_argument('--wait-seconds',type=float,default=0)
    args=p.parse_args()
    guard=load_module('projection_guard',STATE/'db_workload_guard.py')
    shared=load_module('collection_resource_policy',STATE/'collection_recovery.py')
    try:
        if args.install:return install(guard,shared)
        if args.tick:return tick(guard,shared,args.wait_seconds)
        return body(args.market_date,guard)
    except Exception as exc:
        emit(status='projection_failed',error_type=type(exc).__name__)
        return 1

if __name__=='__main__':raise SystemExit(main())
