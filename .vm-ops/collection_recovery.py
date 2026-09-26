"""Bounded raw-price collection, independent of downstream publication recovery.

Uses the existing global workload lock, a separately latched collection hold,
and the existing scrape queue. Never clears the publication/incident holds.
"""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ROOT = Path('/home/ubuntu/repos/EVRCalculator')
STATE = Path('/home/ubuntu/state/db-safety')
LANE = STATE / 'collection'
PYTHON = ROOT / '.venv/bin/python'
SCRIPT = STATE / 'collection_recovery.py'
CONFIG = LANE / 'authorization.json'
BASE = 'https://zwxzxuuawalvwioadhmf.supabase.co'
VERSION = '2026-09-26.collection-v1'
MARKER = '# INDEX_BOUNDED_COLLECTION_V1'


def emit(**data):
    print(json.dumps(data, default=str, sort_keys=True), flush=True)


def get_guard():
    spec = importlib.util.spec_from_file_location('collection_guard', STATE / 'db_workload_guard.py')
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    return guard


def physical_pressure(m):
    required = ('total', 'available', 'swap_total', 'swap_free', 'pg_up')
    if any(k not in m for k in required):
        return 'missing_physical_metrics'
    if not all(isinstance(m[k], (int, float)) and math.isfinite(m[k]) for k in required):
        return 'invalid_physical_metrics'
    if not (m['total'] > 0 and 0 <= m['available'] <= m['total'] and 0 <= m['swap_free'] <= m['swap_total']):
        return 'invalid_physical_metrics'
    if m['pg_up'] != 1:
        return 'postgres_not_up'
    if m['available'] / m['total'] < .25:
        return 'available_memory_below_25_percent'
    if m['swap_total'] and (m['swap_total'] - m['swap_free']) / m['swap_total'] > .40:
        return 'swap_usage_above_40_percent'
    # Committed_AS/CommitLimit is retained as evidence, not equated with RAM
    # consumption. It is not a standalone process-kill criterion.
    return None


def parse_metrics(text):
    aliases = {
        'node_memory_MemTotal_bytes': 'total',
        'node_memory_MemAvailable_bytes': 'available',
        'node_memory_SwapTotal_bytes': 'swap_total',
        'node_memory_SwapFree_bytes': 'swap_free',
        'node_memory_Committed_AS_bytes': 'committed',
        'node_memory_CommitLimit_bytes': 'commit_limit',
        'node_vmstat_oom_kill': 'oom_kills',
        'node_boot_time_seconds': 'boot_time', 'pg_up': 'pg_up',
    }
    result = {}
    for line in text.splitlines():
        if not line or line.startswith('#'):
            continue
        match = re.match(r'^([^\s{]+)(?:\{[^\n]*\})?\s+([-+0-9.eE]+)(?:\s+[0-9]+)?$', line)
        if match and match[1] in aliases:
            result[aliases[match[1]]] = float(match[2])
    return result


def transition_reason(old, new):
    if old.get('boot_time') is not None and new.get('boot_time') != old['boot_time']:
        return 'database_host_changed_during_collection'
    if new.get('oom_kills', 0) > old.get('oom_kills', 0):
        return 'new_host_oom_kill'
    return None


def expected_hold(config, hold):
    if not hold.exists() and not hold.is_symlink():
        return True
    return hashlib.sha256(hold.read_bytes()).hexdigest() == config.get('approved_incident_hold_sha256')


def make_pressure(guard, config):
    from dotenv import dotenv_values
    import httpx
    key = dotenv_values(ROOT / 'backend/.env', interpolate=False).get('SUPABASE_SERVICE_ROLE_KEY')
    baseline = {}
    def check():
        metrics = {}
        try:
            if not expected_hold(config, STATE / 'hold.json'):
                reason = 'global_hold_changed_operator_review_required'
            elif not key:
                reason = 'metrics_credential_missing'
            else:
                with httpx.Client(timeout=8) as client:
                    r = client.get(BASE + '/customer/v1/privileged/metrics', auth=('service_role', key))
                    r.raise_for_status()
                    metrics = parse_metrics(r.text)
                reason = physical_pressure(metrics)
                if reason is None and baseline:
                    reason = transition_reason(baseline, metrics)
                if not baseline:
                    baseline.update(metrics)
        except Exception as exc:
            reason = 'resource_probe_' + type(exc).__name__
        sample = {'checked_at': datetime.now(timezone.utc).isoformat(), 'metrics': metrics, 'stop_reason': reason}
        guard.atomic_write(LANE / 'latest_resources.json', json.dumps(sample) + '\n')
        if reason:
            guard.atomic_write(LANE / 'last_stop_evidence.json', json.dumps(sample) + '\n')
        return reason
    return check


def prepare_cron(text):
    target = str(SCRIPT)
    if MARKER in text or target in text:
        if text.count(target) != 1 or MARKER not in text:
            raise RuntimeError('conflicting_collection_schedule')
        return text
    return text.rstrip() + '\n\n' + MARKER + '\n' + (
        '* * * * * ' + str(PYTHON) + ' ' + target + ' --tick >> ' + str(LANE / 'cron.log') + ' 2>&1\n'
    )


