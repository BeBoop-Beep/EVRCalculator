from datetime import datetime, timedelta, timezone

import pytest

from backend.pricing_pipeline import budget_v2 as b
from backend.pricing_pipeline import ebay_quota_policy as policy
from backend.pricing_pipeline.contracts import (
    PIPELINE_VERSION, PIPELINE_VERSION_V2, PLANNING_FRACTION_V2, V2_STANDARD_USABLE_CEILING, PipelineError,
)
from backend.pricing_pipeline.orchestrator import Orchestrator
from backend.pricing_pipeline.store import MemoryStore, SupabaseStore
from backend.pricing_pipeline import targets
from backend.scripts.index_fair_value_ebay_evidence_collector import BudgetExhausted, CollectorConfig, RunCounters, TokenProvider

NOW = datetime(2026, 9, 21, 17, 0, tzinfo=timezone.utc)
KEYSET = b.keyset_identity("PRODUCTION", "App-PRD-abcdef")


class Query:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *_): return self
    def eq(self, *_): return self
    def order(self, *_, **__): return self
    def limit(self, *_): return self
    def execute(self):
        return type("R", (), {"data": self.rows})


class FakeClient:
    def __init__(self, rows=None, rpc_error=None):
        self.rows, self.rpc_error, self.calls = rows or [], rpc_error, []

    def table(self, name):
        return Query(self.rows)

    def rpc(self, name, params):
        self.calls.append((name, params))
        outer = self

        class R:
            def execute(self):
                if outer.rpc_error:
                    raise Exception(outer.rpc_error)
        return R()


def limits(std=5000, bulk=5000, reset="2026-09-22T07:00:00.000Z"):
    row = lambda res, lim: {"resource": res, "limit": lim, "count": 0, "remaining": lim, "reset": reset, "time_window_seconds": 86400}
    return {"state": policy.PROVIDER_OK, "limits": [row("buy.browse", std), row("buy.browse.item.bulk", bulk)]}


def last_verified(hours_ago, limit=5000, reserved=100):
    return [{"provider_limit": limit, "verified_at": (NOW - timedelta(hours=hours_ago)).isoformat(), "requests_reserved": reserved,
             "provider_usage_state": "PROVIDER_USAGE_OK"}]


# ------------------------------------------------------------------------------------------- identity / buckets
def test_versions_are_distinct_and_v1_is_preserved():
    assert PIPELINE_VERSION == "multi_source_daily_pipeline_p6_v1" and PIPELINE_VERSION_V2 == "multi_source_daily_pipeline_p6_v2"
    assert b.POLICY_VERSION == "ebay_api_budget_policy_v2"
    assert V2_STANDARD_USABLE_CEILING == policy.usable_limit(5000) == 4500


def test_keyset_identity_hashes_the_app_id():
    assert "App-PRD-abcdef" not in KEYSET and KEYSET.startswith("PRODUCTION:")
    assert b.keyset_identity("PRODUCTION", "x") != b.keyset_identity("SANDBOX", "x")


@pytest.mark.parametrize("url,bucket", [
    ("https://api.ebay.com/buy/browse/v1/item_summary/search?q=x", b.STANDARD),
    ("https://api.ebay.com/buy/browse/v1/item/v1%7C123%7C0", b.STANDARD),  # getItem: conservative standard attribution
    ("https://api.ebay.com/buy/browse/v1/item?item_ids=a,b", b.BULK)])
def test_bucket_mapping(url, bucket):
    assert b.bucket_for_url(url) == bucket


def test_unmapped_operations_fail_closed():
    for url in ("https://api.ebay.com/buy/browse/v1/item", "https://api.ebay.com/buy/marketplace_insights/v1_beta/item_sales/search",
                "https://api.ebay.com/buy/browse/v1/item_summary/search_by_image"):
        with pytest.raises(PipelineError) as exc:
            b.bucket_for_url(url)
        assert exc.value.code == "UNMAPPED_BROWSE_OPERATION"


