"""Bounded read-only verification of the independently restored Market path."""
from datetime import datetime,timezone
from pathlib import Path
import json,re,subprocess,time
import httpx

APP=Path('/home/ubuntu/repos/EVRCalculator')
STATE=Path('/home/ubuntu/state/db-safety')
LANE=STATE/'market-publication'
def emit(check,value):print(json.dumps({'check':check,'value':value},default=str,sort_keys=True),flush=True)

emit('checked_at',datetime.now(timezone.utc).isoformat())
emit('runtime_sha',subprocess.check_output(['git','-C',str(APP),'rev-parse','HEAD'],text=True).strip())
cron=subprocess.check_output(['crontab','-l'],text=True,timeout=5)
active=[line for line in cron.splitlines() if line.strip() and not line.lstrip().startswith('#')]
emit('schedules',{'collection':sum('collection_recovery.py --tick' in l for l in active),
                   'projection':sum('price_projection_recovery.py --tick' in l for l in active),
                   'market':sum('market_publication_recovery.py --tick' in l for l in active),
                   'market_schedule':[l.split(str(APP))[0].strip() for l in active if 'market_publication_recovery.py --tick' in l],
                   'legacy_disabled':sum(l.startswith('# CODE_RED_DISABLED ') for l in cron.splitlines())})
for name in ('authorization.json','hold.json','last_error.json','latest_resources.json'):
    p=LANE/name
    if not p.exists():emit(name,{'exists':False});continue
    value=json.loads(p.read_text());value.pop('approved_incident_hold_sha256',None)
    if 'message' in value:value['message']=re.sub(r'eyJ[A-Za-z0-9_.-]+','<REDACTED>',value['message'])[:1500]
    emit(name,value)
for pattern in ('*.progress.json','*.complete.json','job.*.json'):
    for p in sorted(LANE.glob(pattern))[-4:]:emit(p.name,json.loads(p.read_text()))
log=LANE/'cron.log'
if log.exists():
    with log.open('rb') as f:
        f.seek(max(0,log.stat().st_size-8000));lines=f.read().decode(errors='replace').splitlines()
    emit('scheduled_market_log',{'modified_at':datetime.fromtimestamp(log.stat().st_mtime,timezone.utc).isoformat(),
        'tail':[re.sub(r'eyJ[A-Za-z0-9_.-]+','<REDACTED>',x[:900]) for x in lines[-12:]]})
# Public unauthenticated serving endpoint, not a privileged database fetch.
started=time.monotonic()
try:
    with httpx.Client(timeout=25,follow_redirects=False) as client:
        response=client.get('https://evrcalculator.onrender.com/explore/set-value-market')
    result={'status':response.status_code,'elapsed_ms':round((time.monotonic()-started)*1000)}
    if response.status_code==200:
        payload=response.json();meta=payload.get('meta') or {};snapshot=meta.get('snapshot') or {}
        result['market_date']=payload.get('marketDate') or meta.get('marketDate') or snapshot.get('marketDate')
        sets=payload.get('sets') or []
        result['market_count']=len(sets)
        result['edition_markets']=[{k:r.get(k) for k in ('name','marketScope','marketKey','setValueAsOf','historyEndDate','currentSetValue','valueStatus','certificationStatus')}
          for r in sets if r.get('marketScope') in ('first_edition','unlimited','shadowless')]
    emit('public_market_read',result)
except Exception as exc:emit('public_market_read',{'error_type':type(exc).__name__})
emit('mutations',False)
