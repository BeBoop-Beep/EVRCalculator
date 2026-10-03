import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
import collection_recovery as m

class CollectionTests(unittest.TestCase):
    def healthy(self):
        return dict(total=2000, available=800, swap_total=1000, swap_free=800, pg_up=1, committed=3000, commit_limit=2000)
    def test_commitment_alone_not_physical_pressure(self):
        self.assertIsNone(m.physical_pressure(self.healthy()))
    def test_low_physical_memory_stops(self):
        value=self.healthy();value['available']=499
        self.assertEqual(m.physical_pressure(value),'available_memory_below_25_percent')
    def test_high_swap_stops(self):
        value=self.healthy();value['swap_free']=599
        self.assertEqual(m.physical_pressure(value),'swap_usage_above_40_percent')
    def test_postgres_down_stops(self):
        value=self.healthy();value['pg_up']=0
        self.assertEqual(m.physical_pressure(value),'postgres_not_up')
    def test_missing_metrics_stops(self):
        self.assertEqual(m.physical_pressure({}),'missing_physical_metrics')
    def test_nonfinite_metrics_stops(self):
        value=self.healthy();value['available']=math.nan
        self.assertEqual(m.physical_pressure(value),'invalid_physical_metrics')
    def test_impossible_metrics_stops(self):
        value=self.healthy();value['available']=2001
        self.assertEqual(m.physical_pressure(value),'invalid_physical_metrics')
    def test_zero_swap_valid(self):
        value=self.healthy();value.update(swap_total=0,swap_free=0)
        self.assertIsNone(m.physical_pressure(value))
    def test_prometheus_labels_supported(self):
        actual=m.parse_metrics('node_memory_MemTotal_bytes{service="db"} 2e9\npg_up 1\n')
        self.assertEqual(actual,{'total':2000000000.,'pg_up':1.})
    def test_restart_stops(self):
        self.assertEqual(m.transition_reason({'boot_time':1},{'boot_time':2}),'database_host_changed_during_collection')
    def test_new_oom_stops(self):
        self.assertEqual(m.transition_reason({'oom_kills':2},{'oom_kills':3}),'new_host_oom_kill')
    def test_old_oom_not_new_event(self):
        self.assertIsNone(m.transition_reason({'oom_kills':2},{'oom_kills':2}))
    def test_cron_leaves_disabled_publishers_unchanged(self):
        old='# CODE_RED_DISABLED * * * * * guarded-publisher\n0 * * * * echo heartbeat\n'
        new=m.prepare_cron(old)
        self.assertTrue(new.startswith(old))
        self.assertEqual(new.count(str(m.SCRIPT)),1)
        self.assertIn('--tick',new)
    def test_cron_idempotent(self):
        new=m.prepare_cron('SHELL=/bin/bash\n')
        self.assertEqual(m.prepare_cron(new),new)
    def test_cron_conflict_refused(self):
        with self.assertRaises(RuntimeError):m.prepare_cron(str(m.SCRIPT)+' --other\n')
    def test_changed_global_hold_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'hold';p.write_text('first')
            cfg={'approved_incident_hold_sha256':m.hashlib.sha256(p.read_bytes()).hexdigest()}
            self.assertTrue(m.expected_hold(cfg,p))
            p.write_text('new incident')
            self.assertFalse(m.expected_hold(cfg,p))
    def test_removed_global_hold_not_an_independent_failure(self):
        with tempfile.TemporaryDirectory() as d:self.assertTrue(m.expected_hold({},Path(d)/'absent'))
    def test_broken_hold_symlink_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'hold';p.symlink_to(Path(d)/'absent')
            with self.assertRaises(OSError):m.expected_hold({},p)
    def test_collection_disabled_never_runs(self):
        guard=Mock();guard.load.return_value={'enabled':False}
        self.assertEqual(m.tick(guard),75);guard.run_command.assert_not_called()
    def test_other_global_worker_blocks_collection(self):
        with tempfile.TemporaryDirectory() as d,patch.object(m,'STATE',Path(d)):
            guard=Mock();guard.load.return_value={'enabled':True}
            with (Path(d)/'worker.lock').open('a') as lock:
                m.fcntl.flock(lock,m.fcntl.LOCK_EX|m.fcntl.LOCK_NB)
                self.assertEqual(m.tick(guard),75)
            guard.run_command.assert_not_called()
    def test_completed_batch_does_not_rescrape(self):
        with tempfile.TemporaryDirectory() as d,patch.object(m,'STATE',Path(d)):
            guard=Mock();guard.load.side_effect=[{'enabled':True},{'status':'complete'}]
            self.assertEqual(m.tick(guard),0);guard.run_command.assert_not_called()

if __name__=='__main__':unittest.main()
