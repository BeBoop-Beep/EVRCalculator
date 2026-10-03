"""Explicit serial recovery with resource limits and durable phase receipts."""
from __future__ import annotations
import argparse,fcntl,importlib.util,json,os,re,subprocess,sys,time
from pathlib import Path
from datetime import date,datetime
from zoneinfo import ZoneInfo
ROOT=Path('/home/ubuntu/repos/EVRCalculator')
STATE=Path('/home/ubuntu/state/db-safety')
PY=STATE/'recovery-venv/bin/python'
PY_LIB=PY.resolve().parent.parent/'lib'
if PY_LIB.is_dir():
    os.environ['LD_LIBRARY_PATH']=str(PY_LIB)+(os.pathsep+os.environ['LD_LIBRARY_PATH'] if os.environ.get('LD_LIBRARY_PATH') else '')
PHASES=('simulations','collector','publication','explorer','pricing')
sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('db_guard',STATE/'db_workload_guard.py')
guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)

def emit(value):print(json.dumps(value,default=str,sort_keys=True),flush=True)
def receipt_path(day,phase):return STATE/'recovery'/day/(phase+'.json')
def write_receipt(day,phase,value):guard.atomic_write(receipt_path(day,phase),json.dumps(value,default=str)+'\n')
def loaded(day,phase):return guard.load(receipt_path(day,phase))
def running(pid):
    try:
        os.kill(int(pid),0)
        return b'--action\0worker' in (Path('/proc')/str(pid)/'cmdline').read_bytes()
    except (OSError,TypeError,ValueError):return False

def commands(phase,day):
    if phase=='simulations':return [str(PY),str(Path(__file__).resolve()),'--action','simulation-body','--market-date',day]
    if phase=='collector':return [str(PY),'-m','backend.scripts.operationalize_historical_rip','--as-of-date',day,'--commit']
    if phase=='publication':return [str(PY),'-m','backend.scripts.run_daily_opening_publication','--market-date',day,'--gate-wait-attempts','1','--gate-wait-seconds','1','--json']
    if phase=='explorer':
        helper=Path(__file__).with_name(Path(__file__).name.replace('db_recovery_control.','explorer_recovery.',1))
        if not helper.is_file():raise RuntimeError('pinned_explorer_helper_missing')
        return [str(PY),str(helper),'--market-date',day]
    if phase=='pricing':return [str(PY),'-m','backend.scripts.run_daily_multi_source_card_pricing','--json','--resume','--no-frontend-env-fallback']
    raise ValueError('unsupported phase')

def simulation_body(day):
    from backend.db.clients.supabase_client import create_service_role_client
    from backend.db.services.publication_gate import evaluate_publication_gate,MODE_REQUIRED
    from backend.db.services.opening_simulation_gate import evaluate_opening_simulation_freshness,sets_needing_simulation
    from backend.scripts.run_daily_opening_publication import run_simulations_for_sets
    client=create_service_role_client()
    authority=evaluate_publication_gate(client,market_date=day,mode=MODE_REQUIRED)
    if not authority.allowed:raise RuntimeError('promoted_market_authority_not_ready')
    before=evaluate_opening_simulation_freshness(client,market_date=day,unsupported_keys=())
    if before.error:raise RuntimeError('simulation_freshness_unreadable')
    pending=sets_needing_simulation(before)
    emit({'stage':'simulation_inventory','eligible':before.eligible_count,'pending':pending,'target':day})
    if pending and datetime.now(ZoneInfo('America/Phoenix')).date().isoformat()!=day:
        raise RuntimeError('refusing_simulation_execution_date_rollover')
    for key in pending:
        if guard.live_pressure():raise RuntimeError('resource_pressure_before_next_set')
        result=run_simulations_for_sets([key],market_date=day,python_executable=str(PY),max_attempts=1)
        emit({'stage':'simulation_set_finished','set':key,'succeeded':bool(result and result[0].succeeded)})
        if not result or not result[0].succeeded:return 1
        time.sleep(2)
    after=evaluate_opening_simulation_freshness(client,market_date=day,unsupported_keys=())
    for line in after.report_lines(entry_point='serialized upgrade recovery'):print(line,flush=True)
    emit({'stage':'simulation_verified','ok':after.ok,'eligible':after.eligible_count,'target':day})
    return 0 if after.ok else 1

