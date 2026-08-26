import pytest

from backend.db.services.pokemon_market_index_service import (
    _paged_source_rows, build_index_rows, build_market_overview, read_index_history,
    resolve_market_entry_dates)


SETS = [
    {"id": "a", "canonical_key": "a", "release_date": "2026-01-01"},
    {"id": "b", "canonical_key": "b", "release_date": "2026-01-01"},
    {"id": "c", "canonical_key": "c", "release_date": "2026-01-02"},
]


def source(day, set_id, scope, value, count):
    return {"snapshot_date": day, "set_id": set_id, "value_scope": scope, "set_value": value,
            "priced_card_count": count, "source": "canonical", "updated_at": day}


def test_joint_market_entry_keeps_raw_and_top10_cohorts_aligned():
    rows = []
    for scope, values, count in (("standard", {"a": 100, "b": 100}, 20), ("top10", {"a": 60, "b": 60}, 10)):
        rows += [source("2026-01-01", key, scope, value, count) for key, value in values.items()]
    # C is not jointly ready on day two, so it enters neither index yet.
    for scope, values, count in (("standard", {"a": 110, "b": 110, "c": 500}, 20), ("top10", {"a": 66, "b": 66}, 10)):
        rows += [source("2026-01-02", key, scope, value, count) for key, value in values.items()]
    built = build_index_rows(SETS, rows)
    raw = [row for row in built if row["index_key"] == "raw"]
    chase = [row for row in built if row["index_key"] == "top10"]
    assert [row["market_date"] for row in raw] == ["2026-01-01", "2026-01-02"]
    assert raw[-1]["normalized_index_value"] == pytest.approx(110)
    assert raw[-1]["basket_value"] == 220
    assert [row["market_date"] for row in chase] == ["2026-01-01", "2026-01-02"]


@pytest.mark.parametrize("release_date,entry_date,blackout_start", [
    ("2026-05-22", "2026-06-16", "2026-05-22"),
    ("2026-07-17", "2026-08-01", "2026-07-17"),
])
def test_unvalued_released_set_does_not_black_out_existing_market(
    release_date, entry_date, blackout_start,
):
    sets = [{"id": "old", "canonical_key": "old", "release_date": "2020-01-01"},
            {"id": "new", "canonical_key": "new", "release_date": release_date}]
    prior = blackout_start
    rows = []
    for day, old_value in ((prior, 100), (entry_date, 110)):
        for scope, multiplier, count in (("standard", 1, 20), ("top10", .6, 10)):
            rows.append(source(day, "old", scope, old_value * multiplier, count))
    for scope, multiplier, count in (("standard", 1, 20), ("top10", .6, 10)):
        rows.append(source(entry_date, "new", scope, 500 * multiplier, count))
    built = build_index_rows(sets, rows)
    for key in ("raw", "top10"):
        family = [row for row in built if row["index_key"] == key]
        assert [row["market_date"] for row in family] == [prior, entry_date]
        assert family[-1]["set_count"] == 2
        assert family[-1]["normalized_index_value"] == pytest.approx(110)
        assert family[-1]["diagnostics_json"]["commonSetIds"] == ["old"]


def test_market_entry_date_requires_both_scopes_and_release():
    sets = [{"id": "s", "release_date": "2026-05-22"}]
    rows = [source("2026-05-20", "s", "standard", 100, 20),
            source("2026-06-16", "s", "top10", 60, 10)]
    assert resolve_market_entry_dates(sets, rows) == {"s": "2026-06-16"}


def test_input_order_does_not_change_source_fingerprints():
    rows = [source("2026-01-01", "a", "standard", 100, 20), source("2026-01-01", "b", "standard", 100, 20),
            source("2026-01-01", "a", "top10", 60, 10), source("2026-01-01", "b", "top10", 60, 10)]
    forward = build_index_rows(SETS[:2], rows)
    reverse = build_index_rows(list(reversed(SETS[:2])), list(reversed(rows)))
    assert [(r["index_key"], r["source_generation_fingerprint"]) for r in forward] == [(r["index_key"], r["source_generation_fingerprint"]) for r in reverse]


def test_paged_source_rows_has_total_order_across_tied_date_boundary():
    rows = [source("2026-01-01", f"set-{index:04d}", scope, index + 1, 10)
            for index in range(501) for scope in ("standard", "top10")]
    class Result:
        def __init__(self, data): self.data = data
    class Query:
        def __init__(self): self.orders = []; self.bounds = (0, len(rows) - 1)
        def select(self, *_a): return self
        def in_(self, *_a): return self
        def order(self, column, desc=False): self.orders.append((column, desc)); return self
        def range(self, start, end): self.bounds = (start, end); return self
        def execute(self):
            ordered = sorted(rows, key=lambda row: tuple(row[column] for column, _ in self.orders))
            return Result(ordered[self.bounds[0]:self.bounds[1] + 1])
    class Client:
        def __init__(self): self.queries = []
        def table(self, _name): query = Query(); self.queries.append(query); return query
    client = Client(); loaded = _paged_source_rows(client, [row["set_id"] for row in rows])
    identities = [(row["snapshot_date"], row["set_id"], row["value_scope"]) for row in loaded]
    assert len(identities) == 1002 == len(set(identities))
    assert all(query.orders == [("snapshot_date", False), ("set_id", False), ("value_scope", False)] for query in client.queries)


