"""Production-safe alert dispatcher for scrape job events.

This module reads unsent alerts from the public.alert_events table,
formats them as Slack messages, sends them to the Slack webhook, and marks
them as sent only after successful delivery.

Configuration:
    ALERTS_ENABLED (bool, default: false)  — Enable/disable alert dispatch
    SLACK_ALERT_WEBHOOK_URL (str, required if enabled)  — Incoming webhook URL
    ALERT_BATCH_SIZE (int, default: 25)  — Max alerts to process per run

Usage:
    from backend.alerts.dispatcher import send_pending_alerts

    summary = send_pending_alerts(limit=25)
    print(summary)  # {"fetched": 3, "sent": 3, "failed": 0}
"""

import argparse
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypedDict

import requests

from backend.db.clients.supabase_client import supabase

logger = logging.getLogger(__name__)

_ALERT_TAG = "[alert-dispatcher]"
_FIELD_LABELS = {
    "market_date": "Market Date", "stage": "Stage", "status": "Status",
    "batch_id": "Batch", "progress": "Progress", "missing_sets": "Missing Sets",
    "error_code": "Error Code", "previous_accepted_market_date": "Public Date",
    "runtime_git_sha": "Runtime SHA", "duration": "Duration",
    "canonical_key": "Set", "queue_job_id": "Queue Job",
}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _get_alerts_enabled() -> bool:
    """Check if alerts are enabled via ALERTS_ENABLED env var."""
    value = os.getenv("ALERTS_ENABLED", "false").strip().lower()
    return value in ("1", "true", "yes")


