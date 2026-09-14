from backend.db.services import pokemon_sealed_product_detail_service as detail_service
from backend.domain.access.index_plan_access import project_sealed_product_detail_response


PREPARED = {
    "available": True,
    "reason": None,
    "snapshotId": "bop-snapshot",
    "methodVersion": "budget_product_best_open_price_full_market_v1",
    "sourceBudgetSnapshotId": "budget-snapshot",
    "sourceMarketDate": "2026-09-08",
    "sourceFullMarketBudget": 1350,
    "sourceEligibleCohortCount": 138,
    "row": {
        "sealed_product_id": "p1",
        "current_market_price": 14.57,
        "current_budget_rank": 2,
        "status": "resolved_below_market",
        "best_open_price": 13.23,
        "threshold_quantity": 102,
        "price_gap_dollars": 1.34,
        "price_gap_percent": 0.09196980096,
    },
}


def test_product_detail_best_open_contract_preserves_dated_ranking_source(monkeypatch):
    monkeypatch.setattr(
        detail_service,
        "load_best_open_price_product",
        lambda _client, _product_id: dict(PREPARED),
    )

    result = detail_service._best_open_price_contract(object(), "p1")

    assert result == {
        "available": True,
        "reason": None,
        "bestOpenPrice": 13.23,
        "status": "resolved_below_market",
        "priceGapDollars": 1.34,
        "priceGapPercent": 0.09196980096,
        "thresholdQuantity": 102,
        "sourceUnitPrice": 14.57,
        "sourceBudgetRank": 2,
        "sourceMarketDate": "2026-09-08",
        "sourceFullMarketBudget": 1350,
        "sourceCohortSize": 138,
        "sourceBudgetSnapshotId": "budget-snapshot",
        "methodVersion": "budget_product_best_open_price_full_market_v1",
    }


def test_newer_live_market_price_never_rewrites_prepared_threshold_or_source_price(monkeypatch):
    monkeypatch.setattr(
        detail_service,
        "load_best_open_price_product",
        lambda _client, _product_id: dict(PREPARED),
    )
    best_open = detail_service._best_open_price_contract(object(), "p1")
    live_market = {"currentPrice": 16.25, "marketDate": "2026-09-14"}

    # The backend publishes the two authorities separately. The frontend may
    # compare 16.25 to 13.23 as prices, but it cannot reinterpret the threshold
    # as if 16.25 had been part of the Sep-8 Full Market cohort.
    assert live_market["currentPrice"] != best_open["sourceUnitPrice"]
    assert best_open["sourceUnitPrice"] == 14.57
    assert best_open["bestOpenPrice"] == 13.23
    assert best_open["sourceMarketDate"] == "2026-09-08"


def test_stale_or_failed_prepared_read_returns_unavailable_not_old_threshold(monkeypatch):
    monkeypatch.setattr(
        detail_service,
        "load_best_open_price_product",
        lambda _client, _product_id: {
            "available": False,
            "reason": "stale_source_publication",
            "row": None,
        },
    )
    assert detail_service._best_open_price_contract(object(), "p1") == {
        "available": False,
        "reason": "stale_source_publication",
    }

    def explode(*_args, **_kwargs):
        raise RuntimeError("store unavailable")

    monkeypatch.setattr(detail_service, "load_best_open_price_product", explode)
    assert detail_service._best_open_price_contract(object(), "p1") == {
        "available": False,
        "reason": "prepared_read_failed",
    }


def test_basic_product_detail_projection_cannot_receive_best_open_price():
    payload = {
        "set": {"id": "s1"},
        "product": {"id": "p1"},
        "market": {"currentPrice": 16.25},
        "meta": {},
        "rip": {"bestOpenPrice": detail_service._best_open_price_contract},
        "comparisons": {},
    }

    basic = project_sealed_product_detail_response(payload, None)
    assert "rip" not in basic
    assert "comparisons" not in basic

    plus_payload = {
        **payload,
        "rip": {"bestOpenPrice": {"available": True, "bestOpenPrice": 13.23}},
    }
    plus = project_sealed_product_detail_response(plus_payload, "plus")
    assert plus["rip"]["bestOpenPrice"]["bestOpenPrice"] == 13.23
