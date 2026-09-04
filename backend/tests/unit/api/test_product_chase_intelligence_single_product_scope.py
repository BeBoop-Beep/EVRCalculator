"""Phase 12 perf fix: a single product-detail-page request must not resolve
the FULL global Chase Access cohort.

Before this fix, ``GET /explore/product-chase-intelligence`` always called
``resolve_product_chase_access`` with the ENTIRE pinned cohort (117 products /
18 sets in production), which batches 1 Accessibility read + 1 variant-universe
read PER DISTINCT SET in the cohort it is handed - i.e. 18 variant reads for
one product's page. This test asserts the new ``sealed_product_id`` scoping
param collapses that to exactly 1 Accessibility read + 1 variant-universe read
when a single product is requested, while an unscoped (ranking-context) call
still costs one read per distinct set.
"""

from __future__ import annotations

from collections import defaultdict

from backend.db.services.chase_accessibility_service import SNAPSHOT_TABLE, PULL_RATES_TABLE
from backend.desirability.chase_accessibility import CHASE_ACCESSIBILITY_VERSION


def _snapshot_row(set_id, run_id, accessibility=0.08, mass=0.995):
    return {
        "set_id": set_id, "calculation_run_id": run_id, "accessibility": accessibility,
        "chase_depth": 3.2, "mapped_hc_mass": mass, "status": "ready",
        "status_reason": None, "version": CHASE_ACCESSIBILITY_VERSION,
        "significance_version": "chase_significance_v1_squared_value_share",
        "depth_version": "chase_depth_v1_hc_effective_count",
    }


def _pull_rate_row(set_id, run_id, variant_id, price, probability, pull_count=5):
    return {
        "calculation_run_id": run_id, "set_id": set_id, "card_variant_id": variant_id,
        "price_used": price, "modeled_probability": probability,
        "effective_pull_rate": None if not probability else 1.0 / probability,
        "pull_count": pull_count, "pack_presence_count": pull_count, "simulation_count": 1000,
    }


def _cohort_row(sealed_product_id, set_id, run_id, price, random_pack_count):
    return {
        "sealed_product_id": sealed_product_id, "set_id": set_id,
        "calculation_run_id": run_id, "product_market_cost": price,
        "random_pack_count": random_pack_count, "product_name": "Product %s" % sealed_product_id,
        "product_family": "elite_trainer_box",
    }


class _Query:
    def __init__(self, table_name, rows, call_log):
        self._table = table_name
        self._rows = rows
        self._filters = []
        self._call_log = call_log

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self._filters.append(("eq", column, value))
        return self

    def gt(self, column, value):
        self._filters.append(("gt", column, value))
        return self

    def in_(self, column, values):
        self._filters.append(("in", column, set(values)))
        return self

    def order(self, *_a, **_k):
        return self

    def range(self, start, end):
        self._filters.append(("range", start, end))
        return self

    def execute(self):
        self._call_log[self._table] += 1
        rows = list(self._rows)
        for kind, *rest in self._filters:
            if kind == "eq":
                column, value = rest
                rows = [r for r in rows if r.get(column) == value]
            elif kind == "gt":
                column, value = rest
                rows = [r for r in rows if (r.get(column) or 0) > value]
            elif kind == "in":
                column, values = rest
                rows = [r for r in rows if r.get(column) in values]
            elif kind == "range":
                start, end = rest
                rows = rows[start:end + 1]
        return type("R", (), {"data": rows})()


class _FakeClient:
    def __init__(self, snapshot_rows, pull_rate_rows):
        self._tables = {SNAPSHOT_TABLE: snapshot_rows, PULL_RATES_TABLE: pull_rate_rows}
        self.call_log = defaultdict(int)

    def table(self, name):
        return _Query(name, self._tables.get(name, []), self.call_log)


def _four_product_three_set_fixture():
    """3 sets, 3 distinct runs, 4 products (set-1 has TWO products)."""
    snapshot_rows = [
        _snapshot_row("set-1", "run-1"),
        _snapshot_row("set-2", "run-2", accessibility=0.05),
        _snapshot_row("set-3", "run-3", accessibility=0.03),
    ]
    pull_rate_rows = [
        _pull_rate_row("set-1", "run-1", "v1", 1.0, 0.10),
        _pull_rate_row("set-1", "run-1", "v2", 2.0, 0.40),
        _pull_rate_row("set-2", "run-2", "v3", 5.0, 0.20),
        _pull_rate_row("set-3", "run-3", "v4", 10.0, 0.05),
    ]
    cohort = [
        _cohort_row("p1", "set-1", "run-1", price=12.0, random_pack_count=1),
        _cohort_row("p2", "set-1", "run-1", price=144.0, random_pack_count=36),
        _cohort_row("p3", "set-2", "run-2", price=42.0, random_pack_count=4),
        _cohort_row("p4", "set-3", "run-3", price=25.0, random_pack_count=3),
    ]
    return _FakeClient(snapshot_rows, pull_rate_rows), cohort


def _call_route(monkeypatch, *, sealed_product_id, cohort, client):
    from backend.api import main

    monkeypatch.setattr(main, "_require_product_chase_intelligence", lambda **_: "u1")
    monkeypatch.setattr(main, "_enforce_paid_abuse", lambda *_a, **_k: None)
    monkeypatch.setattr(main, "_resolve_index_plan", lambda *_a, **_k: "premium")
    monkeypatch.setattr(main, "load_pinned_cohort", lambda _client, price_as_of=None: (cohort, {}))
    monkeypatch.setattr(main, "service_read_client", client)

    request = type("Req", (), {"headers": {}, "client": None})()
    return main.get_product_chase_intelligence(
        request, budget=50.0, price_as_of=None, sealed_product_id=sealed_product_id,
        authorization="Bearer x", token_cookie=None,
    )


def test_single_product_scope_costs_exactly_one_accessibility_and_one_variant_read(monkeypatch):
    client, cohort = _four_product_three_set_fixture()
    response = _call_route(monkeypatch, sealed_product_id="p1", cohort=cohort, client=client)
    assert client.call_log[SNAPSHOT_TABLE] == 1
    assert client.call_log[PULL_RATES_TABLE] == 1

    import json
    body = json.loads(response.body)
    assert body["distinctSetCount"] == 1
    assert body["productCount"] == 1
    assert body["products"][0]["sealedProductId"] == "p1"
    # Ranking context is meaningless against a 1-product cohort - must not leak a fake "#1".
    assert body["products"][0]["oBudgetRank"] is None


def test_unscoped_call_still_costs_one_read_per_distinct_set_not_more(monkeypatch):
    client, cohort = _four_product_three_set_fixture()
    _call_route(monkeypatch, sealed_product_id=None, cohort=cohort, client=client)
    assert client.call_log[SNAPSHOT_TABLE] == 1
    assert client.call_log[PULL_RATES_TABLE] == 3


def test_unknown_sealed_product_id_returns_404_not_an_empty_ready_payload(monkeypatch):
    client, cohort = _four_product_three_set_fixture()
    response = _call_route(monkeypatch, sealed_product_id="does-not-exist", cohort=cohort, client=client)
    assert response.status_code == 404
    # No accessibility/variant reads should have been issued for a cohort miss.
    assert client.call_log[SNAPSHOT_TABLE] == 0
    assert client.call_log[PULL_RATES_TABLE] == 0
