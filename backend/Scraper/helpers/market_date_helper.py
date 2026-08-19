from datetime import datetime, timedelta, timezone
from typing import Optional


def resolve_phoenix_market_date(now: Optional[datetime] = None) -> str:
    """Resolve the Arizona business date without relying on UTC DATE coercion."""
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    phoenix = timezone(timedelta(hours=-7), "America/Phoenix")
    return instant.astimezone(phoenix).date().isoformat()
