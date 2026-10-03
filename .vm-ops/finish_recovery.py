"""Finish the explicitly approved upgrade recovery without overlapping phases.

Waits only on local receipts. Stops on a failed phase; never retries it. Restores
schedules only after simulations, publication and Explorer all prove completion.
"""
from __future__ import annotations
import argparse,fcntl,importlib.util,json,os,re,subprocess,sys,time
from datetime import date,datetime,timezone
from pathlib import Path
STATE=Path('/home/ubuntu/state/db-safety')
ROOT=Path('/home/ubuntu/repos/EVRCalculator')
PY=ROOT/'.venv/bin/python'

def import_path(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def prepare_cron(current,guard):
    prefix='# CODE_RED_DISABLED '
    active=[];count=0;has_prewarm=False
    import base64
    for original in current.splitlines():
        line=original[len(prefix):] if original.startswith(prefix) else original
        if str(STATE/'db_workload_guard.py') in line and '--run-encoded ' in line:
            command=base64.b64decode(line.split('--run-encoded ',1)[1].split()[0],validate=True).decode()
            has_prewarm |= 'run_market_explorer_maintained_cache_prewarm' in command
            count+=1
            active.append(line)
        elif str(ROOT) in line and 'VM heartbeat' not in line and line.strip() and not line.lstrip().startswith('#'):
            raise ValueError('unwrapped_application_schedule_refused')
        else:active.append(original)
    if count!=14:raise ValueError('unexpected_current_guarded_schedule_count')
    if not has_prewarm:
        command='cd '+str(ROOT)+' && '+str(PY)+' -m backend.scripts.run_market_explorer_maintained_cache_prewarm --commit --max-caches 1 >> '+str(ROOT/'backend/logs/market_explorer_maintained_cache_prewarm.log')+' 2>&1'
        added,n=guard.guarded_crontab('3-59/5 7-23 * * * '+command+'\n')
        if n!=1:raise ValueError('prewarm_schedule_guard_failed')
        active.extend(['# One-cache maintenance under shared resource admission; initial catch-up verified.',added.rstrip()])
    return '\n'.join(active)+'\n',15 if not has_prewarm else count

def phase_receipt(day,phase):
    path=STATE/'recovery'/day/(phase+'.json')
    return json.loads(path.read_text()) if path.exists() else None

def wait_phase(day,phase,controller,limit=7200):
    start=time.monotonic()
    while time.monotonic()-start<limit:
        r=phase_receipt(day,phase)
        if not r:raise RuntimeError('missing_phase_receipt:'+phase)
        if r.get('status')=='completed' and r.get('exit_code')==0:return r
        if r.get('status')=='blocked':raise RuntimeError('phase_failed_no_automatic_retry:'+phase)
        if not controller.running(r.get('pid')):raise RuntimeError('phase_process_not_alive:'+phase)
        time.sleep(10)
    raise RuntimeError('phase_wait_exceeded_budget:'+phase)

def services_healthy():
    import httpx
    from dotenv import dotenv_values
    config=dotenv_values(ROOT/'backend/.env',interpolate=False)
    key=config.get('SUPABASE_SERVICE_ROLE_KEY')
    if not key:raise RuntimeError('health_credential_missing')
    result=[]
    with httpx.Client(timeout=8) as client:
        for path in ('/rest/v1/sets?select=id&limit=1','/auth/v1/health','/storage/v1/bucket'):
            t=time.monotonic()
            response=client.get('https://zwxzxuuawalvwioadhmf.supabase.co'+path,headers={'apikey':key,'Authorization':'Bearer '+key})
            if response.status_code!=200:raise RuntimeError('service_probe_failed')
            result.append({'path':path,'status':response.status_code,'ms':round((time.monotonic()-t)*1000)})
    return result

def restore(day,guard):
    # Recheck authority receipts immediately before removing the recovery hold.
    for phase in ('simulations','publication','explorer'):
        r=phase_receipt(day,phase)
        if not r or r.get('status')!='completed' or r.get('exit_code')!=0:raise RuntimeError('recovery_incomplete:'+phase)
    for _ in range(2):
        reason=guard.live_pressure()
        if reason:raise RuntimeError('resource_preflight:'+reason)
        time.sleep(10)
    service_proof=services_healthy()
    with (STATE/'worker.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        hold=STATE/'hold.json'
        if not hold.is_file():raise RuntimeError('recovery_hold_missing')
        current=subprocess.check_output(['crontab','-l'],text=True)
        active,count=prepare_cron(current,guard)
        stamp=str(time.time_ns())
        guard.atomic_write(STATE/('crontab.before-reactivation.'+stamp),current)
        try:
            subprocess.run(['crontab','-'],input=active,text=True,check=True,timeout=5)
            if subprocess.check_output(['crontab','-l'],text=True)!=active:raise RuntimeError('cron_install_verification_failed')
            guard.atomic_write(Path('/home/ubuntu/ops-backups/crontab.code-red-db-load-shed.backup'),active)
            os.replace(hold,STATE/('hold.released.'+stamp+'.json'))
            result={'status':'reactivated','market_date':day,'guarded_schedules':count,'global_hold':False,'services':service_proof,'released_at':datetime.now(timezone.utc).isoformat(),'experimental_database_shadow_cron':'left_disabled'}
            guard.atomic_write(STATE/'reactivation.json',json.dumps(result)+'\n')
            print(json.dumps(result),flush=True)
        except Exception:
            guard.hold('reactivation_failed_closed')
            subprocess.run(['crontab','-'],input=current,text=True,timeout=5,check=True)
            raise
    return result

def execute(day,controller_path):
    guard=import_path('guard',STATE/'db_workload_guard.py')
    controller=import_path('controller',controller_path)
    state_path=STATE/'recovery'/day/'sequence.json'
    def state(**value):
        value.update(market_date=day,pid=os.getpid(),updated_at=datetime.now(timezone.utc).isoformat())
        guard.atomic_write(state_path,json.dumps(value)+'\n');print(json.dumps(value),flush=True)
    with (STATE/'recovery-sequence.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            state(status='waiting',phase='publication')
            wait_phase(day,'simulations',controller,10)
            wait_phase(day,'publication',controller)
            time.sleep(2)
            existing=phase_receipt(day,'explorer')
            if not existing:
                state(status='starting',phase='explorer')
                rc=controller.start(day,'explorer')
                if rc:raise RuntimeError('explorer_launch_failed')
            elif existing.get('status')=='blocked':raise RuntimeError('explorer_failed_manual_review_required')
            state(status='waiting',phase='explorer')
            wait_phase(day,'explorer',controller)
            time.sleep(2)
            state(status='verifying',phase='reactivation')
            proof=restore(day,guard)
            state(status='completed',reactivation=proof)
            return 0
        except Exception as exc:
            state(status='blocked',reason=str(exc)[:200],error_type=type(exc).__name__)
            return 1

def main():
    p=argparse.ArgumentParser();p.add_argument('--market-date',required=True);p.add_argument('--controller',required=True)
    a=p.parse_args();date.fromisoformat(a.market_date)
    return execute(a.market_date,Path(a.controller))
if __name__=='__main__':raise SystemExit(main())
