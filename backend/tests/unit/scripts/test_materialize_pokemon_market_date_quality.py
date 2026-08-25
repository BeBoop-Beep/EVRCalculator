"""Contract for the Market Date Quality materialization CLI."""

import pytest

from backend.scripts import materialize_pokemon_market_date_quality as cli
from backend.db.services.market_date_quality import (
    MARKET_QUALITY_CONTRACT_VERSION,
    STATUS_DEGRADED,
    STATUS_LEGACY_VERIFIED,
    STATUS_READY,
)

SOURCE_TABLE = "pokemon_set_value_daily_history"
INDEX_TABLE = "pokemon_market_index_daily_history"
QUALITY_TABLE = "pokemon_market_date_quality"

COHORT = ["set-a", "set-b"]
DAYS = ["2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20"]


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, client, table):
        self._client, self._table = client, table
        self._rows = list(client.tables.get(table, []))
        self._range = None

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self._rows = [r for r in self._rows
                      if column not in r or str(r.get(column)) == str(value)]
        return self

    def lte(self, column, value):
        self._rows = [r for r in self._rows if str(r.get(column, ""))[:10] <= str(value)[:10]]
        return self

    def in_(self, column, values):
        vals = {str(v) for v in values}
        self._rows = [r for r in self._rows if column not in r or str(r.get(column)) in vals]
        return self

    def order(self, column, desc=False):
        self._rows = sorted(self._rows, key=lambda r: str(r.get(column, "")), reverse=desc)
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def upsert(self, rows, **_k):
        self._client.upserts.append((self._table, [dict(r) for r in rows]))
        return self

    def execute(self):
        self._client.reads.append(self._table)
        if self._range is None:
            return _Result(list(self._rows))
        start, end = self._range
        return _Result(self._rows[start:end + 1])


class _Client:
    def __init__(self, tables):
        self.tables = dict(tables)
        self.upserts = []
        self.reads = []

    def table(self, name):
        return _Query(self, name)


def _source_rows(days=DAYS):
    return [{"set_id": s, "snapshot_date": d, "value_scope": scope,
             "set_value": 100.0, "priced_card_count": 5}
            for d in days for s in COHORT for scope in ("standard", "top10")]


def _client(*, days=DAYS, index_dates=(), quality_rows=()):
    return _Client({
        SOURCE_TABLE: _source_rows(days),
        INDEX_TABLE: [{"market_date": d, "index_key": "raw"} for d in index_dates],
        QUALITY_TABLE: list(quality_rows),
    })


@pytest.fixture(autouse=True)
def _service_evidence(monkeypatch):
    """Aug 19/20 fully qualified; Aug 17/18 not (the production shape)."""
    monkeypatch.setattr(cli, "resolve_market_entry_dates_for_client",
                        lambda _c: {set_id: DAYS[0] for set_id in COHORT})
    monkeypatch.setattr(cli, "cohort_set_ids_for_date",
                        lambda _c, _d, **_k: list(COHORT))
    monkeypatch.setattr(cli, "valuation_set_ids_for_date",
                        lambda _c, _d, _s: {"standard": set(COHORT), "top10": set(COHORT)})
    monkeypatch.setattr(cli, "qualifying_set_ids_for_date",
                        lambda _c, day: set(COHORT) if day >= "2026-08-19" else set())


def _args(**kw):
    base = {"market_date": None, "all_history": False, "from_date": None,
            "to_date": None, "dry_run": True, "commit": False, "json": False}
    base.update(kw)
    return type("Args", (), base)()


# --------------------------------------------------------------------------- #
# Modes
# --------------------------------------------------------------------------- #

def test_dry_run_writes_nothing():
    client = _client()
    code, report = cli.run(client, _args(all_history=True))
    assert code == cli.EXIT_OK
    assert report["wrote"] is False
    assert report["rowsPersisted"] == 0
    assert client.upserts == []