def _env_true(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes")


def _positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        return max(1, int(raw))
    except ValueError:
        logger.warning("%s %s invalid (%s), using default %s", _ALERT_TAG, name, raw, default)
        return default


def _get_slack_webhook_url() -> str:
    """Get Slack incoming webhook URL from environment.

    Raises:
        ValueError: If SLACK_ALERT_WEBHOOK_URL is not set.
    """
    url = os.getenv("SLACK_ALERT_WEBHOOK_URL", "").strip()
    if not url:
        raise ValueError(
            "SLACK_ALERT_WEBHOOK_URL is not set. Set it to your Slack incoming webhook URL "
            "or disable alerts by setting ALERTS_ENABLED=false"
        )
    return url


def _get_batch_size() -> int:
    """Get max batch size for alert processing."""
    value = os.getenv("ALERT_BATCH_SIZE", "25").strip()
    try:
        return max(1, int(value))
    except ValueError:
        logger.warning("%s ALERT_BATCH_SIZE invalid (%s), using default 25", _ALERT_TAG, value)
        return 25


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Type definitions
# ---------------------------------------------------------------------------

class AlertSummary(TypedDict, total=False):
    """Summary of alert dispatch run."""
    fetched_count: int
    sent_count: int
    failed_count: int
    errors: List[str]


# ---------------------------------------------------------------------------
# Alert fetching
# ---------------------------------------------------------------------------

def fetch_pending_alerts(limit: int) -> List[Dict[str, Any]]:
    """Fetch unsent, unsuppressed alerts from public.alert_events."""
    if limit < 1:
        limit = 1

    try:
        result = (
            supabase.table("alert_events")
            .select("id, alert_type, severity, title, message, payload, created_at")
            .eq("sent", False)
            .is_("suppressed_at", "null")
            .order("created_at", desc=False)
            .limit(limit)
            .execute()
        )
        rows = result.data if result and result.data else []
        logger.info("%s fetched %d pending alert(s)", _ALERT_TAG, len(rows))
        return rows
    except Exception as exc:
        logger.error("%s failed to fetch pending alerts: %s", _ALERT_TAG, exc)
        # A database read failure is not an empty queue. Raising makes cron and
        # deployment monitoring see a nonzero dispatcher exit instead of a
        # false-success run that silently leaves every alert pending.
        raise RuntimeError("pending alert queue could not be read") from exc


# ---------------------------------------------------------------------------
# Slack message formatting
# ---------------------------------------------------------------------------

def format_slack_message(alert_row: Dict[str, Any]) -> Dict[str, Any]:
    """Format an alert row as a Slack incoming-webhook payload."""
    severity = alert_row.get("severity", "info").upper()
    alert_type = alert_row.get("alert_type", "unknown")
    title = alert_row.get("title", "(no title)")
    message = alert_row.get("message", "(no message)")
    created_at = alert_row.get("created_at", "")
    payload = alert_row.get("payload") or {}

    color_map = {
        "CRITICAL": "danger",
        "ERROR": "danger",
        "WARNING": "warning",
        "INFO": "good",
        "DEBUG": "#808080",
    }
    color = color_map.get(severity, "#808080")
    fields = []

    # The allowlist deliberately excludes secrets and raw provider payloads
    # even if a caller accidentally includes them.
    for key, label in _FIELD_LABELS.items():
        value = payload.get(key)
        if value is None or value == "":
            continue
        if isinstance(value, (list, tuple)):
            value = ", ".join(str(item) for item in value[:20])
        fields.append({"title": label, "value": str(value)[:500], "short": key not in {"missing_sets"}})

    if payload.get("run_id"):
        fields.append({"title": "Run ID", "value": str(payload["run_id"])[:50], "short": True})
    if payload.get("job_name"):
        fields.append({"title": "Job", "value": payload["job_name"], "short": True})
    if payload.get("source_system"):
        fields.append({"title": "Source", "value": payload["source_system"], "short": True})
    if payload.get("status"):
        fields.append({"title": "Status", "value": payload["status"], "short": True})
    if payload.get("items_attempted") is not None:
        fields.append({"title": "Attempted", "value": str(payload["items_attempted"]), "short": True})
    if payload.get("items_failed") is not None:
        fields.append({"title": "Failed", "value": str(payload["items_failed"]), "short": True})
    if payload.get("rate_limit_events") is not None and payload["rate_limit_events"] > 0:
        fields.append({"title": "Rate Limit Events", "value": str(payload["rate_limit_events"]), "short": True})
    if payload.get("error_summary"):
        fields.append({"title": "Error Summary", "value": str(payload["error_summary"])[:100], "short": False})

    return {
        "text": f"{severity} | {alert_type}",
        "username": "Scrape Alert",
        "icon_emoji": ":warning:" if severity in ("WARNING", "CRITICAL", "ERROR") else ":info:",
        "attachments": [
            {
                "fallback": f"{alert_type}: {title}",
                "color": color,
                "title": title,
                "text": message,
                "fields": fields,
                "footer": alert_type,
                "footer_icon": "https://a.slack-edge.com/80588/img/default_application_icon.png",
                "ts": int(datetime.fromisoformat(created_at.replace("Z", "+00:00")).timestamp())
                if created_at
                else int(datetime.now(timezone.utc).timestamp()),
            }
        ],
    }


# ---------------------------------------------------------------------------
# Slack sending
# ---------------------------------------------------------------------------

def send_slack_alert(alert_row: Dict[str, Any], webhook_url: str) -> bool:
    """Send an alert to Slack via incoming webhook."""
    try:
        payload = format_slack_message(alert_row)
        response = requests.post(
            webhook_url,
            json=payload,
            timeout=max(1.0, float(os.getenv("SLACK_ALERT_TIMEOUT_SECONDS", "10"))),
        )
        if response.status_code == 200:
            alert_id = alert_row.get("id", "?")
            logger.info("%s sent alert id=%s to Slack", _ALERT_TAG, alert_id)
            return True
        alert_id = alert_row.get("id", "?")
        logger.warning(
            "%s Slack POST failed for alert id=%s: HTTP %d %s",
            _ALERT_TAG,
            alert_id,
            response.status_code,
            response.text[:200],
        )
        return False
    except requests.Timeout:
        alert_id = alert_row.get("id", "?")
        logger.error("%s Slack POST timeout for alert id=%s", _ALERT_TAG, alert_id)
        return False
    except requests.RequestException as exc:
        alert_id = alert_row.get("id", "?")
        logger.error("%s Slack POST failed for alert id=%s: %s", _ALERT_TAG, alert_id, exc)
        return False
    except Exception as exc:
        alert_id = alert_row.get("id", "?")
        logger.error("%s unexpected error sending alert id=%s: %s", _ALERT_TAG, alert_id, exc)
        return False


# ---------------------------------------------------------------------------
# Alert marking
# ---------------------------------------------------------------------------

def mark_alert_sent(alert_id: str) -> bool:
    """Mark an alert sent only after successful Slack delivery."""
    try:
        result = (
            supabase.table("alert_events")
            .update({"sent": True, "sent_at": datetime.now(timezone.utc).isoformat()})
            .eq("id", alert_id)
            .execute()
        )
        if result and result.data:
            logger.info("%s marked alert id=%s as sent", _ALERT_TAG, alert_id)
            return True
        logger.warning("%s mark_alert_sent id=%s returned no data", _ALERT_TAG, alert_id)
        return False
    except Exception as exc:
        logger.error("%s failed to mark alert id=%s as sent: %s", _ALERT_TAG, alert_id, exc)
        return False


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def send_pending_alerts(limit: Optional[int] = None) -> AlertSummary:
    """Fetch and send pending alerts, marking rows only after delivery."""
    if not _get_alerts_enabled():
        logger.info("%s ALERTS_ENABLED=false, skipping", _ALERT_TAG)
        return {"fetched_count": 0, "sent_count": 0, "failed_count": 0}

    if limit is None:
        limit = _get_batch_size()

    webhook_url = _get_slack_webhook_url()
    try:
        backlog = get_dispatcher_health()
        logger.info(
            "%s backlog pending=%s oldest_age_minutes=%s",
            _ALERT_TAG,
            backlog["pending_unsuppressed_count"],
            backlog["oldest_pending_age_minutes"],
        )
    except Exception as exc:  # delivery may still proceed from the normal fetch
        logger.error("%s backlog health query failed: %s", _ALERT_TAG, exc)

    alerts = fetch_pending_alerts(limit)
    summary: AlertSummary = {
        "fetched_count": len(alerts),
        "sent_count": 0,
        "failed_count": 0,
        "errors": [],
    }
    if not alerts:
        logger.info("%s no pending alerts to send", _ALERT_TAG)
        return summary

    for alert in alerts:
        alert_id = alert.get("id", "?")
        if not send_slack_alert(alert, webhook_url):
            summary["failed_count"] += 1
            summary["errors"].append(f"alert {alert_id} failed to send to Slack")
            continue
        if not mark_alert_sent(alert_id):
            summary["failed_count"] += 1
            summary["errors"].append(f"alert {alert_id} marked sent in DB failed")
            continue
        summary["sent_count"] += 1

    logger.info(
        "%s completed: fetched=%d sent=%d failed=%d",
        _ALERT_TAG,
        summary["fetched_count"],
        summary["sent_count"],
        summary["failed_count"],
    )
    return summary


def get_dispatcher_health() -> Dict[str, Any]:
    """Read delivery/configuration health without exposing webhook contents.

    Configuration alone is not sufficient for a healthy dispatcher. A queue
    whose oldest unsuppressed row is beyond the configured critical-age
    threshold is unhealthy even when ALERTS_ENABLED and the webhook are set.
    A recent successful send is reported separately as delivery progress; it
    does not make an already-stale backlog healthy.
    """
    now = datetime.now(timezone.utc)
    result = (
        supabase.table("alert_events")
        .select("id,created_at", count="exact")
        .eq("sent", False)
        .is_("suppressed_at", "null")
        .order("created_at", desc=False)
        .limit(1)
        .execute()
    )
    rows = list(result.data or [])
    pending_count = int(getattr(result, "count", None) or len(rows))
    oldest = rows[0].get("created_at") if rows else None
    oldest_dt = _parse_timestamp(oldest)
    age_minutes = None
    if oldest_dt:
        age_minutes = max(0, int((now - oldest_dt).total_seconds() / 60))

    sent_result = (
        supabase.table("alert_events")
        .select("sent_at")
        .eq("sent", True)
        .order("sent_at", desc=True)
        .limit(1)
        .execute()
    )
    sent_rows = list(sent_result.data or [])
    last_sent_at = sent_rows[0].get("sent_at") if sent_rows else None
    last_sent_dt = _parse_timestamp(last_sent_at)

    warning_count = _positive_int_env("ALERT_BACKLOG_WARNING_COUNT", 20)
    critical_age = _positive_int_env("ALERT_BACKLOG_CRITICAL_AGE_MINUTES", 10)
    backlog_warning = pending_count >= warning_count
    backlog_critical = age_minutes is not None and age_minutes >= critical_age
    backlog_healthy = not backlog_critical

    recent_delivery = bool(
        last_sent_dt
        and (now - last_sent_dt).total_seconds() >= 0
        and (now - last_sent_dt).total_seconds() / 60 < critical_age
    )
    delivery_progress_healthy = pending_count == 0 or not backlog_critical or recent_delivery

    alerts_enabled = _get_alerts_enabled()
    webhook_configured = bool(os.getenv("SLACK_ALERT_WEBHOOK_URL", "").strip())
    dispatcher_scheduled = _env_true("ALERT_DISPATCHER_SCHEDULED")
    watchdog_scheduled = _env_true("MARKET_FRESHNESS_WATCHDOG_SCHEDULED")
    production_mode = any(
        os.getenv(name, "").strip().lower() in {"production", "prod"}
        for name in ("APP_ENV", "ENVIRONMENT", "NODE_ENV")
    )
    schedules_required = _env_true("ALERT_SCHEDULES_REQUIRED") or production_mode

    healthy = (
        alerts_enabled
        and webhook_configured
        and backlog_healthy
        and delivery_progress_healthy
    )
    if schedules_required:
        healthy = healthy and dispatcher_scheduled and watchdog_scheduled

    health = {
        "alerts_enabled": alerts_enabled,
        "slack_webhook_configured": webhook_configured,
        "dispatcher_scheduled": dispatcher_scheduled,
        "freshness_watchdog_scheduled": watchdog_scheduled,
        "schedules_required": schedules_required,
        "production_mode": production_mode,
        "database_connected": True,
        "pending_unsuppressed_count": pending_count,
        "oldest_pending_created_at": oldest,
        "oldest_pending_age_minutes": age_minutes,
        "last_sent_at": last_sent_at,
        "backlog_warning_count": warning_count,
        "backlog_critical_age_minutes": critical_age,
        "backlog_warning": backlog_warning,
        "backlog_critical": backlog_critical,
        "backlog_healthy": backlog_healthy,
        "recent_delivery": recent_delivery,
        "delivery_progress_healthy": delivery_progress_healthy,
        "healthy": healthy,
    }

    if backlog_warning:
        logger.warning("%s ALERT BACKLOG pending=%s", _ALERT_TAG, pending_count)
    if backlog_critical:
        logger.error("%s ALERT BACKLOG oldest_age_minutes=%s", _ALERT_TAG, age_minutes)
    return health


def send_test_message() -> bool:
    """Send exactly one explicit test message; never queues or mutates an event."""
    return send_slack_alert(
        {
            "id": "health-check",
            "alert_type": "dispatcher_test",
            "severity": "info",
            "title": "✅ Alert dispatcher test",
            "message": "Explicit operator-requested Slack delivery test.",
            "payload": {"stage": "dispatcher", "status": "healthy"},
        },
        _get_slack_webhook_url(),
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    """CLI entry point for running the alert dispatcher."""
    parser = argparse.ArgumentParser(description="Send pending scrape alerts to Slack")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max alerts to send (default: ALERT_BATCH_SIZE env or 25)",
    )
    parser.add_argument(
        "--health",
        "--health-check",
        dest="health_check",
        action="store_true",
        help="Check configuration, database connectivity, and pending backlog",
    )
    parser.add_argument(
        "--send-test",
        action="store_true",
        help="Send one explicit test message (requires --health-check)",
    )
    args = parser.parse_args()
    if args.send_test and not args.health_check:
        parser.error("--send-test requires --health-check")

    try:
        if args.health_check:
            health = get_dispatcher_health()
            if args.send_test:
                health["test_message_sent"] = send_test_message()
            print(json.dumps(health, indent=2, sort_keys=True))
            return 0 if health["database_connected"] and health["healthy"] and (
                not args.send_test or health.get("test_message_sent")
            ) else 1

        logger.info("%s starting alert dispatch (limit=%s)", _ALERT_TAG, args.limit)
        summary = send_pending_alerts(limit=args.limit)
        logger.info("%s dispatch complete: %s", _ALERT_TAG, summary)
        return 0 if summary["failed_count"] == 0 else 1
    except ValueError as exc:
        logger.error("%s config error: %s", _ALERT_TAG, exc)
        return 1
    except Exception as exc:
        logger.exception("%s unexpected error: %s", _ALERT_TAG, exc)
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
