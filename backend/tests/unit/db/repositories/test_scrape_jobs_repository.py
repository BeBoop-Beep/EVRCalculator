from datetime import datetime, timezone
from types import SimpleNamespace

import backend.db.repositories.scrape_jobs_repository as repo


class _NotFilter:
    def __init__(self, query):
        self.query = query

    def is_(self, column, value):
        self.query.filters.append(("not_is", column, value))
        return self.query


class _FakeQuery:
    def __init__(self, fake_db, table_name):
        self.fake_db = fake_db
        self.table_name = table_name
        self.filters = []
        self.action = None
        self.payload = None

    @property
    def not_(self):
        return _NotFilter(self)

    def select(self, _columns):
        self.action = "select"
        return self

    def eq(self, column, value):
        self.filters.append(("eq", column, value))
        return self

    def in_(self, column, values):
        self.filters.append(("in", column, set(values)))
        return self

    def gte(self, column, value):
        self.filters.append(("gte", column, value))
        return self

    def lt(self, column, value):
        self.filters.append(("lt", column, value))
        return self

    def insert(self, payload):
        self.action = "insert"
        self.payload = payload
        return self

    def execute(self):
        if self.action == "insert":
            return SimpleNamespace(data=self.fake_db.insert_jobs(self.payload))

        rows = self.fake_db.rows_for(self.table_name)
        for op, column, value in self.filters:
            if op == "eq":
                rows = [row for row in rows if row.get(column) == value]
            elif op == "in":
                rows = [row for row in rows if row.get(column) in value]
            elif op == "gte":
                rows = [row for row in rows if row.get(column) is not None and row.get(column) >= value]
            elif op == "lt":
                rows = [row for row in rows if row.get(column) is not None and row.get(column) < value]
            elif op == "not_is" and value == "null":
                rows = [row for row in rows if row.get(column) is not None]
        return SimpleNamespace(data=[dict(row) for row in rows])


class _FakeSupabase:
    def __init__(self, sets, jobs):
        self.sets = [dict(row) for row in sets]
        self.jobs = [dict(row) for row in jobs]
        self.next_job_id = 1000

    def table(self, table_name):
        return _FakeQuery(self, table_name)

    def rows_for(self, table_name):
        if table_name == "sets":
            return list(self.sets)
        if table_name == "scrape_jobs":
            return list(self.jobs)
        raise AssertionError(f"Unexpected table: {table_name}")

    def insert_jobs(self, payload):
        rows = payload if isinstance(payload, list) else [payload]
        inserted = []
        for row in rows:
            if row.get("status") in {"pending", "running"}:
                active_exists = any(
                    existing.get("set_id") == row.get("set_id")
                    and existing.get("status") in {"pending", "running"}
                    for existing in self.jobs
                )
                if active_exists:
                    raise RuntimeError("duplicate key on scrape_jobs idx_scrape_jobs_one_active_per_set")

            inserted_row = {
                "id": self.next_job_id,
                "created_at": "db-now",
                **dict(row),
            }
            self.next_job_id += 1
            self.jobs.append(inserted_row)
            inserted.append(inserted_row)
        return inserted


def _ready_set(set_id="set-ready"):
    return {
        "id": set_id,
        "ready_for_daily_scrape": True,
        "has_card_details_url": True,
        "card_details_url": "https://example.test/cards",
    }


def _install_fake_db(monkeypatch, fake_db):
    monkeypatch.setattr(repo, "supabase", fake_db)
    monkeypatch.setattr(
        repo,
        "_current_utc_day_window",
        lambda: (
            datetime(2026, 6, 24, tzinfo=timezone.utc),
            datetime(2026, 6, 25, tzinfo=timezone.utc),
        ),
    )


def _job(status, created_at, set_id="set-ready"):
    return {
        "id": 1,
        "set_id": set_id,
        "status": status,
        "attempts": 1,
        "created_at": created_at,
    }


def test_enqueue_missing_scrape_jobs_inserts_pending_job_for_ready_set(monkeypatch):
    fake_db = _FakeSupabase(sets=[_ready_set()], jobs=[])
    _install_fake_db(monkeypatch, fake_db)

    inserted_count = repo.enqueue_missing_scrape_jobs_for_ready_sets()

    assert inserted_count == 1
    assert fake_db.jobs == [
        {
            "id": 1000,
            "created_at": "db-now",
            "set_id": "set-ready",
            "status": "pending",
            "attempts": 0,
        }
    ]


def test_enqueue_missing_scrape_jobs_skips_existing_pending_job(monkeypatch):
    fake_db = _FakeSupabase(
        sets=[_ready_set()],
        jobs=[_job("pending", "2026-06-24T08:00:00+00:00")],
    )
    _install_fake_db(monkeypatch, fake_db)

    assert repo.enqueue_missing_scrape_jobs_for_ready_sets() == 0
    assert len(fake_db.jobs) == 1


def test_enqueue_missing_scrape_jobs_skips_existing_running_job(monkeypatch):
    fake_db = _FakeSupabase(
        sets=[_ready_set()],
        jobs=[_job("running", "2026-06-24T08:00:00+00:00")],
    )
    _install_fake_db(monkeypatch, fake_db)

    assert repo.enqueue_missing_scrape_jobs_for_ready_sets() == 0
    assert len(fake_db.jobs) == 1


def test_enqueue_missing_scrape_jobs_skips_existing_completed_job_from_current_utc_day(monkeypatch):
    fake_db = _FakeSupabase(
        sets=[_ready_set()],
        jobs=[_job("completed", "2026-06-24T08:00:00+00:00")],
    )

    _install_fake_db(monkeypatch, fake_db)

    assert repo.enqueue_missing_scrape_jobs_for_ready_sets() == 0
    assert len(fake_db.jobs) == 1


def test_enqueue_missing_scrape_jobs_skips_existing_failed_job_from_current_utc_day(monkeypatch):
    fake_db = _FakeSupabase(
        sets=[_ready_set()],
        jobs=[_job("failed", "2026-06-24T08:00:00+00:00")],
    )
    _install_fake_db(monkeypatch, fake_db)

    assert repo.enqueue_missing_scrape_jobs_for_ready_sets() == 0
    assert len(fake_db.jobs) == 1


def test_enqueue_missing_scrape_jobs_allows_new_job_after_older_completed_or_failed_history(monkeypatch):
    fake_db = _FakeSupabase(
        sets=[_ready_set("completed-old"), _ready_set("failed-old")],
        jobs=[
            _job("completed", "2026-06-23T23:59:59+00:00", set_id="completed-old"),
            _job("failed", "2026-06-23T23:59:59+00:00", set_id="failed-old"),
        ],
    )
    _install_fake_db(monkeypatch, fake_db)

    assert repo.enqueue_missing_scrape_jobs_for_ready_sets() == 2
    assert [job["status"] for job in fake_db.jobs] == ["completed", "failed", "pending", "pending"]


def test_enqueue_missing_scrape_jobs_skips_sets_that_are_not_ready_or_have_no_url(monkeypatch):
    fake_db = _FakeSupabase(
        sets=[
            {**_ready_set("not-ready"), "ready_for_daily_scrape": False},
            {**_ready_set("details-disabled"), "has_card_details_url": False},
            {**_ready_set("missing-url"), "card_details_url": None},
        ],
        jobs=[],
    )
    _install_fake_db(monkeypatch, fake_db)

    assert repo.enqueue_missing_scrape_jobs_for_ready_sets() == 0
    assert fake_db.jobs == []
