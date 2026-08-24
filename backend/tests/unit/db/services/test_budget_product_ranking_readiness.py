from datetime import datetime
from types import SimpleNamespace

import pytest

from backend.db.services import budget_product_ranking_readiness as service
from backend.db.services.budget_product_ranking_authority import (
    EXPECTED_COLLECTOR_APPEAL_VERSION, EXPECTED_FINANCIAL_RIP_VERSION,
    EXPECTED_OVERALL_RIP_VERSION,
)


def _product(pid="p1", set_id="s1", run="r1", date="2026-08-22", **changes):
    row = {"sealed_product_id": pid, "set_id": set_id, "calculation_run_id": run,
           "product_family": "booster_box", "product_market_cost": 100, "price_as_of": date,
           "price_source": "tcgplayer", "pack_count": 36, "random_pack_count": 36,
           "accessory_value_included": False, "financial_rip_v4_status": "ready",
           "financial_rip_v4_rankable": True, "financial_rip_v4_score": 50,
           "financial_rip_v4_version": EXPECTED_FINANCIAL_RIP_VERSION,
           "overall_rip_v10_rankable": True, "overall_rip_v10_score": 51,
           "overall_rip_v10_version": EXPECTED_OVERALL_RIP_VERSION,
           "collector_appeal_score": 60, "collector_appeal_version": EXPECTED_COLLECTOR_APPEAL_VERSION}
    row.update(changes); return row


class Query:
    def __init__(self, client, table): self.client, self.name, self.rows = client, table, list(client.tables.get(table, []))
    def select(self, *_a, **_k): return self
    def in_(self, key, values): self.rows = [r for r in self.rows if r.get(key) in values]; return self
    def eq(self, key, value): self.rows = [r for r in self.rows if r.get(key) == value]; return self
    def order(self, key, desc=False): self.rows.sort(key=lambda r: r.get(key) or "", reverse=desc); return self
    def limit(self, n): self.rows = self.rows[:n]; return self
    @property
    def not_(self): return self
    def is_(self, key, _value): self.rows = [r for r in self.rows if r.get(key) is not None]; return self
    def execute(self): return SimpleNamespace(data=self.rows)


class Client:
    def __init__(self, products, raw=None): self.tables = {"simulation_sealed_product_results": raw or products}
    def table(self, name): return Query(self, name)


def _gate(monkeypatch, statuses=None):
    statuses = statuses or [SimpleNamespace(status="current", set_id="s1", calculation_run_id="r1")]
    monkeypatch.setattr(service, "evaluate_opening_simulation_freshness", lambda *_a, **_k: SimpleNamespace(ok=True, statuses=statuses, failures=[], error=None))
    monkeypatch.setattr(service, "load_pack_outcome_artifact_metadata", lambda *_a: {"ok": True})
    monkeypatch.setattr(service, "evaluate_publication_gate", lambda *_a, **_k: SimpleNamespace(allowed=True, reason=None, reason_code=None))


def test_complete_exact_run_authority_is_publish_eligible(monkeypatch):
    _gate(monkeypatch)
    result = service.resolve_budget_ranking_readiness(Client([_product()]), latest_snapshot={"pinned_price_as_of": "2026-08-21"}, promoted_market_date="2026-08-22")
    assert result.status == service.BudgetRankingStatus.PUBLISHED
    assert result.authority["productCount"] == 1


def test_same_authority_is_noop(monkeypatch):
    _gate(monkeypatch)
    result = service.resolve_budget_ranking_readiness(Client([_product()]), latest_snapshot={"pinned_price_as_of": "2026-08-22"}, promoted_market_date="2026-08-22")
    assert result.status == service.BudgetRankingStatus.NO_NEW_AUTHORITY
    assert not result.products


@pytest.mark.parametrize("change,expected", [
    ({"financial_rip_v4_version": "future"}, service.BudgetRankingStatus.METHOD_VERSION_MISMATCH),
    ({"product_family": "new_family"}, service.BudgetRankingStatus.HEALTH_GATE_BLOCKED),
    ({"price_source": None}, service.BudgetRankingStatus.UPSTREAM_NOT_READY),
    ({"product_market_cost": 0}, service.BudgetRankingStatus.UPSTREAM_NOT_READY),
    ({"overall_rip_v10_rankable": False}, service.BudgetRankingStatus.UPSTREAM_NOT_READY),
])
def test_fail_closed_contracts(monkeypatch, change, expected):
    _gate(monkeypatch)
    result = service.resolve_budget_ranking_readiness(Client([_product(**change)]), latest_snapshot=None, promoted_market_date="2026-08-22")
    assert result.status == expected


def test_mixed_dates_and_duplicate_sku_are_rejected(monkeypatch):
    _gate(monkeypatch, [SimpleNamespace(status="current", set_id="s1", calculation_run_id="r1"), SimpleNamespace(status="current", set_id="s2", calculation_run_id="r2")])
    mixed = Client([_product(), _product("p2", "s2", "r2", "2026-08-21")])
    assert service.resolve_budget_ranking_readiness(mixed, latest_snapshot=None, promoted_market_date="2026-08-22").status == service.BudgetRankingStatus.UPSTREAM_NOT_READY
    duplicate = Client([_product(), _product("p1", "s2", "r2")])
    assert service.resolve_budget_ranking_readiness(duplicate, latest_snapshot=None, promoted_market_date="2026-08-22").status == service.BudgetRankingStatus.UPSTREAM_NOT_READY


def test_force_date_does_not_bypass_normal_gates(monkeypatch):
    _gate(monkeypatch)
    result = service.resolve_budget_ranking_readiness(Client([_product(product_family="new")]), latest_snapshot=None, promoted_market_date="2026-08-22", force_price_as_of="2026-08-22")
    assert result.status == service.BudgetRankingStatus.HEALTH_GATE_BLOCKED


def test_stale_after_two_expected_cycles_with_newer_raw(monkeypatch):
    _gate(monkeypatch)
    current = _product(date="2026-08-21")
    raw = [current, _product("raw", run="historical-new", date="2026-08-22")]
    result = service.resolve_budget_ranking_readiness(Client([current], raw=raw), latest_snapshot={"pinned_price_as_of": "2026-08-21", "published_at": "2026-08-21T12:00:00Z"}, promoted_market_date="2026-08-23", now=datetime.fromisoformat("2026-08-23T20:00:00+00:00"))
    assert result.status == service.BudgetRankingStatus.STALE


def test_dynamic_population_is_not_hard_coded(monkeypatch):
    statuses = [SimpleNamespace(status="current", set_id=f"s{i}", calculation_run_id=f"r{i}") for i in range(3)]
    _gate(monkeypatch, statuses)
    products = [_product(f"p{i}", f"s{i}", f"r{i}") for i in range(3)]
    result = service.resolve_budget_ranking_readiness(Client(products), latest_snapshot=None, promoted_market_date="2026-08-22")
    assert result.authority["productCount"] == 3
