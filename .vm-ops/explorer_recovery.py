"""Bounded Explorer recovery. Run ONLY inside the resource-admission controller.

Projection advances first. Each cache build gets a fresh Python process, so
large planners do not accumulate in one process. Existing database cache state
is the checkpoint; no lease stealing, false freshness or automatic failed retry.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path('/home/ubuntu/repos/EVRCalculator')
STATE=Path('/home/ubuntu/state/db-safety')
sys.path.insert(0,str(ROOT))


def stale(rows,day):
    result=set()
    for row in rows:
        key=row.get('query_fingerprint')
        if not isinstance(key,str) or not key:
            raise ValueError('invalid_cache_identity')
        if row.get('status')!='ready' or str(row.get('computed_through') or '')[:10]<day:
            result.add(key)
    return result


def prove_progress(before,after,day):
    before_ids={r['query_fingerprint'] for r in before}
    after_ids={r['query_fingerprint'] for r in after}
    if len(before_ids)!=len(before) or len(after_ids)!=len(after):
        raise RuntimeError('duplicate_cache_identity')
    if before_ids!=after_ids:
        raise RuntimeError('cache_cohort_changed_during_recovery')
    old=stale(before,day);new=stale(after,day)
    if not new.issubset(old) or len(new)>=len(old):
        raise RuntimeError('cache_build_made_no_verified_progress')
    return len(old)-len(new),len(new)


def inventory(client):
    rows=list(client.table('pokemon_market_explorer_query_cache').select('query_fingerprint,status,computed_through').eq('cache_kind','maintained').limit(201).execute().data or [])
    if not rows or len(rows)>200:raise RuntimeError('maintained_cache_cohort_outside_bound')
    return rows


def emit(value):print(json.dumps(value,sort_keys=True,default=str),flush=True)


def invoke(day,label,module,args):
    folder=STATE/'recovery'/day/'explorer_steps'
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/(label+'.log')
    with path.open('a') as out:
        os.chmod(path,0o600)
        result=subprocess.run([sys.executable,'-m',module,*args],cwd=ROOT,stdout=out,stderr=subprocess.STDOUT)
    emit({'stage':label,'exit_code':result.returncode,'log':str(path)})
    if result.returncode:
        with path.open('rb') as f:
            f.seek(max(0,path.stat().st_size-12000));text=f.read().decode(errors='replace')
        import re
        print(re.sub(r'eyJ[A-Za-z0-9_.-]+','<REDACTED>',text)[-6000:],flush=True)
        raise RuntimeError('explorer_stage_failed:'+label)


def execute(client,day):
    invoke(day,'projection','backend.scripts.run_market_explorer_daily_publication',['--commit','--market-date',day])
    before=inventory(client)
    initial=len(stale(before,day))
    emit({'stage':'cache_inventory','target':day,'maintained':len(before),'stale':initial})
    # Exactly one attempt per initially stale cache, with a proof of decreasing
    # work after every successful invocation. A failed/no-op build stops here.
    for index in range(initial):
        invoke(day,f'cache_{index+1:03d}','backend.scripts.run_market_explorer_maintained_cache_prewarm',['--commit','--market-date',day,'--max-caches','1'])
        after=inventory(client)
        advanced,remaining=prove_progress(before,after,day)
        emit({'stage':'cache_checkpoint','advanced':advanced,'remaining':remaining,'target':day})
        before=after
        if not remaining:break
        time.sleep(3)
    if stale(before,day):raise RuntimeError('maintained_cache_catchup_incomplete')
    # Zero stale at entry needs its own guarded prepared-generation handoff.
    if initial==0:
        invoke(day,'prepared_handoff','backend.scripts.run_market_explorer_maintained_cache_prewarm',['--commit','--market-date',day,'--max-caches','1'])
    pointers=list(client.table('pokemon_market_explorer_prepared_serving_v1').select('generation_id').limit(2).execute().data or [])
    if len(pointers)!=1:raise RuntimeError('prepared_serving_pointer_not_unique')
    generation=pointers[0]['generation_id']
    rows=list(client.table('pokemon_market_explorer_prepared_generations_v1').select('generation_id,status,comparison_as_of,source_as_of').eq('generation_id',generation).limit(1).execute().data or [])
    if not rows:raise RuntimeError('prepared_generation_missing')
    row=rows[0]
    if str(row.get('comparison_as_of') or '')[:10]<day:
        raise RuntimeError('prepared_comparison_date_stale')
    dates=row.get('source_as_of') or {}
    if any(str(dates.get(k) or '')[:10]<day for k in ('sets','sealed')):
        raise RuntimeError('prepared_source_authority_stale')
    emit({'stage':'explorer_verified','generation':row,'maintained_caches':len(before),'target':day})
    return 0


def main():
    p=argparse.ArgumentParser();p.add_argument('--market-date',required=True);args=p.parse_args()
    from datetime import date
    date.fromisoformat(args.market_date)
    from backend.db.clients.supabase_client import create_service_role_client
    return execute(create_service_role_client(),args.market_date)

if __name__=='__main__':raise SystemExit(main())