def test_commit_persists_through_the_canonical_service(monkeypatch):
    persisted = []
    monkeypatch.setattr(cli, "persist_market_date_quality",
                        lambda _c, ev: persisted.append(ev) or 1)
    client = _client()
    code, report = cli.run(client, _args(all_history=True, commit=True))
    assert code == cli.EXIT_OK
    assert report["wrote"] is True
    assert report["rowsPersisted"] == len(DAYS)
    assert [p["marketDate"] for p in persisted] == DAYS


def test_commit_upserts_only_the_quality_table():
    client = _client()
    cli.run(client, _args(all_history=True, commit=True))
    assert {t for t, _ in client.upserts} == {QUALITY_TABLE}


def test_single_date_mode():
    client = _client(index_dates=DAYS,
                     quality_rows=[{"market_date": d, "status": STATUS_READY,
                                    "contract_version": MARKET_QUALITY_CONTRACT_VERSION}
                                   for d in DAYS])
    code, report = cli.run(client, _args(market_date="2026-08-20"))
    assert code == cli.EXIT_OK
    assert [r["market_date"] for r in report["dates"]] == ["2026-08-20"]


def test_full_history_mode_covers_every_source_date():
    code, report = cli.run(_client(), _args(all_history=True))
    assert code == cli.EXIT_OK
    assert [r["market_date"] for r in report["dates"]] == DAYS
    assert report["summary"]["totalDates"] == len(DAYS)


def test_explicit_range_mode():
    code, report = cli.run(_client(), _args(from_date="2026-08-19", to_date="2026-08-20"))
    assert [r["market_date"] for r in report["dates"]] == ["2026-08-19", "2026-08-20"]


def test_unknown_market_date_fails():
    code, report = cli.run(_client(), _args(market_date="2030-01-01"))
    assert code == cli.EXIT_FAILED
    assert "error" in report


# --------------------------------------------------------------------------- #
# Historical safety - the rollout hazard
# --------------------------------------------------------------------------- #

def test_partial_run_over_uncovered_history_fails_closed():
    """Materializing only Aug 20 while Apr-Aug history has no verdict is unsafe."""
    client = _client(index_dates=["2026-04-23", "2026-05-01"] + DAYS)
    code, report = cli.run(client, _args(market_date="2026-08-20", commit=True))
    assert code == cli.EXIT_UNSAFE_PARTIAL
    assert report["status"] == "refused_unsafe_partial"
    assert report["wrote"] is False
    assert client.upserts == [], "an unsafe run must write nothing"
    assert "2026-04-23" in report["uncoveredHistoryDates"]
    assert "--all-history" in report["coverage"]


def test_partial_run_is_safe_when_history_is_already_covered():
    covered = ["2026-04-23"] + DAYS
    client = _client(index_dates=covered,
                     quality_rows=[{"market_date": d, "status": STATUS_READY,
                                    "contract_version": MARKET_QUALITY_CONTRACT_VERSION}
                                   for d in covered])
    code, report = cli.run(client, _args(market_date="2026-08-20"))
    assert code == cli.EXIT_OK
    assert report["status"] == "dry_run"


def test_full_history_run_is_always_safe():
    client = _client(index_dates=["2026-04-23"] + DAYS)
    code, report = cli.run(client, _args(all_history=True, commit=True))
    assert code == cli.EXIT_OK
    assert report["wrote"] is True


def test_full_history_preserves_existing_index_coverage():
    """Every persisted index date ends up with a verdict."""
    client = _client(index_dates=DAYS)
    _, report = cli.run(client, _args(all_history=True))
    evaluated = {r["market_date"] for r in report["dates"]}
    assert set(DAYS).issubset(evaluated)


def test_first_run_with_no_index_history_is_safe():
    code, _ = cli.run(_client(index_dates=[]), _args(market_date="2026-08-20"))
    assert code == cli.EXIT_OK


# --------------------------------------------------------------------------- #
# Statuses are service-computed
# --------------------------------------------------------------------------- #