def tick(guard):
    config = guard.load(CONFIG)
    if config.get('enabled') is not True:
        return 75
    with (STATE / 'worker.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 75
        local_now = datetime.now(ZoneInfo('America/Phoenix'))
        if (local_now.hour, local_now.minute) < (1, 5):
            return 0
        day = local_now.date().isoformat()
        complete = guard.load(LANE / (day + '.complete.json'))
        if complete.get('status') == 'complete':
            return 0
        command = shlex.join([
            '/usr/bin/timeout', '--foreground', '--signal=TERM', '--kill-after=20s', '300s',
            str(PYTHON), str(SCRIPT), '--body', '--market-date', day,
        ])
        return guard.run_command(command, state=LANE, pressure=make_pressure(guard, config), interval=20)


def body(day, guard):
    if day != datetime.now(ZoneInfo('America/Phoenix')).date().isoformat():
        raise RuntimeError('refusing_wrong_execution_date')
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    from dotenv import load_dotenv
    load_dotenv(ROOT / 'backend/.env', override=False)
    from backend.db.clients.supabase_client import create_service_role_client
    client = create_service_role_client()
    def batch():
        rows = client.table('pokemon_scrape_batches').select(
            'id,market_date,status,promoted_at,expected_set_count,succeeded_set_count,failed_set_count,missing_set_count'
        ).eq('market_date', day).limit(1).execute().data or []
        return rows[0] if rows else None
    current = batch()
    if current is None:
        subprocess.run([
            '/usr/bin/flock', '-n', '/tmp/pokemon-batch-create.lock', str(PYTHON),
            str(ROOT / 'backend/scripts/create_daily_scrape_batch.py'),
            '--market-date', day, '--trigger-source', 'scheduled', '--if-missing', '--skip-new-set-detection',
        ], check=True)
        current = batch()
        if current is None:
            raise RuntimeError('batch_creation_not_verified')
    emit(stage='collection_before', batch=current)
    if current['status'] != 'complete':
        env = os.environ.copy()
        env['SCRAPE_DRAIN_MAX_JOBS'] = '5'
        env['SCRAPE_DRAIN_MAX_RUNTIME_SECONDS'] = '120'
        subprocess.run([
            '/usr/bin/flock', '-n', '/tmp/pokemon-scrape-dispatcher.lock', str(PYTHON),
            str(ROOT / 'backend/scripts/run_next_scrape_job.py'), '--market-date', day,
        ], env=env, check=True)
        current = batch()
    if current is None:
        raise RuntimeError('batch_status_unreadable')
    result = {'checked_at': datetime.now(timezone.utc).isoformat(), 'stage': 'collection_after', 'batch': current}
    guard.atomic_write(LANE / (day + '.progress.json'), json.dumps(result) + '\n')
    emit(**result)
    if current['status'] == 'complete' and current.get('promoted_at'):
        guard.atomic_write(LANE / (day + '.complete.json'), json.dumps({'status': 'complete', **result}) + '\n')
    return 0


def install(guard):
    LANE.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (STATE / 'worker.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        hold = STATE / 'hold.json'
        if not hold.is_file():
            raise RuntimeError('expected_incident_hold_missing')
        original = subprocess.check_output(['crontab', '-l'], text=True, timeout=5)
        if sum(x.startswith('# CODE_RED_DISABLED ') for x in original.splitlines()) != 14:
            raise RuntimeError('schedule_state_changed_review_required')
        config = {'version': VERSION, 'enabled': True, 'approved_incident_hold_sha256': hashlib.sha256(hold.read_bytes()).hexdigest(),
                  'authorized_at': datetime.now(timezone.utc).isoformat(), 'max_jobs_per_tick': 5}
        check = make_pressure(guard, config)
        for _ in range(2):
            reason = check()
            if reason:
                raise RuntimeError(reason)
            time.sleep(5)
        trigger = (ROOT / 'backend/db/services/post_scrape_publication_trigger.py').read_text()
        if 'skipped_database_safety_hold' not in trigger:
            raise RuntimeError('publication_hold_code_missing')
        active = prepare_cron(original)
        stamp = str(time.time_ns())
        guard.atomic_write(LANE / ('crontab.before.' + stamp), original)
        restore_backup = Path('/home/ubuntu/ops-backups/crontab.code-red-db-load-shed.backup')
        previous_backup = restore_backup.read_text() if restore_backup.exists() else None
        if previous_backup is not None:
            guard.atomic_write(LANE / ('restore-backup.before.' + stamp), previous_backup)
        guard.atomic_write(SCRIPT, Path(__file__).read_text())
        guard.atomic_write(CONFIG, json.dumps(config) + '\n')
        try:
            subprocess.run(['crontab', '-'], input=active, text=True, check=True, timeout=5)
            if subprocess.check_output(['crontab', '-l'], text=True, timeout=5) != active:
                raise RuntimeError('schedule_verification_failed')
            guard.atomic_write(restore_backup, active)
        except Exception:
            guard.atomic_write(CONFIG, json.dumps({**config, 'enabled': False}) + '\n')
            subprocess.run(['crontab', '-'], input=original, text=True, check=True, timeout=5)
            if previous_backup is not None:
                guard.atomic_write(restore_backup, previous_backup)
            raise
        emit(status='collection_schedule_installed', global_incident_hold_preserved=hold.exists(),
             previous_schedules_unchanged=True, max_jobs_per_tick=5)
    return 0


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--install', action='store_true')
    mode.add_argument('--tick', action='store_true')
    mode.add_argument('--body', action='store_true')
    parser.add_argument('--market-date')
    args = parser.parse_args()
    guard = get_guard()
    try:
        return install(guard) if args.install else tick(guard) if args.tick else body(args.market_date, guard)
    except Exception as exc:
        emit(status='collection_failed', error_type=type(exc).__name__)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
