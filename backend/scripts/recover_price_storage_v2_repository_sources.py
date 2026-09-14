"""Offline original-source recovery: accept only the frozen ledger's exact hash.

No database connection, execution, migration-directory edits, or SQL application.
Representational transforms are candidates, never acceptance criteria. A recovery
is accepted only if its complete UTF-8 bytes match the independently captured MD5.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import textwrap

MANIFEST_MD5 = 'd988d2e6e877d3373f613d2351e86339'


def md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def variants(data: bytes):
    yield 'original_bytes', data
    text = data.decode('utf-8-sig')
    texts = {'utf8_lf': text.replace('\r\n', '\n')}
    plain = texts['utf8_lf']
    # Every candidate must match the original hash. Never use normalized equality
    # as evidence of original-byte identity or functional SQL equivalence.
    lines = plain.splitlines(keepends=True)
    without_comments = ''.join(l for l in lines if not l.lstrip().startswith('--'))
    texts['without_standalone_comments'] = without_comments
    for label, value in list(texts.items()):
        stripped = re.sub(r'^\s*BEGIN;\s*', '', value, count=1, flags=re.I)
        stripped = re.sub(r'\s*COMMIT;\s*$', '', stripped, count=1, flags=re.I)
        texts[label + '_without_outer_transaction'] = stripped
        texts[label + '_without_blank_lines'] = ''.join(l for l in value.splitlines(True) if l.strip())
    for label, value in list(texts.items()):
        texts[label + '_dedented'] = textwrap.dedent(value)
        texts[label + '_blank_runs_collapsed'] = re.sub(r'\n[ \t]*\n(?:[ \t]*\n)+', '\n\n', value)
    seen = set()
    for label, value in texts.items():
        for ending, candidate in (('unchanged', value), ('strip_final_lf', value.rstrip('\n')),
                                  ('strip_edges', value.strip()), ('single_final_lf', value.strip()+'\n')):
            encoded = candidate.encode('utf-8')
            if encoded in seen:
                continue
            seen.add(encoded)
            yield label + ':' + ending, encoded


def git(repo: Path, *args):
    return subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True).stdout


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[2])
    p.add_argument('--main-ref', required=True)
    p.add_argument('--base-ref', required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        raise ValueError('output must be a new directory')
    for ref in (args.main_ref, args.base_ref):
        if not re.fullmatch(r'[0-9a-f]{40}', ref):
            raise ValueError('pin full commit IDs')
    entries = [line.split('|') for line in (args.repo/'docs/price_storage_v2/applied_migration_manifest.psv').read_text().splitlines()]
    if len(entries) != 89 or md5('\n'.join(f'{v}:{h}' for v, n, h in entries).encode()) != MANIFEST_MD5:
        raise ValueError('independent migration manifest mismatch')
    names = git(args.repo, 'ls-tree', '-r', '--name-only', args.main_ref).decode().splitlines()
    sqlpaths = [s for s in names if s.endswith('.sql') and s.startswith(('supabase/migrations/', 'backend/db/migrations/'))]
    args.output.mkdir(parents=True)
    recovered_dir = args.output/'recovered'; recovered_dir.mkdir()
    source_dir = args.output/'sources'; source_dir.mkdir()
    report = []
    for version, name, expected in entries:
        candidates = [s for s in sqlpaths if Path(s).name.startswith(version+'_') or Path(s).name.endswith('_'+name+'.sql')]
        record = dict(version=version, name=name, expected_md5=expected, sources=[], recovered=False)
        for path in candidates:
            content = git(args.repo, 'show', f'{args.main_ref}:{path}')
            source_path = source_dir/path; source_path.parent.mkdir(parents=True, exist_ok=True); source_path.write_bytes(content)
            item = dict(path=path, bytes=len(content), md5=md5(content), exact=False)
            for transform, candidate in variants(content):
                if md5(candidate) == expected:
                    (recovered_dir/f'{version}_{name}.sql').write_bytes(candidate)
                    item.update(exact=True, transform=transform, recovered_bytes=len(candidate),
                                recovered_git_blob_sha=hashlib.sha1(f'blob {len(candidate)}\0'.encode()+candidate).hexdigest())
                    record['recovered'] = True
                    break
            record['sources'].append(item)
        report.append(record)
    # Export the precise three-way inputs for only files changed on both branches.
    ours = set(git(args.repo, 'diff', '--name-only', args.base_ref, 'HEAD').decode().splitlines())
    theirs = set(git(args.repo, 'diff', '--name-only', args.base_ref, args.main_ref).decode().splitlines())
    overlaps = []
    for path in sorted(ours & theirs):
        item = dict(path=path)
        for label, ref in (('base', args.base_ref), ('pr', 'HEAD'), ('main', args.main_ref)):
            try:
                content = git(args.repo, 'show', f'{ref}:{path}')
            except subprocess.CalledProcessError:
                item[label] = None
                continue
            target = args.output/'three_way'/label/path
            target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(content)
            item[label] = hashlib.sha256(content).hexdigest()
        overlaps.append(item)
    output = dict(main_ref=args.main_ref, base_ref=args.base_ref,
                  head_ref=git(args.repo, 'rev-parse', 'HEAD').decode().strip(),
                  database_access=False, executable_migrations_changed=False,
                  original_sources_recovered=sum(r['recovered'] for r in report),
                  unresolved_existing_sources=sum(bool(r['sources']) and not r['recovered'] for r in report),
                  records=report, overlapping_files=overlaps)
    (args.output/'report.json').write_text(json.dumps(output, indent=2, sort_keys=True)+'\n')
    print(json.dumps({k:v for k,v in output.items() if k!='records'}, indent=2))
    print('EXISTING_SOURCE_RESULTS='+json.dumps([r for r in report if r['sources']], sort_keys=True))


if __name__ == '__main__':
    main()
