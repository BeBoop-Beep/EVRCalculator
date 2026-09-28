from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.pricing_pipeline.contracts import DAILY_REQUEST_LIMIT, digest
from backend.pricing_pipeline.contracts import PHOENIX as PP_PHOENIX
from backend.scripts.freeze_ebay_active_ask_v1 import VERSION as ESTIMATOR_VERSION
from backend.scripts.pokemon_multi_source_card_price_v1 import POLICY_VERSION
from backend.sentinel.checks.pricing import PRICING_SCHEDULER_CHECK_KEY, check_pricing_scheduler
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
        self._count_exact = False
        self._exact_count = None

    def select(self, *args, **kwargs):
        self._count_exact = kwargs.get("count") == "exact"
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
        if self._count_exact:
            self._exact_count = len(self.rows)
        self.rows = self.rows[:n]
        return self

    def execute(self):
        count = self._exact_count
        if self._count_exact and count is None:
            count = len(self.rows)
        return _Result(self.rows, count=count)


class _Result:
    def __init__(self, data, *, count=None):
        self.data = data
        self.count = count


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
    multi_source_run_id = "11111111-1111-1111-1111-111111111111"
    ebay_run_id = "22222222-2222-2222-2222-222222222222"
    manifest = {
        "target_count": 1,
        "cards": [{"canonical_card_id": "card-1"}],
    }
    manifest["selector_fingerprint"] = digest(manifest)
    return {
        "pokemon_multi_source_pricing_runs_v1": [
            {"run_id": multi_source_run_id, "market_date": market_date, "status": "COMPLETE", "stage": "done", "failure_code": None,
             "updated_at": NOW.isoformat(), "finished_at": NOW.isoformat(), "requests_attempted": 10,
             "target_count": 1, "target_fingerprint": manifest["selector_fingerprint"], "manifest": manifest,
             "ebay_pricing_run_id": ebay_run_id},
        ],
        "pokemon_scrape_batches": [
            {"market_date": market_date, "status": "complete"},
        ],
        "ebay_pricing_runs_v1": [
            {"run_id": ebay_run_id, "market_date": market_date, "status": "COMPLETE",
             "finished_at": NOW.isoformat()},
        ],
        "ebay_active_ask_price_estimates_v1": [
            {"id": "estimate-1", "pricing_run_id": ebay_run_id, "market_date": market_date,
             "estimator_version": ESTIMATOR_VERSION},
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


def test_pricing_scheduler_contract_detects_missing_and_valid_managed_block():
    missing = check_pricing_scheduler(CTX, crontab_loader=lambda: "")
    assert missing.outcome == CheckOutcome.FAILURE
    assert missing.failure_code == "EBAY_DAILY_SCHEDULE_MISSING"
    assert missing.severity == Severity.WARNING

    valid = """# BEGIN multi-source-pricing (managed by install_multi_source_pricing_cron.sh)
10 4 * * * /usr/bin/flock -n /tmp/multi-source-pricing.lock -c 'python -m backend.scripts.run_daily_multi_source_card_pricing'
40 4,5,7-20 * * * /usr/bin/flock -n /tmp/multi-source-pricing.lock -c 'python -m backend.scripts.run_daily_multi_source_card_pricing'
20 9 * * * python -m backend.scripts.check_multi_source_pricing_health
# END multi-source-pricing
"""
    healthy = check_pricing_scheduler(CTX, crontab_loader=lambda: valid)
    assert healthy.outcome == CheckOutcome.HEALTHY


def test_recent_completed_scrape_without_ebay_run_is_continuity_gap():
    now = datetime(2026, 9, 28, 16, 0, tzinfo=timezone.utc)  # 09:00 Phoenix
    expected = now.astimezone(PP_PHOENIX).date().isoformat()
    prior = (now.astimezone(PP_PHOENIX).date() - timedelta(days=1)).isoformat()
    client = _client({
        "pokemon_scrape_batches": [
            {"market_date": expected, "status": "complete"},
            {"market_date": prior, "status": "complete"},
        ],
        "ebay_pricing_runs_v1": [
            {"market_date": expected, "status": "COMPLETE", "finished_at": now.isoformat()},
        ],
    })
    registry = build_fast_registry(client=client)
    result = registry.get("pricing.ebay.calendar_continuity").run(
        CheckContext(now=now, runner_identity=CTX.runner_identity)
    )
    assert result.outcome == CheckOutcome.FAILURE
    assert result.severity == Severity.WARNING
    assert prior in result.observed["missing_ebay_dates"]


def test_pre_enforcement_ebay_gaps_are_diagnostic_not_current_failure():
    now = datetime(2026, 9, 27, 16, 0, tzinfo=timezone.utc)
    expected = now.astimezone(PP_PHOENIX).date().isoformat()
    client = _client({
        "pokemon_scrape_batches": [
            {"market_date": day, "status": "complete"}
            for day in ("2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24",
                        "2026-09-25", "2026-09-26", "2026-09-27")
        ],
        "ebay_pricing_runs_v1": [
            {"market_date": day, "status": "COMPLETE", "finished_at": now.isoformat()}
            for day in ("2026-09-21", "2026-09-25", "2026-09-27")
        ],
    })
    registry = build_fast_registry(client=client)
    result = registry.get("pricing.ebay.calendar_continuity").run(
        CheckContext(now=now, runner_identity=CTX.runner_identity)
    )
    assert result.outcome == CheckOutcome.HEALTHY
    assert result.observed["missing_ebay_dates"] == []
    assert result.observed["historical_pre_enforcement_gaps"] == [
        "2026-09-22", "2026-09-23", "2026-09-24", "2026-09-26"
    ]


def test_pricing_checks_registered_exactly_once_in_fast_profile():
    registry = build_fast_registry(client=_client())
    keys = registry.keys()
    for key in PRICING_CHECK_KEYS:
        assert keys.count(key) == 1
    assert set(PRICING_CHECK_KEYS).issubset(set(FAST_CHECK_KEYS))
    assert PRICING_SCHEDULER_CHECK_KEY in FAST_CHECK_KEYS


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


def test_estimate_coverage_follows_linked_ebay_pricing_run_id():
    results = _run_all(_client())
    coverage = results["pricing.ebay.estimate_coverage"]
    assert coverage.outcome == CheckOutcome.HEALTHY
    assert coverage.observed["multi_source_run_id"] == "11111111-1111-1111-1111-111111111111"
    assert coverage.observed["ebay_pricing_run_id"] == "22222222-2222-2222-2222-222222222222"
    assert coverage.observed["pricing_run_id"] == coverage.observed["ebay_pricing_run_id"]
    assert coverage.observed["eligible_estimate_count"] == 1


def test_zero_eligible_ebay_estimates_in_successful_run_has_explicit_warning():
    results = _run_all(_client({"ebay_active_ask_price_estimates_v1": []}))
    coverage = results["pricing.ebay.estimate_coverage"]
    assert coverage.outcome == CheckOutcome.FAILURE
    assert coverage.severity == Severity.WARNING
    assert coverage.failure_code == "EBAY_ZERO_ELIGIBLE_ESTIMATES"
    assert coverage.observed["target_count"] == 1
    assert coverage.observed["eligible_estimate_count"] == 0
    assert results["pricing.canonical.source_guard"].outcome == CheckOutcome.HEALTHY
    assert results["pricing.multi_source.run_freshness"].outcome == CheckOutcome.HEALTHY


def test_target_manifest_content_tamper_is_detected_even_when_stored_fingerprint_is_present():
    tables = _healthy_tables()
    run = dict(tables["pokemon_multi_source_pricing_runs_v1"][0])
    manifest = dict(run["manifest"])
    manifest["cards"] = [{"canonical_card_id": "tampered-card"}]
    run["manifest"] = manifest
    tables["pokemon_multi_source_pricing_runs_v1"] = [run]
    results = _run_all(_CountingClient(tables))
    integrity = results["pricing.multi_source.target_manifest_integrity"]
    assert integrity.outcome == CheckOutcome.FAILURE
    assert integrity.severity == Severity.WARNING
    assert integrity.failure_code == "TARGET_MANIFEST_CONTENT_INVALID"
    assert results["pricing.multi_source.target_freshness"].outcome == CheckOutcome.HEALTHY


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
