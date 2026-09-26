from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.pricing_pipeline.contracts import DAILY_REQUEST_LIMIT
from backend.pricing_pipeline.contracts import PHOENIX as PP_PHOENIX
from backend.scripts.freeze_ebay_active_ask_v1 import VERSION as ESTIMATOR_VERSION
from backend.scripts.pokemon_multi_source_card_price_v1 import POLICY_VERSION
from backend.sentinel.checks.registry import (
    FAST_CHECK_KEYS,
    PRICING_CHECK_KEYS,
    build_fast_registry,
    build_profile_registry,
)
from backend.sentinel.models import CheckOutcome, RunnerIdentity, Severity
from backend.sentinel.registry import CheckContext

# 09:00 Phoenix -> run deadline (08:00) has passed, so "today" (Phoenix) is expected.
NOW = datetime(2026, 9, 20, 16, 0, tzinfo=timezone.utc)
EXPECTED_MARKET_DATE = NOW.astimezone(PP_PHOENIX).date().isoformat()
CTX = CheckContext(
    now=NOW,
    runner_identity=RunnerIdentity(component="sentinel", host="test", build_sha="sha"),
)


class _Query:
    def __init__(self, rows, *, err=None):
        self.rows = [dict(row) for row in rows]
        self._err = err

    def select(self, *args, **kwargs):
        return self

    def eq(self, key, value):
        self.rows = [row for row in self.rows if row.get(key) == value]
        return self

    def neq(self, key, value):
        if self._err is not None:
            raise self._err
        self.rows = [row for row in self.rows if row.get(key) != value]
        return self

    def order(self, key, desc=False):
        self.rows = sorted(self.rows, key=lambda r: r.get(key), reverse=desc)
        return self

    def limit(self, n):
        self.rows = self.rows[:n]
        return self

    def execute(self):
        return _Result(self.rows)


class _Result:
    def __init__(self, data):
        self.data = data


class _CountingClient:
    """Fake Supabase-style client that also counts calls to .table() for cache verification."""

    def __init__(self, tables, *, guard_errors=None):
        self.tables = tables
        self.guard_errors = guard_errors or {}
        self.table_calls = 0

    def table(self, name):
        self.table_calls += 1
        err = self.guard_errors.get(name)
        return _Query(self.tables.get(name, []), err=err)


def _healthy_tables():
    market_date = EXPECTED_MARKET_DATE
    return {
        "pokemon_multi_source_pricing_runs_v1": [
            {"market_date": market_date, "status": "COMPLETE", "stage": "done", "failure_code": None,
             "updated_at": NOW.isoformat(), "finished_at": NOW.isoformat(), "requests_attempted": 10,
             "target_fingerprint": "abc123"},
        ],
        "ebay_pricing_runs_v1": [
            {"market_date": market_date, "status": "COMPLETE", "finished_at": NOW.isoformat()},
        ],
        "ebay_active_ask_price_estimates_v1": [
            {"market_date": market_date, "estimator_version": ESTIMATOR_VERSION},
        ],
        "pokemon_multi_source_card_prices_v1": [
            {"market_date": market_date, "policy_version": POLICY_VERSION},
        ],
        "ebay_browse_request_ledger_v1": [
            {"budget_day": market_date, "requests_reserved": 10, "daily_limit": DAILY_REQUEST_LIMIT},
        ],
        "ebay_api_request_budget_v2": [
            {"resource_bucket": "BUY_BROWSE_STANDARD",
             "provider_window_start": (NOW - timedelta(hours=1)).isoformat(),
             "provider_window_end": (NOW + timedelta(hours=1)).isoformat(),
             "usable_limit": 1000, "requests_reserved": 10,
             "verified_at": (NOW - timedelta(minutes=5)).isoformat(),
             "provider_usage_state": "ok"},
        ],
        "card_variant_price_current_v2": [],
        "pokemon_canonical_card_market_prices_latest": [],
    }


def _client(overrides=None, guard_errors=None):
    tables = _healthy_tables()
    for key, rows in (overrides or {}).items():
        tables[key] = rows
    return _CountingClient(tables, guard_errors=guard_errors)


def _run_all(client):
    registry = build_fast_registry(client=client)
    return {key: registry.get(key).run(CTX) for key in PRICING_CHECK_KEYS}


# --------------------------------------------------------------------------------- registration


def test_pricing_checks_registered_exactly_once_in_fast_profile():
    registry = build_fast_registry(client=_client())
    keys = registry.keys()
    for key in PRICING_CHECK_KEYS:
        assert keys.count(key) == 1
    assert set(PRICING_CHECK_KEYS).issubset(set(FAST_CHECK_KEYS))


def test_pricing_checks_registered_exactly_once_in_all_profile():
    registry = build_profile_registry(
        "all", client=_client(), backend_base_url="https://api.example.test",
        http_get=lambda *a, **k: None,
    )
    keys = registry.keys()
    for key in PRICING_CHECK_KEYS:
        assert keys.count(key) == 1


# --------------------------------------------------------------------------------- snapshot caching


def test_registry_build_gathers_pricing_snapshot_exactly_once_per_run():
    client = _client()
    registry = build_fast_registry(client=client)
    for key in PRICING_CHECK_KEYS:
        registry.get(key).run(CTX)
    # gather() issues a fixed number of .table() calls per invocation; running every
    # pricing check must not multiply that count by len(PRICING_CHECK_KEYS).
    single_pass_calls = client.table_calls
    for key in PRICING_CHECK_KEYS:
        registry.get(key).run(CTX)
    # Running every pricing check a second time on the SAME registry instance must not
    # issue any further .table() calls: the snapshot is cached for this registry's lifetime.
    assert client.table_calls == single_pass_calls, (
        f"expected snapshot reuse, got {client.table_calls - single_pass_calls} extra .table() calls"
    )


