from pathlib import Path
import subprocess
import sys
from backend.scripts.publish_best_open_price_if_ready import PublicationFileLock


def test_os_releases_lock_when_worker_is_killed(tmp_path):
    path=tmp_path/'worker.lock'
    code='''import sys,time
from backend.scripts.publish_best_open_price_if_ready import PublicationFileLock
lock=PublicationFileLock(sys.argv[1])
assert lock.acquire()
print('locked',flush=True)
time.sleep(60)
'''
    worker=subprocess.Popen([sys.executable,'-c',code,str(path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        assert worker.stdout.readline().strip()=='locked'
        other=PublicationFileLock(path)
        assert not other.acquire()
    finally:
        worker.kill(); worker.communicate(timeout=10)
    replacement=PublicationFileLock(path)
    assert replacement.acquire()
    replacement.release()
