"""Quality-aware Market index READ path.

The build path already excludes unaccepted dates before chain math. These
cover the other half: a row that is still physically stored must not reach the
public view once quality has judged its date unacceptable.
"""

import pytest

from backend.db.services import pokemon_market_index_service as svc
from backend.db.services.market_date_quality import (
    MARKET_QUALITY_CONTRACT_VERSION,
    STATUS_DEGRADED,
    STATUS_INCOMPLETE,
    STATUS_LEGACY_VERIFIED,
    STATUS_READY,
)
from backend.db.services.pokemon_market_index_service import (
    read_index_history,
    read_raw_index_history_for_audit,
    resolve_accepted_market_dates,
)

INDEX_TABLE = "pokemon_market_index_daily_history"
QUALITY_TABLE = "pokemon_market_date_quality"

# The production incident, frozen as a fixture.
AUG_FIXTURE_QUALITY = [
    {"market_date": "2026-08-17", "status": STATUS_LEGACY_VERIFIED,
     "contract_version": MARKET_QUALITY_CONTRACT_VERSION},
    {"market_date": "2026-08-18", "status": STATUS_DEGRADED,
     "contract_version": MARKET_QUALITY_CONTRACT_VERSION},
    {"market_date": "2026-08-19", "status": STATUS_READY,
     "contract_version": MARKET_QUALITY_CONTRACT_VERSION},
    {"market_date": "2026-08-20", "status": STATUS_READY,
     "contract_version": MARKET_QUALITY_CONTRACT_VERSION},
]

AUG_FIXTURE_INDEX = [
    {"market_date": "2026-08-17", "index_key": "raw", "normalized_index_value": 101.94654697406233,
     "previous_market_date": "2026-08-16", "daily_return": -0.0023360739581663736},
    {"market_date": "2026-08-18", "index_key": "raw", "normalized_index_value": 101.92764516988373,
     "previous_market_date": "2026-08-17", "daily_return": -0.0001854089691081251},
    {"market_date": "2026-08-19", "index_key": "raw", "normalized_index_value": 101.35250127779067,
     "previous_market_date": "2026-08-17", "daily_return": -0.005827031065827160},
    {"market_date": "2026-08-20", "index_key": "raw", "normalized_index_value": 101.13703098287394,
     "previous_market_date": "2026-08-19", "daily_return": -0.0021259494556148395},
]


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

    def order(self, column, desc=False):
        self._rows = sorted(self._rows, key=lambda r: str(r.get(column, "")), reverse=desc)
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def execute(self):
        self._client.reads.append(self._table)
        if self._range is None:
            return _Result(list(self._rows))
        start, end = self._range
        return _Result(self._rows[start:end + 1])


class _Client:
    def __init__(self, index_rows, quality_rows):
        self.tables = {INDEX_TABLE: index_rows, QUALITY_TABLE: quality_rows}
        self.reads = []

    def table(self, name):
        return _Query(self, name)


def _aug_client(quality=None, index=None):
    return _Client(list(index if index is not None else AUG_FIXTURE_INDEX),
                   list(quality if quality is not None else AUG_FIXTURE_QUALITY))


def _dates(rows):
    return [str(r["market_date"])[:10] for r in rows]


# --------------------------------------------------------------------------- #
# The frozen Aug 17-20 scenario
# --------------------------------------------------------------------------- #

def test_public_read_serves_exactly_the_three_accepted_points():
    rows = read_index_history(_aug_client())
    assert _dates(rows) == ["2026-08-17", "2026-08-19", "2026-08-20"]


def test_aug18_never_appears_in_the_public_trend():
    rows = read_index_history(_aug_client())
    assert "2026-08-18" not in _dates(rows)


def test_degraded_row_remains_physically_stored():
    client = _aug_client()
    read_index_history(client)
    stored = _dates(client.tables[INDEX_TABLE])
    assert "2026-08-18" in stored, "the read path must filter the view, never the table"
    assert len(client.tables[INDEX_TABLE]) == len(AUG_FIXTURE_INDEX)


def test_audit_path_can_still_inspect_the_degraded_row():
    rows = read_raw_index_history_for_audit(_aug_client())
    assert _dates(rows) == ["2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20"]
    aug18 = next(r for r in rows if r["market_date"] == "2026-08-18")
    assert aug18["normalized_index_value"] == pytest.approx(101.92764516988373)


