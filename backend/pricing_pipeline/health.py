"""Non-invasive health checks for the daily multi-source pricing pipeline.

Semantics (P6M): eBay-side problems degrade *multi-source coverage* only. They are never reported as a failure of the
canonical TCGplayer pricing system. The only CRITICAL check is an unexpected non-TCGPlayer source in canonical/generic
current pricing, which would violate the P5A source-lock authority.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Mapping

from backend.pricing_pipeline.contracts import DAILY_REQUEST_LIMIT, PHOENIX
from backend.scripts.freeze_ebay_active_ask_v1 import VERSION as ESTIMATOR_VERSION
from backend.scripts.pokemon_multi_source_card_price_v1 import POLICY_VERSION

OK, DEGRADED, CRITICAL = "ok", "degraded_multi_source_coverage", "critical"
# Scheduled 04:10 Phoenix; a run is considered overdue only after this local time.
RUN_DEADLINE_PHOENIX = time(8, 0)
MAX_EVIDENCE_AGE_HOURS = 36


def expected_market_date(now: datetime) -> date:
    local = now.astimezone(PHOENIX)
    return local.date() if local.time() >= RUN_DEADLINE_PHOENIX else local.date() - timedelta(days=1)


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
    policies = client.table("pokemon_multi_source_card_prices_v1").select("policy_version").order("market_date", desc=True).limit(50).execute().data or []
    return {
        "now": now,
        "run": one("pokemon_multi_source_pricing_runs_v1", "market_date,status,stage,failure_code,updated_at,finished_at,requests_attempted,target_fingerprint", "market_date"),
        "evidence": one("ebay_pricing_runs_v1", "market_date,status,finished_at", "market_date", status="COMPLETE"),
        "estimate": one("ebay_active_ask_price_estimates_v1", "market_date,estimator_version", "market_date"),
        "shadow": one("pokemon_multi_source_card_prices_v1", "market_date,policy_version", "market_date"),
        "ledger": ledger[0] if ledger else None,
        "shadow_policies": sorted({p["policy_version"] for p in policies}),
        "non_tcg_current": len(client.table("card_variant_price_current_v2").select("source").neq("source", "TCGPlayer").limit(1).execute().data or []),
        "non_tcg_canonical": len(client.table("pokemon_canonical_card_market_prices_latest").select("source").neq("source", "TCGPlayer").limit(1).execute().data or []),
    }


def _check(key: str, ok: bool, code: str, observed: Mapping[str, Any], *, severity: str = DEGRADED) -> dict[str, Any]:
    return {"check": key, "status": OK if ok else severity, "code": None if ok else code, "observed": dict(observed)}


def assess(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    now = snapshot["now"]
    expected = expected_market_date(now).isoformat()
    run, evidence, estimate, shadow, ledger = (snapshot.get(k) for k in ("run", "evidence", "estimate", "shadow", "ledger"))
    results = [
        _check("pricing.multi_source.run_freshness", bool(run and run["market_date"] >= expected and run["status"] == "COMPLETE"),
               "DAILY_RUN_STALE_OR_INCOMPLETE", {"expected_market_date": expected, "latest_run": run and {k: run[k] for k in ("market_date", "status", "stage", "failure_code")}}),
        _check("pricing.multi_source.target_freshness", bool(run and run["market_date"] >= expected and run.get("target_fingerprint")),
               "TARGET_MANIFEST_MISSING_FOR_EXPECTED_DATE", {"expected_market_date": expected, "latest_target_market_date": run and run["market_date"]}),
    ]
    used = ledger["requests_reserved"] if ledger else 0
    limit = ledger["daily_limit"] if ledger else DAILY_REQUEST_LIMIT
    results.append(_check("pricing.ebay.budget_health", used <= min(limit, DAILY_REQUEST_LIMIT), "REQUEST_BUDGET_OVER_LIMIT",
                          {"requests_reserved_today": used, "daily_limit": limit}))
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
    results.append(_check("pricing.canonical.source_guard", snapshot["non_tcg_current"] == 0 and snapshot["non_tcg_canonical"] == 0,
                          "NON_TCGPLAYER_SOURCE_IN_CANONICAL_PRICING",
                          {"non_tcg_current_rows": snapshot["non_tcg_current"], "non_tcg_canonical_rows": snapshot["non_tcg_canonical"]}, severity=CRITICAL))
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
    for r in assess(snapshot):
        if r["status"] == OK:
            out.append(CheckResult.healthy(r["check"], observed=r["observed"], checked_at=snapshot["now"]))
        else:
            out.append(CheckResult.failure(r["check"], failure_code=r["code"], severity=Severity.CRITICAL if r["status"] == CRITICAL else Severity.WARNING,
                                           observed=r["observed"], checked_at=snapshot["now"]))
    return out
