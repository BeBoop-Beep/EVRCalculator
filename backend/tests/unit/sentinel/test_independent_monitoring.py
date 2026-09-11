from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.sentinel.checks.independent import check_component_heartbeat
from backend.sentinel.config import SentinelConfig
from backend.sentinel.deadman import ping_deadman
from backend.sentinel.models import CheckOutcome, RunnerIdentity
from backend.sentinel.registry import CheckContext
from backend.sentinel.state import MemoryStateStore, SupabaseStateStore


NOW = datetime(2026, 9, 11, 20, 0, tzinfo=timezone.utc)
TARGET_COMPONENT = "sentinel_vm"
TARGET_HOST = "tcgplayer-scraper-pokemon"
OBSERVER = RunnerIdentity(component="sentinel_observer", host="observer-1", build_sha="obs-sha")
CTX = CheckContext(now=NOW, runner_identity=OBSERVER)


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows):
        self.rows = [dict(row) for row in rows]

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, key, value):
        self.rows = [row for row in self.rows if row.get(key) == value]
        return self

    def limit(self, n):
        self.rows = self.rows[:n]
        return self

    def execute(self):
        return _Result(self.rows)


class _Client:
    def __init__(self, rows):
        self.rows = rows
        self.tables = []

    def table(self, name):
        self.tables.append(name)
        return _Query(self.rows)


def _row(at):
    return {
        "component": TARGET_COMPONENT,
        "host": TARGET_HOST,
        "build_sha": "vm-sha",
        "heartbeat_at": at.isoformat(),
        "metadata": {"check_count": 13},
        "updated_at": at.isoformat(),
    }


def _check(rows, *, ctx=CTX, max_age=900):
    return check_component_heartbeat(
        ctx,
        client=_Client(rows),
        component=TARGET_COMPONENT,
        host=TARGET_HOST,
        max_age_seconds=max_age,
    )


def test_fresh_component_heartbeat_is_healthy():
    result = _check([_row(NOW - timedelta(minutes=4))])
    assert result.outcome == CheckOutcome.HEALTHY
    assert result.observed["age_seconds"] == 240.0


def test_exact_heartbeat_threshold_is_still_healthy():
    result = _check([_row(NOW - timedelta(seconds=900))])
    assert result.outcome == CheckOutcome.HEALTHY


def test_stale_component_heartbeat_is_critical_failure():
    result = _check([_row(NOW - timedelta(seconds=901))])
    assert result.failure_code == "component_heartbeat_stale"
    assert result.observed["age_seconds"] == 901.0


def test_missing_component_heartbeat_fails_closed():
    result = _check([])
    assert result.failure_code == "component_heartbeat_missing"


def test_invalid_and_far_future_heartbeat_fail_closed():
    invalid = _row(NOW)
    invalid["heartbeat_at"] = None
    assert _check([invalid]).failure_code == "component_heartbeat_contract_invalid"

    future = _check([_row(NOW + timedelta(seconds=61))])
    assert future.failure_code == "component_heartbeat_clock_invalid"


def test_same_component_and_host_cannot_claim_independent_observation():
    self_ctx = CheckContext(
        now=NOW,
        runner_identity=RunnerIdentity(
            component=TARGET_COMPONENT, host=TARGET_HOST, build_sha="same-host"
        ),
    )
    result = check_component_heartbeat(
        self_ctx,
        client=object(),
        component=TARGET_COMPONENT,
        host=TARGET_HOST,
        max_age_seconds=900,
    )
    assert result.failure_code == "heartbeat_observer_not_independent"


def test_heartbeat_target_host_and_threshold_are_mandatory():
    with pytest.raises(ValueError, match="host"):
        check_component_heartbeat(CTX, client=object(), component=TARGET_COMPONENT, host="")
    with pytest.raises(ValueError, match="positive"):
        check_component_heartbeat(
            CTX, client=object(), component=TARGET_COMPONENT, host=TARGET_HOST, max_age_seconds=0
        )


def test_memory_heartbeat_store_overwrites_same_component_host_instead_of_appending():
    store = MemoryStateStore()
    identity = RunnerIdentity(component=TARGET_COMPONENT, host=TARGET_HOST, build_sha="a")
    store.record_heartbeat(identity, NOW - timedelta(minutes=5), {"run": 1})
    store.record_heartbeat(identity, NOW, {"run": 2})
    assert len(store.heartbeats) == 1
    latest = store.heartbeats[(TARGET_COMPONENT, TARGET_HOST)]
    assert latest["heartbeat_at"] == NOW
    assert latest["metadata"] == {"run": 2}


class _UpsertQuery:
    def __init__(self, calls):
        self.calls = calls

    def upsert(self, payload, on_conflict=None):
        self.calls.append((payload, on_conflict))
        return self

    def execute(self):
        return _Result([])


class _UpsertClient:
    def __init__(self):
        self.calls = []
        self.table_names = []

    def table(self, name):
        self.table_names.append(name)
        return _UpsertQuery(self.calls)


def test_supabase_heartbeat_store_uses_component_host_conflict_upsert():
    client = _UpsertClient()
    store = SupabaseStateStore(client)
    identity = RunnerIdentity(component=TARGET_COMPONENT, host=TARGET_HOST, build_sha="vm-sha")
    store.record_heartbeat(identity, NOW, {"check_count": 13})
    assert client.table_names == ["sentinel_component_heartbeats"]
    payload, conflict = client.calls[0]
    assert conflict == "component,host"
    assert payload["component"] == TARGET_COMPONENT
    assert payload["host"] == TARGET_HOST
    assert payload["heartbeat_at"] == NOW.isoformat()


class _Response:
    def __init__(self, status_code):
        self.status_code = status_code


def test_deadman_unconfigured_is_inert():
    called = []
    result = ping_deadman("", http_get=lambda *a, **k: called.append(True))
    assert result.configured is False
    assert result.delivered is False
    assert called == []


def test_deadman_success_returns_only_safe_delivery_metadata():
    secret_url = "https://heartbeat.example.test/very-secret-capability"
    seen = []

    def get(url, **kwargs):
        seen.append((url, kwargs))
        return _Response(204)

    result = ping_deadman(secret_url, http_get=get)
    rendered = str(result.to_dict())
    assert result.configured is True
    assert result.delivered is True
    assert result.status_code == 204
    assert secret_url not in rendered
    assert "very-secret-capability" not in rendered
    assert seen[0][0] == secret_url


def test_deadman_non_2xx_and_exception_fail_without_url_leakage():
    secret_url = "https://heartbeat.example.test/private-token"
    non_ok = ping_deadman(secret_url, http_get=lambda *a, **k: _Response(500))
    assert non_ok.delivered is False
    assert non_ok.error_type == "deadman_http_error"
    assert secret_url not in str(non_ok.to_dict())

    def boom(*_args, **_kwargs):
        raise RuntimeError(f"request failed for {secret_url}")

    failed = ping_deadman(secret_url, http_get=boom)
    assert failed.delivered is False
    assert failed.error_type == "RuntimeError"
    assert secret_url not in str(failed.to_dict())
    assert "private-token" not in str(failed.to_dict())


def test_deadman_rejects_non_https_capability_url():
    result = ping_deadman("http://heartbeat.example.test/token")
    assert result.configured is True
    assert result.delivered is False
    assert result.error_type == "invalid_deadman_url"


def test_config_repr_never_exposes_deadman_capability_url():
    secret_url = "https://heartbeat.example.test/hidden-token"
    config = SentinelConfig(deadman_ping_url=secret_url)
    assert secret_url not in repr(config)
    assert "hidden-token" not in repr(config)