def test_fresh_registry_instance_gathers_again():
    client = _client()
    build_fast_registry(client=client).get("pricing.multi_source.run_freshness").run(CTX)
    first = client.table_calls
    build_fast_registry(client=client).get("pricing.multi_source.run_freshness").run(CTX)
    assert client.table_calls > first  # not a cross-run global cache


# --------------------------------------------------------------------------------- healthy state


def test_all_pricing_checks_healthy_on_fresh_complete_state():
    results = _run_all(_client())
    for key, result in results.items():
        assert result.outcome == CheckOutcome.HEALTHY, (key, result.failure_code)


# --------------------------------------------------------------------------------- degraded, never critical


def test_stale_daily_run_is_warning_not_critical():
    stale_date = "2026-01-01"
    results = _run_all(_client({
        "pokemon_multi_source_pricing_runs_v1": [
            {"market_date": stale_date, "status": "COMPLETE", "stage": "done", "failure_code": None,
             "updated_at": NOW.isoformat(), "finished_at": NOW.isoformat(), "requests_attempted": 1,
             "target_fingerprint": "abc"},
        ],
    }))
    result = results["pricing.multi_source.run_freshness"]
    assert result.outcome == CheckOutcome.FAILURE
    assert result.severity == Severity.WARNING


def test_missing_daily_run_is_warning_not_critical():
    results = _run_all(_client({"pokemon_multi_source_pricing_runs_v1": []}))
    result = results["pricing.multi_source.run_freshness"]
    assert result.outcome == CheckOutcome.FAILURE
    assert result.severity == Severity.WARNING


def test_stale_ebay_evidence_is_warning():
    results = _run_all(_client({
        "ebay_pricing_runs_v1": [
            {"market_date": "2026-01-01", "status": "COMPLETE",
             "finished_at": (NOW - timedelta(hours=200)).isoformat()},
        ],
    }))
    result = results["pricing.ebay.evidence_freshness"]
    assert result.outcome == CheckOutcome.FAILURE
    assert result.severity == Severity.WARNING


def test_missing_ebay_evidence_is_warning_not_failure_of_canonical_pricing():
    results = _run_all(_client({"ebay_pricing_runs_v1": []}))
    result = results["pricing.ebay.evidence_freshness"]
    assert result.outcome == CheckOutcome.FAILURE
    assert result.severity == Severity.WARNING
    # canonical source guard is unaffected by missing eBay evidence
    assert results["pricing.canonical.source_guard"].outcome == CheckOutcome.HEALTHY


def test_zero_eligible_ebay_estimates_in_successful_run_is_not_reported_unhealthy():
    # No rows in the estimates table simply means the estimator freshness check fails
    # (stale/missing), which is WARNING-level multi-source degradation, not a reported
    # "zero eligible estimates" failure of the run itself. There is no separate
    # "eligible estimate count" signal in health.py to report as unhealthy here.
    results = _run_all(_client({"ebay_active_ask_price_estimates_v1": []}))
    assert results["pricing.ebay.estimator_freshness"].severity in (Severity.WARNING,)
    assert results["pricing.canonical.source_guard"].outcome == CheckOutcome.HEALTHY
    assert results["pricing.multi_source.run_freshness"].outcome == CheckOutcome.HEALTHY


def test_estimator_and_policy_version_drift_detected_and_reported():
    results = _run_all(_client({
        "ebay_active_ask_price_estimates_v1": [
            {"market_date": EXPECTED_MARKET_DATE, "estimator_version": "stale-version"},
        ],
        "pokemon_multi_source_card_prices_v1": [
            {"market_date": EXPECTED_MARKET_DATE, "policy_version": "old-policy"},
        ],
    }))
    result = results["pricing.multi_source.policy_drift"]
    assert result.outcome == CheckOutcome.FAILURE
    assert result.severity == Severity.WARNING
    assert result.observed["observed_estimator"] == "stale-version"
    assert result.observed["observed_policies"] == ["old-policy"]


# --------------------------------------------------------------------------------- source guard: the only CRITICAL


def test_unexpected_non_tcgplayer_canonical_source_is_critical():
    results = _run_all(_client({
        "pokemon_canonical_card_market_prices_latest": [{"source": "eBay"}],
    }))
    result = results["pricing.canonical.source_guard"]
    assert result.outcome == CheckOutcome.FAILURE
    assert result.severity == Severity.CRITICAL
    assert result.failure_code == "NON_TCGPLAYER_SOURCE_IN_CANONICAL_PRICING"


def test_source_guard_db_timeout_is_degraded_not_false_critical():
    results = _run_all(_client(guard_errors={
        "card_variant_price_current_v2": Exception("57014 canceling statement due to statement timeout"),
    }))
    result = results["pricing.canonical.source_guard"]
    assert result.outcome == CheckOutcome.FAILURE
    assert result.severity == Severity.WARNING
    assert result.failure_code == "SOURCE_GUARD_UNVERIFIABLE_TRANSIENT_TIMEOUT"


def test_only_source_guard_check_can_be_critical_across_all_failure_scenarios():
    # Combine every degraded scenario at once; nothing but the source guard may go CRITICAL,
    # and the source guard itself must stay healthy since it isn't contaminated here.
    tables_overrides = {
        "pokemon_multi_source_pricing_runs_v1": [],
        "ebay_pricing_runs_v1": [],
        "ebay_active_ask_price_estimates_v1": [],
        "pokemon_multi_source_card_prices_v1": [],
        "ebay_browse_request_ledger_v1": [],
    }
    results = _run_all(_client(tables_overrides))
    for key, result in results.items():
        if key == "pricing.canonical.source_guard":
            continue
        assert result.severity != Severity.CRITICAL, (key, result.severity)
