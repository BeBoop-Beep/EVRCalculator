"""Offline regression tests; no live DB/network access is needed."""
from pathlib import Path
from types import SimpleNamespace, ModuleType
from unittest.mock import Mock, patch
import tempfile
import os
import sys
import unittest
from backend.db.services import production_db_safety as safety
from backend.db.services import post_scrape_publication_trigger as trigger

DAY='2026-09-25'

class TestSafety(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.path=Path(self.directory.name)/'hold.json'
        self.env=patch.dict(os.environ,{'INDEX_DB_SAFETY_HOLD_PATH':str(self.path)})
        self.env.start()
    def tearDown(self):
        self.env.stop();self.directory.cleanup()
    def test_absent_hold_allows(self):
        self.assertFalse(safety.maintenance_hold_active())
    def test_existing_hold_blocks(self):
        self.path.write_text('{}')
        self.assertTrue(safety.maintenance_hold_active())
        with self.assertRaisesRegex(RuntimeError,'safety_hold'):
            safety.require_maintenance_allowed()
    def test_broken_symlink_blocks(self):
        self.path.symlink_to(self.path.parent/'missing')
        self.assertTrue(safety.maintenance_hold_active())
    def test_unreadable_state_blocks(self):
        with patch.object(Path,'lstat',side_effect=PermissionError):
            self.assertTrue(safety.maintenance_hold_active())
    def test_hold_stops_before_projection_or_currency(self):
        self.path.write_text('{}')
        projection=Mock(side_effect=AssertionError('must not query'))
        currency=Mock(side_effect=AssertionError('must not audit'))
        launch=Mock(side_effect=AssertionError('must not launch'))
        out=trigger.trigger_post_scrape_publication_if_needed(DAY,price_projection_check=projection,publication_current=currency,popen=launch)
        self.assertEqual(out['status'],'skipped_database_safety_hold')
        projection.assert_not_called();currency.assert_not_called();launch.assert_not_called()
    def test_hold_prevents_manual_launcher(self):
        self.path.write_text('{}')
        with patch.object(trigger.subprocess,'Popen') as launch:
            with self.assertRaises(RuntimeError):
                trigger._default_popen(['false'],cwd='/',log_path=self.path.parent/'not-created')
            launch.assert_not_called()
        self.assertFalse((self.path.parent/'not-created').exists())
    def test_hold_currency_is_unknown_without_reads(self):
        self.path.write_text('{}')
        client=Mock()
        self.assertIs(trigger.evaluate_post_scrape_publication_currency(client,DAY),trigger.PublicationCurrencyStatus.UNKNOWN)
        client.table.assert_not_called()
    def test_scalar_failure_does_not_escalate(self):
        audit=Mock(side_effect=AssertionError('no heavy fallback'))
        with patch.object(trigger,'_global_market_authority_date',side_effect=RuntimeError('unreachable')):
            actual=trigger.evaluate_post_scrape_publication_currency(Mock(),DAY,audit_runner=audit)
        self.assertIs(actual,trigger.PublicationCurrencyStatus.UNKNOWN)
        audit.assert_not_called()
    def test_known_stale_avoids_full_audit(self):
        audit=Mock(side_effect=AssertionError('no unnecessary audit'))
        with patch.object(trigger,'_global_market_authority_date',return_value='2026-09-24'):
            actual=trigger.evaluate_post_scrape_publication_currency(Mock(),DAY,audit_runner=audit)
        self.assertIs(actual,trigger.PublicationCurrencyStatus.STALE)
        audit.assert_not_called()
    def test_default_delegates_to_compact_audit(self):
        core=ModuleType('backend.scripts.audit_pokemon_market_publication')
        core.PHASE_POST_SCRAPE='post-scrape'
        core.run_market_publication_audit=Mock(side_effect=AssertionError('legacy reader invoked'))
        compact=ModuleType('backend.scripts.audit_pokemon_market_publication_resilient')
        compact.run_market_publication_audit=Mock(return_value=SimpleNamespace(market_date=DAY,passed=True))
        with patch.dict(sys.modules,{core.__name__:core,compact.__name__:compact}), patch.object(trigger,'_global_market_authority_date',return_value=DAY), patch.object(trigger,'_market_explorer_v2_current',return_value=True):
            actual=trigger.evaluate_post_scrape_publication_currency(Mock(),DAY)
        self.assertIs(actual,trigger.PublicationCurrencyStatus.CURRENT)
        compact.run_market_publication_audit.assert_called_once_with(market_date=DAY,phase='post-scrape')
        core.run_market_publication_audit.assert_not_called()
    def test_injected_audit_failure_stays_stale(self):
        core=ModuleType('backend.scripts.audit_pokemon_market_publication')
        core.PHASE_POST_SCRAPE='post-scrape'
        client=Mock();audit=Mock(return_value=SimpleNamespace(market_date=DAY,passed=False))
        with patch.dict(sys.modules,{core.__name__:core}),patch.object(trigger,'_global_market_authority_date',return_value=DAY):
            actual=trigger.evaluate_post_scrape_publication_currency(client,DAY,audit_runner=audit)
        self.assertIs(actual,trigger.PublicationCurrencyStatus.STALE)
        audit.assert_called_once_with(client,market_date=DAY,phase='post-scrape')

if __name__=='__main__': unittest.main()
