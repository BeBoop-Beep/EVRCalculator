"""A complete ledger can be rechecked without modifying any source files."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('ledger_reconciler',ROOT/'backend/scripts/reconcile_price_storage_v2_migrations.py')
RECONCILER=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RECONCILER)


class ReimportTests(unittest.TestCase):
    def test_exact_complete_export_is_a_zero_write_noop(self):
        records=[]
        for line in (ROOT/'docs/price_storage_v2/applied_migration_manifest.psv').read_text().splitlines():
            version,name,checksum=line.split('|')
            data=(ROOT/'docs/price_storage_v2/applied_migrations'/f'{version}_{name}.sql').read_bytes()
            records.append(dict(version=version,name=name,md5=checksum,statements=[data.decode('utf-8')]))
        verified=RECONCILER.validate_export(records)
        pending,conflicts=RECONCILER.plan_files(verified,ROOT)
        self.assertEqual(len(verified),89)
        self.assertEqual(conflicts,[])
        self.assertEqual(pending,[])
        self.assertEqual(RECONCILER.write_plan(pending,conflicts,write=False),0)


if __name__=='__main__':unittest.main(verbosity=2)
