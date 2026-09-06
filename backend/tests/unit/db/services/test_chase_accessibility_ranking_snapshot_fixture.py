"""UI-4 Phase 14 dry-run fixture.

Proves the Set RIP / Product Family Rankings projection - the shape a future
Rankings snapshot publication will carry - already contains the Chase
Accessibility set-rank block end to end, without touching the actual
publication/publisher/snapshot-builder modules (those are concurrent,
out-of-scope work for this task). This is a fixture-level proof only; no
publication happens here.
"""

from __future__ import annotations

from backend.db.services import product_family_rankings_service as pfr_service
from backend.db.services import set_rip_service
from backend.desirability.chase_accessibility import CHASE_ACCESSIBILITY_VERSION
from backend.desirability.scoring_config import (
    CANONICAL_FINANCIAL_RIP_VERSION,
    CANONICAL_OVERALL_RIP_VERSION,
    canonical_collector_appeal_version,
)


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *_a, **_kw):
        return self

    def in_(self, field, values):
        self.rows = [row for row in self.rows if row.get(field) in values]
        return self

    def eq(self, field, value):
        self.rows = [row for row in self.rows if row.get(field) == value]
        return self

    def order(self, *_a, **_kw):
        return self

    def range(self, *_a, **_kw):
        return self

    def limit(self, *_a, **_kw):
        return self

    def execute(self):
        return type("Result", (), {"data": self.rows})()


class _Client:
    def __init__(self, product_rows, chase_rows):
        self.product_rows = product_rows
        self.chase_rows = chase_rows

    def table(self, name):
        if name == "simulation_sealed_product_results":
            return _Query(list(self.product_rows))
        if name == "sealed_products":
            return _Query([])
        if name == "pokemon_set_chase_accessibility_snapshot_latest":
            return _Query(list(self.chase_rows))
        raise AssertionError(f"unexpected table read: {name}")


def _product_row(product_id, set_id, family="booster_box"):
    return {
        "calculation_run_id": "run-1", "sealed_product_id": product_id, "set_id": set_id,
        "product_family": family, "product_name": product_id, "pack_count": 36,
        "product_market_cost": 100.0, "expected_value": 80.0, "median_value": 55.0,
        "chance_to_recover_cost": 0.4,
        "financial_rip_v4_score": 70.0, "financial_rip_v4_version": CANONICAL_FINANCIAL_RIP_VERSION,
        "collector_appeal_score": 60.0, "collector_appeal_version": canonical_collector_appeal_version(),
        "overall_rip_v12_score": 80.0, "overall_rip_v12_version": CANONICAL_OVERALL_RIP_VERSION,
        "overall_rip_v12_rankable": True, "overall_rip_v12_status": "ready",
        "overall_rip_v12_payload": None,
    }


def _chase_row(set_id, accessibility):
    return {
        "set_id": set_id, "calculation_run_id": "run-1", "accessibility": accessibility,
        "status": "ready", "version": CHASE_ACCESSIBILITY_VERSION, "mapped_hc_mass": 0.995,
        "chase_depth": 12.0,
    }


def test_product_family_rankings_snapshot_fixture_carries_full_chase_block(monkeypatch):
    monkeypatch.setattr(pfr_service, "CANONICAL_OVERALL_RIP_VERSION", CANONICAL_OVERALL_RIP_VERSION)
    product_rows = [
        _product_row("prod-a1", "set-a"),
        _product_row("prod-a2", "set-a", family="elite_trainer_box"),
        _product_row("prod-b1", "set-b"),
    ]
    chase_rows = [_chase_row("set-a", 0.05), _chase_row("set-b", 0.02)]
    client = _Client(product_rows, chase_rows)
    set_targets = [
        {"set_id": "set-a", "canonical_key": "alpha", "calculation_run_id": "run-1", "name": "Alpha"},
        {"set_id": "set-b", "canonical_key": "beta", "calculation_run_id": "run-1", "name": "Beta"},
    ]

    result = pfr_service.build_product_family_rankings(client, set_targets=set_targets)

    all_products = [p for family in result["families"].values() for p in family["products"]]
    assert len(all_products) == 3
    for product in all_products:
        block = product["chaseAccessibility"]
        for key in ("value", "percent", "status", "version", "chaseDepth", "mappedHcMass",
                    "setRank", "setCohortSize"):
            assert key in block, f"missing {key} in chaseAccessibility block"

    set_a_blocks = [p["chaseAccessibility"] for p in all_products if p["setId"] == "set-a"]
    assert set_a_blocks[0] == set_a_blocks[1]  # both set-a products share identical block
    assert set_a_blocks[0]["setRank"] == 1  # set-a has the higher raw accessibility
    assert set_a_blocks[0]["setCohortSize"] == 2

    set_b_block = next(p["chaseAccessibility"] for p in all_products if p["setId"] == "set-b")
    assert set_b_block["setRank"] == 2

    # Feed straight into Set RIP - proves the same block survives the
    # product-family -> set-level projection without a second computation.
    set_rip = set_rip_service.build_set_rip(result, set_targets=[
        {**target, "overallRipV10": {"rank": index + 1}} for index, target in enumerate(set_targets)
    ])
    for row in set_rip["sets"]:
        assert row["chaseAccessibility"]["setCohortSize"] == 2
