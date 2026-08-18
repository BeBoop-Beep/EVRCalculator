from backend.scripts.build_pokemon_explore_set_value_snapshot import _load_canonical_histories


def test_standard_histories_are_stably_paged_across_tied_date_boundary():
    rows = [{"set_id": f"set-{index:04d}", "snapshot_date": "2026-01-01", "set_value": index + 1}
            for index in range(1002)]
    class Result:
        def __init__(self, data): self.data = data
    class Query:
        def __init__(self): self.orders = []; self.bounds = (0, len(rows) - 1)
        def select(self, *_a): return self
        def in_(self, *_a): return self
        def eq(self, *_a): return self
        def order(self, column, desc=False): self.orders.append((column, desc)); return self
        def range(self, start, end): self.bounds = (start, end); return self
        def execute(self):
            ordered = sorted(rows, key=lambda row: tuple(row[column] for column, _ in self.orders))
            return Result(ordered[self.bounds[0]:self.bounds[1] + 1])
    class Client:
        def __init__(self): self.queries = []
        def table(self, _name): query = Query(); self.queries.append(query); return query
    client = Client(); grouped = _load_canonical_histories(client, [row["set_id"] for row in rows])
    loaded = [item for values in grouped.values() for item in values]
    identities = [(row["snapshot_date"], row["set_id"]) for row in loaded]
    assert len(identities) == 1002 == len(set(identities))
    assert all(query.orders == [("snapshot_date", False), ("set_id", False)] for query in client.queries)