def worker(day,phase):
    import shlex
    os.chdir(ROOT)
    from dotenv import load_dotenv
    load_dotenv(ROOT/'backend/.env')
    os.environ['PYTHONUNBUFFERED']='1'
    os.environ['EVR_PRICING_STATE_DIR']='/home/ubuntu/state/multi_source_pricing'
    lane=STATE/'recovery'/day/'admission';lane.mkdir(parents=True,exist_ok=True)
    with (STATE/'worker.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('another_guarded_workload_is_active')
        record={'phase':phase,'market_date':day,'status':'running','pid':os.getpid(),'started_at':datetime.now(ZoneInfo('UTC')).isoformat(),'app_sha':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'python':str(PY)}
        write_receipt(day,phase,record);emit(record)
        rc=75
        try:rc=guard.run_command(shlex.join(commands(phase,day)),state=lane,interval=20)
        finally:
            record.update(status='completed' if rc==0 else 'blocked',exit_code=rc,finished_at=datetime.now(ZoneInfo('UTC')).isoformat())
            write_receipt(day,phase,record);emit(record)
    return rc

def start(day,phase):
    if not PY.is_file() or not (STATE/'recovery-venv/READY').is_file():raise RuntimeError('validated_recovery_runtime_missing')
    subprocess.run([str(PY),'-c','import scipy,numpy; from backend.jobs.evr_runner import EVRRunOrchestrator'],cwd=ROOT,check=True,timeout=20,stdout=subprocess.DEVNULL)
    reason=guard.live_pressure()
    if reason:raise RuntimeError('resource_preflight:'+reason)
    if not (STATE/'hold.json').exists():raise RuntimeError('global_recovery_hold_missing')
    with (STATE/'recovery-start.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for p in (STATE/'recovery').glob('*/*.json') if (STATE/'recovery').exists() else []:
            r=guard.load(p)
            if r.get('status') in ('running','starting') and running(r.get('pid')):raise RuntimeError('existing_recovery_phase_is_running')
        previous=loaded(day,phase)
        if previous.get('status')=='completed':emit({'status':'already_completed','receipt':previous});return 0
        folder=receipt_path(day,phase).parent;folder.mkdir(parents=True,exist_ok=True)
        log=folder/(phase+'.log')
        env=os.environ.copy();env['RUNNER_TRACKING_ID']='';env['PYTHONUNBUFFERED']='1';env['PYTHONPATH']=str(ROOT)
        with log.open('a') as out:
            p=subprocess.Popen([str(PY),str(Path(__file__).resolve()),'--action','worker','--phase',phase,'--market-date',day],cwd=ROOT,env=env,start_new_session=True,stdin=subprocess.DEVNULL,stdout=out,stderr=out)
        os.chmod(log,0o600);time.sleep(2)
        if p.poll() is not None and p.returncode!=0:status(day);raise RuntimeError('worker_exited_before_start_confirmation')
        emit({'status':'launched','phase':phase,'pid':p.pid,'log':str(log),'global_hold_preserved':True});status(day)
    return 0

def status(day):
    emit({'target':day,'global_hold':(STATE/'hold.json').exists(),'resource_preflight':guard.live_pressure()})
    for phase in PHASES:
        r=loaded(day,phase)
        if not r:continue
        r['process_alive']=running(r.get('pid'));emit(r)
        if r.get('status')=='completed':continue
        path=receipt_path(day,phase).with_suffix('.log')
        if path.exists():
            with path.open('rb') as f:
                f.seek(max(0,path.stat().st_size-40000));text=f.read().decode(errors='replace')
            selected=[l for l in text.splitlines() if ('[daily-opening-publication]' in l or '[refresh-' in l or l.startswith('{') or 'ERROR' in l or 'Traceback' in l or 'Error:' in l or '[START]' in l or 'COLLECTOR_' in l)]
            for l in selected[-14:]:print(re.sub(r'eyJ[A-Za-z0-9_.-]+','<REDACTED>',l)[:1200],flush=True)
    return 0

def main():
    p=argparse.ArgumentParser();p.add_argument('--action',choices=('start','worker','status','simulation-body'),required=True);p.add_argument('--phase',choices=PHASES);p.add_argument('--market-date',required=True)
    a=p.parse_args();date.fromisoformat(a.market_date)
    try:
        if a.action=='status':return status(a.market_date)
        if a.action=='simulation-body':return simulation_body(a.market_date)
        if not a.phase:raise ValueError('phase required')
        return start(a.market_date,a.phase) if a.action=='start' else worker(a.market_date,a.phase)
    except Exception as exc:
        emit({'status':'refused_or_failed','error_type':type(exc).__name__,'reason':str(exc)[:180] if type(exc) in (RuntimeError,ValueError) else 'inspect private log'})
        return 1
if __name__=='__main__':raise SystemExit(main())
