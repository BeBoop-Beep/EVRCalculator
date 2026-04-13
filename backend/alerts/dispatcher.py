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

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypedDict

import requests

from backend.db.clients.supabase_client import supabase

logger = logging.getLogger(__name__)

_ALERT_TAG = "[alert-dispatcher]"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _get_alerts_enabled() -> bool:
    """Check if alerts are enabled via ALERTS_ENABLED env var."""
    value = os.getenv("ALERTS_ENABLED", "false").strip().lower()
    return value in ("1", "true", "yes")


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
    """Fetch unsent alerts from public.alert_events.
    
    Query:
        SELECT id, alert_type, severity, title, message, payload, created_at
        FROM public.alert_events
        WHERE sent = false
        ORDER BY created_at ASC
        LIMIT %s
    
    Args:
        limit: Maximum number of alerts to fetch (should be >= 1).
    
    Returns:
        List of alert row dicts. Empty list if none found or query fails.
    """
    if limit < 1:
        limit = 1
    
    try:
        result = (
            supabase.table("alert_events")
            .select("id, alert_type, severity, title, message, payload, created_at")
            .eq("sent", False)
            .order("created_at", desc=False)
            .limit(limit)
            .execute()
        )
        
        rows = result.data if result and result.data else []
        logger.info("%s fetched %d pending alert(s)", _ALERT_TAG, len(rows))
        return rows
    
    except Exception as exc:
        logger.error("%s failed to fetch pending alerts: %s", _ALERT_TAG, exc)
        return []


# ---------------------------------------------------------------------------
# Slack message formatting
# ---------------------------------------------------------------------------

