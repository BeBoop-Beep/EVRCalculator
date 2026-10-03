"""Source-anchored safety updates for reactivating scheduled publication."""
from pathlib import Path
import sys
root=Path(sys.argv[1]); bundle=Path(sys.argv[2])
def once(s,a,b):
    if s.count(a)!=1:raise RuntimeError('source anchor mismatch')
    return s.replace(a,b,1)

p=root/'backend/scripts/run_daily_opening_publication.py';s=p.read_text()
s=once(s,'''    from backend.scripts.audit_pokemon_market_publication import (
        format_report_lines,
        run_market_publication_audit,
    )

    try:
        report = run_market_publication_audit(client, market_date=resolved_market_date)''',
'''    from backend.scripts.audit_pokemon_market_publication import format_report_lines
    from backend.scripts.audit_pokemon_market_publication_resilient import run_market_publication_audit

    try:
        report = run_market_publication_audit(market_date=resolved_market_date)''')
p.write_text(s)

p=root/'backend/scripts/rebuild_snapshots_after_scrape.sh';s=p.read_text()
anchor='PYTHON_BIN="${PYTHON_BIN:-${REPO_ROOT}/.venv/bin/python}"\n'
addition='''
# Detached publication must hold the same resource-admission lock as scheduled
# writers for its ENTIRE lifetime. The triggering cron process can return first.
DB_GUARD="/home/ubuntu/state/db-safety/db_workload_guard.py"
if [[ -f "$DB_GUARD" && "${INDEX_POST_SCRAPE_GUARDED:-0}" != "1" ]]; then
  ENCODED="$("${PYTHON_BIN}" - "$0" "$@" <<'GUARD_PY'
import base64, shlex, sys
print(base64.b64encode(shlex.join(['bash', *sys.argv[1:]]).encode()).decode())
GUARD_PY
)"
  export INDEX_POST_SCRAPE_GUARDED=1
  exec "${PYTHON_BIN}" "$DB_GUARD" --wait-lock-seconds 120 --run-encoded "$ENCODED"
fi
'''
s=once(s,anchor,anchor+addition);p.write_text(s)
p=root/'backend/db/services/post_scrape_publication_trigger.py';s=p.read_text()
s=once(s,'    child_env["RUNNER_TRACKING_ID"] = ""\n','    child_env["RUNNER_TRACKING_ID"] = ""\n    child_env.pop("INDEX_POST_SCRAPE_GUARDED", None)\n')
p.write_text(s)

p=bundle/'db_workload_guard.py';s=p.read_text()
s=once(s,"VERSION = '2026-09-26.1'","VERSION = '2026-09-26.2'")
s=once(s,'pressure=live_pressure, interval: float = 30) -> int:', 'pressure=live_pressure, interval: float = 30, wait_lock_seconds: float = 0) -> int:')
s=once(s,'''        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return DEFERRED
        if (state / 'hold.json').exists():''',
'''        deadline = time.monotonic() + max(0, min(wait_lock_seconds, 300))
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if (state / 'hold.json').exists() or time.monotonic() >= deadline:
                    return DEFERRED
                time.sleep(min(.2, max(0, deadline-time.monotonic())))
        if (state / 'hold.json').exists():''')
s=once(s,"    args = parser.parse_args()","    parser.add_argument('--wait-lock-seconds', type=float, default=0)\n    args = parser.parse_args()")
s=once(s,'        return run_command(command)\n','        return run_command(command, wait_lock_seconds=args.wait_lock_seconds)\n')
p.write_text(s)

tests='''import fcntl
from pathlib import Path
import tempfile, threading, time, unittest
import db_workload_guard as g
class WaitingTests(unittest.TestCase):
    def test_waiter_runs_after_trigger_releases_lock(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d); lock=(state/'worker.lock').open('a')
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            thread=threading.Thread(target=lambda:(time.sleep(.1),fcntl.flock(lock,fcntl.LOCK_UN)))
            thread.start()
            try:self.assertEqual(g.run_command('true',state=state,pressure=lambda:None,wait_lock_seconds=2),0)
            finally:thread.join();lock.close()
    def test_waiter_does_not_bypass_hold(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d);g.hold('incident',state)
            self.assertEqual(g.run_command('false',state=state,pressure=lambda:self.fail('probe'),wait_lock_seconds=1),75)
    def test_waiter_has_deadline(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)
            with (state/'worker.lock').open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                t=time.monotonic()
                self.assertEqual(g.run_command('false',state=state,pressure=lambda:self.fail('probe'),wait_lock_seconds=.05),75)
                self.assertLess(time.monotonic()-t,1)
if __name__=='__main__':unittest.main()
'''
(bundle/'test_guard_wait.py').write_text(tests)
(root/'backend/tests/unit/scripts/test_opening_compact_recovery_audit.py').write_text('''from types import ModuleType,SimpleNamespace
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
''')
print('SOURCE_ANCHORS_VERIFIED=true')
