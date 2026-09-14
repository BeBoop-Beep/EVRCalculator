from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from backend.sentinel.checks.authorities import (
    CANONICAL_LEGACY_RUNNING_GRACE_SECONDS,
    check_alert_delivery,
    check_market_freshness,
    check_post_scrape_publication_audit,
    check_publication_batch_gate,
    check_scrape_queue_leases,
    check_set_page_generation,
)
from backend.sentinel.models import CheckOutcome, RunnerIdentity
from backend.sentinel.registry import CheckContext


NOW = datetime(2026, 9, 11, 20, 0, tzinfo=timezone.utc)
CTX = CheckContext(
    now=NOW,
    runner_identity=RunnerIdentity(component="sentinel", host="test", build_sha="sha"),
)


class _Result:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _Query:
    def __init__(self, rows):
        self.rows = [dict(row) for row in rows]
        self.want_count = False
        self.total_before_limit = None

    def select(self, *args, **kwargs):
        self.want_count = kwargs.get("count") == "exact"
        return self

    def eq(self, key, value):
        self.rows = [row for row in self.rows if row.get(key) == value]
        return self

    def limit(self, n):
        self.total_before_limit = len(self.rows)
        self.rows = self.rows[:n]
        return self

    def execute(self):
        count = None
        if self.want_count:
            count = self.total_before_limit if self.total_before_limit is not None else len(self.rows)
        return _Result(self.rows, count)


class _Client:
    def __init__(self, tables):
        self.tables = tables

    def table(self, name):
        return _Query(self.tables.get(name, []))


def _healthy_alert_health():
    return {
        "database_connected": True,
        "alerts_enabled": True,
        "slack_webhook_configured": True,
        "dispatcher_scheduled": True,
        "freshness_watchdog_scheduled": True,
        "backlog_healthy": True,
        "delivery_progress_healthy": True,
        "healthy": True,
        "pending_unsuppressed_count": 0,
        "oldest_pending_age_minutes": None,
        "last_sent_at": "2026-09-11T19:55:00Z",
    }


def test_alert_delivery_healthy_uses_existing_health_contract():
    result = check_alert_delivery(CTX, health_loader=_healthy_alert_health)
    assert result.outcome == CheckOutcome.HEALTHY


def test_alert_delivery_disabled_is_critical_failure():
    health = _healthy_alert_health()
    health["alerts_enabled"] = False
    health["healthy"] = False
    result = check_alert_delivery(CTX, health_loader=lambda: health)
    assert result.failure_code == "alert_delivery_disabled"


def test_alert_delivery_detects_unconfirmed_schedules_even_if_other_fields_are_good():
    health = _healthy_alert_health()
    health["freshness_watchdog_scheduled"] = False
    result = check_alert_delivery(CTX, health_loader=lambda: health)
    assert result.failure_code == "alert_schedules_unconfirmed"


def test_alert_delivery_detects_stalled_backlog():
    health = _healthy_alert_health()
    health["backlog_healthy"] = False
    result = check_alert_delivery(CTX, health_loader=lambda: health)
    assert result.failure_code == "alert_backlog_stalled"


def test_market_freshness_never_queues_and_maps_healthy_report():
    calls = []

    def runner(**kwargs):
        calls.append(kwargs)
        return {
            "healthy": True,
            "market_date": "2026-09-11",
            "failure_count": 0,
            "failures": [],
            "state": {"authority_dates": {"set_value": "2026-09-11"}},
        }

    result = check_market_freshness(CTX, client=object(), watchdog_runner=runner)
    assert result.outcome == CheckOutcome.HEALTHY
    assert calls[0]["queue_failures"] is False


def test_market_freshness_maps_watchdog_load_failure():
    result = check_market_freshness(
        CTX,
        client=object(),
        watchdog_runner=lambda **kwargs: {
            "healthy": False,
            "execution_failed": True,
            "market_date": "2026-09-11",
            "failure_count": 1,
            "failures": [{"alert_type": "market_watchdog_execution_failed", "failure_class": "state_load_failed"}],
            "state": {},
        },
    )
    assert result.failure_code == "market_watchdog_state_load_failed"


