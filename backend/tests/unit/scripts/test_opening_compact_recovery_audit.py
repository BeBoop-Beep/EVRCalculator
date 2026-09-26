from types import ModuleType,SimpleNamespace
from unittest.mock import Mock,patch
import sys,unittest
from backend.scripts import run_daily_opening_publication as daily
class CompactAuditTests(unittest.TestCase):
    def run_audit(self,passed=True,error=None):
        core=ModuleType('backend.scripts.audit_pokemon_market_publication')
        core.format_report_lines=lambda r:[]
        core.run_market_publication_audit=Mock(side_effect=AssertionError('heavy reader'))
        compact=ModuleType('backend.scripts.audit_pokemon_market_publication_resilient')
        report=SimpleNamespace(passed=passed,error=error,failed_rows=[])
        report.to_dict=lambda:{'passed':passed}
        compact.run_market_publication_audit=Mock(return_value=report)
        summary=daily.PublicationSummary()
        with patch.dict(sys.modules,{core.__name__:core,compact.__name__:compact}):
            value=daily._run_market_publication_audit(object(),summary,resolved_market_date='2026-09-25',dry_run=False,skip_snapshots=False)
        compact.run_market_publication_audit.assert_called_once_with(market_date='2026-09-25')
        core.run_market_publication_audit.assert_not_called()
        return value
    def test_pass(self):self.assertEqual(self.run_audit(),'passed')
    def test_failure_preserved(self):self.assertEqual(self.run_audit(False),'failed')
    def test_error_preserved(self):self.assertEqual(self.run_audit(False,'unavailable'),'error:unavailable')
if __name__=='__main__':unittest.main()