# --------------------------------------------------------------------------------------------- pool separation
class RecordingLedger:
    def __init__(self, name, limit=None, log=None):
        self.name, self.limit, self.count, self.log = name, limit, 0, log if log is not None else []

    def reserve(self, market_date=None):
        if self.limit is not None and self.count >= self.limit:
            raise BudgetExhausted(self.name)
        self.count += 1
        self.log.append(self.name)


def routed(std, bulk, opener):
    return b.RoutedBrowseHTTP(TokenProvider({}, fetch=lambda: "t"), CollectorConfig(retry_budget=0), {b.STANDARD: std, b.BULK: bulk},
                              opener=opener, sleep=lambda s: None)


def test_routed_http_reserves_in_the_bucket_of_the_operation_only():
    log = []
    std, bulk = RecordingLedger("std", log=log), RecordingLedger("bulk", log=log)
    http = routed(std, bulk, lambda url, token: {"ok": True})
    counters = RunCounters(remaining_run_budget=50)
    http.get("https://api.ebay.com/buy/browse/v1/item_summary/search?q=x", counters)
    http.get("https://api.ebay.com/buy/browse/v1/item/abc", counters)
    http.get("https://api.ebay.com/buy/browse/v1/item?item_ids=a,b", counters)
    assert log == ["std", "std", "bulk"] and (std.count, bulk.count) == (2, 1)


def test_standard_exhaustion_never_borrows_the_bulk_pool_and_vice_versa():
    std, bulk = RecordingLedger("std", limit=1), RecordingLedger("bulk", limit=1)
    http = routed(std, bulk, lambda url, token: {"ok": True})
    counters = RunCounters(remaining_run_budget=50)
    http.get("https://api.ebay.com/buy/browse/v1/item_summary/search?q=x", counters)
    with pytest.raises(BudgetExhausted):
        http.get("https://api.ebay.com/buy/browse/v1/item/abc", counters)  # standard is full: does NOT spill into bulk
    assert bulk.count == 0
    http.get("https://api.ebay.com/buy/browse/v1/item?item_ids=a", counters)
    with pytest.raises(BudgetExhausted):
        http.get("https://api.ebay.com/buy/browse/v1/item?item_ids=b", counters)
    assert std.count == 1 and bulk.count == 1


def test_retries_are_reserved_in_the_same_bucket():
    import urllib.error
    log = []
    attempts = {"n": 0}

    def flaky(url, token):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise urllib.error.HTTPError(url, 503, "x", {}, None)
        return {"ok": True}
    std, bulk = RecordingLedger("std", log=log), RecordingLedger("bulk", log=log)
    http = b.RoutedBrowseHTTP(TokenProvider({}, fetch=lambda: "t"), CollectorConfig(retry_budget=2, backoff_base_seconds=0), {b.STANDARD: std, b.BULK: bulk},
                              opener=flaky, sleep=lambda s: None)
    http.get("https://api.ebay.com/buy/browse/v1/item/abc", RunCounters(remaining_run_budget=10))
    assert log == ["std", "std"]


def test_pool_ledger_maps_database_errors():
    ok = FakeClient()
    b.PoolLedger(ok, KEYSET, b.STANDARD).reserve()
    assert ok.calls == [("reserve_ebay_api_request_v2", {"p_keyset": KEYSET, "p_api": "Browse", "p_bucket": "BUY_BROWSE_STANDARD"})]
    with pytest.raises(BudgetExhausted):
        b.PoolLedger(FakeClient(rpc_error="EBAY_BUDGET_EXHAUSTED"), KEYSET, b.STANDARD).reserve()
    for text in ("EBAY_BUDGET_WINDOW_UNKNOWN", "EBAY_BUDGET_VERIFICATION_STALE"):
        with pytest.raises(PipelineError) as exc:
            b.PoolLedger(FakeClient(rpc_error=text), KEYSET, b.STANDARD).reserve()
        assert exc.value.code == "QUOTA_UNVERIFIED"
    with pytest.raises(PipelineError) as exc:
        b.PoolLedger(FakeClient(rpc_error="connection refused"), KEYSET, b.BULK).reserve()
    assert exc.value.code == "BUDGET_AUTHORITY_UNAVAILABLE"
    with pytest.raises(ValueError):
        b.PoolLedger(ok, KEYSET, "BUY_MARKETPLACE_INSIGHTS")