def test_market_freshness_uses_deterministic_dominant_failure():
    failures = [
        {"alert_type": "market_snapshot_date_divergence", "failure_class": "authority_date_mismatch"},
        {"alert_type": "batch_not_created", "failure_class": "missing_batch"},
    ]
    result = check_market_freshness(
        CTX,
        client=object(),
        watchdog_runner=lambda **kwargs: {
            "healthy": False,
            "execution_failed": False,
            "market_date": "2026-09-11",
            "failure_count": 2,
            "failures": failures,
            "state": {},
        },
    )
    assert result.failure_code == "batch_not_created"
    assert len(result.evidence["failures"]) == 2


def test_scrape_queue_future_lease_is_healthy():
    client = _Client({"scrape_jobs": [{
        "id": 1,
        "status": "running",
        "started_at": (NOW - timedelta(minutes=5)).isoformat(),
        "lease_expires_at": (NOW + timedelta(minutes=5)).isoformat(),
    }]})
    result = check_scrape_queue_leases(CTX, client=client)
    assert result.outcome == CheckOutcome.HEALTHY


def test_scrape_queue_expired_lease_is_failure():
    client = _Client({"scrape_jobs": [{
        "id": 1,
        "status": "running",
        "started_at": (NOW - timedelta(minutes=10)).isoformat(),
        "lease_expires_at": (NOW - timedelta(seconds=1)).isoformat(),
    }]})
    result = check_scrape_queue_leases(CTX, client=client)
    assert result.failure_code == "scrape_job_lease_expired"


def test_scrape_queue_legacy_running_grace_matches_canonical_watchdog_semantics():
    client = _Client({"scrape_jobs": [{
        "id": 1,
        "status": "running",
        "started_at": (NOW - timedelta(seconds=CANONICAL_LEGACY_RUNNING_GRACE_SECONDS + 1)).isoformat(),
        "lease_expires_at": None,
    }]})
    result = check_scrape_queue_leases(CTX, client=client)
    assert result.failure_code == "scrape_job_lease_expired"
    assert result.evidence["stale_jobs"][0]["stale_reason"] == "legacy_running_grace_exceeded"


def test_scrape_queue_recent_legacy_running_row_is_not_prematurely_failed():
    client = _Client({"scrape_jobs": [{
        "id": 1,
        "status": "running",
        "started_at": (NOW - timedelta(minutes=30)).isoformat(),
        "lease_expires_at": None,
    }]})
    assert check_scrape_queue_leases(CTX, client=client).outcome == CheckOutcome.HEALTHY


def test_scrape_grace_constant_is_pinned_to_canonical_db_watchdog_default():
    root = Path(__file__).resolve().parents[4]
    sql = (root / "backend/db/migrations/048_scrape_queue_batch_lease_orchestration.sql").read_text(encoding="utf-8")
    assert f"p_legacy_running_grace_seconds INTEGER DEFAULT {CANONICAL_LEGACY_RUNNING_GRACE_SECONDS}" in sql


