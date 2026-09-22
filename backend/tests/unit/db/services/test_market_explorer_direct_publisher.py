from __future__ import annotations

import sys
from types import SimpleNamespace

from backend.db.services import market_explorer_direct_publisher as publisher


class FakeCursor:
    def __init__(self):
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return ({"generationId": "g1"},)


class FakeConnection:
    def __init__(self):
        self._cursor = FakeCursor()
        self.committed = False
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def install_fake_psycopg(monkeypatch, connection, calls):
    def connect(dsn, **kwargs):
        calls.append((dsn, kwargs))
        return connection

    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=connect))


def test_missing_direct_db_credential_fails_closed(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    assert publisher.publish_prepared_generation("2026-09-19") == {
        "status": "failed",
        "error": "direct_db_credential_missing",
    }


def test_database_url_precedes_supabase_db_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "primary-dsn")
    monkeypatch.setenv("SUPABASE_DB_URL", "secondary-dsn")
    assert publisher.resolve_database_url() == "primary-dsn"


def test_rollback_only_verification_never_commits(monkeypatch):
    conn = FakeConnection()
    calls = []
    install_fake_psycopg(monkeypatch, conn, calls)

    result = publisher.publish_prepared_generation(
        "2026-09-19",
        database_url="opaque-dsn",
        rollback_only=True,
    )

    assert result["status"] == "verified_rollback"
    assert conn.rolled_back is True
    assert conn.committed is False
    assert calls[0][1]["connect_timeout"] == 10
    assert conn._cursor.executed[0][0].startswith("select set_config")
    assert conn._cursor.executed[0][1] == ("120000",)
    assert "run_market_explorer_guarded_publisher_v1" in conn._cursor.executed[1][0]
    assert conn._cursor.executed[1][1] == ("2026-09-19",)


def test_commit_publishes_once(monkeypatch):
    conn = FakeConnection()
    calls = []
    install_fake_psycopg(monkeypatch, conn, calls)

    result = publisher.publish_prepared_generation(
        "2026-09-19",
        database_url="opaque-dsn",
    )

    assert result["status"] == "refreshed"
    assert conn.committed is True
    assert conn.rolled_back is False
    publish_calls = [
        sql for sql, _ in conn._cursor.executed
        if "run_market_explorer_guarded_publisher_v1" in sql
    ]
    assert len(publish_calls) == 1


def test_errors_redact_opaque_dsn(monkeypatch):
    opaque = "opaque-dsn-value"

    def connect(dsn, **kwargs):
        raise RuntimeError("connection failed for " + dsn)

    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=connect))
    result = publisher.publish_prepared_generation(
        "2026-09-19",
        database_url=opaque,
    )

    assert result["status"] == "failed"
    assert opaque not in result["error"]
    assert "<REDACTED_DATABASE_URL>" in result["error"]
