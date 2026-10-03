import unittest
from datetime import datetime,timezone
import market_publication_recovery as m

class TimestampTests(unittest.TestCase):
    def test_all_postgres_fraction_lengths_preserve_instant(self):
        for fraction in ('1','12','123','1234','13337','123456'):
            for offset in ('Z','+00:00'):
                with self.subTest(fraction=fraction,offset=offset):
                    self.assertEqual(m.parse_timestamp('2026-09-26T22:40:37.'+fraction+offset),
                        datetime(2026,9,26,22,40,37,int(fraction.ljust(6,'0')),tzinfo=timezone.utc))
    def test_timezone_required(self):
        with self.assertRaises(ValueError):m.parse_timestamp('2026-09-26T22:40:37.12345')
    def test_167_jobs_including_13_five_digit_timestamps_are_not_dropped(self):
        b={'status':'complete','promoted_at':'2026-09-26T23:30:00Z','expected_set_count':167,'succeeded_set_count':167}
        jobs=[];projections=[]
        for i in range(167):
            stamp='2026-09-26T22:40:37.'+('13337' if i<13 else '123456')+'+00:00'
            jobs.append({'id':i,'set_id':str(i),'status':'completed','completed_at':stamp})
            projections.append({'id':i,'set_id':str(i),'status':'complete','source_completed_at':stamp,'completed_at':'2026-09-26T23:00:00Z'})
        self.assertTrue(m.source_ready(b,jobs,projections))

if __name__=='__main__':unittest.main()
