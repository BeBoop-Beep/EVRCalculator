"""ebay_api_budget_policy_v2: provider-window, resource-bucket request budget.

Authorities (never conflated):
  * provider analytics  -> verify the ceiling, the window and the keyset (QuotaVerifier)
  * database ledger     -> per-request accounting across hosts (PoolLedger -> reserve_ebay_api_request_v2)
The provider counter lags, so it is never used to reconcile the ledger downward. Phoenix stays the market-date clock; the
quota window is the provider's own reset window. Pools never borrow from each other: each PoolLedger reserves in exactly
one bucket, and RoutedBrowseHTTP picks the ledger from the URL, failing closed on an unmapped operation.
"""
from __future__ import annotations

import hashlib
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping

from backend.pricing_pipeline import ebay_quota_policy as policy
from backend.pricing_pipeline.contracts import PipelineError
from backend.scripts.index_fair_value_ebay_evidence_collector import BrowseHTTP, BudgetExhausted

POLICY_VERSION = "ebay_api_budget_policy_v2"
API_NAME = "Browse"
STANDARD = "BUY_BROWSE_STANDARD"
BULK = "BUY_BROWSE_BULK_ITEMS"
PROVIDER_RESOURCE = {STANDARD: policy.BUCKET_BROWSE, BULK: policy.BUCKET_BROWSE_BULK}
MAX_VERIFICATION_AGE = timedelta(hours=36)


def keyset_identity(environment: str, client_id: str) -> str:
    """Environment plus a hash of the App ID (the ID itself is never stored)."""
    return f"{environment}:{hashlib.sha256(client_id.encode()).hexdigest()[:32]}"


def bucket_for_url(url: str) -> str:
    """Attribution is deliberately conservative: search and single getItem both draw from the standard pool because the
    provider's attribution of getItem is inconclusive; only a getItems (?item_ids=) call may use the bulk pool."""
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.rstrip("/")
    if path == "/buy/browse/v1/item_summary/search" or path.startswith("/buy/browse/v1/item/"):
        return STANDARD
    if path == "/buy/browse/v1/item" and "item_ids" in urllib.parse.parse_qs(parsed.query):
        return BULK
    raise PipelineError("UNMAPPED_BROWSE_OPERATION", path)


class PoolLedger:
    """Reserves in ONE bucket. `reserve()` matches the interface BrowseHTTP expects."""

    def __init__(self, client: Any, keyset: str, bucket: str) -> None:
        if bucket not in (STANDARD, BULK):
            raise ValueError(bucket)
        self.client, self.keyset, self.bucket = client, keyset, bucket

    RETRY_ATTEMPTS = 4

    def reserve(self, market_date: str | None = None, sleep: Callable[[float], None] | None = None) -> None:
        """Reserve one request. Transient database stalls (statement timeout / gateway errors) are retried a few times with
        short backoff; a cancelled statement is not committed, so a retry can only over-count, never under-count."""
        import time

        sleep = sleep or time.sleep
        for attempt in range(self.RETRY_ATTEMPTS):
            try:
                self.client.rpc("reserve_ebay_api_request_v2", {"p_keyset": self.keyset, "p_api": API_NAME, "p_bucket": self.bucket}).execute()
                return
            except Exception as exc:  # noqa: BLE001 - PostgREST surfaces the SQL exception text
                text = str(exc)
                transient = ("57014" in text or "statement timeout" in text or " 502" in text or " 503" in text or " 504" in text)
                if transient and attempt < self.RETRY_ATTEMPTS - 1:
                    sleep(1.5 * (attempt + 1))
                    continue
                self._raise_mapped(exc, text)

    def _raise_mapped(self, exc: Exception, text: str) -> None:
        if "EBAY_BUDGET_EXHAUSTED" in text:
            raise BudgetExhausted(f"{self.bucket} pool exhausted for the current provider window") from exc
        if "EBAY_BUDGET_WINDOW_UNKNOWN" in text or "EBAY_BUDGET_VERIFICATION_STALE" in text:
            raise PipelineError("QUOTA_UNVERIFIED", "window unknown or verification older than 36h; failing closed") from exc
        raise PipelineError("BUDGET_AUTHORITY_UNAVAILABLE", text[:200]) from exc

    def window(self, now: datetime | None = None) -> dict[str, Any] | None:
        now = now or datetime.now(timezone.utc)
        rows = self.client.table("ebay_api_request_budget_v2").select("*").eq("provider_keyset_identity", self.keyset).eq(
            "api_name", API_NAME).eq("resource_bucket", self.bucket).order("provider_window_end", desc=True).limit(3).execute().data or []
        for row in rows:
            if _dt(row["provider_window_start"]) <= now < _dt(row["provider_window_end"]):
                return row
        return None

    def used(self) -> int:
        row = self.window()
        return int(row["requests_reserved"]) if row else 0

    def remaining(self) -> int:
        row = self.window()
        return max(0, int(row["usable_limit"]) - int(row["requests_reserved"])) if row else 0

    def usable_limit(self) -> int:
        row = self.window()
        return int(row["usable_limit"]) if row else 0