def format_slack_message(alert_row: Dict[str, Any]) -> Dict[str, Any]:
    """Format an alert row as a Slack incoming webhook payload.
    
    Returns a Slack message with:
        - Title and severity color
        - Alert type, title, message
        - Created timestamp
        - Key fields from payload (run_id, job_name, status, metrics, etc.)
    
    Args:
        alert_row: Alert row from public.alert_events.
    
    Returns:
        Dict suitable for Slack incoming webhook POST.
    """
    severity = alert_row.get("severity", "info").upper()
    alert_type = alert_row.get("alert_type", "unknown")
    title = alert_row.get("title", "(no title)")
    message = alert_row.get("message", "(no message)")
    created_at = alert_row.get("created_at", "")
    payload = alert_row.get("payload") or {}
    
    # Determine color based on severity
    color_map = {
        "CRITICAL": "danger",      # red
        "ERROR": "danger",         # red
        "WARNING": "warning",      # orange/yellow
        "INFO": "good",            # green
        "DEBUG": "#808080",        # gray
    }
    color = color_map.get(severity, "#808080")
    
    # Build field list from payload
    fields = []
    
    # Priority 1: scrape run context
    if payload.get("run_id"):
        fields.append({
            "title": "Run ID",
            "value": str(payload["run_id"])[:50],
            "short": True,
        })
    if payload.get("job_name"):
        fields.append({
            "title": "Job",
            "value": payload["job_name"],
            "short": True,
        })
    if payload.get("source_system"):
        fields.append({
            "title": "Source",
            "value": payload["source_system"],
            "short": True,
        })
    if payload.get("status"):
        fields.append({
            "title": "Status",
            "value": payload["status"],
            "short": True,
        })
    
    # Priority 2: metrics
    if payload.get("items_attempted") is not None:
        fields.append({
            "title": "Attempted",
            "value": str(payload["items_attempted"]),
            "short": True,
        })
    if payload.get("items_failed") is not None:
        fields.append({
            "title": "Failed",
            "value": str(payload["items_failed"]),
            "short": True,
        })
    if payload.get("rate_limit_events") is not None and payload["rate_limit_events"] > 0:
        fields.append({
            "title": "Rate Limit Events",
            "value": str(payload["rate_limit_events"]),
            "short": True,
        })
    
    # Priority 3: error context
    if payload.get("error_summary"):
        fields.append({
            "title": "Error Summary",
            "value": str(payload["error_summary"])[:100],
            "short": False,
        })
    
    # Build Slack message
    slack_payload = {
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
    
    return slack_payload


# ---------------------------------------------------------------------------
# Slack sending
# ---------------------------------------------------------------------------

def send_slack_alert(alert_row: Dict[str, Any], webhook_url: str) -> bool:
    """Send an alert to Slack via incoming webhook.
    
    Args:
        alert_row: Alert row from public.alert_events.
        webhook_url: Slack incoming webhook URL.
    
    Returns:
        True if the POST was successful (HTTP 200), False otherwise.
        On failure, logs the error but does not raise.
    """
    try:
        payload = format_slack_message(alert_row)
        
        response = requests.post(
            webhook_url,
            json=payload,
            timeout=10,
        )
        
        if response.status_code == 200:
            alert_id = alert_row.get("id", "?")
            logger.info("%s sent alert id=%s to Slack", _ALERT_TAG, alert_id)
            return True
        else:
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
    """Mark an alert as sent in public.alert_events.
    
    Query:
        UPDATE public.alert_events
        SET sent = true, sent_at = NOW()
        WHERE id = %s
    
    This is only called after a successful Slack POST. If this UPDATE fails,
    the alert will be retried on the next run.
    
    Args:
        alert_id: UUID of the alert row to mark sent.
    
    Returns:
        True if the update succeeded, False otherwise.
    """
    try:
        result = (
            supabase.table("alert_events")
            .update({
                "sent": True,
                "sent_at": datetime.now(timezone.utc).isoformat(),
            })
            .eq("id", alert_id)
            .execute()
        )
        
        if result and result.data:
            logger.info("%s marked alert id=%s as sent", _ALERT_TAG, alert_id)
            return True
        else:
            logger.warning("%s mark_alert_sent id=%s returned no data", _ALERT_TAG, alert_id)
            return False
    
    except Exception as exc:
        logger.error("%s failed to mark alert id=%s as sent: %s", _ALERT_TAG, alert_id, exc)
        return False


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def send_pending_alerts(limit: Optional[int] = None) -> AlertSummary:
    """Fetch and send all pending alerts to Slack.
    
    This is the main entry point. It:
        1. Fetches up to `limit` unsent alerts
        2. For each alert:
            a. Formats as Slack message
            b. POSTs to Slack webhook
            c. If successful, marks sent in DB
        3. Continues on failure (does not abort)
        4. Returns a summary of what happened
    
    Only marks alerts sent AFTER successful Slack delivery. Slack failures
    do not mark the alert sent (it will retry on the next run).
    
    Database failures (fetch/mark sent) are logged but do not abort processing.
    
    Args:
        limit: Max alerts to process. Defaults to ALERT_BATCH_SIZE env var or 25.
    
    Returns:
        AlertSummary dict with fetched_count, sent_count, failed_count.
    
    Raises:
        ValueError: If ALERTS_ENABLED=true but SLACK_ALERT_WEBHOOK_URL is missing.
    """
    if not _get_alerts_enabled():
        logger.info("%s ALERTS_ENABLED=false, skipping", _ALERT_TAG)
        return {
            "fetched_count": 0,
            "sent_count": 0,
            "failed_count": 0,
        }
    
    if limit is None:
        limit = _get_batch_size()
    
    webhook_url = _get_slack_webhook_url()  # Raises if missing
    
    # Fetch pending alerts
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
    
    # Process each alert
    for alert in alerts:
        alert_id = alert.get("id", "?")
        
        # Send to Slack
        if not send_slack_alert(alert, webhook_url):
            summary["failed_count"] += 1
            summary["errors"].append(f"alert {alert_id} failed to send to Slack")
            continue
        
        # Mark sent in DB
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


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    """CLI entry point for running the alert dispatcher.
    
    Usage:
        python -m backend.alerts.dispatcher
        python -m backend.alerts.dispatcher --limit 10
    
    Returns:
        0 on success, 1 on error.
    """
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="Send pending scrape alerts to Slack")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max alerts to send (default: ALERT_BATCH_SIZE env or 25)",
    )
    args = parser.parse_args()
    
    try:
        logger.info("%s starting alert dispatch (limit=%s)", _ALERT_TAG, args.limit)
        summary = send_pending_alerts(limit=args.limit)
        logger.info("%s dispatch complete: %s", _ALERT_TAG, summary)
        
        # Exit with error code if any failed (for cron monitoring)
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
