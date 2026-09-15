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

    def or_(self, expression):
        self._recorder["or_"] = expression
        return self

    def update(self, payload):
        self._recorder["update_payload"] = payload
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


def test_due_only_filters_on_next_attempt_at(monkeypatch):
    recorder: dict = {}
    monkeypatch.setattr(repo, "supabase", _FakeSupabase(recorder, []))

    repo.list_jobs(include_waiting=True, due_only=True)

    assert "or_" in recorder
    assert "next_attempt_at.is.null" in recorder["or_"]
    assert "next_attempt_at.lte." in recorder["or_"]


def test_due_only_false_does_not_filter(monkeypatch):
    recorder: dict = {}
    monkeypatch.setattr(repo, "supabase", _FakeSupabase(recorder, []))

    repo.list_jobs(include_waiting=True)

    assert "or_" not in recorder


def test_update_claimed_strict_raises_on_zero_rows(monkeypatch):
    monkeypatch.setattr(repo, "supabase", _FakeSupabase({}, []))
    try:
        repo.update_claimed("job-1", "worker-1", {"status": "ready"}, strict=True)
    except repo.LeaseFencingError:
        pass
    else:
        raise AssertionError("expected LeaseFencingError on a zero-row fenced update")


def test_update_claimed_non_strict_returns_none_on_zero_rows(monkeypatch):
    monkeypatch.setattr(repo, "supabase", _FakeSupabase({}, []))
    assert repo.update_claimed("job-1", "worker-1", {"status": "ready"}) is None


def test_ready_beats_waiting_regardless_of_next_attempt_at_age(monkeypatch):
    rows = [
        {"id": "waiting-old", "status": "waiting", "next_attempt_at": "2020-01-01T00:00:00+00:00"},
        {"id": "ready-new", "status": "ready", "next_attempt_at": "2026-09-14T00:00:00+00:00"},
    ]
    monkeypatch.setattr(repo, "supabase", _FakeSupabase({}, rows))

    result = repo.list_jobs(include_waiting=True)

    assert [row["id"] for row in result] == ["ready-new", "waiting-old"]


def test_due_retry_is_not_starved_by_older_waiting_row(monkeypatch):
    rows = [
        {"id": "waiting-old", "status": "waiting", "next_attempt_at": "2020-01-01T00:00:00+00:00"},
        {"id": "retry-due", "status": "retry", "next_attempt_at": "2026-09-10T00:00:00+00:00"},
    ]
    monkeypatch.setattr(repo, "supabase", _FakeSupabase({}, rows))

    result = repo.list_jobs(include_waiting=True, limit=1)

    assert [row["id"] for row in result] == ["retry-due"]


def test_waiting_jobs_eventually_run_when_no_runnable_work(monkeypatch):
    rows = [{"id": "waiting-only", "status": "waiting", "next_attempt_at": "2026-09-01T00:00:00+00:00"}]
    monkeypatch.setattr(repo, "supabase", _FakeSupabase({}, rows))

    result = repo.list_jobs(include_waiting=True)

    assert [row["id"] for row in result] == ["waiting-only"]


def test_manual_review_excluded_from_statuses_without_force_retry(monkeypatch):
    recorder: dict = {}
    monkeypatch.setattr(repo, "supabase", _FakeSupabase(recorder, []))

    repo.list_jobs(include_waiting=True, include_manual_review=False)

    assert "manual_review" not in recorder["status"]


def test_manual_review_included_only_when_explicitly_requested(monkeypatch):
    recorder: dict = {}
    monkeypatch.setattr(repo, "supabase", _FakeSupabase(recorder, []))

    repo.list_jobs(include_waiting=True, include_manual_review=True)

    assert "manual_review" in recorder["status"]


def test_priority_ordering_is_deterministic_on_ties(monkeypatch):
    rows = [
        {"id": "b-ready", "status": "ready", "next_attempt_at": "2026-09-14T00:00:00+00:00"},
        {"id": "a-ready", "status": "ready", "next_attempt_at": "2026-09-14T00:00:00+00:00"},
    ]
    monkeypatch.setattr(repo, "supabase", _FakeSupabase({}, rows))

    result_a = repo.list_jobs(include_waiting=True)
    result_b = repo.list_jobs(include_waiting=True)

    assert [row["id"] for row in result_a] == ["a-ready", "b-ready"]
    assert result_a == result_b


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
