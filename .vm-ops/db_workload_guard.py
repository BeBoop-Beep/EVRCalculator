"""Latched, host-local admission control for production maintenance, not API traffic.

No automatic release after an outage. Does not claim to fence direct SQL or
workers launched outside this wrapper. Runtime state stays outside Git.
"""
from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, urlopen

REPO = Path('/home/ubuntu/repos/EVRCalculator')
STATE = Path('/home/ubuntu/state/db-safety')
PROJECT = 'zwxzxuuawalvwioadhmf'
VERSION = '2026-09-26.1'
DEFERRED = 75


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.db-safety-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            out.write(text)
            out.flush()
            os.fsync(out.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def load(path: Path) -> dict:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError('invalid state')
    return value


def hold(reason: str, state: Path = STATE) -> None:
    # Preserve the first cause; a release is an explicit operator action.
    payload = json.dumps({'version': VERSION, 'created_at': time.time(), 'reason': reason}) + '\n'
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        with (state / 'hold.json').open('x', encoding='utf-8') as out:
            os.chmod(out.name, 0o600)
            out.write(payload)
            out.flush()
            os.fsync(out.fileno())
    except FileExistsError:
        pass


def parse_metrics(text: str) -> dict[str, float]:
    result = {}
    for line in text.splitlines():
        if not line or line.startswith('#'):
            continue
        match = re.match(r'^(node_memory_[A-Za-z_]+_bytes)(?:\{[^\n]*\})?\s+([-+eE.0-9]+)$', line)
        if match:
            result[match.group(1)] = float(match.group(2))
    return result


def pressure_reason(metrics: dict[str, float]) -> str | None:
    required = ['MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree', 'Committed_AS', 'CommitLimit']
    try:
        total, available, swap, swap_free, committed, commit_limit = [metrics['node_memory_' + x + '_bytes'] for x in required]
    except KeyError:
        return 'missing_resource_metrics'
    if not all(math.isfinite(x) for x in (total,available,swap,swap_free,committed,commit_limit)) or total <= 0 or commit_limit <= 0 or not 0 <= available <= total or swap < 0 or not 0 <= swap_free <= swap:
        return 'invalid_resource_metrics'
    if available / total < .25:
        return 'available_memory_below_25_percent'
    if swap > 0 and (swap - swap_free) / swap > .40:
        return 'swap_usage_above_40_percent'
    if committed / commit_limit > .95:
        return 'memory_commitment_above_95_percent'
    return None


def live_pressure() -> str | None:
    from dotenv import dotenv_values
    config = dotenv_values(REPO / 'backend/.env', interpolate=False)
    key = config.get('SUPABASE_SERVICE_ROLE_KEY')
    if not key:
        return 'metrics_credential_unavailable'
    auth = base64.b64encode(('service_role:' + key).encode()).decode()
    req = Request('https://' + PROJECT + '.supabase.co/customer/v1/privileged/metrics',
                  headers={'Authorization': 'Basic ' + auth})
    try:
        with urlopen(req, timeout=6) as response:
            text = response.read(2_000_001)
        if len(text) > 2_000_000:
            return 'metrics_response_oversized'
        return pressure_reason(parse_metrics(text.decode()))
    except Exception:
        # Never print DSNs, credentials, responses, or exception strings.
        return 'metrics_unavailable'


def guarded_crontab(text: str) -> tuple[str, int]:
    lines = []
    count = 0
    prefix = '# CODE_RED_DISABLED '
    guard = str(STATE / 'db_workload_guard.py')
    for original in text.splitlines():
        line = original[len(prefix):] if original.startswith(prefix) else original
        if not line.strip() or line.lstrip().startswith('#') or 'VM heartbeat' in line:
            lines.append(original)
            continue
        if guard in line:
            lines.append(line)
            count += 1
            continue
        if str(REPO) not in line:
            lines.append(original)
            continue
        parts = line.split(None, 5)
        if len(parts) != 6 or parts[0].startswith('@'):
            raise ValueError('unsupported application cron entry; refusing partial installation')
        command = parts[5]
        # Cron processes escaped percent signs before the shell. Reproduce
        # that behavior once inside the encoded command; reject stdin syntax.
        if re.search(r'(?<!\\)%', command):
            raise ValueError('cron stdin syntax unsupported')
        command = command.replace('\\%', '%')
        encoded = base64.b64encode(command.encode()).decode()
        lines.append(' '.join(parts[:5]) + ' ' + str(REPO / '.venv/bin/python') + ' ' + guard + ' --run-encoded ' + encoded)
        count += 1
    return '\n'.join(lines) + '\n', count


def install_hold() -> dict:
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(STATE, 0o700)
    with (STATE / 'install.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        current = subprocess.run(['crontab', '-l'], check=True, capture_output=True, text=True, timeout=5).stdout
        backup = Path('/home/ubuntu/ops-backups/crontab.code-red-db-load-shed.backup')
        guarded, count = guarded_crontab(current)
        if count == 0:
            raise ValueError('no application schedules recognized')
        stamp = str(time.time_ns())
        atomic_write(STATE / ('crontab.before.' + stamp), current)
        if backup.exists():
            atomic_write(STATE / ('restore-backup.before.' + stamp), backup.read_text())
        atomic_write(STATE / 'db_workload_guard.py', Path(__file__).read_text())
        hold('recurring_database_outage_manual_clear_required')
        # Keep live schedules disabled. The existing restore operation receives
        # GUARD-wrapped commands, so restoring the backup does not clear HOLD.
        disabled = '\n'.join('# CODE_RED_DISABLED ' + line if str(STATE / 'db_workload_guard.py') in line and not line.lstrip().startswith('#') else line for line in guarded.splitlines()) + '\n'
        subprocess.run(['crontab', '-'], input=disabled, text=True, check=True, timeout=5)
        atomic_write(backup, guarded)
        verify = subprocess.run(['crontab', '-l'], check=True, capture_output=True, text=True, timeout=5).stdout
        if verify != disabled:
            raise RuntimeError('crontab verification failed')
        probe = STATE / 'must_not_execute'
        if probe.exists():
            raise RuntimeError('unexpected test marker exists')
        command = 'touch ' + str(probe)
        rc = run_command(command)
        if rc != DEFERRED or probe.exists():
            raise RuntimeError('hold safety proof failed')
        return {'hold_active': True, 'guarded_schedules': count, 'active_application_schedules': 0,
                'restore_backup_guarded': True, 'hold_prevents_execution': True, 'version': VERSION}


def stop_process_group(child: subprocess.Popen) -> None:
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        child.wait(timeout=15)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.wait(timeout=5)


def run_command(command: str, *, state: Path = STATE, pressure=live_pressure, interval: float = 30) -> int:
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    if (state / 'hold.json').exists():
        return DEFERRED
    with (state / 'worker.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return DEFERRED
        if (state / 'hold.json').exists():
            return DEFERRED
        key = hashlib.sha256(command.encode()).hexdigest()[:24]
        receipt_path = state / ('job.' + key + '.json')
        receipt = load(receipt_path)
        if receipt.get('not_before', 0) > time.time():
            return DEFERRED
        reason = pressure()
        if reason:
            hold(reason, state)
            return DEFERRED
        child = subprocess.Popen(['/bin/sh', '-c', command], start_new_session=True)
        stopped = False
        previous = {}
        def forward(signum, frame):
            nonlocal stopped
            stopped = True
            hold('guard_interrupted_check_worker_before_resume', state)
            stop_process_group(child)
        for signum in (signal.SIGTERM, signal.SIGINT):
            previous[signum] = signal.signal(signum, forward)
        start = time.monotonic()
        try:
            while child.poll() is None:
                try:
                    child.wait(timeout=interval)
                except subprocess.TimeoutExpired:
                    reason = 'operator_hold' if (state / 'hold.json').exists() else pressure()
                    if time.monotonic() - start > 7200:
                        reason = 'maintenance_exceeded_two_hours'
                    if reason:
                        hold(reason, state)
                        stop_process_group(child)
                        stopped = True
                        break
        except Exception:
            hold('runtime_guard_failed_closed', state)
            stop_process_group(child)
            stopped = True
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, handler)
        rc = DEFERRED if stopped else child.returncode
        failures = 0 if rc == 0 else int(receipt.get('failures', 0)) + 1
        cooldown = 0 if rc == 0 else (60 if rc in (3, 4) else min(3600, 900 * 2 ** min(failures - 1, 2)))
        atomic_write(receipt_path, json.dumps({'version': VERSION, 'exit_code': rc, 'failures': failures,
                    'finished_at': time.time(), 'not_before': time.time() + cooldown}) + '\n')
        return rc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--install-hold', action='store_true')
    group.add_argument('--run-encoded')
    args = parser.parse_args()
    try:
        if args.install_hold:
            print(json.dumps(install_hold(), sort_keys=True))
            return 0
        command = base64.b64decode(args.run_encoded, validate=True).decode('utf-8')
        return run_command(command)
    except Exception as exc:
        hold('safety_guard_failed_closed')
        print(json.dumps({'status': 'failed_closed', 'error_type': type(exc).__name__}))
        return DEFERRED


if __name__ == '__main__':
    raise SystemExit(main())