def test_remaining_uses_the_provider_window_covering_now():
    window = {"provider_window_start": "2026-09-21T07:00:00+00:00", "provider_window_end": "2026-09-22T07:00:00+00:00",
              "usable_limit": 4500, "requests_reserved": 700}
    ledger = b.PoolLedger(FakeClient([window]), KEYSET, b.STANDARD)
    assert ledger.window(NOW)["usable_limit"] == 4500
    assert ledger.window(datetime(2026, 9, 22, 8, 0, tzinfo=timezone.utc)) is None  # window over: nothing covers now


# ------------------------------------------------------------------------------- provider analytics scenarios
def verify(client, snapshot):
    def fetch():
        if isinstance(snapshot, Exception):
            raise snapshot
        return snapshot
    return b.QuotaVerifier(client, KEYSET, fetch).verify(NOW)


def test_analytics_200_registers_both_buckets_with_the_provider_window():
    client = FakeClient()
    result = verify(client, limits())
    assert {r["mode"] for r in result["buckets"].values()} == {policy.HEALTHY}
    registered = {p["p_bucket"]: p for _, p in client.calls}
    assert set(registered) == {b.STANDARD, b.BULK}
    std = registered[b.STANDARD]
    assert std["p_provider_limit"] == 5000 and std["p_reset_at"].startswith("2026-09-22T07:00:00")
    assert std["p_window_start"].startswith("2026-09-21T07:00:00")  # reset minus 86400s: the provider's window, not Phoenix midnight


@pytest.mark.parametrize("snapshot", [{"state": "PROVIDER_USAGE_UNRESOLVED_NO_CONTENT", "limits": []},  # 204
                                      {"state": "PROVIDER_USAGE_EMPTY_LIST", "limits": []},              # empty response
                                      {"state": "PROVIDER_USAGE_ERROR", "limits": []}, TimeoutError("timed out")])
def test_analytics_unavailable_degrades_within_36h_and_never_registers_or_goes_unlimited(snapshot):
    client = FakeClient(rows=last_verified(hours_ago=5))
    result = verify(client, snapshot)
    assert client.calls == []  # nothing is registered from a non-answer
    for bucket in result["buckets"].values():
        assert bucket["mode"] == policy.DEGRADED_LAST_KNOWN and bucket["usable_limit"] == 4500


def test_analytics_unavailable_and_verification_older_than_36h_fails_closed():
    result = verify(FakeClient(rows=last_verified(hours_ago=37)), {"state": "PROVIDER_USAGE_UNRESOLVED_NO_CONTENT", "limits": []})
    assert {r["mode"] for r in result["buckets"].values()} == {policy.FAIL_CLOSED}
    assert {r["reason"] for r in result["buckets"].values()} == {"QUOTA_VERIFICATION_STALE"}


def test_new_keyset_with_no_verified_history_fails_closed():
    result = verify(FakeClient(rows=[]), TimeoutError("down"))  # e.g. credentials rotated to a different app key
    assert {r["reason"] for r in result["buckets"].values()} == {"QUOTA_NEVER_VERIFIED"}


def test_provider_limit_reduction_is_registered_and_lowers_the_ceiling():
    client = FakeClient()
    verify(client, limits(std=2000))
    std = next(p for _, p in client.calls if p["p_bucket"] == b.STANDARD)
    assert std["p_provider_limit"] == 2000 and policy.usable_limit(2000) == 1800


def test_bucket_missing_from_a_200_response_is_degraded_not_assumed():
    snapshot = {"state": policy.PROVIDER_OK, "limits": [limits()["limits"][0]]}  # bulk bucket absent
    client = FakeClient(rows=last_verified(hours_ago=2))
    result = verify(client, snapshot)
    assert result["buckets"][b.STANDARD]["mode"] == policy.HEALTHY and result["buckets"][b.BULK]["mode"] == policy.DEGRADED_LAST_KNOWN


