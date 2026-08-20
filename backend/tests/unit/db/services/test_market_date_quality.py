import inspect

from backend.db.services import market_date_quality as mdq
from backend.db.services.market_date_quality import (
    MARKET_QUALITY_ENFORCEMENT_START,
    STATUS_DEGRADED,
    STATUS_INCOMPLETE,
    STATUS_LEGACY_VERIFIED,
    STATUS_READY,
    classify_market_date,
)

COHORT = {"a", "b", "c"}


def _classify(**overrides):
    kwargs = {
        "market_date": "2026-08-19",
        "cohort_set_ids": COHORT,
        "qualifying_set_ids": set(COHORT),
        "valuation_set_ids": {"standard": set(COHORT), "top10": set(COHORT)},
        "has_later_accepted_date": False,
        "legacy_allowlist": frozenset(),
    }
    kwargs.update(overrides)
    return classify_market_date(**kwargs)


def test_full_cohort_with_valuation_is_ready():
    result = _classify()
    assert result["status"] == STATUS_READY
    assert result["missingSetIds"] == []


def test_missing_qualifying_run_on_current_date_is_incomplete():
    result = _classify(qualifying_set_ids={"a", "b"})
    assert result["status"] == STATUS_INCOMPLETE
    assert result["missingSetIds"] == ["c"]


def test_missing_qualifying_run_with_a_later_accepted_date_is_degraded():
    result = _classify(qualifying_set_ids={"a", "b"}, has_later_accepted_date=True)
    assert result["status"] == STATUS_DEGRADED


def test_missing_valuation_input_blocks_ready():
    result = _classify(valuation_set_ids={"standard": COHORT, "top10": {"a", "b"}})
    assert result["status"] == STATUS_INCOMPLETE


def test_post_enforcement_date_is_never_legacy_verified():
    # Blocker 4 / spec: incomplete telemetry after the cutoff must NOT be
    # laundered into LEGACY_VERIFIED, even if the operator allowlists it.
    result = _classify(market_date="2026-08-19", qualifying_set_ids=set(),
                       legacy_allowlist=frozenset({"2026-08-19"}))
    assert result["status"] != STATUS_LEGACY_VERIFIED


def test_pre_enforcement_allowlisted_date_is_legacy_verified():
    result = _classify(market_date="2026-08-17", qualifying_set_ids=set(),
                       legacy_allowlist=frozenset({"2026-08-17"}))
    assert result["status"] == STATUS_LEGACY_VERIFIED


def test_pre_enforcement_date_not_allowlisted_is_not_legacy_verified():
    result = _classify(market_date="2026-08-17", qualifying_set_ids=set(),
                       has_later_accepted_date=True)
    assert result["status"] == STATUS_DEGRADED


def test_enforcement_cutoff_is_frozen():
    assert MARKET_QUALITY_ENFORCEMENT_START == "2026-08-18"


class _PagingResult:
    def __init__(self, data):
        self.data = data