def test_statuses_are_computed_never_caller_supplied():
    _, report = cli.run(_client(), _args(all_history=True))
    by_date = {r["market_date"]: r for r in report["dates"]}
    assert by_date["2026-08-19"]["status"] == STATUS_READY
    assert by_date["2026-08-20"]["status"] == STATUS_READY
    assert by_date["2026-08-18"]["status"] == STATUS_DEGRADED
    assert by_date["2026-08-17"]["status"] == STATUS_LEGACY_VERIFIED


def test_degraded_requires_a_later_accepted_date():
    """Without Aug 19/20, Aug 18 is still recoverable, not terminal."""
    client = _client(days=["2026-08-17", "2026-08-18"])
    _, report = cli.run(client, _args(all_history=True))
    by_date = {r["market_date"]: r for r in report["dates"]}
    assert by_date["2026-08-18"]["status"] != STATUS_DEGRADED


def test_report_rows_carry_the_required_fields():
    _, report = cli.run(_client(), _args(all_history=True))
    for row in report["dates"]:
        for field in ("market_date", "status", "qualifying_count",
                      "expected_count", "accepted", "reason"):
            assert field in row, field


def test_bulk_summary_counts():
    _, report = cli.run(_client(), _args(all_history=True))
    s = report["summary"]
    assert s["totalDates"] == 4
    assert s["readyCount"] == 2
    assert s["legacyVerifiedCount"] == 1
    assert s["degradedCount"] == 1
    assert s["otherCount"] == 0
    assert s["acceptedTotal"] == 3
    assert s["lastAccepted"] == "2026-08-20"


# --------------------------------------------------------------------------- #
# Architecture guarantees
# --------------------------------------------------------------------------- #

def test_no_force_publish_flag_exists():
    parser = cli.build_parser()
    flags = {opt for action in parser._actions for opt in action.option_strings}
    assert "--force-publish" not in flags
    assert not any("force" in f for f in flags)


def test_scrape_batch_gate_is_irrelevant_to_the_cli():
    client = _client()
    cli.run(client, _args(all_history=True, commit=True))
    assert "pokemon_scrape_batches" not in client.reads


def test_cli_does_not_duplicate_quality_calculation():
    import inspect
    source = inspect.getsource(cli)
    assert "classify_market_date(" in source
    assert "persist_market_date_quality(" in source
    # No second definition of acceptance or of the status vocabulary.
    assert "def classify_market_date" not in source
    assert '"READY"' not in source


def test_cli_publishes_no_market_artifacts():
    client = _client()
    cli.run(client, _args(all_history=True, commit=True))
    written = {t for t, _ in client.upserts}
    for artifact in (INDEX_TABLE, "pokemon_explore_set_value_snapshot_latest",
                     "pokemon_set_market_dashboard_snapshot_latest"):
        assert artifact not in written


# --------------------------------------------------------------------------- #
# Pagination
# --------------------------------------------------------------------------- #

def test_source_date_read_paginates_beyond_one_page():
    many = [f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(300)]
    client = _client(days=many)
    assert len(client.tables[SOURCE_TABLE]) > cli.PAGE_SIZE
    assert len(cli.all_market_source_dates(client)) == len(set(many))


def test_quality_and_index_coverage_reads_paginate():
    # >PAGE_SIZE rows in BOTH the index and quality tables.
    many = [f"20{26 + i // 336:02d}-{1 + (i // 28) % 12:02d}-{1 + i % 28:02d}"
            for i in range(1200)]
    client = _Client({
        SOURCE_TABLE: _source_rows(["2026-08-20"]),
        INDEX_TABLE: [{"market_date": d, "index_key": k}
                      for d in many for k in ("raw", "top10")],
        QUALITY_TABLE: [{"market_date": d, "status": STATUS_READY,
                         "contract_version": MARKET_QUALITY_CONTRACT_VERSION}
                        for d in many],
    })
    assert len(client.tables[INDEX_TABLE]) > cli.PAGE_SIZE
    assert len(cli.persisted_index_dates(client)) == len(set(many))
    assert len(cli.already_covered_dates(client)) == len(set(many))
