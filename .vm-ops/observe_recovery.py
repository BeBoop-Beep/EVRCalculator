"""Local read-only observations for long recovery phases."""
from pathlib import Path
import json,os,re,time
ROOT=Path('/home/ubuntu/state/db-safety/recovery/2026-09-25')
def emit(x):print(json.dumps(x,default=str,sort_keys=True),flush=True)
for p in ROOT.glob('*.json'):
    r=json.loads(p.read_text());emit({'receipt':r})
    if r.get('status')=='completed':continue
    log=p.with_suffix('.log')
    if log.is_file():
        with log.open('rb') as f:
            f.seek(max(0,log.stat().st_size-8000));tail=f.read().decode(errors='replace').splitlines()[-10:]
        tail=[re.sub(r'eyJ[A-Za-z0-9_.-]+','<REDACTED>',l)[:550] for l in tail]
        emit({'phase':p.stem,'log_bytes':log.stat().st_size,'log_age_seconds':round(time.time()-log.stat().st_mtime,1),'tail':tail})
workers=[]
for p in Path('/proc').iterdir():
    if not p.name.isdigit() or int(p.name)==os.getpid():continue
    try:
        if p.stat().st_uid!=os.getuid():continue
        args=(p/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
        matches=[m for m in ('db_recovery_control','run_daily_opening_publication','run_all_v2_sets','refresh_stale_public_snapshots','operationalize_historical_rip','explorer_recovery','run_market_explorer','python') if m in args]
        if not matches:continue
        stat=(p/'stat').read_text().rsplit(')',1)[1].split()
        rss=(p/'status').read_text()
        workers.append({'pid':int(p.name),'ppid':int(stat[1]),'state':stat[0],'cpu_seconds':round((int(stat[11])+int(stat[12]))/os.sysconf('SC_CLK_TCK'),1),'rss_kib':re.search(r'VmRSS:\s+(\d+)',rss).group(1) if 'VmRSS:' in rss else None,'workloads':matches})
    except (OSError,ValueError):pass
emit({'worker_processes':workers[:30]})
