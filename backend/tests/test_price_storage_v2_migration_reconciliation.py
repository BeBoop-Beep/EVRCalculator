"""Offline regression checks for the eight exact, original applied sources."""
from pathlib import Path
import hashlib
import importlib.util
import unittest

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = {
 '20260906003840': (3609, '0c20332085302d9778454074764eb6b7c1cb9e14'),
 '20260906052214': (9306, '838dfdb323620a00feb6a2b185d8b098a36159f7'),
 '20260906055303': (2498, '9c1517da4a5ec509ed892e9a9db2094f191d6331'),
 '20260906055315': (4362, 'f00a8e0ead38c83391f7dbecfaf551802d866801'),
 '20260906230828': (7186, '040ac8eedcfbd91adb3e993d3bf81a1f41f38cdc'),
 '20260906232931': (9139, '328b56f485efcde435b2f82ce00fbaa93daedac5'),
 '20260906233426': (17533, '67271cf35ac0715fb0f4c2a5feea0d70f76701df'),
 '20260906233651': (1300, '0d4cf9fda0ad61614d0a88a2adf6991398d72efe'),
}
COPIES = {
 '20260906003840_harden_market_explorer_reproject_authority_boundary.sql': 'a630f5c168e460eb36fc560f6af125a9e593f57a',
 '20260906045000_isolate_public_market_era_rollout_v1.sql': 'c61dc4367dc4897f7bd18cf338b0d35fa083ea26',
 '20260905120000_add_v12_v11_to_rip_statistics_targets_compact_rpc.sql': 'c8385da1dd43b028940b804fa3531a86fe2f4816',
 '20260905120100_add_v12_v11_to_rankings_sets_lens_rpc.sql': '3471db0cefff894d5a7ac9a74b861f84db1ccceb',
 '20260906232931_remove_boss_orders_display_name_alias_cards.sql': '5ac3272d967110cf4305dae8b723ae132386c6d3',
}


def blob_sha(data):
    return hashlib.sha1(f'blob {len(data)}\0'.encode()+data).hexdigest()


class SourceReconciliationTests(unittest.TestCase):
    def setUp(self):
        entries = [line.split('|') for line in (ROOT/'docs/price_storage_v2/applied_migration_manifest.psv').read_text().splitlines()]
        self.entries = {v: (n, h) for v, n, h in entries}

    def test_independent_full_ledger_checkpoint_retained(self):
        self.assertEqual(len(self.entries), 89)
        encoded = '\n'.join(f'{v}:{h}' for v, (n,h) in self.entries.items()).encode()
        self.assertEqual(hashlib.md5(encoded).hexdigest(), 'd988d2e6e877d3373f613d2351e86339')

    def test_both_migration_directories_match_eight_originals(self):
        for version, (size, sha) in EXPECTED.items():
            name, checksum = self.entries[version]
            for directory in ('supabase/migrations', 'backend/db/migrations', 'docs/price_storage_v2/applied_migrations'):
                with self.subTest(version=version, directory=directory):
                    data = (ROOT/directory/f'{version}_{name}.sql').read_bytes()
                    self.assertEqual(len(data), size)
                    self.assertEqual(hashlib.md5(data).hexdigest(), checksum)
                    self.assertEqual(blob_sha(data), sha)

    def test_nominal_timestamp_aliases_not_executable(self):
        for directory in ('supabase/migrations', 'backend/db/migrations'):
            for old in ('20260906045000', '20260905120000', '20260905120100'):
                self.assertFalse(list((ROOT/directory).glob(old+'_*.sql')))

    def test_preexisting_explanatory_sources_preserved_exactly(self):
        for name, sha in COPIES.items():
            data = (ROOT/'docs/price_storage_v2/reconciliation_repository_copies'/name).read_bytes()
            self.assertEqual(blob_sha(data), sha)

    def test_boss_postcondition_code_was_not_removed(self):
        version = '20260906232931'; name, _ = self.entries[version]
        sql = (ROOT/'supabase/migrations'/f'{version}_{name}.sql').read_text()
        self.assertIn('DO $postcheck$', sql)
        self.assertIn('IF v_remaining_aliases <> 0 THEN', sql)
        self.assertIn('IF v_survivors <> 2 THEN', sql)

    def test_two_rip_projections_retain_current_and_historical_contracts(self):
        for version in ('20260906055303', '20260906055315'):
            name, _ = self.entries[version]
            sql = (ROOT/'supabase/migrations'/f'{version}_{name}.sql').read_text()
            for field in ('overallRipV10', 'overallRipV12', 'publicRipContractV10', 'publicRipContractV11'):
                self.assertIn(field, sql)

    def test_audit_recognizes_reconciled_subset_without_waiving_full_gate(self):
        spec = importlib.util.spec_from_file_location('source_auditor', ROOT/'backend/scripts/audit_price_storage_v2_migration_sources.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        report = module.audit(ROOT)
        selected = [r for r in report['records'] if r['version'] in EXPECTED]
        self.assertEqual(len(selected), 8)
        self.assertTrue(all(r['status']=='reconciled' for r in selected))
        self.assertEqual(report['migration_sync_complete'], all(r['status']=='reconciled' for r in report['records']))


if __name__ == '__main__':
    unittest.main(verbosity=2)