def test_read_index_history_has_total_order_across_tied_market_date_boundary():
    rows = [{"market_date": "2025-01-01", "index_key": "raw", "row": 0}]
    rows += [{"market_date": f"2026-{1 + day // 28:02d}-{1 + day % 28:02d}", "index_key": key, "row": 1 + day * 2 + offset}
             for day in range(501) for offset, key in enumerate(("raw", "top10"))]
    class Result:
        def __init__(self, data): self.data = data
    class Query:
        def __init__(self): self.orders = []; self.bounds = (0, len(rows) - 1)
        def select(self, *_a): return self
        def eq(self, *_a): return self
        def lte(self, *_a): return self
        def order(self, column, desc=False): self.orders.append((column, desc)); return self
        def range(self, start, end): self.bounds = (start, end); return self
        def execute(self):
            ordered = sorted(rows, key=lambda row: tuple(row[column] for column, _ in self.orders))
            return Result(ordered[self.bounds[0]:self.bounds[1] + 1])
    class EmptyQuery:
        def select(self, *_a): return self
        def eq(self, *_a): return self
        def lte(self, *_a): return self
        def order(self, *_a, **_k): return self
        def range(self, *_a): return self
        def execute(self): return Result([])
    class Client:
        def __init__(self): self.query = Query()
        # Only the index table serves index rows; the Market Date Quality
        # authority is empty here, so this exercises the unfiltered read.
        def table(self, name):
            return self.query if name == "pokemon_market_index_daily_history" else EmptyQuery()
    client = Client(); loaded = read_index_history(client)
    identities = [(row["market_date"], row["index_key"], row["row"]) for row in loaded]
    assert len(identities) == 1003 == len(set(identities))
    assert len({(day, key) for day, key, _ in identities}) == 1003
    assert client.query.orders == [("market_date", False), ("index_key", False)]


# ---------------------------------------------------------------------------
# Tracked Value vs. Price Performance.
#
# `changes` (chain-linked price performance) and `basketChanges` (literal
# tracked-basket dollars) answer different questions and MUST be able to
# disagree. These tests pin the divergence, and pin that neither figure can be
# contaminated by the other's underlying column.
# ---------------------------------------------------------------------------

COHORT_SETS = [
    {"id": "a", "canonical_key": "a", "release_date": "2026-01-01"},
    {"id": "b", "canonical_key": "b", "release_date": "2026-01-02"},
]


def cohort_history():
    """A enters day one; B enters day two; both appreciate 10% on day three."""
    rows = []
    for day, values in (
        ("2026-01-01", {"a": 100}),
        ("2026-01-02", {"a": 100, "b": 50}),
        ("2026-01-03", {"a": 110, "b": 55}),
    ):
        for set_id, value in values.items():
            rows.append(source(day, set_id, "standard", value, 20))
            # top10 mirrors the cohort at a smaller basket so the overview's
            # raw/chase agreement guards are satisfied.
            rows.append(source(day, set_id, "top10", value * 0.6, 10))
    return build_index_rows(COHORT_SETS, rows)


def test_new_set_entry_moves_tracked_value_but_not_the_price_index():
    overview = build_market_overview(cohort_history(), market_date="2026-01-02")
    raw = overview["raw"]

    # Day 1 -> Day 2: the basket grew purely because B joined the universe.
    assert raw["basketValue"] == pytest.approx(150)
    assert raw["basketChanges"]["1D"]["percent"] == pytest.approx(50.0)
    # ...and the chain-linked index is flat, because A did not move.
    assert raw["indexValue"] == pytest.approx(100.0)
    assert raw["changes"]["1D"]["percent"] == pytest.approx(0.0)


def test_a_newly_entered_set_does_affect_the_index_once_it_moves():
    overview = build_market_overview(cohort_history(), market_date="2026-01-03")
    raw = overview["raw"]

    # Day 3: the common cohort is now {A, B} and it appreciated 10%.
    assert raw["indexValue"] == pytest.approx(110.0)
    assert raw["changes"]["SinceTracking"]["percent"] == pytest.approx(10.0)
    # The tracked basket grew 65%: 10% of price performance plus B's arrival.
    assert raw["basketValue"] == pytest.approx(165)
    assert raw["basketChanges"]["SinceTracking"]["percent"] == pytest.approx(65.0)
    # The whole point of publishing both: they are not the same number.
    assert raw["changes"]["SinceTracking"]["percent"] != pytest.approx(
        raw["basketChanges"]["SinceTracking"]["percent"]
    )