# --------------------------------------------------------------------------------------- ceiling / capacity / gate
def test_cli_cannot_raise_the_ceiling_only_lower_it():
    over = Orchestrator(MemoryStore(), RecordingLedger("s"), "x", max_requests=999999, request_ceiling=4500)
    assert over.max_requests == 4500
    assert Orchestrator(MemoryStore(), RecordingLedger("s"), "x", max_requests=300, request_ceiling=4500).max_requests == 300
    assert Orchestrator(MemoryStore(), RecordingLedger("s"), "x").max_requests == 1000  # V1 default unchanged


def test_v2_capacity_uses_measured_cost_and_holds_back_20_percent():
    assert targets.plan_capacity(4500, 7.14, PLANNING_FRACTION_V2, 4500) == 504  # not 4.5 x the V1 count (126)
    assert targets.plan_capacity(4500, 7.14) == 126  # V1 defaults preserved: 1000-request ceiling x 0.90 / 7.14
    assert targets.plan_capacity(99999, 7.14, PLANNING_FRACTION_V2, 4500) == 504  # a bigger remaining figure cannot exceed the ceiling
    assert round(4500 * (1 - PLANNING_FRACTION_V2)) == 900  # capacity left for retries, late hydration and manual probes


def test_transient_read_timeouts_are_retried_but_other_errors_are_not():
    delays, calls = [], {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise Exception("{'code': '57014', 'message': 'canceling statement due to statement timeout'}")
        return "ok"
    assert SupabaseStore._retry(flaky, sleep=delays.append) == "ok" and delays == [3.0, 6.0]
    with pytest.raises(Exception, match="permission denied"):
        SupabaseStore._retry(lambda: (_ for _ in ()).throw(Exception("permission denied")), sleep=delays.append)
    with pytest.raises(Exception, match="57014"):
        SupabaseStore._retry(lambda: (_ for _ in ()).throw(Exception("57014")), attempts=2, sleep=delays.append)


def test_quota_gate_runs_before_network_work_but_not_on_a_replay(tmp_path):
    from datetime import date
    from backend.scripts.pokemon_multi_source_card_price_v1 import POLICY_VERSION
    calls = []

    def gate():
        calls.append("gate")
        raise PipelineError("QUOTA_UNVERIFIED", "analytics down and verification stale")

    store = MemoryStore()
    store.batches["2026-09-21"] = "complete"
    with pytest.raises(PipelineError) as exc:
        Orchestrator(store, RecordingLedger("s"), tmp_path, quota_gate=gate).run(date(2026, 9, 21))
    assert exc.value.code == "QUOTA_UNVERIFIED" and calls == ["gate"]
    assert store.get_run("2026-09-21")["status"] == "FAILED" and not store.evidence  # stopped before any collection or persistence
    # a COMPLETE market date replays with ZERO eBay/provider calls: the gate is never consulted
    store.runs["r"] = {"run_id": "r", "market_date": "2026-09-22", "policy_version": POLICY_VERSION, "status": "COMPLETE",
                       "receipt": {"market_date": "2026-09-22", "receipt_fingerprint": "f"}}
    calls.clear()
    assert Orchestrator(store, RecordingLedger("s"), tmp_path, quota_gate=gate).run(date(2026, 9, 22))["idempotent_replay"] is True
    assert calls == []


@pytest.mark.skipif(not __import__("os").environ.get("PGLITE_PACKAGE"), reason="PGLITE_PACKAGE not set")
def test_disposable_postgres_quota_v2_integration():
    import subprocess
    from pathlib import Path
    root = Path(__file__).resolve().parents[4]
    result = subprocess.run(["node", "backend/tests/integration/p6_6_disposable_postgres.mjs"], cwd=root, capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stderr[-2000:]
