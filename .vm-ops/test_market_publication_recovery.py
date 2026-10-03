import copy,unittest
from types import SimpleNamespace
import market_publication_recovery as m

class Tests(unittest.TestCase):
    def setup_data(self):
        batch={'status':'complete','promoted_at':'2026-09-26T12:00:00Z','expected_set_count':2,'succeeded_set_count':2,'failed_set_count':0,'missing_set_count':0}
        jobs=[{'id':i,'set_id':str(i),'status':'completed','completed_at':'2026-09-26T11:00:00Z'} for i in (1,2)]
        q=[{'id':i,'set_id':str(i),'status':'complete','source_completed_at':'2026-09-26T11:00:00+00:00','completed_at':'2026-09-26T11:01:00Z'} for i in (1,2)]
        return batch,jobs,q
    def test_complete_matching_source(self):self.assertTrue(m.source_ready(*self.setup_data()))
    def test_incomplete_batch(self):
        b,j,q=self.setup_data();b['status']='running';self.assertFalse(m.source_ready(b,j,q))
    def test_unpromoted(self):
        b,j,q=self.setup_data();b['promoted_at']=None;self.assertFalse(m.source_ready(b,j,q))
    def test_missing_source_set(self):
        b,j,q=self.setup_data();self.assertFalse(m.source_ready(b,j[:1],q))
    def test_missing_projection(self):
        b,j,q=self.setup_data();self.assertFalse(m.source_ready(b,j,q[:1]))
    def test_pending_projection(self):
        b,j,q=self.setup_data();q[0]['status']='pending';self.assertFalse(m.source_ready(b,j,q))
    def test_stale_source_provenance(self):
        b,j,q=self.setup_data();q[0]['source_completed_at']='2026-09-25T11:00:00Z';self.assertFalse(m.source_ready(b,j,q))
    def test_wrong_projection_completion(self):
        b,j,q=self.setup_data();q[0]['completed_at']='2026-09-25T11:00:00Z';self.assertFalse(m.source_ready(b,j,q))
    def test_duplicate_projection(self):
        b,j,q=self.setup_data();self.assertFalse(m.source_ready(b,j,q+[q[0]]))
    def test_newest_scrape_wins(self):
        b,j,q=self.setup_data();j.append({**j[0],'id':3,'completed_at':'2026-09-26T11:02:00Z'});self.assertFalse(m.source_ready(b,j,q))
    def test_failed_batch_refused(self):
        b,j,q=self.setup_data();b['failed_set_count']=1;self.assertFalse(m.source_ready(b,j,q))
    def test_cron_idempotent_and_preserves_existing(self):
        old='# CODE_RED_DISABLED * * * * * old\n* * * * * collection_recovery.py --tick\n'
        new=m.prepare_cron(old);self.assertTrue(new.startswith(old));self.assertEqual(m.prepare_cron(new),new)
    def test_cron_conflict_refused(self):
        with self.assertRaises(RuntimeError):m.prepare_cron(str(m.SCRIPT))
    def snapshot(self):
        return {'sets':[{'marketKey':'set:x:first_edition','marketScope':'first_edition','certificationStatus':'CERTIFIED','valueStatus':'current','setValueAsOf':'2026-09-26','currentSetValue':12},
                        {'marketKey':'set:x:shadowless','marketScope':'shadowless','certificationStatus':'SCOPED_MARKET_INCOMPLETE','valueStatus':'unavailable','currentSetValue':None}]}
    def test_snapshot_valid_and_unavailable_not_faked(self):self.assertEqual(len(m.validate_snapshot(self.snapshot(),'2026-09-26')),2)
    def test_snapshot_certified_stale_refused(self):
        s=self.snapshot();s['sets'][0]['setValueAsOf']='2026-09-25'
        with self.assertRaises(RuntimeError):m.validate_snapshot(s,'2026-09-26')
    def test_snapshot_duplicate_scope_refused(self):
        s=self.snapshot();s['sets'].append(s['sets'][0])
        with self.assertRaises(RuntimeError):m.validate_snapshot(s,'2026-09-26')
    def test_snapshot_uncertified_price_refused(self):
        s=self.snapshot();s['sets'][1]['currentSetValue']=12
        with self.assertRaises(RuntimeError):m.validate_snapshot(s,'2026-09-26')
    def test_absent_editions_refused(self):
        with self.assertRaises(RuntimeError):m.validate_snapshot({'sets':[]},'2026-09-26')
    def test_capped_source_pages_continue_to_exact_count(self):
        rows=[{'id':i} for i in range(600)]
        class C:
            def table(self,*a):return self
            def select(self,*a,**k):return self
            def eq(self,*a):return self
            def order(self,*a):return self
            def range(self,start,end):self.start=start;return self
            def execute(self):return SimpleNamespace(count=len(rows),data=rows[self.start:self.start+100])
        self.assertEqual(m.read_complete(C(),'scrape_jobs','id','2026-09-26'),rows)
    def test_missing_exact_count_refused(self):
        class C:
            def table(self,*a):return self
            def select(self,*a,**k):return self
            def eq(self,*a):return self
            def order(self,*a):return self
            def range(self,*a):return self
            def execute(self):return SimpleNamespace(count=None,data=[])
        with self.assertRaises(RuntimeError):m.read_complete(C(),'scrape_jobs','id','2026-09-26')

if __name__=='__main__':unittest.main()
