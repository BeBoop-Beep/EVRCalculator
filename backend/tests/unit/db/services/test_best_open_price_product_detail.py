from backend.db.services import pokemon_sealed_product_detail_service as detail_service
from backend.domain.access.index_plan_access import project_sealed_product_detail_response

BEST_OPEN_PRICE_METHOD_VERSION = detail_service.BEST_OPEN_PRICE_METHOD_VERSION
BEST_OPEN_PRICE_V2_METHOD_VERSION = detail_service.BEST_OPEN_PRICE_V2_METHOD_VERSION

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
    # CURRENT-authority selection (Finding 1) requests V2 first; this V1-only
    # fixture reports V2 unavailable so the second, explicit-V1 call is what
    # actually serves the row -- exactly the "missing V2 falls back to
    # current V1" path (Finding 1, test D).
    calls = []

    def fake_load(_client, _product_id, *, best_open_price_method_version):
        calls.append(best_open_price_method_version)
        if best_open_price_method_version == BEST_OPEN_PRICE_V2_METHOD_VERSION:
            return {"available": False, "reason": "no_published_snapshot", "row": None}
        return dict(PREPARED)

    monkeypatch.setattr(detail_service, "load_best_open_price_product", fake_load)

    result = detail_service._best_open_price_contract(object(), "p1")
    assert calls == [BEST_OPEN_PRICE_V2_METHOD_VERSION, BEST_OPEN_PRICE_METHOD_VERSION]

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
        lambda _client, _product_id, **_kwargs: dict(PREPARED),
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
        lambda _client, _product_id, **_kwargs: {
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


def test_current_product_detail_requests_v2_first(monkeypatch):
    """Finding 1 test B: the current/live-serving Product Detail call site
    must attempt the V2 method version before ever falling back to V1."""
    calls = []

    def fake_load(_client, _product_id, *, best_open_price_method_version):
        calls.append(best_open_price_method_version)
        return {"available": False, "reason": "no_published_snapshot", "row": None}

    monkeypatch.setattr(detail_service, "load_best_open_price_product", fake_load)
    detail_service._best_open_price_contract(object(), "p1")
    assert calls[0] == BEST_OPEN_PRICE_V2_METHOD_VERSION


def test_current_v2_is_selected_when_available(monkeypatch):
    """Finding 1 test C + Finding 2: a current V2 publication is used and its
    row exposes both the rip* aliases and the financial_* fields."""
    v2_prepared = {
        "available": True, "reason": None,
        "snapshotId": "bop-v2-snapshot",
        "methodVersion": BEST_OPEN_PRICE_V2_METHOD_VERSION,
        "sourceBudgetSnapshotId": "budget-snapshot-v2",
        "sourceMarketDate": "2026-09-16",
        "sourceFullMarketBudget": 1350,
        "sourceEligibleCohortCount": 138,
        "row": {
            "sealed_product_id": "p1", "current_market_price": 14.57, "current_budget_rank": 2,
            "status": "resolved_below_market", "best_open_price": 13.23,
            "threshold_quantity": 102, "price_gap_dollars": 1.34, "price_gap_percent": 0.0919,
            "current_financial_only_rank": 1, "financial_status": "current_number_one_with_headroom",
            "financial_best_open_price": 15.00, "financial_threshold_quantity": 90,
            "financial_price_gap_dollars": -0.43, "financial_price_gap_percent": -0.0295,
        },
    }

    def fake_load(_client, _product_id, *, best_open_price_method_version):
        if best_open_price_method_version == BEST_OPEN_PRICE_V2_METHOD_VERSION:
            return dict(v2_prepared)
        raise AssertionError("V1 must not be attempted when V2 is current")

    monkeypatch.setattr(detail_service, "load_best_open_price_product", fake_load)
    result = detail_service._best_open_price_contract(object(), "p1")
    assert result["methodVersion"] == BEST_OPEN_PRICE_V2_METHOD_VERSION
    assert result["ripBestOpenPrice"] == 13.23
    assert result["financialBestOpenPrice"] == 15.00
    assert result["financialBestOpenPriceStatus"] == "current_number_one_with_headroom"


def test_stale_v1_cannot_mask_current_v2(monkeypatch):
    """Finding 1 test E: even though a V1 publication exists, a current V2
    publication must win -- V1 must never be consulted once V2 succeeds."""
    v1_consulted = []

    def fake_load(_client, _product_id, *, best_open_price_method_version):
        if best_open_price_method_version == BEST_OPEN_PRICE_V2_METHOD_VERSION:
            return dict(PREPARED, methodVersion=BEST_OPEN_PRICE_V2_METHOD_VERSION)
        v1_consulted.append(True)
        return dict(PREPARED)

    monkeypatch.setattr(detail_service, "load_best_open_price_product", fake_load)
    result = detail_service._best_open_price_contract(object(), "p1")
    assert result["methodVersion"] == BEST_OPEN_PRICE_V2_METHOD_VERSION
    assert v1_consulted == []


def test_explicit_v1_read_remains_possible(monkeypatch):
    """Finding 1 test F: the low-level loader's explicit V1 default is
    untouched -- an explicit V1-targeted call still works exactly as before."""
    from backend.db.services.budget_product_best_open_price_service import load_best_open_price_product

    monkeypatch.setattr(
        "backend.db.services.budget_product_best_open_price_service.load_latest_snapshot",
        lambda _client, **_kwargs: None,
    )
    result = load_best_open_price_product(
        object(), "p1", best_open_price_method_version=BEST_OPEN_PRICE_METHOD_VERSION,
    )
    assert result == {"available": False, "reason": "no_published_snapshot", "row": None}


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
