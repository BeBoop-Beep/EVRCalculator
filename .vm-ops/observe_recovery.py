"""Local read-only observations; fresh inputs are not proof of publication."""
from pathlib import Path
import base64,json,os,re,subprocess,time
ROOT=Path('/home/ubuntu/state/db-safety/recovery/2026-09-25')
STATE=ROOT.parent.parent
REPO=Path('/home/ubuntu/repos/EVRCalculator')
def emit(x):print(json.dumps(x,default=str,sort_keys=True),flush=True)
paths=[STATE/'hold.json',ROOT/'admission/hold.json',STATE/'reactivation.json']
for lane in ('collection','price-projection'):
    paths.extend(STATE/lane/name for name in ('authorization.json','hold.json','latest_resources.json','last_stop_evidence.json'))
for path in paths:
    report={'safety_file':str(path),'exists':path.exists()}
    if path.is_file():
        try:
            payload=json.loads(path.read_text())
            report['state']={k:payload[k] for k in ('version','status','reason','created_at','released_at','market_date','guarded_schedules','global_hold','enabled','authorized_at','max_jobs_per_tick','max_sets_per_tick','checked_at','metrics','stop_reason') if k in payload}
        except (OSError,ValueError):report['read_error']=True
    emit(report)
cron=subprocess.run(['crontab','-l'],text=True,capture_output=True,timeout=5)
if cron.returncode:
    emit({'cron_read_error':cron.returncode})
else:
    rows=[]
    for original in cron.stdout.splitlines():
        if not original.strip():continue
        independent=next((name for name in ('collection_recovery','price_projection_recovery') if name+'.py --tick' in original),None)
        if independent:
            rows.append({'disabled':original.lstrip().startswith('#'),'schedule':' '.join(original.split()[:5]),'workloads':[independent],'admission':'stage_local_hold_with_shared_global_lock'})
            continue
        line=original.removeprefix('# CODE_RED_DISABLED ')
        if '--run-encoded ' not in line:continue
        try:
            encoded=line.split('--run-encoded ',1)[1].split()[0]
            command=base64.b64decode(encoded,validate=True).decode()
            markers=[m for m in ('create_daily_scrape_batch','reconcile_stale_scrape_jobs','run_next_scrape_job','publish_post_scrape_if_needed','post_scrape_publication_watchdog','backend.alerts.dispatcher','market_freshness_watchdog','backend.sentinel.operational','run_daily_multi_source_card_pricing','check_multi_source_pricing_health','run_market_explorer_maintained_cache_prewarm') if m in command]
            rows.append({'disabled':original.lstrip().startswith('#'),'schedule':' '.join(line.split()[:5]),'workloads':markers,'admission':'legacy_global_hold'})
        except (ValueError,UnicodeError):rows.append({'decode_error':True})
    emit({'cron_state':rows,'active_guarded_schedules':sum(not r.get('disabled',True) for r in rows)})
for p in ROOT.glob('*.json'):
    r=json.loads(p.read_text());emit({'receipt':r})
    if r.get('status')=='completed':continue
    log=p.with_suffix('.log')
    if log.is_file():
        with log.open('rb') as f:
            f.seek(max(0,log.stat().st_size-8000));tail=f.read().decode(errors='replace').splitlines()[-10:]
        tail=[re.sub(r'eyJ[A-Za-z0-9_.-]+','<REDACTED>',l)[:550] for l in tail]
        emit({'phase':p.stem,'log_bytes':log.stat().st_size,'log_age_seconds':round(time.time()-log.stat().st_mtime,1),'tail':tail})
for lane in ('collection','price-projection'):
    for p in sorted((STATE/lane).glob('*.progress.json'))[-3:]:
        data=json.loads(p.read_text())
        if lane=='price-projection':
            projection=data.get('projection') or {};after=projection.get('after') or {};process=projection.get('process_result') or {}
            data={'market_date':data.get('market_date'),'checked_at':data.get('checked_at'),'public_source_cohort_ready':data.get('public_source_cohort_ready'),'expected_completed_scrape_sets':after.get('expected_set_count'),'projected_sets':after.get('complete_set_count'),'failed_sets':after.get('failed_set_count'),'processed_this_tick':process.get('processed')}
        emit({'lane':lane,'progress':data})
workers=[]
for p in Path('/proc').iterdir():
    if not p.name.isdigit() or int(p.name)==os.getpid():continue
    try:
        if p.stat().st_uid!=os.getuid():continue
        args=(p/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
        matches=[m for m in ('db_recovery_control','collection_recovery','price_projection_recovery','run_next_scrape_job','run_daily_opening_publication','run_all_v2_sets','refresh_stale_public_snapshots','operationalize_historical_rip','explorer_recovery','run_market_explorer','python') if m in args]
        if not matches:continue
        stat=(p/'stat').read_text().rsplit(')',1)[1].split()
        rss=(p/'status').read_text()
        workers.append({'pid':int(p.name),'ppid':int(stat[1]),'state':stat[0],'cpu_seconds':round((int(stat[11])+int(stat[12]))/os.sysconf('SC_CLK_TCK'),1),'rss_kib':re.search(r'VmRSS:\s+(\d+)',rss).group(1) if 'VmRSS:' in rss else None,'workloads':matches})
    except (OSError,ValueError):pass
emit({'worker_processes':workers[:30]})
