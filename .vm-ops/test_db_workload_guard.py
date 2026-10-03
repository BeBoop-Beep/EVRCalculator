import base64
import fcntl
from pathlib import Path
import tempfile
import unittest
import db_workload_guard as g


def healthy():
    return {'node_memory_' + k + '_bytes': v for k, v in {
        'MemTotal': 1000, 'MemAvailable': 600, 'SwapTotal': 1000,
        'SwapFree': 950, 'Committed_AS': 900, 'CommitLimit': 1500}.items()}


class Tests(unittest.TestCase):
    def test_healthy_metrics(self):
        self.assertIsNone(g.pressure_reason(healthy()))
    def test_low_ram(self):
        m=healthy(); m['node_memory_MemAvailable_bytes']=200
        self.assertEqual(g.pressure_reason(m),'available_memory_below_25_percent')
    def test_high_swap(self):
        m=healthy(); m['node_memory_SwapFree_bytes']=500
        self.assertEqual(g.pressure_reason(m),'swap_usage_above_40_percent')
    def test_high_commitment(self):
        m=healthy(); m['node_memory_Committed_AS_bytes']=1600
        self.assertEqual(g.pressure_reason(m),'memory_commitment_above_95_percent')
    def test_missing_metrics(self):
        self.assertEqual(g.pressure_reason({}),'missing_resource_metrics')
    def test_invalid_metrics(self):
        m=healthy(); m['node_memory_MemTotal_bytes']=0
        self.assertEqual(g.pressure_reason(m),'invalid_resource_metrics')
    def test_parse_metrics(self):
        self.assertEqual(g.parse_metrics('# help\nnode_memory_MemTotal_bytes{service="db"} 1e+09\n'),{'node_memory_MemTotal_bytes':1e9})
    def test_cron_round_trip_and_idempotency(self):
        cmd='cd ' + str(g.REPO) + " && python job.py >> out.log 2>&1"
        text='# heading\nSHELL=/bin/bash\n* * * * * ' + cmd + '\n0 * * * * echo "VM heartbeat"\n'
        result,count=g.guarded_crontab(text)
        self.assertEqual(count,1)
        encoded=result.splitlines()[2].split('--run-encoded ')[1]
        self.assertEqual(base64.b64decode(encoded).decode(),cmd)
        self.assertEqual(g.guarded_crontab(result),(result,count))
        self.assertIn('0 * * * * echo "VM heartbeat"',result)
    def test_disabled_entry_supported(self):
        text='# CODE_RED_DISABLED * * * * * cd ' + str(g.REPO) + ' && python job.py\n'
        result,count=g.guarded_crontab(text)
        self.assertEqual(count,1); self.assertTrue(result.startswith('* * * * *'))
    def test_percent_unescape(self):
        text='* * * * * cd ' + str(g.REPO) + ' && date +\\%F\n'
        result,_=g.guarded_crontab(text)
        command=base64.b64decode(result.split('--run-encoded ')[1]).decode()
        self.assertTrue(command.endswith('date +%F'))
    def test_unescaped_percent_refused(self):
        with self.assertRaises(ValueError):
            g.guarded_crontab('* * * * * cd ' + str(g.REPO) + ' && date +%F\n')
    def test_hold_blocks_without_probe(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); g.hold('incident',p)
            rc=g.run_command('touch '+str(p/'bad'),state=p,pressure=lambda:self.fail('probe'))
            self.assertEqual(rc,75);self.assertFalse((p/'bad').exists())
    def test_first_cause_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);g.hold('first',p);g.hold('second',p)
            self.assertEqual(g.load(p/'hold.json')['reason'],'first')
    def test_pressure_latches(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            self.assertEqual(g.run_command('touch '+str(p/'bad'),state=p,pressure=lambda:'pressure'),75)
            self.assertEqual(g.load(p/'hold.json')['reason'],'pressure')
            self.assertFalse((p/'bad').exists())
    def test_one_worker_only(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            with (p/'worker.lock').open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                self.assertEqual(g.run_command('true',state=p,pressure=lambda:self.fail('probe')),75)
    def test_success(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            self.assertEqual(g.run_command('true',state=p,pressure=lambda:None,interval=.1),0)
            self.assertEqual(g.load(next(p.glob('job.*.json')))['failures'],0)
    def test_failures_back_off(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            self.assertEqual(g.run_command('exit 7',state=p,pressure=lambda:None,interval=.1),7)
            self.assertEqual(g.run_command('exit 7',state=p,pressure=lambda:self.fail('retry')),75)
    def test_runtime_pressure_stops_group(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); checks=iter([None,'pressure'])
            self.assertEqual(g.run_command('sleep 20; touch '+str(p/'bad'),state=p,pressure=lambda:next(checks),interval=.05),75)
            self.assertTrue((p/'hold.json').exists()); self.assertFalse((p/'bad').exists())
    def test_atomic_file_permissions(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'state.json';g.atomic_write(p,'{}\n')
            self.assertEqual(p.stat().st_mode&0o777,0o600)

if __name__=='__main__': unittest.main()
