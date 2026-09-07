"""One-use verified source restoration. SQL is file data, never executed.

Restricted to the existing PR168 branch. This restores immutable ledger sources;
it does not apply migrations, connect to a DB, or modify main. Remove the transient
workflow and transport after the verified import commit has been inspected.
"""
from pathlib import Path
import base64
import hashlib
import importlib.util
import json
import os
import re
import subprocess

ROOT=Path(__file__).resolve().parents[2]
BRANCH='codex/price-storage-v2-scope-integration-10176be'
KNOWN={'20260906003840','20260906052214','20260906055303','20260906055315',
       '20260906230828','20260906232931','20260906233426','20260906233651'}
MANIFEST='d988d2e6e877d3373f613d2351e86339'
UPLOAD_SHA='26f40b379488f6ae927bf0287bae9b94a78b79c3526ed7aa46c94991422c532c'


def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()


def main():
    import lzma
    if os.environ.get('GITHUB_REPOSITORY')!='BeBoop-Beep/EVRCalculator' or os.environ.get('GITHUB_REF')!='refs/heads/'+BRANCH:
        raise RuntimeError('Import is restricted to the authorized repository and PR168 branch')
    starting=git('rev-parse','HEAD')
    if starting!=os.environ.get('GITHUB_SHA') or git('status','--porcelain'):
        raise RuntimeError('Checkout is not the clean triggering commit')
    docs=ROOT/'docs/price_storage_v2'
    ledger=(docs/'applied_migration_manifest.psv').read_bytes()
    if hashlib.sha256(ledger).hexdigest()!='c30834ad03807f0759c7d5071262074e467ef86b42ad660d46e15efa4bcffde1':
        raise RuntimeError('Independent version/name/checksum ledger changed')
    entries=[line.split('|') for line in ledger.decode().splitlines()]
    if len(entries)!=89 or len({v for v,n,h in entries})!=89:
        raise RuntimeError('89 distinct original migration records are required')
    if hashlib.md5('\n'.join(v+':'+h for v,n,h in entries).encode()).hexdigest()!=MANIFEST:
        raise RuntimeError('Original independent manifest check failed')
    packed=base64.b64decode(b''.join((docs/'import_transport'/f'part{i}.b64').read_bytes() for i in range(4)),validate=True)
    if hashlib.sha256(packed).hexdigest()!='bfb8eccd5d60e834923eec99a7172fb02693881e84bf64b7189ea521b95ca64e':
        raise RuntimeError('Transport checksum failed')
    decoder=lzma.LZMADecompressor(memlimit=128*1024*1024)
    body=decoder.decompress(packed,max_length=1_000_000)
    if not decoder.eof or decoder.unused_data or hashlib.sha256(body).hexdigest()!='ec588fb96c62f5cc4644b7b4bcf454fd09073c9e71cce2ff0addc2642c29c596':
        raise RuntimeError('Complete uploaded SQL transport is not intact')
    missing=json.loads(body)
    if len(missing)!=81 or not all(isinstance(s,str) for s in missing):
        raise RuntimeError('Expected 81 missing original SQL strings')
    statements=iter(missing); records=[]; pending=[]; unchanged=0
    folders=('supabase/migrations','backend/db/migrations','docs/price_storage_v2/applied_migrations')
    for version,name,checksum in entries:
        if not re.fullmatch(r'\d{14}',version) or not re.fullmatch(r'[a-z0-9_]+',name):
            raise RuntimeError('Unsafe ledger filename')
        filename=f'{version}_{name}.sql'
        data=((docs/'applied_migrations'/filename).read_bytes() if version in KNOWN else next(statements).encode('utf-8'))
        if hashlib.md5(data).hexdigest()!=checksum:
            raise RuntimeError(f'Original SQL mismatch for {version}')
        records.append(dict(version=version,name=name,md5=checksum,bytes=len(data),
                            git_blob_sha=hashlib.sha1(f'blob {len(data)}\0'.encode()+data).hexdigest()))
        for folder in folders:
            directory=ROOT/folder; target=directory/filename
            if directory.is_symlink() or any(p.is_symlink() for p in target.parents if p!=ROOT.parent):
                raise RuntimeError('Symlink destination is not allowed')
            aliases=set(directory.glob(version+'_*.sql'))|set(directory.glob('*_'+name+'.sql'))
            if any(p!=target for p in aliases):
                raise RuntimeError(f'Existing version/name alias for {version}')
            if target.exists():
                if target.is_symlink() or target.read_bytes()!=data:
                    raise RuntimeError(f'Existing original differs at {target.relative_to(ROOT)}')
                unchanged+=1
            else:
                pending.append((target,data))
    if sum(r['bytes'] for r in records)!=409228 or len(pending)!=243 or unchanged!=24:
        raise RuntimeError('Unexpected restoration plan; nothing has been written')
    # All 267 targets have been validated before the first exclusive file creation.
    for path,data in pending:
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as f:f.write(data)
    audit=json.loads(subprocess.check_output(['python3','backend/scripts/audit_price_storage_v2_migration_sources.py','--strict'],cwd=ROOT,text=True))
    if audit['status_counts']!={'reconciled':89} or audit['originals_archived']!=89:
        raise RuntimeError('Strict 89-record audit did not pass')
    for cmd in (['python3','backend/tests/run_price_storage_v2_unit.py'],
                ['python3','-m','unittest','backend.tests.test_price_storage_v2_migration_reconciliation','-v']):
        subprocess.run(cmd,cwd=ROOT,check=True,timeout=60)
    report=dict(status='frozen_window_source_restoration_complete',first_version=entries[0][0],last_version=entries[-1][0],
                records=89,statement_bytes=409228,manifest_md5=MANIFEST,uploaded_export_sha256=UPLOAD_SHA,
                original_sources_added=81,new_sql_files=len(pending),preexisting_sql_files_unchanged=unchanged,
                directories=list(folders),source_audit={k:v for k,v in audit.items() if k!='records'},
                production_sql_statements_executed=0,migrations_applied=0,post_window_history_verified=False,
                production_cutover_authorized=False,starting_commit=starting,workflow_run=os.environ.get('GITHUB_RUN_ID'),
                originals=records)
    proof=docs/'FULL_LEDGER_IMPORT_2026-09-07.json'
    with proof.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2,sort_keys=True);f.write('\n')
    paths=[str(p.relative_to(ROOT)) for p,d in pending]+[str(proof.relative_to(ROOT))]
    if set(git('ls-files','--others','--exclude-standard').splitlines())!=set(paths) or git('diff','--name-only'):
        raise RuntimeError('Unexpected file changes; refusing to commit')
    git('add','--',*paths)
    if set(git('diff','--cached','--name-only').splitlines())!=set(paths):
        raise RuntimeError('Unexpected index contents')
    # Never force-update or push to main. Concurrent branch edits stop this import.
    remote=git('ls-remote','origin','refs/heads/'+BRANCH).split()[0]
    if remote!=starting:raise RuntimeError('PR branch moved during import; refusing to push')
    git('-c','user.name=github-actions[bot]','-c','user.email=41898282+github-actions[bot]@users.noreply.github.com',
        'commit','-m','chore(pricing): restore all 89 original migration sources from verified ledger export')
    git('push','origin','HEAD:refs/heads/'+BRANCH)
    print('VERIFIED_LEDGER_IMPORT='+json.dumps({k:v for k,v in report.items() if k!='originals'},sort_keys=True))
    print('SOURCE_IMPORT_COMMIT='+git('rev-parse','HEAD'))


if __name__=='__main__':main()
