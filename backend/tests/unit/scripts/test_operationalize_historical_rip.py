from datetime import date, datetime, timezone

from backend.scripts import operationalize_historical_rip as subject


class _Result:
    def __init__(self, data): self.data = data


class _Rpc:
    def __init__(self, value): self.value = value
    def execute(self): return _Result(self.value)


class _Client:
    def __init__(self, inserted=0): self.inserted = inserted; self.calls = []
    def rpc(self, name, payload):
        self.calls.append((name, payload)); return _Rpc(self.inserted)


def _plan(all_fresh=True):
    return {"freshness":{"allFresh":all_fresh,"sources":[{"key":"artist_12m","due":not all_fresh}]},
            "rowsPlanned":128,"scoredRows":22,"unavailableRows":106,
            "providerCallsPlanned":0,"rowsToAppend":128}


def test_dry_run_has_zero_mutation_and_zero_provider_calls(monkeypatch):
    monkeypatch.setattr(subject, "build_plan", lambda *_a, **_k: _plan())
    client = _Client()
    result = subject.execute(client, as_of=date(2026,9,11),
                             now=datetime.now(timezone.utc), commit=False)
    assert result["status"] == "VALIDATED_DRY_RUN"
    assert result["mutationsPerformed"] == result["providerCallsPlanned"] == 0
    assert client.calls == []


def test_stale_source_fails_closed_without_history_write(monkeypatch):
    monkeypatch.setattr(subject, "build_plan", lambda *_a, **_k: _plan(False))
    client = _Client()
    result = subject.execute(client, as_of=date(2026,9,18),
                             now=datetime.now(timezone.utc), commit=True)
    assert result["status"] == "SOURCE_REFRESH_REQUIRED"
    assert result["dueSources"] == ["artist_12m"] and client.calls == []


def test_commit_uses_idempotent_database_append(monkeypatch):
    monkeypatch.setattr(subject, "build_plan", lambda *_a, **_k: _plan())
    client = _Client(inserted=0)
    result = subject.execute(client, as_of=date(2026,9,11),
                             now=datetime.now(timezone.utc), commit=True)
    assert result["status"] == "ALREADY_PRESENT" and result["mutationsPerformed"] == 0
    assert client.calls[0][0] == "append_current_collector_v7_history"
