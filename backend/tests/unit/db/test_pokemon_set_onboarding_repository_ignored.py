"""The onboarding worker's queue reads must never surface baseline 'ignored' rows."""

from backend.db.repositories import pokemon_set_onboarding_repository as repo
from backend.services.pokemon_new_set_discovery_service import BASELINE_STATUS


class _FakeQuery:
    def __init__(self, recorder, rows):
        self._recorder = recorder
        self._rows = rows

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def in_(self, column, values):
        self._recorder[column] = list(values)
        return self

    def execute(self):
        return type("R", (), {"data": self._rows})()


class _FakeSupabase:
    def __init__(self, recorder, rows):
        self._recorder = recorder
        self._rows = rows

    def table(self, _name):
        return _FakeQuery(self._recorder, self._rows)


def test_worker_queue_read_never_requests_ignored_status(monkeypatch):
    recorder: dict = {}
    monkeypatch.setattr(repo, "supabase", _FakeSupabase(recorder, []))

    repo.list_jobs(include_waiting=True, include_manual_review=True)

    assert BASELINE_STATUS not in recorder["status"]
    assert recorder["status"] == ["detected", "ready", "retry", "waiting", "manual_review"]


def test_identity_statuses_expose_baseline_rows_to_discovery(monkeypatch):
    rows = [
        {"source_set_id": "604", "status": BASELINE_STATUS},
        {"source_set_id": "24688", "status": "detected"},
    ]
    monkeypatch.setattr(repo, "supabase", _FakeSupabase({}, rows))

    assert repo.list_source_identity_statuses("tcgplayer") == {
        "604": BASELINE_STATUS,
        "24688": "detected",
    }
