"""Offline inventory of applied migration sources; never connects to a database.

A successful integrity check is NOT a completed migration sync. Use --strict to
require all 89 originals in both executable migration directories with no aliases.
Archive sources remain outside executable folders until ordering is reconciled.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

FIRST='20260905235956'
LAST='20260906233651'
EXPECTED_MANIFEST='d988d2e6e877d3373f613d2351e86339'
FOLDERS=('supabase/migrations','backend/db/migrations')


def audit(repo: Path) -> dict:
    directory=repo/'docs/price_storage_v2'
    records=[]
    for line in (directory/'applied_migration_manifest.psv').read_text().splitlines():
        version,name,checksum=line.split('|')
        if not re.fullmatch(r'\d{14}',version) or not re.fullmatch(r'[a-z0-9_]+',name) or not re.fullmatch(r'[a-f0-9]{32}',checksum):
            raise ValueError('invalid applied migration metadata')
        records.append(dict(version=version,name=name,md5=checksum))
    signature=hashlib.md5('\n'.join(f"{r['version']}:{r['md5']}" for r in records).encode()).hexdigest()
    if len(records)!=89 or signature!=EXPECTED_MANIFEST or len({r['version'] for r in records})!=89:
        raise ValueError('applied migration manifest failed its independently inspected checkpoint')
    files=[]
    for folder in FOLDERS:
        for path in (repo/folder).glob('*.sql'):
            files.append(dict(path=path.relative_to(repo).as_posix(),name=path.name,
                              md5=hashlib.md5(path.read_bytes()).hexdigest()))
    archive=directory/'applied_migrations'
    known={f"{r['version']}_{r['name']}.sql":r for r in records}
    for path in archive.glob('*.sql'):
        if path.name not in known or hashlib.md5(path.read_bytes()).hexdigest()!=known[path.name]['md5']:
            raise ValueError(f'archive is not an exact original: {path.name}')
    result=[]
    for record in records:
        name=f"{record['version']}_{record['name']}.sql"
        exact=[f['path'] for f in files if f['name']==name and f['md5']==record['md5']]
        same_version=[f['path'] for f in files if f['name'].startswith(record['version']+'_') and f['path'] not in exact]
        # Compare the complete name after the version, not a suffix: fix_foo is
        # a distinct migration from foo, whereas a second version of foo is an alias.
        same_name=[f['path'] for f in files if f['name'].partition('_')[2]==record['name']+'.sql' and f['path'] not in exact]
        other_exact=[f['path'] for f in files if f['md5']==record['md5'] and f['path'] not in exact]
        archived=(archive/name).exists()
        status=('reconciled' if len(exact)==len(FOLDERS) and not (same_version or same_name)
                else 'alias_or_content_conflict' if (same_version or same_name or other_exact)
                else 'one_directory_only' if exact else 'missing_executable_source')
        result.append(dict(**record,status=status,exact_paths=exact,
            same_version_conflicts=same_version,same_name_aliases=same_name,
            exact_content_other_paths=other_exact,exact_original_archived=archived))
    counts=Counter(r['status'] for r in result)
    return dict(manifest_records=89,manifest_md5=signature,
        integrity_check='pass',migration_sync_complete=counts.get('reconciled',0)==89,
        status_counts=dict(sorted(counts.items())),
        originals_archived=sum(r['exact_original_archived'] for r in result),
        originals_not_archived=sum(not r['exact_original_archived'] for r in result),
        database_writes=0,files_modified=0,records=result)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[2])
    p.add_argument('--strict',action='store_true')
    args=p.parse_args()
    result=audit(args.repo)
    print(json.dumps(result,indent=2,sort_keys=True))
    return 2 if args.strict and not result['migration_sync_complete'] else 0


if __name__=='__main__':
    raise SystemExit(main())
