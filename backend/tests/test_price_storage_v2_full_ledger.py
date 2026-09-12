"""Strict full-window source restoration tests. Never connect to or execute SQL."""
from pathlib import Path
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
FOLDERS=('supabase/migrations','backend/db/migrations','docs/price_storage_v2/applied_migrations')
MANIFEST='d988d2e6e877d3373f613d2351e86339'
UPLOAD_SHA='26f40b379488f6ae927bf0287bae9b94a78b79c3526ed7aa46c94991422c532c'
SPEC=importlib.util.spec_from_file_location('full_ledger_auditor',ROOT/'backend/scripts/audit_price_storage_v2_migration_sources.py')
AUDITOR=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDITOR)


class FullLedgerTests(unittest.TestCase):
    def setUp(self):
        self.rows=[line.split('|') for line in (ROOT/'docs/price_storage_v2/applied_migration_manifest.psv').read_text().splitlines()]

    def test_all_89_originals_exact_in_all_three_directories(self):
        self.assertEqual(len(self.rows),89)
        total=0
        for version,name,checksum in self.rows:
            data=[]
            for folder in FOLDERS:
                content=(ROOT/folder/f'{version}_{name}.sql').read_bytes()
                self.assertEqual(hashlib.md5(content).hexdigest(),checksum,(folder,version))
                data.append(content)
            self.assertEqual(data[0],data[1]);self.assertEqual(data[1],data[2])
            total+=len(data[0])
        self.assertEqual(total,409228)

    def test_import_proof_matches_every_original_and_uploaded_checkpoint(self):
        proof=json.loads((ROOT/'docs/price_storage_v2/FULL_LEDGER_IMPORT_2026-09-07.json').read_text())
        self.assertEqual(proof['records'],89)
        self.assertEqual(proof['original_sources_added'],81)
        self.assertEqual(proof['new_sql_files'],243)
        self.assertEqual(proof['preexisting_sql_files_unchanged'],24)
        self.assertEqual(proof['manifest_md5'],MANIFEST)
        self.assertEqual(proof['uploaded_export_sha256'],UPLOAD_SHA)
        self.assertEqual(proof['production_sql_statements_executed'],0)
        self.assertFalse(proof['production_cutover_authorized'])
        self.assertFalse(proof['post_window_history_verified'])
        self.assertEqual(len(proof['originals']),89)
        for row in proof['originals']:
            content=(ROOT/FOLDERS[2]/f"{row['version']}_{row['name']}.sql").read_bytes()
            self.assertEqual(len(content),row['bytes'])
            self.assertEqual(hashlib.md5(content).hexdigest(),row['md5'])
            self.assertEqual(hashlib.sha1(f'blob {len(content)}\0'.encode()+content).hexdigest(),row['git_blob_sha'])

    def test_strict_gate_passes_full_frozen_window(self):
        result=subprocess.run([sys.executable,str(ROOT/'backend/scripts/audit_price_storage_v2_migration_sources.py'),'--strict'],capture_output=True,text=True,check=False)
        self.assertEqual(result.returncode,0,result.stderr)
        report=json.loads(result.stdout)
        self.assertTrue(report['migration_sync_complete'])
        self.assertEqual(report['status_counts'],{'reconciled':89})
        self.assertEqual(report['originals_archived'],89)
        self.assertEqual(report['originals_not_archived'],0)

    def test_followup_fix_name_is_distinct_from_original_not_an_alias(self):
        report=AUDITOR.audit(ROOT)
        for name in ('activate_exact_parity_set_market_rollouts','fix_activate_exact_parity_set_market_rollouts'):
            row=next(r for r in report['records'] if r['name']==name)
            self.assertEqual(row['status'],'reconciled')
            self.assertEqual(row['same_name_aliases'],[])

    def test_strict_gate_still_rejects_missing_tampered_and_real_alias_files(self):
        with tempfile.TemporaryDirectory() as directory:
            dest=Path(directory)
            for folder in FOLDERS:
                shutil.copytree(ROOT/folder,dest/folder)
            shutil.copy2(ROOT/'docs/price_storage_v2/applied_migration_manifest.psv',dest/'docs/price_storage_v2/applied_migration_manifest.psv')
            version,name,checksum=self.rows[0]
            target=dest/FOLDERS[0]/f'{version}_{name}.sql';original=target.read_bytes()
            target.unlink()
            result=subprocess.run([sys.executable,str(ROOT/'backend/scripts/audit_price_storage_v2_migration_sources.py'),'--repo',str(dest),'--strict'],capture_output=True,text=True,check=False)
            self.assertEqual(result.returncode,2)
            target.write_bytes(original+b'\n-- changed bytes')
            self.assertFalse(AUDITOR.audit(dest)['migration_sync_complete'])
            target.write_bytes(original)
            alias=target.with_name('20260905000001_'+name+'.sql');alias.write_bytes(original)
            row=next(r for r in AUDITOR.audit(dest)['records'] if r['version']==version)
            self.assertEqual(row['status'],'alias_or_content_conflict')
            self.assertIn(alias.relative_to(dest).as_posix(),row['same_name_aliases'])
            alias.unlink()
            self.assertTrue(AUDITOR.audit(dest)['migration_sync_complete'])


if __name__=='__main__':unittest.main(verbosity=2)