def test_legacy_verified_and_ready_are_both_retained():
    rows = read_index_history(_aug_client())
    by_date = {str(r["market_date"])[:10]: r for r in rows}
    assert "2026-08-17" in by_date, "LEGACY_VERIFIED must be retained"
    assert "2026-08-19" in by_date and "2026-08-20" in by_date, "READY must be retained"


def test_chain_fields_are_the_persisted_ones_from_the_accepted_rebuild():
    """The read path filters; it must never recompute or rewrite chain links."""
    by_date = {str(r["market_date"])[:10]: r for r in read_index_history(_aug_client())}
    assert by_date["2026-08-19"]["previous_market_date"] == "2026-08-17"
    assert by_date["2026-08-20"]["previous_market_date"] == "2026-08-19"
    assert by_date["2026-08-19"]["daily_return"] == pytest.approx(-0.005827031065827160)


def test_incomplete_dates_are_excluded_too():
    quality = [dict(r) for r in AUG_FIXTURE_QUALITY]
    quality[1]["status"] = STATUS_INCOMPLETE
    assert "2026-08-18" not in _dates(read_index_history(_aug_client(quality=quality)))


def test_unevaluated_date_is_excluded_once_enforcement_is_active():
    """A stored date with no quality row at all is withheld."""
    quality = [r for r in AUG_FIXTURE_QUALITY if r["market_date"] != "2026-08-18"]
    rows = read_index_history(_aug_client(quality=quality))
    assert _dates(rows) == ["2026-08-17", "2026-08-19", "2026-08-20"]


# --------------------------------------------------------------------------- #
# Enforcement activation + performance
# --------------------------------------------------------------------------- #

def test_no_quality_rows_means_enforcement_is_not_active():
    """Never blank the whole chart just because quality was never materialized."""
    client = _aug_client(quality=[])
    assert resolve_accepted_market_dates(client) is None
    assert _dates(read_index_history(client)) == [
        "2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20"]


def test_quality_authority_is_read_once_not_per_history_row():
    client = _aug_client()
    read_index_history(client)
    quality_reads = [t for t in client.reads if t == QUALITY_TABLE]
    assert len(quality_reads) == 1, f"N+1 quality lookup: {len(quality_reads)} reads"


def test_caller_supplied_accepted_dates_skip_the_quality_read():
    client = _aug_client()
    rows = read_index_history(client, accepted_dates={"2026-08-19", "2026-08-20"})
    assert _dates(rows) == ["2026-08-19", "2026-08-20"]
    assert QUALITY_TABLE not in client.reads


def test_accepted_dates_read_paginates_beyond_one_page():
    from backend.db.services import market_date_quality as mdq

    total = mdq.PAGE_SIZE + 130
    quality = [{"market_date": f"2020-01-01", "status": STATUS_READY,
                "contract_version": MARKET_QUALITY_CONTRACT_VERSION, "n": i}
               for i in range(total)]
    client = _aug_client(quality=quality)
    accepted = resolve_accepted_market_dates(client)
    assert accepted == {"2020-01-01"}
    assert len([t for t in client.reads if t == QUALITY_TABLE]) >= 2, (
        "quality history must be read with bounded pagination")


def test_index_history_read_paginates_beyond_one_page():
    total = svc.PAGE_SIZE + 40
    index = [{"market_date": "2026-08-20", "index_key": "raw", "n": i} for i in range(total)]
    client = _aug_client(index=index)
    rows = read_raw_index_history_for_audit(client)
    assert len(rows) == total


def test_read_and_build_share_one_acceptance_definition():
    """Guard against a second hardcoded READY/LEGACY_VERIFIED list."""
    import inspect
    from backend.db.services.market_date_quality import ACCEPTED_STATUSES

    source = inspect.getsource(svc.resolve_accepted_market_dates)
    assert "ACCEPTED_STATUSES" in source
    assert '"READY"' not in source and "'READY'" not in source
    assert '"LEGACY_VERIFIED"' not in source and "'LEGACY_VERIFIED'" not in source
    assert ACCEPTED_STATUSES == frozenset({STATUS_READY, STATUS_LEGACY_VERIFIED})