class _PagingQuery:
    def __init__(self, rows, calls):
        self._rows, self._calls = rows, calls
        self._range = None

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def lte(self, *_a, **_k):
        return self

    def in_(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def range(self, start, end):
        self._range = (start, end)
        self._calls.append((start, end))
        return self

    def execute(self):
        start, end = self._range
        return _PagingResult(self._rows[start:end + 1])


class _PagingClient:
    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def table(self, _name):
        return _PagingQuery(self.rows, self.calls)


def test_quality_history_read_paginates_beyond_one_page():
    total = mdq.PAGE_SIZE + 250
    rows = [{"market_date": "2020-01-01", "status": mdq.STATUS_READY, "n": i}
            for i in range(total)]
    client = _PagingClient(rows)

    result = mdq.read_market_date_quality_history(client)

    assert len(result) == total, "an unpaginated read would truncate at PAGE_SIZE"
    assert client.calls[0] == (0, mdq.PAGE_SIZE - 1)
    assert client.calls[1] == (mdq.PAGE_SIZE, 2 * mdq.PAGE_SIZE - 1)
    assert len(client.calls) >= 2


def test_quality_history_read_source_uses_bounded_range():
    source = inspect.getsource(mdq._paged)
    assert ".range(" in source, "quality history reads must request bounded pages"


def test_accepted_dates_exclude_degraded_and_incomplete():
    client = _PagingClient([
        {"market_date": "2026-08-17", "status": mdq.STATUS_LEGACY_VERIFIED},
        {"market_date": "2026-08-18", "status": mdq.STATUS_DEGRADED},
        {"market_date": "2026-08-19", "status": mdq.STATUS_READY},
    ])
    assert mdq.accepted_market_dates(client) == {"2026-08-17", "2026-08-19"}
    assert mdq.resolve_latest_accepted_market_date(client) == "2026-08-19"


def test_case6_aug19_chains_directly_off_aug17():
    """Case 6, restated at the quality+math seam."""
    from backend.db.services.pokemon_market_index_service import build_index_rows

    sets = [{"id": "s", "canonical_key": "s", "release_date": "2020-01-01"}]

    def source(aug18):
        return [{"set_id": "s", "snapshot_date": day, "set_value": value,
                 "priced_card_count": 3, "value_scope": scope, "source": "t",
                 "updated_at": f"{day}T00:00:00Z"}
                for day, value in (("2026-08-17", 200.0), ("2026-08-18", aug18),
                                   ("2026-08-19", 240.0))
                for scope in ("standard", "top10")]

    accepted = {"2026-08-17", "2026-08-19"}
    low = build_index_rows(sets, source(1.0), accepted_dates=accepted)
    high = build_index_rows(sets, source(1_000_000.0), accepted_dates=accepted)

    def aug19(rows):
        return next(r for r in rows
                    if r["market_date"] == "2026-08-19" and r["index_key"] == "raw")

    assert aug19(low)["previous_market_date"] == "2026-08-17"
    assert aug19(low)["normalized_index_value"] == aug19(high)["normalized_index_value"]
    assert aug19(low)["normalized_index_value"] == 120.0  # 100 * 240/200


def test_case7_legacy_verified_date_participates_in_chain_and_backfill():
    from backend.db.services.market_date_quality import ACCEPTED_STATUSES
    assert STATUS_LEGACY_VERIFIED in ACCEPTED_STATUSES

    client = _PagingClient([
        {"market_date": "2026-08-16", "status": STATUS_LEGACY_VERIFIED},
        {"market_date": "2026-08-17", "status": STATUS_LEGACY_VERIFIED},
        {"market_date": "2026-08-18", "status": mdq.STATUS_DEGRADED},
    ])
    assert mdq.accepted_market_dates(client) == {"2026-08-16", "2026-08-17"}


def test_case8_missing_evidence_after_cutoff_is_never_laundered():
    for later, expected in ((False, STATUS_INCOMPLETE), (True, STATUS_DEGRADED)):
        result = _classify(market_date="2026-08-20", qualifying_set_ids=set(),
                           has_later_accepted_date=later,
                           legacy_allowlist=frozenset({"2026-08-20"}))
        assert result["status"] == expected
        assert result["status"] != STATUS_LEGACY_VERIFIED


def test_degraded_date_never_wins_latest_public_authority():
    client = _PagingClient([
        {"market_date": "2026-08-17", "status": STATUS_LEGACY_VERIFIED},
        {"market_date": "2026-08-18", "status": mdq.STATUS_DEGRADED},
        {"market_date": "2026-08-19", "status": STATUS_READY},
    ])
    assert mdq.resolve_latest_accepted_market_date(client) == "2026-08-19"


def test_latest_authority_falls_back_to_prior_good_date_when_current_is_blocked():
    client = _PagingClient([
        {"market_date": "2026-08-17", "status": STATUS_READY},
        {"market_date": "2026-08-18", "status": mdq.STATUS_DEGRADED},
    ])
    assert mdq.resolve_latest_accepted_market_date(client) == "2026-08-17"
