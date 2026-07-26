"""Stale-row reconciliation is safe: it never touches or deletes observations."""

from types import SimpleNamespace

import pytest

import backend.scripts.reconcile_stale_scrape_jobs as recon


class _Query:
    def __init__(self, tracker, table_name):
        self._t = tracker
        self._table = table_name
        self._rows = tracker.data.get(table_name, [])

    # chainable no-op filters
    def select(self, *_a, **_k): return self
    def in_(self, *_a, **_k): return self
    def eq(self, *_a, **_k): return self
    def is_(self, *_a, **_k): return self
    def lt(self, *_a, **_k): return self
    def order(self, *_a, **_k): return self
    def limit(self, *_a, **_k): return self

    def update(self, _payload):
        self._t.updated_tables.add(self._table)
        return self

    def delete(self):
        self._t.deletes.append(self._table)
        raise AssertionError(f"reconciliation must never DELETE from {self._table}")

    def execute(self):
        return SimpleNamespace(data=self._rows)


class _FakeSupabase:
    def __init__(self, data):
        self.data = data
        self.touched_tables = []
        self.updated_tables = set()
        self.deletes = []

    def table(self, name):
        self.touched_tables.append(name)
        return _Query(self, name)


@pytest.fixture
def fake(monkeypatch):
    data = {
        "scrape_jobs": [{"id": 89138, "set_id": "s1", "status": "running"}],
        "scrape_job_runs": [{"id": "run-1", "status": "running", "queue_job_id": None,
                             "started_at": "2026-07-01T00:00:00+00:00"}],
        "sets": [{"id": "s1", "name": "Neo Genesis", "canonical_key": "neoGenesis"}],
    }
    fake = _FakeSupabase(data)
    monkeypatch.setattr(recon, "supabase", fake)
    return fake


def test_reconciliation_never_touches_price_observations(fake):
    recon._fetch_stale_active_jobs()
    recon._fetch_orphaned_stale_runs("2026-07-17T00:00:00+00:00")
    recon._close_orphaned_run("run-1", "2026-07-17T12:00:00+00:00")
    recon._report_incident_sets()

    assert "card_variant_price_observations" not in fake.touched_tables
    assert fake.deletes == []  # no deletes anywhere
    # only queue + diagnostic tables are mutated
    assert fake.updated_tables <= {"scrape_jobs", "scrape_job_runs"}


def test_incident_sets_are_explicitly_covered():
    assert set(recon.INCIDENT_SET_KEYS) == {
        "neoGenesis", "pokMonGO", "scarletAndViolet151", "journeyTogether"
    }


def test_orphan_close_only_updates_diagnostic_runs(fake):
    recon._close_orphaned_run("run-1", "2026-07-17T12:00:00+00:00")
    assert fake.updated_tables == {"scrape_job_runs"}
    assert fake.deletes == []
