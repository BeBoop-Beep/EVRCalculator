"""Non-invasive health checks for the daily multi-source pricing pipeline.

Semantics (P6M): eBay-side problems degrade *multi-source coverage* only. They are never reported as a failure of the
canonical TCGplayer pricing system. The only CRITICAL check is an unexpected non-TCGPlayer source in canonical/generic
current pricing, which would violate the P5A source-lock authority.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Mapping

from backend.pricing_pipeline.contracts import DAILY_REQUEST_LIMIT, PHOENIX
from backend.pricing_pipeline.targets import verify_manifest
from backend.scripts.freeze_ebay_active_ask_v1 import VERSION as ESTIMATOR_VERSION
from backend.scripts.pokemon_multi_source_card_price_v1 import POLICY_VERSION

OK, DEGRADED, CRITICAL = "ok", "degraded_multi_source_coverage", "critical"
# Scheduled 04:10 Phoenix; a run is considered overdue only after this local time.
RUN_DEADLINE_PHOENIX = time(8, 0)
MAX_EVIDENCE_AGE_HOURS = 36
EBAY_CONTINUITY_LOOKBACK_DAYS = 7
# Strict daily-continuity enforcement begins when the repaired scheduler +
# Sentinel self-healing contract became production-authoritative. Earlier
# missed dates remain diagnostic evidence; current active listings cannot
# truthfully reconstruct their historical eBay market state.
EBAY_CONTINUITY_ENFORCEMENT_DATE = date(2026, 9, 27)
EBAY_DIAGNOSTIC_START_DATE = date(2026, 9, 21)


def expected_market_date(now: datetime) -> date:
    local = now.astimezone(PHOENIX)
    return local.date() if local.time() >= RUN_DEADLINE_PHOENIX else local.date() - timedelta(days=1)


def _guard(client: Any, table: str) -> int | None:
    """Rows with a non-TCGPlayer source; None when the full-table probe cannot complete (transient timeout)."""
    try:
        return len(client.table(table).select("source").neq("source", "TCGPlayer").limit(1).execute().data or [])
    except Exception as exc:  # noqa: BLE001
        if "57014" in str(exc) or "statement timeout" in str(exc):
            return None
        raise


def gather(client: Any, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)

    def one(table: str, cols: str, order: str, **eq: Any):
        q = client.table(table).select(cols)
        for key, value in eq.items():
            q = q.eq(key, value)
        rows = q.order(order, desc=True).limit(1).execute().data or []
        return rows[0] if rows else None

    day = now.astimezone(PHOENIX).date().isoformat()
    ledger = client.table("ebay_browse_request_ledger_v1").select("requests_reserved,daily_limit").eq("budget_day", day).limit(1).execute().data or []
    v2 = client.table("ebay_api_request_budget_v2").select(
        "resource_bucket,provider_window_start,provider_window_end,usable_limit,requests_reserved,verified_at,provider_usage_state").order(
        "provider_window_end", desc=True).limit(4).execute().data or []
    policies = client.table("pokemon_multi_source_card_prices_v1").select("policy_version").order("market_date", desc=True).limit(50).execute().data or []

    expected_day = expected_market_date(now)
    lookback_start = expected_day - timedelta(days=EBAY_CONTINUITY_LOOKBACK_DAYS - 1)
    continuity_start = max(EBAY_CONTINUITY_ENFORCEMENT_DATE, lookback_start)
    diagnostic_start = max(EBAY_DIAGNOSTIC_START_DATE, lookback_start)
    batch_rows = (
        client.table("pokemon_scrape_batches")
        .select("market_date,status")
        .eq("status", "complete")
        .order("market_date", desc=True)
        .limit(14)
        .execute().data or []
    )
    ebay_rows = (
        client.table("ebay_pricing_runs_v1")
        .select("market_date,status")
        .eq("status", "COMPLETE")
        .order("market_date", desc=True)
        .limit(14)
        .execute().data or []
    )

    def dates_between(rows, start):
        out = set()
        for row in rows:
            raw = str(row.get("market_date") or "")[:10]
            try:
                parsed = date.fromisoformat(raw)
            except ValueError:
                continue
            if start <= parsed <= expected_day:
                out.add(raw)
        return sorted(out)

    run = one(
        "pokemon_multi_source_pricing_runs_v1",
        "run_id,market_date,status,stage,failure_code,updated_at,finished_at,requests_attempted,"
        "target_count,target_fingerprint,manifest",
        "market_date",
    )
    eligible_estimate_count = None
    if run and run.get("run_id"):
        response = (
            client.table("ebay_active_ask_price_estimates_v1")
            .select("id", count="exact")
            .eq("pricing_run_id", run["run_id"])
            .limit(1)
            .execute()
        )
        eligible_estimate_count = int(response.count or 0)

    return {
        "now": now,
        "run": run,
        "evidence": one("ebay_pricing_runs_v1", "market_date,status,finished_at", "market_date", status="COMPLETE"),
        "estimate": one("ebay_active_ask_price_estimates_v1", "market_date,estimator_version", "market_date"),
        "eligible_estimate_count": eligible_estimate_count,
        "shadow": one("pokemon_multi_source_card_prices_v1", "market_date,policy_version", "market_date"),
        "ledger": ledger[0] if ledger else None, "budget_v2": v2,
        "shadow_policies": sorted({p["policy_version"] for p in policies}),
        "expected_ebay_dates": dates_between(batch_rows, continuity_start),
        "completed_ebay_dates": dates_between(ebay_rows, continuity_start),
        "diagnostic_expected_ebay_dates": dates_between(batch_rows, diagnostic_start),
        "diagnostic_completed_ebay_dates": dates_between(ebay_rows, diagnostic_start),
        "continuity_enforcement_date": EBAY_CONTINUITY_ENFORCEMENT_DATE.isoformat(),
        "non_tcg_current": _guard(client, "card_variant_price_current_v2"),
        "non_tcg_canonical": _guard(client, "pokemon_canonical_card_market_prices_latest"),
    }


def _check(key: str, ok: bool, code: str, observed: Mapping[str, Any], *, severity: str = DEGRADED) -> dict[str, Any]:
    return {"check": key, "status": OK if ok else severity, "code": None if ok else code, "observed": dict(observed)}


def _target_manifest_integrity(run: Mapping[str, Any] | None) -> bool:
    """Recompute the stored target manifest fingerprint and verify its structural counts."""
    if not isinstance(run, Mapping):
        return False
    manifest = run.get("manifest")
    if not isinstance(manifest, Mapping):
        return False
    cards = manifest.get("cards")
    if not isinstance(cards, list):
        return False
    try:
        target_count = int(run.get("target_count"))
        manifest_target_count = int(manifest.get("target_count"))
    except (TypeError, ValueError):
        return False
    fingerprint = str(run.get("target_fingerprint") or "")
    if not fingerprint or str(manifest.get("selector_fingerprint") or "") != fingerprint:
        return False
    if target_count != manifest_target_count or target_count != len(cards):
        return False
    try:
        return bool(verify_manifest(manifest))
    except (KeyError, TypeError, ValueError):
        return False


def assess(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    now = snapshot["now"]
    expected = expected_market_date(now).isoformat()
    run, evidence, estimate, shadow, ledger = (snapshot.get(k) for k in ("run", "evidence", "estimate", "shadow", "ledger"))
    expected_ebay_dates = list(snapshot.get("expected_ebay_dates") or [])
    completed_ebay_dates = set(snapshot.get("completed_ebay_dates") or [])
    missing_ebay_dates = [day for day in expected_ebay_dates if day not in completed_ebay_dates]
    diagnostic_expected = list(snapshot.get("diagnostic_expected_ebay_dates") or [])
    diagnostic_completed = set(snapshot.get("diagnostic_completed_ebay_dates") or [])
    historical_missing = [
        day for day in diagnostic_expected
        if day not in diagnostic_completed and day < EBAY_CONTINUITY_ENFORCEMENT_DATE.isoformat()
    ]
    target_count = int(run.get("target_count") or 0) if run else 0
    current_complete_run = bool(
        run and run["market_date"] >= expected and run["status"] == "COMPLETE"
    )
    eligible_estimate_count = snapshot.get("eligible_estimate_count")
    results = [
        _check("pricing.multi_source.run_freshness", current_complete_run,
               "DAILY_RUN_STALE_OR_INCOMPLETE", {"expected_market_date": expected, "latest_run": run and {k: run[k] for k in ("market_date", "status", "stage", "failure_code")}}),
        _check("pricing.ebay.calendar_continuity", not missing_ebay_dates,
               "EBAY_DAILY_COVERAGE_GAP", {
                   "expected_market_date": expected,
                   "continuity_enforcement_date": snapshot.get("continuity_enforcement_date"),
                   "expected_completed_batch_dates": expected_ebay_dates,
                   "completed_ebay_dates": sorted(completed_ebay_dates),
                   "missing_ebay_dates": missing_ebay_dates,
                   "historical_pre_enforcement_gaps": historical_missing,
               }),
        _check("pricing.multi_source.target_freshness", bool(
                   run and run["market_date"] >= expected and run.get("target_fingerprint") and target_count > 0
               ),
               "TARGET_MANIFEST_MISSING_FOR_EXPECTED_DATE", {
                   "expected_market_date": expected,
                   "latest_target_market_date": run and run["market_date"],
                   "target_count": target_count,
               }),
        _check("pricing.multi_source.target_manifest_integrity", bool(
                   current_complete_run and _target_manifest_integrity(run)
               ),
               "TARGET_MANIFEST_CONTENT_INVALID", {
                   "expected_market_date": expected,
                   "latest_target_market_date": run and run["market_date"],
                   "target_count": target_count,
                   "manifest_target_count": (
                       (run.get("manifest") or {}).get("target_count")
                       if isinstance(run and run.get("manifest"), Mapping) else None
                   ),
                   "stored_target_fingerprint": run and run.get("target_fingerprint"),
                   "manifest_target_fingerprint": (
                       (run.get("manifest") or {}).get("selector_fingerprint")
                       if isinstance(run and run.get("manifest"), Mapping) else None
                   ),
               }),
        _check("pricing.ebay.estimate_coverage", bool(
                   not current_complete_run
                   or target_count <= 0
                   or (eligible_estimate_count is not None and int(eligible_estimate_count) > 0)
               ),
               "EBAY_ZERO_ELIGIBLE_ESTIMATES", {
                   "market_date": run and run.get("market_date"),
                   "pricing_run_id": run and run.get("run_id"),
                   "target_count": target_count,
                   "eligible_estimate_count": eligible_estimate_count,
               }),
    ]
    used = ledger["requests_reserved"] if ledger else 0
    limit = ledger["daily_limit"] if ledger else DAILY_REQUEST_LIMIT
    results.append(_check("pricing.ebay.budget_health", used <= min(limit, DAILY_REQUEST_LIMIT), "REQUEST_BUDGET_OVER_LIMIT",
                          {"requests_reserved_today": used, "daily_limit": limit}))
    windows = list(snapshot.get("budget_v2") or [])
    if windows or "budget_v2" in snapshot:
        def _parse(v):
            return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        current = [w for w in windows if _parse(w["provider_window_start"]) <= now < _parse(w["provider_window_end"])]
        std = next((w for w in current if w["resource_bucket"] == "BUY_BROWSE_STANDARD"), None)
        ok = bool(std) and now - _parse(std["verified_at"]) <= timedelta(hours=36) and std["requests_reserved"] <= std["usable_limit"]
        results.append(_check("pricing.ebay.quota_authority_v2", ok, "EBAY_QUOTA_WINDOW_UNVERIFIED_OR_OVERSPENT",
                              {"standard_window": std and {k: std[k] for k in ("provider_window_end", "usable_limit", "requests_reserved", "provider_usage_state")}}))
    evidence_age = None
    if evidence and evidence.get("finished_at"):
        finished = datetime.fromisoformat(str(evidence["finished_at"]).replace("Z", "+00:00"))
        evidence_age = (now - finished).total_seconds() / 3600
    results.append(_check("pricing.ebay.evidence_freshness", evidence_age is not None and evidence_age <= MAX_EVIDENCE_AGE_HOURS,
                          "EBAY_EVIDENCE_STALE", {"latest_evidence_market_date": evidence and evidence["market_date"], "age_hours": evidence_age}))
    results.append(_check("pricing.ebay.estimator_freshness", bool(estimate and estimate["market_date"] >= (date.fromisoformat(expected) - timedelta(days=1)).isoformat()),
                          "EBAY_ESTIMATES_STALE", {"latest_estimate_market_date": estimate and estimate["market_date"]}))
    results.append(_check("pricing.multi_source.shadow_freshness", bool(shadow and shadow["market_date"] >= expected),
                          "MULTI_SOURCE_SHADOW_STALE", {"expected_market_date": expected, "latest_shadow_market_date": shadow and shadow["market_date"]}))
    observed = {"non_tcg_current_rows": snapshot["non_tcg_current"], "non_tcg_canonical_rows": snapshot["non_tcg_canonical"]}
    if any(v is not None and v > 0 for v in observed.values()):
        results.append(_check("pricing.canonical.source_guard", False, "NON_TCGPLAYER_SOURCE_IN_CANONICAL_PRICING", observed, severity=CRITICAL))
    elif any(v is None for v in observed.values()):
        # could not be verified (timeout): NOT contamination, so never CRITICAL, but never silently "ok" either
        results.append(_check("pricing.canonical.source_guard", False, "SOURCE_GUARD_UNVERIFIABLE_TRANSIENT_TIMEOUT", observed))
    else:
        results.append(_check("pricing.canonical.source_guard", True, "", observed))
    policies = list(snapshot.get("shadow_policies") or [])
    versions_ok = all(p == POLICY_VERSION for p in policies) and (not estimate or estimate["estimator_version"] == ESTIMATOR_VERSION)
    results.append(_check("pricing.multi_source.policy_drift", versions_ok, "POLICY_OR_ESTIMATOR_VERSION_DRIFT",
                          {"expected_policy": POLICY_VERSION, "observed_policies": policies, "expected_estimator": ESTIMATOR_VERSION,
                           "observed_estimator": estimate and estimate["estimator_version"]}))
    return results


def overall(results: list[Mapping[str, Any]]) -> dict[str, Any]:
    """canonical_pricing_healthy depends ONLY on the source guard; eBay trouble is `degraded`, never a canonical failure."""
    critical = [r["check"] for r in results if r["status"] == CRITICAL]
    degraded = [r["check"] for r in results if r["status"] == DEGRADED]
    return {"canonical_pricing_healthy": not critical, "multi_source_coverage": "degraded" if degraded else "healthy",
            "critical_checks": critical, "degraded_checks": degraded}


def sentinel_results(snapshot: Mapping[str, Any]):
    """Adapter into Sentinel CheckResult objects (eBay failures are WARNING severity; source guard is CRITICAL)."""
    from backend.sentinel.models import CheckResult, Severity

    out = []
    expected_authority = expected_market_date(snapshot["now"]).isoformat()
    for r in assess(snapshot):
        authority_identity = expected_authority if r["check"] in {
            "pricing.multi_source.run_freshness",
            "pricing.multi_source.target_freshness",
            "pricing.multi_source.shadow_freshness",
            "pricing.ebay.calendar_continuity",
        } else None
        if r["status"] == OK:
            out.append(CheckResult.healthy(r["check"], observed=r["observed"], authority_identity=authority_identity,
                                           checked_at=snapshot["now"]))
        else:
            out.append(CheckResult.failure(r["check"], failure_code=r["code"], severity=Severity.CRITICAL if r["status"] == CRITICAL else Severity.WARNING,
                                           observed=r["observed"], authority_identity=authority_identity,
                                           checked_at=snapshot["now"]))
    return out
