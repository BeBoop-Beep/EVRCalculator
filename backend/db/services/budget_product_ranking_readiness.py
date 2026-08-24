"""Fail-closed readiness for recurring private Budget Ranking publication.

The automatic path is deliberately stricter than the operator-oriented cohort
resolver: it binds products to the exact calculation runs certified by the
daily opening freshness gate.  It never assembles a cohort from newest rows per
SKU or from a global maximum ``price_as_of``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Sequence

from backend.calculations.evr.budget_normalized_product_ranking import (
    ALLOCATION_METHOD_VERSION, BUDGET_COMPARISON_SCOPE_VERSION,
    BUDGET_NORMALIZED_RANKING_METHOD_VERSION, FULL_MARKET_ROUNDING_RULE_VERSION,
)
from backend.db.services.budget_product_ranking_authority import (
    AUTHORITY_RESOLVER_VERSION,
    EXPECTED_COLLECTOR_APPEAL_VERSION,
    EXPECTED_FINANCIAL_RIP_VERSION,
    EXPECTED_OVERALL_RIP_VERSION,
    VALIDATED_PRODUCT_FAMILIES,
)
from backend.db.services.opening_simulation_gate import (
    STATUS_CURRENT,
    evaluate_opening_simulation_freshness,
)
from backend.db.services.pack_outcome_artifact_service import load_pack_outcome_artifact_metadata
from backend.db.services.publication_gate import MODE_REQUIRED, evaluate_publication_gate


class BudgetRankingStatus(str, Enum):
    PUBLISHED = "PUBLISHED"
    NO_NEW_AUTHORITY = "NO_NEW_AUTHORITY"
    UPSTREAM_NOT_READY = "UPSTREAM_NOT_READY"
    METHOD_VERSION_MISMATCH = "METHOD_VERSION_MISMATCH"
    HEALTH_GATE_BLOCKED = "HEALTH_GATE_BLOCKED"
    PUBLICATION_FAILED = "PUBLICATION_FAILED"
    POST_PUBLISH_VERIFICATION_FAILED = "POST_PUBLISH_VERIFICATION_FAILED"
    STALE = "STALE"


EXIT_CODES = {
    BudgetRankingStatus.PUBLISHED: 0,
    BudgetRankingStatus.NO_NEW_AUTHORITY: 0,
    BudgetRankingStatus.UPSTREAM_NOT_READY: 3,
    BudgetRankingStatus.METHOD_VERSION_MISMATCH: 1,
    BudgetRankingStatus.HEALTH_GATE_BLOCKED: 1,
    BudgetRankingStatus.PUBLICATION_FAILED: 1,
    BudgetRankingStatus.POST_PUBLISH_VERIFICATION_FAILED: 1,
    BudgetRankingStatus.STALE: 1,
}

PRODUCT_COLUMNS = (
    "sealed_product_id,set_id,product_family,product_name,pack_count,random_pack_count,"
    "guaranteed_component_count,guaranteed_component_market_value,product_market_cost,"
    "price_as_of,price_source,collector_appeal_score,collector_appeal_version,calculation_run_id,"
    "financial_rip_v4_status,financial_rip_v4_rankable,financial_rip_v4_score,financial_rip_v4_version,"
    "overall_rip_v10_score,overall_rip_v10_rankable,overall_rip_v10_version,accessory_value_included"
)


@dataclass
class ReadinessResult:
    status: BudgetRankingStatus
    promoted_market_date: Optional[str] = None
    selected_price_as_of: Optional[str] = None
    products: List[Dict[str, Any]] = field(default_factory=list)
    authority: Dict[str, Any] = field(default_factory=dict)
    candidate_authorities: List[Dict[str, Any]] = field(default_factory=list)
    gate_results: List[Dict[str, Any]] = field(default_factory=list)
    failure_reason: Optional[str] = None
    failed_gate: Optional[str] = None

    @property
    def eligible(self) -> bool:
        return self.status == BudgetRankingStatus.PUBLISHED


def _rows(response: Any) -> List[Dict[str, Any]]:
    return list((response.data if response else []) or [])


def _fail(status: BudgetRankingStatus, gate: str, reason: str, **kwargs: Any) -> ReadinessResult:
    return ReadinessResult(
        status=status, failed_gate=gate, failure_reason=reason,
        gate_results=[{"gate": gate, "passed": False, "reason": reason}], **kwargs,
    )


def _latest_raw_price_as_of(client: Any) -> Optional[str]:
    rows = _rows(
        client.table("simulation_sealed_product_results").select("price_as_of")
        .not_.is_("price_as_of", "null").order("price_as_of", desc=True).limit(1).execute()
    )
    return str(rows[0]["price_as_of"]) if rows else None


def _stale(
    latest: Optional[Mapping[str, Any]], raw_date: Optional[str], now: Optional[datetime]
) -> bool:
    if not latest or not raw_date or raw_date <= str(latest.get("pinned_price_as_of") or ""):
        return False
    published = latest.get("published_at") or latest.get("built_at")
    if not published:
        return False
    published_at = datetime.fromisoformat(str(published).replace("Z", "+00:00"))
    # Arizona does not observe DST; fixed UTC-07:00 is deterministic on the
    # repository's Python 3.8 runtime (which predates stdlib zoneinfo).
    phoenix = timezone(timedelta(hours=-7), "America/Phoenix")
    current = (now or datetime.now(phoenix)).astimezone(phoenix)
    local_published = published_at.astimezone(phoenix)
    second_cycle = local_published.date() + timedelta(days=2)
    return current >= datetime.combine(second_cycle, time(12, 30), phoenix)


def resolve_budget_ranking_readiness(
    client: Any,
    *,
    latest_snapshot: Optional[Mapping[str, Any]],
    promoted_market_date: Optional[str] = None,
    force_price_as_of: Optional[str] = None,
    now: Optional[datetime] = None,
) -> ReadinessResult:
    """Resolve one complete exact-run authority, without writing anything."""
    if promoted_market_date is None:
        from backend.scripts.audit_opening_analytics_publication import resolve_market_date
        promoted_market_date, error = resolve_market_date(client, None)
        if error or not promoted_market_date:
            return _fail(BudgetRankingStatus.UPSTREAM_NOT_READY, "promoted_market_date", error or "missing")

    common = {"promoted_market_date": str(promoted_market_date)}
    if latest_snapshot:
        expected_latest = {
            "ranking_method_version": BUDGET_NORMALIZED_RANKING_METHOD_VERSION,
            "allocation_method_version": ALLOCATION_METHOD_VERSION,
            "comparison_scope_version": BUDGET_COMPARISON_SCOPE_VERSION,
            "full_market_rounding_rule_version": FULL_MARKET_ROUNDING_RULE_VERSION,
            "financial_rip_version": EXPECTED_FINANCIAL_RIP_VERSION,
            "overall_rip_version": EXPECTED_OVERALL_RIP_VERSION,
            "collector_appeal_version": EXPECTED_COLLECTOR_APPEAL_VERSION,
        }
        drift = {key: {"expected": value, "found": latest_snapshot.get(key)}
                 for key, value in expected_latest.items()
                 if key in latest_snapshot and latest_snapshot.get(key) != value}
        if drift:
            return _fail(BudgetRankingStatus.METHOD_VERSION_MISMATCH, "latest_method_versions", str(drift), **common)
    promotion = evaluate_publication_gate(client, market_date=str(promoted_market_date), mode=MODE_REQUIRED)
    if not promotion.allowed:
        return _fail(
            BudgetRankingStatus.UPSTREAM_NOT_READY, "promoted_scrape_authority",
            str(promotion.reason or promotion.reason_code or "publication authority denied"), **common,
        )
    freshness = evaluate_opening_simulation_freshness(client, market_date=str(promoted_market_date))
    if not freshness.ok:
        return _fail(
            BudgetRankingStatus.UPSTREAM_NOT_READY, "opening_freshness",
            freshness.error or "; ".join(s.reason or s.status for s in freshness.failures), **common,
        )
    current = [s for s in freshness.statuses if s.status == STATUS_CURRENT]
    run_by_set = {str(s.set_id): str(s.calculation_run_id) for s in current if s.set_id and s.calculation_run_id}
    if len(run_by_set) != len(current) or not run_by_set:
        return _fail(BudgetRankingStatus.UPSTREAM_NOT_READY, "exact_set_run_map", "missing or duplicate current run", **common)

    run_ids = sorted(set(run_by_set.values()))
    products = _rows(
        client.table("simulation_sealed_product_results").select(PRODUCT_COLUMNS)
        .in_("calculation_run_id", run_ids).execute()
    )
    if not products:
        return _fail(BudgetRankingStatus.UPSTREAM_NOT_READY, "exact_run_products", "no exact-run products", **common)
    wrong = [r for r in products if run_by_set.get(str(r.get("set_id"))) != str(r.get("calculation_run_id"))]
    if wrong:
        return _fail(BudgetRankingStatus.UPSTREAM_NOT_READY, "exact_run_membership", "wrong set/run pair", **common)

    by_date: Dict[str, List[Dict[str, Any]]] = {}
    for row in products:
        by_date.setdefault(str(row.get("price_as_of") or ""), []).append(row)
    candidates = [
        {"price_as_of": key or None, "row_count": len(rows),
         "product_count": len({str(r.get('sealed_product_id')) for r in rows})}
        for key, rows in sorted(by_date.items())
    ]
    requested = str(force_price_as_of) if force_price_as_of else None
    if requested and requested not in by_date:
        return _fail(BudgetRankingStatus.UPSTREAM_NOT_READY, "forced_price_authority", "forced date is not present in exact runs", candidate_authorities=candidates, **common)
    if requested:
        selected_date = requested
    elif len(by_date) == 1 and "" not in by_date:
        selected_date = next(iter(by_date))
    else:
        return _fail(BudgetRankingStatus.UPSTREAM_NOT_READY, "single_price_authority", "exact runs contain mixed or null price authorities", candidate_authorities=candidates, **common)
    cohort = by_date[selected_date]

    identities = [str(r.get("sealed_product_id")) for r in cohort]
    if len(set(identities)) != len(identities):
        return _fail(BudgetRankingStatus.UPSTREAM_NOT_READY, "unique_product_identity", "duplicate product identity", candidate_authorities=candidates, **common)
    bad_prices = [r for r in cohort if not _positive_finite(r.get("product_market_cost")) or not r.get("price_source")]
    if bad_prices:
        return _fail(BudgetRankingStatus.UPSTREAM_NOT_READY, "price_provenance", "missing/nonpositive/nonfinite price or provenance", candidate_authorities=candidates, **common)

    versions = {
        "financialRipVersion": {str(r.get("financial_rip_v4_version")) for r in cohort},
        "overallRipVersion": {str(r.get("overall_rip_v10_version")) for r in cohort},
        "collectorAppealVersion": {str(r.get("collector_appeal_version")) for r in cohort},
    }
    version_ok = (
        versions["financialRipVersion"] == {EXPECTED_FINANCIAL_RIP_VERSION}
        and versions["overallRipVersion"] == {EXPECTED_OVERALL_RIP_VERSION}
        and versions["collectorAppealVersion"] == {EXPECTED_COLLECTOR_APPEAL_VERSION}
    )
    if not version_ok:
        return _fail(BudgetRankingStatus.METHOD_VERSION_MISMATCH, "model_versions", str(versions), candidate_authorities=candidates, **common)
    # V4's established persisted contract is status=ready plus a score. Older
    # otherwise-canonical rows legitimately predate population of the redundant
    # rankable projection (NULL); explicit False remains a hard contradiction.
    unready = [r for r in cohort if r.get("financial_rip_v4_status") != "ready" or r.get("financial_rip_v4_rankable") is False or r.get("overall_rip_v10_rankable") is not True or r.get("financial_rip_v4_score") is None or r.get("overall_rip_v10_score") is None or r.get("collector_appeal_score") is None]
    if unready:
        return _fail(BudgetRankingStatus.UPSTREAM_NOT_READY, "rankability", "required score/status/rankability missing", candidate_authorities=candidates, **common)
    invalid_products = [r for r in cohort if r.get("accessory_value_included") is True or int(r.get("random_pack_count") or r.get("pack_count") or 0) < 1]
    if invalid_products:
        return _fail(BudgetRankingStatus.HEALTH_GATE_BLOCKED, "product_contract", "accessory inclusion or invalid pack count", candidate_authorities=candidates, **common)
    unknown = sorted({str(r.get("product_family")) for r in cohort} - VALIDATED_PRODUCT_FAMILIES)
    if unknown:
        return _fail(BudgetRankingStatus.HEALTH_GATE_BLOCKED, "validated_families", "unsupported families: %s" % unknown, candidate_authorities=candidates, **common)
    try:
        for run_id in run_ids:
            load_pack_outcome_artifact_metadata(client, run_id)
    except Exception as exc:
        return _fail(BudgetRankingStatus.UPSTREAM_NOT_READY, "source_artifacts", str(exc), candidate_authorities=candidates, **common)

    raw_date = _latest_raw_price_as_of(client)
    latest_date = str((latest_snapshot or {}).get("pinned_price_as_of") or "")
    if selected_date == latest_date:
        if raw_date and raw_date > selected_date:
            status = BudgetRankingStatus.STALE if _stale(latest_snapshot, raw_date, now) else BudgetRankingStatus.UPSTREAM_NOT_READY
            return _fail(status, "newer_raw_authority", "newer raw evidence is not a complete exact-run authority", candidate_authorities=candidates, **common)
        return ReadinessResult(status=BudgetRankingStatus.NO_NEW_AUTHORITY, selected_price_as_of=selected_date, candidate_authorities=candidates, gate_results=[{"gate": "no_new_authority", "passed": True}], **common)
    if latest_date and selected_date < latest_date:
        return _fail(BudgetRankingStatus.UPSTREAM_NOT_READY, "authority_regression", "selected authority predates latest", candidate_authorities=candidates, **common)

    prices = [float(r["product_market_cost"]) for r in cohort]
    authority = {
        "authorityResolverVersion": AUTHORITY_RESOLVER_VERSION,
        "pinnedPriceAsOf": selected_date,
        "pinMode": "coordinated_exact_runs" if not requested else "forced_exact_runs",
        "candidateCohorts": {c["price_as_of"]: c["product_count"] for c in candidates},
        "productCount": len(cohort), "calculationRunIds": run_ids,
        "financialRipVersion": EXPECTED_FINANCIAL_RIP_VERSION,
        "overallRipVersion": EXPECTED_OVERALL_RIP_VERSION,
        "collectorAppealVersion": next(iter(versions["collectorAppealVersion"])),
        "minimumSkuPrice": min(prices), "maximumSkuPrice": max(prices),
        "excludedRowCount": len(products) - len(cohort), "excludedRunCount": 0, "excludedRows": [],
    }
    return ReadinessResult(
        status=BudgetRankingStatus.PUBLISHED, promoted_market_date=str(promoted_market_date),
        selected_price_as_of=selected_date, products=cohort, authority=authority,
        candidate_authorities=candidates, gate_results=[{"gate": "complete_exact_run_authority", "passed": True}],
    )


def _positive_finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value)) and float(value) > 0
    except (TypeError, ValueError):
        return False
