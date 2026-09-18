from datetime import date, timedelta

from backend.scripts.build_pokemon_explore_set_value_snapshot import _load_canonical_histories


def test_standard_histories_are_stably_paged_across_postgrest_row_cap():
    end = date(2026, 9, 18)
    first = end - timedelta(days=1001)
    rows = [
        {
            "set_id": "set-1",
            "snapshot_date": (first + timedelta(days=index)).isoformat(),
            "set_value": index + 1,
            "source": "canonical-standard",
        }
        for index in range(1002)
    ]

    class Result:
        def __init__(self, data):
            self.data = data

    class Query:
        def __init__(self):
            self.orders = []
            self.bounds = (0, len(rows) - 1)
            self.max_date = None
        def select(self, *_a): return self
        def in_(self, *_a): return self
        def eq(self, *_a): return self
        def lte(self, column, value):
            assert column == "snapshot_date"
            self.max_date = value
            return self
        def order(self, column, desc=False):
            self.orders.append((column, desc))
            return self
        def range(self, start, end):
            self.bounds = (start, end)
            return self
        def execute(self):
            filtered = [row for row in rows if self.max_date is None or row["snapshot_date"] <= self.max_date]
            ordered = sorted(filtered, key=lambda row: tuple(row[column] for column, _ in self.orders))
            return Result(ordered[self.bounds[0]:self.bounds[1] + 1])

    class Client:
        def __init__(self):
            self.queries = []
        def table(self, name):
            assert name == "pokemon_set_value_daily_history"
            query = Query()
            self.queries.append(query)
            return query

    client = Client()
    grouped = _load_canonical_histories(
        client,
        ["set-1"],
        through_date="2026-09-18",
    )

    loaded = grouped["set-1"]
    identities = [(row["snapshot_date"], row["set_id"]) for row in loaded]
    assert len(identities) == 1002 == len(set(identities))
    assert identities[0][0] == first.isoformat()
    assert identities[-1][0] == "2026-09-18"
    assert len(client.queries) == 2
    assert all(
        query.orders == [("snapshot_date", False), ("set_id", False)]
        for query in client.queries
    )
