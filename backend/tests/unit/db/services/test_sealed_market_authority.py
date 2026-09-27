from backend.db.services.sealed_market_authority import (
    DEFERRED_SEALED_MARKET_AUTHORITY_INCOMPLETE,
    SEALED_RESULT_DATE_MISMATCH,
    evaluate_same_day_sealed_market_authority,
    evaluate_snapshot_rows,
    verify_simulation_product_dates,
)

DATE = "2026-09-15"


def _snapshot(*, prices=(DATE, DATE), manifest=("p1", "p2"), fingerprint="fp"):
    return {"set_id": "s1", "market_date": max(prices), "source_generation_fingerprint": fingerprint,
            "payload_json": {"marketDate": max(prices), "set": {"canonicalKey": "megaEvolution"},
                             "meta": {"eligibleProductIds": list(manifest)},
                             "products": [{"sealedProductId": f"p{i+1}", "priceAsOf": value}
                                          for i, value in enumerate(prices)]}}


def test_sep15_style_stale_snapshot_is_deferred():
    report = evaluate_snapshot_rows([_snapshot(prices=("2026-09-14", "2026-09-14"))], DATE)
    assert not report.ready
    assert report.reason_code == DEFERRED_SEALED_MARKET_AUTHORITY_INCOMPLETE
    assert report.stale_product_ids == ["p1", "p2"]
    assert report.min_price_as_of == report.max_price_as_of == "2026-09-14"


def test_rebuilt_same_day_snapshot_passes_and_has_stable_fingerprint():
    first = evaluate_snapshot_rows([_snapshot()], DATE)
    second = evaluate_snapshot_rows([_snapshot()], DATE)
    assert first.ready and first.verified_product_count == 2
    assert first.authority_fingerprint == second.authority_fingerprint


def test_missing_or_one_stale_product_blocks_readiness():
    missing = evaluate_snapshot_rows([_snapshot(prices=(DATE,), manifest=("p1", "p2"))], DATE)
    stale = evaluate_snapshot_rows([_snapshot(prices=(DATE, "2026-09-14"))], DATE)
    assert missing.missing_product_ids == ["p2"] and not missing.ready
    assert stale.stale_product_ids == ["p2"] and not stale.ready


def test_historical_at_or_before_is_not_accepted_by_strict_gate():
    assert not evaluate_snapshot_rows([_snapshot(prices=("2026-09-14", "2026-09-14"))], DATE).ready


class _Query:
    def __init__(self, client, rows): self.client, self.rows = client, rows
    def select(self, *_a, **_k): return self
    def eq(self, *_a, **_k): return self
    def order(self, *_a, **_k): return self
    def in_(self, *_a, **_k): return self
    def execute(self):
        self.client.executes += 1
        return type("R", (), {"data": self.rows})()


class _Client:
    def __init__(self, tables): self.tables, self.executes = tables, 0
    def table(self, name): return _Query(self, self.tables[name])


def test_snapshot_gate_is_one_bounded_query_not_n_plus_one():
    client = _Client({"pokemon_set_sealed_market_snapshot_latest": [_snapshot()]})
    assert evaluate_same_day_sealed_market_authority(client, target_market_date=DATE).ready
    assert client.executes == 1


def test_post_simulation_mismatch_fails_closed_in_one_query():
    client = _Client({"calculation_runs": [{"id": "r1", "target_id": "s1", "created_at": "x"}],
                      "simulation_sealed_product_results": [
        {"sealed_product_id": "p1", "price_as_of": DATE},
        {"sealed_product_id": "p2", "price_as_of": "2026-09-14"},
    ]})
    report = verify_simulation_product_dates(client, target_market_date=DATE)
    assert not report.ready and report.reason_code == SEALED_RESULT_DATE_MISMATCH
    assert report.stale_product_ids == ["p2"]
    assert client.executes == 2


def test_safe_retry_after_deferred_snapshot_rebuild():
    stale = evaluate_snapshot_rows([_snapshot(prices=("2026-09-14", "2026-09-14"))], DATE)
    rebuilt = evaluate_snapshot_rows([_snapshot()], DATE)
    assert not stale.ready and rebuilt.ready