def _dt(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class RoutedBrowseHTTP(BrowseHTTP):
    """BrowseHTTP whose per-attempt reservation goes to the bucket that the URL maps to (retries included)."""

    def __init__(self, token_provider: Any, config: Any, ledgers: Mapping[str, Any], **kwargs: Any) -> None:
        super().__init__(token_provider, config, daily_ledger=None, **kwargs)
        self._ledgers = dict(ledgers)

    def get(self, url: str, counters: Any):  # type: ignore[override]
        bucket = bucket_for_url(url)
        ledger = self._ledgers.get(bucket)
        if ledger is None:
            raise PipelineError("BUCKET_LEDGER_NOT_CONFIGURED", bucket)
        self._daily_ledger = ledger
        return super().get(url, counters)


class QuotaVerifier:
    """Verifies provider ceilings/windows via Developer Analytics and registers them in the ledger."""

    def __init__(self, client: Any, keyset: str, fetch_usage: Callable[[], dict[str, Any]]) -> None:
        self.client, self.keyset, self.fetch_usage = client, keyset, fetch_usage

    def verify(self, now: datetime | None = None) -> dict[str, Any]:
        now = now or datetime.now(timezone.utc)
        try:
            snapshot = self.fetch_usage()
        except Exception as exc:  # noqa: BLE001 - timeouts and transport errors are UNAVAILABLE, never zero/unlimited
            snapshot = {"state": "PROVIDER_USAGE_UNAVAILABLE", "limits": [], "error_type": type(exc).__name__}
        results: dict[str, Any] = {"provider_state": snapshot.get("state"), "buckets": {}}
        for bucket in (STANDARD, BULK):
            verified = policy.verification_from_provider(snapshot.get("limits") or [], PROVIDER_RESOURCE[bucket]) if snapshot.get("state") == policy.PROVIDER_OK else None
            if verified and verified.get("reset_at") and verified.get("window_seconds"):
                reset = _dt(verified["reset_at"])
                start = reset - timedelta(seconds=int(verified["window_seconds"]))
                self.client.rpc("register_ebay_api_budget_window_v2", {
                    "p_keyset": self.keyset, "p_api": API_NAME, "p_bucket": bucket, "p_window_start": start.isoformat(),
                    "p_reset_at": reset.isoformat(), "p_provider_limit": verified["verified_limit"],
                    "p_provider_used": verified.get("provider_reported_used"), "p_provider_remaining": verified.get("provider_reported_remaining")}).execute()
                results["buckets"][bucket] = {"mode": policy.HEALTHY, "verified_limit": verified["verified_limit"], "window_end": reset.isoformat()}
            else:
                # An OK response that omits this bucket is NOT verification of it: treat it as a non-answer for the bucket.
                state = snapshot.get("state")
                results["buckets"][bucket] = self._degraded(bucket, "PROVIDER_USAGE_BUCKET_ABSENT" if state == policy.PROVIDER_OK else state, now)
        return results

    def _degraded(self, bucket: str, provider_state: str | None, now: datetime) -> dict[str, Any]:
        rows = self.client.table("ebay_api_request_budget_v2").select("*").eq("provider_keyset_identity", self.keyset).eq(
            "api_name", API_NAME).eq("resource_bucket", bucket).eq("provider_usage_state", "PROVIDER_USAGE_OK").order(
            "verified_at", desc=True).limit(1).execute().data or []
        last = rows[0] if rows else None
        expected = policy.KeysetIdentity(self.keyset.split(":")[0], self.keyset)
        decision = policy.authorize(
            verified_limit=last["provider_limit"] if last else None, verified_at=_dt(last["verified_at"]) if last else None,
            provider_state=provider_state, provider_remaining=None, ledger_healthy=True, ledger_reserved=last["requests_reserved"] if last else 0,
            now=now, expected_keyset=expected, verified_keyset=expected if last else None,
            policy=policy.QuotaPolicy(max_verification_age=MAX_VERIFICATION_AGE))
        return {"mode": decision.mode, "reason": decision.reason, "usable_limit": decision.usable_limit}
