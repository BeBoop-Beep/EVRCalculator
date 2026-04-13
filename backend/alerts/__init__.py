"""Alert dispatcher module for scrape job events."""

from backend.alerts.dispatcher import send_pending_alerts

__all__ = ["send_pending_alerts"]
