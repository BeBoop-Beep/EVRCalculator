from __future__ import annotations

from datetime import datetime, timezone

from backend.sentinel.models import RunnerIdentity
from backend.sentinel.state import SupabaseStateStore


NOW = datetime(2026, 9, 18, 22, 45, tzinfo=timezone.utc)


class _Transient521(Exception):
    code = 521


class _Result:
    def __init__(self, data=None):
        self.data = data or []


class _Query:
    def __init__(self, client, table_name):
        self.client = client
        self.table_name = table_name
        self.rows = [dict(row) for row in client.rows.get(table_name, [])]
        self.payload = None
        self.on_conflict = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, key, value):
        self.rows = [row for row in self.rows if row.get(key) == value]
        return self

    def in_(self, key, values):
        wanted = set(values)
        self.rows = [row for row in self.rows if row.get(key) in wanted]
        return self

    def order(self, key, desc=False):
        self.rows = sorted(self.rows, key=lambda row: row.get(key), reverse=desc)
        return self

    def limit(self, count):
        self.rows = self.rows[:count]
        return self

    def upsert(self, payload, on_conflict=None):
        self.payload = dict(payload)
        self.on_conflict = on_conflict
        return self

    def update(self, payload):
        self.payload = dict(payload)
        return self

    def execute(self):
        self.client.executes += 1
        if self.client.fail:
            self.client.fail = False
            raise _Transient521("temporary Supabase origin failure")
        if self.payload is not None:
            self.client.writes.append(
                (self.table_name, dict(self.payload), self.on_conflict)
            )
        return _Result(self.rows)


class _Client:
    def __init__(self, *, rows=None, fail=False):
        self.rows = rows or {}
        self.fail = fail
        self.executes = 0
        self.writes = []

    def table(self, name):
        return _Query(self, name)


def test_supabase_state_read_retries_transient_failure_with_fresh_client():
    first = _Client(fail=True)
    second = _Client(
        rows={
            "sentinel_check_state": [
                {
                    "check_key": "market.freshness",
                    "status": "healthy",
                    "consecutive_failures": 0,
                    "last_observation_json": {},
                }
            ]
        }
    )
    clients = iter((first, second))
    factory_calls = []

    def factory():
        client = next(clients)
        factory_calls.append(client)
        return client

    store = SupabaseStateStore(first, client_factory=factory)
    state = store.get_check_state("market.freshness")

    assert state is not None
    assert state.check_key == "market.freshness"
    assert state.status.value == "healthy"
    assert first.executes == 1
    assert second.executes == 1
    assert factory_calls == [first, second]


def test_supabase_heartbeat_write_retries_transient_failure_with_same_identity():
    first = _Client(fail=True)
    second = _Client()
    clients = iter((first, second))

    store = SupabaseStateStore(first, client_factory=lambda: next(clients))
    identity = RunnerIdentity(
        component="sentinel_vm",
        host="tcgplayer-scraper-pokemon-v2",
        build_sha="abc123",
    )

    store.record_heartbeat(identity, NOW, {"check_count": 1})

    assert first.executes == 1
    assert second.executes == 1
    assert len(second.writes) == 1
    table, payload, conflict = second.writes[0]
    assert table == "sentinel_component_heartbeats"
    assert conflict == "component,host"
    assert payload["component"] == "sentinel_vm"
    assert payload["host"] == "tcgplayer-scraper-pokemon-v2"
    assert payload["heartbeat_at"] == NOW.isoformat()


def test_supabase_state_read_accepts_postgrest_trimmed_fractional_seconds():
    client = _Client(
        rows={
            "sentinel_check_state": [
                {
                    "check_key": "market.freshness",
                    "status": "healthy",
                    "last_checked_at": "2026-09-21T05:41:02.71485+00:00",
                    "last_success_at": "2026-09-21T05:41:02.4Z",
                    "consecutive_failures": 0,
                    "last_observation_json": {},
                }
            ]
        }
    )
    store = SupabaseStateStore(client)

    state = store.get_check_state("market.freshness")

    assert state is not None
    assert state.last_checked_at == datetime(
        2026, 9, 21, 5, 41, 2, 714850, tzinfo=timezone.utc
    )
    assert state.last_success_at == datetime(
        2026, 9, 21, 5, 41, 2, 400000, tzinfo=timezone.utc
    )