def _decision(**overrides):
    values = dict(
        allowed=True,
        reason="ok",
        reason_code="allowed_complete",
        gated=True,
        mode="required",
        override=False,
        market_date="2026-09-11",
        batch_id=48,
        batch_status="complete",
        missing_set_count=0,
        expected_set_count=165,
        promoted_at="2026-09-11T08:57:00Z",
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_publication_gate_complete_batch_is_healthy():
    result = check_publication_batch_gate(
        CTX, client=object(), gate_evaluator=lambda *args, **kwargs: _decision()
    )
    assert result.outcome == CheckOutcome.HEALTHY


def test_publication_gate_running_batch_is_neutral_not_duplicate_freshness_alarm():
    result = check_publication_batch_gate(
        CTX,
        client=object(),
        gate_evaluator=lambda *args, **kwargs: _decision(
            allowed=False, reason_code="blocked_incomplete", batch_status="running"
        ),
    )
    assert result.outcome == CheckOutcome.HEALTHY
    assert result.observed["publication_eligible"] is False


def test_publication_gate_terminal_incomplete_is_failure():
    result = check_publication_batch_gate(
        CTX,
        client=object(),
        gate_evaluator=lambda *args, **kwargs: _decision(
            allowed=False, reason_code="blocked_incomplete", batch_status="failed"
        ),
    )
    assert result.failure_code == "publication_batch_terminal_incomplete"


def test_publication_gate_unavailable_and_bypass_fail_closed():
    unavailable = check_publication_batch_gate(
        CTX,
        client=object(),
        gate_evaluator=lambda *args, **kwargs: _decision(
            allowed=False, reason_code="blocked_authority_unavailable", batch_status=None
        ),
    )
    assert unavailable.failure_code == "publication_gate_authority_unavailable"
    bypassed = check_publication_batch_gate(
        CTX,
        client=object(),
        gate_evaluator=lambda *args, **kwargs: _decision(
            allowed=True, reason_code="disabled_explicitly", gated=False, mode="disabled"
        ),
    )
    assert bypassed.failure_code == "publication_gate_bypassed"


def _generation_client(*, expected=7, completed=7, row_count=7, status="published", validation=True):
    generation_id = "11111111-1111-1111-1111-111111111111"
    return _Client({
        "pokemon_set_page_snapshot_current_generation": [{"scope": "pokemon", "generation_id": generation_id}],
        "pokemon_set_page_snapshot_generations": [{
            "id": generation_id,
            "scope": "pokemon",
            "status": status,
            "expected_set_count": expected,
            "completed_set_count": completed,
            "validation_passed": validation,
            "published_at": "2026-09-11T03:54:56Z" if status == "published" else None,
            "generation_fingerprint": "fp",
        }],
        "pokemon_set_page_snapshot_generation_rows": [
            {"generation_id": generation_id, "set_id": f"set-{i}"} for i in range(row_count)
        ],
    })


def test_set_generation_uses_dynamic_expected_count_not_magic_number():
    result = check_set_page_generation(CTX, client=_generation_client(expected=7, completed=7, row_count=7))
    assert result.outcome == CheckOutcome.HEALTHY
    assert result.observed["expected_set_count"] == 7


def test_set_generation_detects_completion_and_row_count_mismatch():
    completion = check_set_page_generation(CTX, client=_generation_client(expected=7, completed=6, row_count=7))
    assert completion.failure_code == "setpage_generation_completion_mismatch"
    rows = check_set_page_generation(CTX, client=_generation_client(expected=7, completed=7, row_count=6))
    assert rows.failure_code == "setpage_generation_row_count_mismatch"


def test_set_generation_missing_pointer_is_failure():
    result = check_set_page_generation(CTX, client=_Client({}))
    assert result.failure_code == "setpage_generation_pointer_missing"


class _AuditReport:
    def __init__(self, payload):
        self.payload = payload

    def to_dict(self):
        return dict(self.payload)


def test_post_scrape_audit_healthy_and_failure_are_compact():
    healthy = check_post_scrape_publication_audit(
        CTX,
        client=object(),
        audit_runner=lambda client: _AuditReport({
            "market_date": "2026-09-11", "phase": "post-scrape", "passed": True,
            "set_count": 165, "failed_set_count": 0, "failed_sets": [], "failed_by_section": {},
        }),
    )
    assert healthy.outcome == CheckOutcome.HEALTHY

    failed = check_post_scrape_publication_audit(
        CTX,
        client=object(),
        audit_runner=lambda client: _AuditReport({
            "market_date": "2026-09-11", "phase": "post-scrape", "passed": False,
            "error": None, "set_count": 165, "failed_set_count": 2,
            "failed_sets": ["a", "b"], "failed_by_section": {"Set Value": ["a", "b"]},
            "sets": [{"huge": "payload"}] * 100,
        }),
    )
    assert failed.failure_code == "publication_audit_failed"
    assert "sets" not in failed.evidence
    assert failed.evidence["failed_sets"] == ["a", "b"]
