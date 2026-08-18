import pytest

from backend.db.services.pokemon_market_index_service import _paged_source_rows, build_index_rows, read_index_history


SETS = [
    {"id": "a", "canonical_key": "a", "release_date": "2026-01-01"},
    {"id": "b", "canonical_key": "b", "release_date": "2026-01-01"},
    {"id": "c", "canonical_key": "c", "release_date": "2026-01-02"},
]


def source(day, set_id, scope, value, count):
    return {"snapshot_date": day, "set_id": set_id, "value_scope": scope, "set_value": value,
            "priced_card_count": count, "source": "canonical", "updated_at": day}


def test_release_gate_completeness_and_independent_top10_authority():
    rows = []
    for scope, values, count in (("standard", {"a": 100, "b": 100}, 20), ("top10", {"a": 60, "b": 60}, 10)):
        rows += [source("2026-01-01", key, scope, value, count) for key, value in values.items()]
    # C enters on day two. Standard is complete, but top10 intentionally lacks C,
    # so only raw may publish that date.
    for scope, values, count in (("standard", {"a": 110, "b": 110, "c": 500}, 20), ("top10", {"a": 66, "b": 66}, 10)):
        rows += [source("2026-01-02", key, scope, value, count) for key, value in values.items()]
    built = build_index_rows(SETS, rows)
    raw = [row for row in built if row["index_key"] == "raw"]
    chase = [row for row in built if row["index_key"] == "top10"]
    assert [row["market_date"] for row in raw] == ["2026-01-01", "2026-01-02"]
    assert raw[-1]["normalized_index_value"] == pytest.approx(110)
    assert raw[-1]["basket_value"] == 720
    assert [row["market_date"] for row in chase] == ["2026-01-01"]


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
    class Client:
        def __init__(self): self.query = Query()
        def table(self, _name): return self.query
    client = Client(); loaded = read_index_history(client)
    identities = [(row["market_date"], row["index_key"], row["row"]) for row in loaded]
    assert len(identities) == 1003 == len(set(identities))
    assert len({(day, key) for day, key, _ in identities}) == 1003
    assert client.query.orders == [("market_date", False), ("index_key", False)]
