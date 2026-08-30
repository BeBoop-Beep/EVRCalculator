"""Alert dispatcher module for scrape job events."""


def send_pending_alerts(*args, **kwargs):
    # Lazy import keeps ``python -m backend.alerts.dispatcher`` from importing
    # the target module once through this package before runpy executes it.
    from backend.alerts.dispatcher import send_pending_alerts as _send

    return _send(*args, **kwargs)


__all__ = ["send_pending_alerts"]
