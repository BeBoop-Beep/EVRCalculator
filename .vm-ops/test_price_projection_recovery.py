from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
import price_projection_recovery as m

class ProjectionTests(unittest.TestCase):
    def batch(self):return {'status':'complete','promoted_at':'observed','expected_set_count':167}
    def ready(self):return {'ready':True,'expected_set_count':167,'complete_set_count':167}
    def test_complete_source_and_projection_required(self):
        self.assertTrue(m.public_ready(self.batch(),self.ready()))
    def test_partial_collection_not_public_ready(self):
        b=self.batch();b['status']='running'
        self.assertFalse(m.public_ready(b,self.ready()))
    def test_unpromoted_not_public_ready(self):
        b=self.batch();b['promoted_at']=None
        self.assertFalse(m.public_ready(b,self.ready()))
    def test_projection_for_partial_sources_not_full_cohort(self):
        self.assertFalse(m.public_ready(self.batch(),{'ready':True,'expected_set_count':5,'complete_set_count':5}))
    def test_mismatched_count_refused(self):
        r=self.ready();r['complete_set_count']=166
        self.assertFalse(m.public_ready(self.batch(),r))
    def test_no_batch_not_ready(self):
        self.assertFalse(m.public_ready(None,self.ready()))
    def test_verdict_false_preserved(self):
        r=self.ready();r['ready']=False
        self.assertFalse(m.public_ready(self.batch(),r))
    def test_worker_failure_nonzero(self):
        self.assertEqual(m.result_code({'after':{},'process_result':{'failed':1}}),1)
    def test_unreadable_authority_nonzero(self):
        self.assertEqual(m.result_code({'after':{'error':'unreadable'}}),1)
    def test_authority_reason_nonzero(self):
        self.assertEqual(m.result_code({'after':{'reason_code':'price_projection_authority_unavailable'}}),1)
    def test_terminal_no_progress_nonzero(self):
        self.assertEqual(m.result_code({'after':{'terminal_failed_set_count':1},'process_result':{'processed':0}}),1)
    def test_partial_success_does_not_require_full_ready(self):
        self.assertEqual(m.result_code({'after':{'ready':False},'process_result':{'processed':1,'completed':1,'failed':0}}),0)
    def test_already_ready_no_writes_is_success(self):
        self.assertEqual(m.result_code({'after':self.ready(),'process_result':None}),0)
    def test_cron_preserves_collection_and_disabled_legacy(self):
        before='# CODE_RED_DISABLED * * * * * legacy\n* * * * * collection_recovery.py --tick\n'
        after=m.prepare_cron(before)
        self.assertTrue(after.startswith(before));self.assertIn('sleep 25;',after)
        self.assertEqual(after.count(str(m.SCRIPT)),1)
        self.assertEqual(m.prepare_cron(after),after)
    def test_cron_conflict_fails_closed(self):
        with self.assertRaises(RuntimeError):m.prepare_cron(str(m.SCRIPT)+' other\n')
    def test_shared_admission_nonblocking(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'worker.lock'
            with p.open('a') as first,p.open('a') as second:
                self.assertTrue(m.acquire(first))
                self.assertFalse(m.acquire(second))
                m.fcntl.flock(first,m.fcntl.LOCK_UN)
                self.assertTrue(m.acquire(second))
    def test_disabled_projection_does_no_work(self):
        guard=Mock();guard.load.return_value={'enabled':False}
        self.assertEqual(m.tick(guard,Mock()),75);guard.run_command.assert_not_called()
    def test_busy_global_worker_does_no_projection(self):
        with tempfile.TemporaryDirectory() as d,patch.object(m,'STATE',Path(d)):
            guard=Mock();guard.load.return_value={'enabled':True}
            with (Path(d)/'worker.lock').open('a') as lock:
                self.assertTrue(m.acquire(lock))
                self.assertEqual(m.tick(guard,Mock()),75)
            guard.run_command.assert_not_called()

if __name__=='__main__':unittest.main()
