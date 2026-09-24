"""Quota authority policy for eBay pricing pipelines (V2 design, pure logic; no I/O, no schema change yet).

Two authorities cooperate:
  * the PROVIDER's reported limit is the external ceiling (Developer Analytics getRateLimits, per API resource bucket);
  * the application's DB ledger is the atomic, fail-closed guard across every host (see ebay_api_budget_ledger_v2).

usable_limit = verified provider quota - explicit safety reserve. A pipeline never spends 100% of a quota by design.
Provider analytics are advisory for *identity and ceiling verification* and are NOT real time (observed lag in the P6.5
probe), so they are never used for per-request accounting, and an unavailable/204 response is never read as zero or as
unlimited quota.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

# Buckets that the daily pipelines may draw from. Browse methods other than getItems share `buy.browse`; getItems has
# its own pool (`buy.browse.item.bulk`); Marketplace Insights is its own API/bucket (`buy.marketplaceinsight`).
BUCKET_BROWSE = "buy.browse"
BUCKET_BROWSE_BULK = "buy.browse.item.bulk"
BUCKET_INSIGHTS = "buy.marketplaceinsight"

HEALTHY, DEGRADED_LAST_KNOWN, FAIL_CLOSED = "HEALTHY", "DEGRADED_LAST_KNOWN_VERIFIED", "FAIL_CLOSED"
PROVIDER_OK = "PROVIDER_USAGE_OK"


@dataclass(frozen=True)
class QuotaPolicy:
    safety_reserve_share: float = 0.10       # never plan to consume more than 90% of the verified quota
    min_reserve_requests: int = 100
    max_verification_age: timedelta = timedelta(hours=36)  # how long a verified ceiling may be trusted when analytics fail
    hard_cap: int | None = None              # optional pipeline-level cap (V1 stays at 1000 and is not changed here)


@dataclass(frozen=True)
class KeysetIdentity:
    """Identifies WHICH quota we are drawing from. A ledger row is only valid for the keyset it was verified for."""
    environment: str        # PRODUCTION / SANDBOX
    client_id_sha256: str   # hash of the App ID, never the ID itself


@dataclass(frozen=True)
class QuotaDecision:
    mode: str
    usable_limit: int
    remaining: int
    reason: str

    @property
    def may_call(self) -> bool:
        return self.mode != FAIL_CLOSED and self.remaining > 0


def usable_limit(verified_limit: int, policy: QuotaPolicy = QuotaPolicy()) -> int:
    reserve = max(policy.min_reserve_requests, int(verified_limit * policy.safety_reserve_share))
    usable = max(0, verified_limit - reserve)
    return min(usable, policy.hard_cap) if policy.hard_cap is not None else usable


def window_bounds(reset_at: datetime, window_seconds: int) -> tuple[datetime, datetime]:
    """The provider window is defined by its own reset time, not by a fixed local-day boundary (the reset follows the
    Pacific clock, which drifts one hour against America/Phoenix in winter)."""
    return reset_at - timedelta(seconds=window_seconds), reset_at


def authorize(*, verified_limit: int | None, verified_at: datetime | None, provider_state: str | None,
              provider_remaining: int | None, ledger_healthy: bool, ledger_reserved: int, now: datetime,
              expected_keyset: KeysetIdentity, verified_keyset: KeysetIdentity | None,
              policy: QuotaPolicy = QuotaPolicy()) -> QuotaDecision:
    """Decide whether and how much a pipeline may spend from one bucket right now."""
    if not ledger_healthy:
        return QuotaDecision(FAIL_CLOSED, 0, 0, "LEDGER_UNAVAILABLE")
    if verified_limit is None or verified_limit <= 0 or verified_at is None or verified_keyset is None:
        return QuotaDecision(FAIL_CLOSED, 0, 0, "QUOTA_NEVER_VERIFIED")
    if verified_keyset != expected_keyset:
        return QuotaDecision(FAIL_CLOSED, 0, 0, "KEYSET_IDENTITY_CHANGED")
    limit = usable_limit(verified_limit, policy)
    remaining = max(0, limit - ledger_reserved)
    if provider_state == PROVIDER_OK:
        if provider_remaining is not None:
            # provider's own remaining, less the same reserve, is a second ceiling (it may include other consumers)
            remaining = min(remaining, max(0, provider_remaining - (verified_limit - limit)))
        return QuotaDecision(HEALTHY, limit, remaining, "PROVIDER_VERIFIED")
    age = now - verified_at
    if age <= policy.max_verification_age:
        # analytics down / 204 / error: keep working under the LAST verified ceiling minus reserve; never unlimited
        return QuotaDecision(DEGRADED_LAST_KNOWN, limit, remaining, f"PROVIDER_USAGE_{provider_state or 'UNAVAILABLE'}_WITHIN_VERIFICATION_WINDOW")
    return QuotaDecision(FAIL_CLOSED, 0, 0, "QUOTA_VERIFICATION_STALE")


def verification_from_provider(limits: list[Mapping[str, Any]], bucket: str) -> dict[str, Any] | None:
    """Pick the verified daily limit for one bucket from a normalized provider snapshot (86400s window preferred)."""
    rows = [x for x in limits if x.get("resource") == bucket and x.get("limit")]
    if not rows:
        return None
    daily = [x for x in rows if x.get("time_window_seconds") in (86400, 86399)] or rows
    best = max(daily, key=lambda x: x["time_window_seconds"] or 0)
    return {"bucket": bucket, "verified_limit": int(best["limit"]), "provider_reported_used": best.get("count"),
            "provider_reported_remaining": best.get("remaining"), "reset_at": best.get("reset"),
            "window_seconds": best.get("time_window_seconds")}
