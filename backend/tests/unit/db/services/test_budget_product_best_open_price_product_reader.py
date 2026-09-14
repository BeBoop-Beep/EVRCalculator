from backend.db.services import budget_product_best_open_price_service as service


class Result:
    def __init__(self, data):
        self.data = data


class Query:
    def __init__(self, rows):
        self.rows = [dict(row) for row in rows]

    def select(self, *_args):
        return self

    def eq(self, key, value):
        self.rows = [row for row in self.rows if str(row.get(key)) == str(value)]
        return self

    def limit(self, n):
        self.rows = self.rows[:n]
        return self

    def execute(self):
        return Result(self.rows)


class Client:
    def __init__(self, tables):
        self.tables = tables
        self.reads = []

    def table(self, name):
        self.reads.append(name)
        return Query(self.tables.get(name, []))


def tables():
    source = {
        "id": "budget-1",
        "published_at": "2026-09-14T12:00:00+00:00",
        "market_date": "2026-09-14",
        "cohort_fingerprint": "cohort-fp",
    }
    snapshot = {
        "id": "bop-1",
        "built_at": "2026-09-14T13:00:00+00:00",
        "published_at": "2026-09-14T13:01:00+00:00",
        "best_open_price_method_version": service.BEST_OPEN_PRICE_METHOD_VERSION,
        "ranking_method_version": "rank-v1",
        "allocation_method_version": "alloc-v1",
        "source_budget_snapshot_id": "budget-1",
        "source_budget_published_at": source["published_at"],
        "source_market_date": source["market_date"],
        "source_cohort_fingerprint": source["cohort_fingerprint"],
        "source_full_market_budget": 1350,
        "source_eligible_cohort_count": 138,
        "resolved_count": 138,
        "unresolved_count": 0,
    }
    return {
        "budget_product_best_open_price_latest": [{
            "best_open_price_method_version": service.BEST_OPEN_PRICE_METHOD_VERSION,
            "snapshot_id": "bop-1",
        }],
        "budget_product_best_open_price_snapshots": [snapshot],
        "budget_product_ranking_latest": [{
            "ranking_method_version": "rank-v1",
            "allocation_method_version": "alloc-v1",
            "snapshot_id": "budget-1",
        }],
        "budget_product_ranking_snapshots": [source],
        "budget_product_best_open_price_rows": [{
            "snapshot_id": "bop-1",
            "sealed_product_id": "p1",
            "current_market_price": 14.57,
            "current_budget_rank": 2,
            "status": "resolved_below_market",
            "best_open_price": 13.23,
            "threshold_quantity": 102,
            "price_gap_dollars": 1.34,
            "price_gap_percent": 0.09197,
        }],
    }


def test_product_reader_transfers_one_row_not_full_138_row_cohort():
    client = Client(tables())
    result = service.load_best_open_price_product(client, "p1")

    assert result["available"] is True
    assert result["sourceBudgetSnapshotId"] == "budget-1"
    assert result["sourceMarketDate"] == "2026-09-14"
    assert result["sourceEligibleCohortCount"] == 138
    assert result["row"]["sealed_product_id"] == "p1"
    assert result["row"]["best_open_price"] == 13.23
    # Exactly one query to the row store, scoped by snapshot + product + limit.
    assert client.reads.count("budget_product_best_open_price_rows") == 1


def test_product_reader_refuses_source_replacement_under_same_method():
    data = tables()
    data["budget_product_ranking_snapshots"][0]["published_at"] = "2026-09-14T14:00:00+00:00"
    result = service.load_best_open_price_product(Client(data), "p1")
    assert result == {"available": False, "reason": "stale_source_publication", "row": None}


def test_product_reader_refuses_incomplete_publication_before_row_read():
    data = tables()
    data["budget_product_best_open_price_snapshots"][0]["resolved_count"] = 137
    client = Client(data)
    result = service.load_best_open_price_product(client, "p1")
    assert result == {"available": False, "reason": "incomplete_snapshot_rows", "row": None}
    assert "budget_product_best_open_price_rows" not in client.reads


def test_product_reader_reports_product_outside_current_full_market():
    result = service.load_best_open_price_product(Client(tables()), "not-in-cohort")
    assert result == {"available": False, "reason": "product_not_in_current_full_market", "row": None}