def test_since_tracking_basket_change_is_latest_over_first_basket():
    history = cohort_history()
    overview = build_market_overview(history, market_date="2026-01-03")
    raw_rows = [row for row in history if row["index_key"] == "raw"]
    first, latest = float(raw_rows[0]["basket_value"]), float(raw_rows[-1]["basket_value"])

    since = overview["raw"]["basketChanges"]["SinceTracking"]
    assert since["percent"] == pytest.approx((latest / first - 1.0) * 100.0)
    assert since["startDate"] == raw_rows[0]["market_date"]
    assert since["endDate"] == raw_rows[-1]["market_date"]


def test_the_two_dimensions_read_disjoint_columns():
    history = cohort_history()
    baseline = build_market_overview(history, market_date="2026-01-03")

    # Perturbing basket_value must move ONLY basketChanges.
    basket_tampered = [dict(row) for row in history]
    for row in basket_tampered:
        if row["market_date"] == "2026-01-01":
            row["basket_value"] = float(row["basket_value"]) / 2
    tampered = build_market_overview(basket_tampered, market_date="2026-01-03")
    assert tampered["raw"]["changes"] == baseline["raw"]["changes"]
    assert tampered["raw"]["indexValue"] == baseline["raw"]["indexValue"]
    assert tampered["raw"]["trend"] == baseline["raw"]["trend"]
    assert tampered["raw"]["basketChanges"] != baseline["raw"]["basketChanges"]

    # Perturbing normalized_index_value must move ONLY changes.
    index_tampered = [dict(row) for row in history]
    for row in index_tampered:
        if row["market_date"] == "2026-01-01":
            row["normalized_index_value"] = float(row["normalized_index_value"]) / 2
    tampered = build_market_overview(index_tampered, market_date="2026-01-03")
    assert tampered["raw"]["basketChanges"] == baseline["raw"]["basketChanges"]
    assert tampered["raw"]["basketValue"] == baseline["raw"]["basketValue"]
    assert tampered["raw"]["changes"] != baseline["raw"]["changes"]


def test_insufficient_long_history_is_reported_as_partial_in_both_dimensions():
    overview = build_market_overview(cohort_history(), market_date="2026-01-03")
    for family in ("raw", "topChase"):
        basket_changes = overview[family]["basketChanges"]
        assert sorted(basket_changes) == sorted(overview[family]["changes"])
        # Three days of history cannot support a FULL 6M or 1Y in either
        # dimension. ONE partial policy now covers both: the window reports the
        # real span it has and flags itself "since first available", rather
        # than Tracked Value going dark while Price Performance reported a
        # fallback under the same label.
        for window in ("6M", "1Y"):
            for dimension in ("basketChanges", "changes", "familyChanges"):
                entry = overview[family][dimension][window]
                assert entry["available"] is True
                assert entry["coverage"] == "partial"
                assert entry["isSinceFirstAvailable"] is True
                assert entry["percent"] == overview[family][dimension]["SinceTracking"]["percent"]


def test_all_reconciles_with_the_published_index_level():
    """THE AUDIT ASSERTION for the user-facing All window.

    For a continuous base-100 series, movement from the tracking start IS the
    index level: 101.04 -> +1.04%, 95.01 -> -4.99%. This is asserted here and
    never computed in a presentation layer. It is what makes "Market Index
    105.87" sitting beside "ALL +3.76%" a test failure rather than a support
    ticket.
    """
    overview = build_market_overview(cohort_history(), market_date="2026-01-03")
    for family_key in ("raw", "topChase"):
        family = overview[family_key]
        since_tracking = family["familyChanges"]["SinceTracking"]
        assert since_tracking["available"] is True
        assert since_tracking["percent"] == pytest.approx(
            (family["indexValue"] / 100.0 - 1.0) * 100.0
        ), family_key
        # The shared-comparison series is NOT required to reconcile with the
        # index, which is precisely why it may not be labelled All.
        assert set(family["changes"]) == set(family["familyChanges"])


def test_the_payload_extension_is_additive_and_keeps_contract_v1():
    overview = build_market_overview(cohort_history(), market_date="2026-01-03")
    assert overview["contractVersion"] == "pokemon-market-overview-v1"
    # Every field an existing reader already consumes is still present.
    for family in ("raw", "topChase"):
        assert {"basketValue", "indexValue", "historyStartDate", "changes", "trend"} <= set(overview[family])
    assert overview["methodology"]["notMarketCapitalization"] is True
    assert overview["methodology"]["indexDefinition"] == "chain-linked return over consecutive common set cohorts"
    assert "cohort additions/removals" in overview["methodology"]["basketChangeDefinition"]
    assert "neutralized" in overview["methodology"]["pricePerformanceDefinition"]
