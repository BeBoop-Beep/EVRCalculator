"""Coherent price authority for Budget-Constrained Whole-Unit Product Ranking.

WHY THIS EXISTS
---------------
A ranking publication must trace to ONE coherent market state. Production
writes `simulation_sealed_product_results` continuously, and during the V1
methodology validation the table went from 477 to 614 rows mid-session,
ending with TWO complete 137-SKU cohorts (`price_as_of` 2026-08-17 and
2026-08-21) plus partial single-set refresh runs in between.

The dangerous resolution is "newest row wins, per SKU". It always returns a
full-looking cohort, so it fails silently — while blending price dates,
calculation runs and market states into one apparently complete ranking.
This module refuses that shape outright: authority is resolved as a WHOLE
cohort keyed on a single `price_as_of`, or it fails.

RESOLUTION RULES
----------------
1. Consider only V4-ready, positively-priced rows.
2. Group by `price_as_of`. Each group is a candidate cohort.
3. If `price_as_of` is given explicitly, use exactly that group.
4. Otherwise pick the group covering the MOST distinct SKUs. If two groups
   tie on coverage the authority is genuinely ambiguous and we FAIL rather
   than guess — the caller must pin explicitly.
5. Within the winning group every SKU must map to exactly one calculation
   run, and model versions must be internally unanimous.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

#: Canonical model versions this ranking is an application layer over. Any
#: drift means the cohort is no longer the validated one (see the drift
#: guards in the builder) — the ranking is NOT authorised to reinterpret a
#: different scoring model under the same method version.
EXPECTED_FINANCIAL_RIP_VERSION = "financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5"
EXPECTED_OVERALL_RIP_VERSION = "overall_rip_v10_90_financial_v4_10_collector_appeal_v5"
EXPECTED_COLLECTOR_APPEAL_VERSION_PREFIX = "collector_appeal_v5_"

AUTHORITY_RESOLVER_VERSION = "budget_ranking_price_as_of_pinned_cohort_v1"


class AuthorityResolutionError(RuntimeError):
    """Raised when a single coherent cohort cannot be resolved."""


def _rows(response: Any) -> List[Dict[str, Any]]:
    return list((response.data if response else []) or [])


def load_pinned_cohort(
    client: Any,
    price_as_of: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Resolve exactly one coherent, fully-priced V4/V10-ready cohort.

    Returns ``(products, authority)``. Raises `AuthorityResolutionError`
    rather than returning a blended cohort.
    """
    raw = _rows(
        client.table("simulation_sealed_product_results").select(
            "sealed_product_id,set_id,product_family,product_name,pack_count,random_pack_count,"
            "guaranteed_component_count,guaranteed_component_market_value,product_market_cost,price_as_of,"
            "collector_appeal_score,collector_appeal_version,calculation_run_id,"
            "financial_rip_v4_status,financial_rip_v4_score,financial_rip_v4_version,"
            "overall_rip_v10_score,overall_rip_v10_version,accessory_value_included"
        ).eq("financial_rip_v4_status", "ready").execute()
    )
    priced = [r for r in raw if float(r.get("product_market_cost") or 0) > 0]
    if not priced:
        raise AuthorityResolutionError("no V4-ready, positively-priced sealed-product rows exist")

    by_as_of: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in priced:
        by_as_of[str(row.get("price_as_of"))].append(row)

    coverage = {key: len({str(r["sealed_product_id"]) for r in group}) for key, group in by_as_of.items()}

    if price_as_of is not None:
        pinned_as_of = str(price_as_of)
        if pinned_as_of not in by_as_of:
            raise AuthorityResolutionError(
                "requested price_as_of %s has no V4-ready rows (available: %s)"
                % (pinned_as_of, sorted(by_as_of))
            )
        pin_mode = "explicit"
    else:
        best = max(coverage.values())
        contenders = sorted(k for k, n in coverage.items() if n == best)
        if len(contenders) > 1:
            raise AuthorityResolutionError(
                "AMBIGUOUS AUTHORITY: %d complete cohorts tie at %d SKUs (%s). Re-run with an "
                "explicit --price-as-of; refusing to guess which market state to publish."
                % (len(contenders), best, ", ".join(contenders))
            )
        pinned_as_of = contenders[0]
        pin_mode = "resolved_by_coverage"

    cohort = by_as_of[pinned_as_of]

    runs_by_product: Dict[str, set] = defaultdict(set)
    for row in cohort:
        runs_by_product[str(row["sealed_product_id"])].add(str(row["calculation_run_id"]))
    ambiguous = sorted(p for p, runs in runs_by_product.items() if len(runs) > 1)
    if ambiguous:
        raise AuthorityResolutionError(
            "MIXED AUTHORITY: %d SKU(s) have more than one V4-ready calculation run inside "
            "price_as_of %s (e.g. %s)" % (len(ambiguous), pinned_as_of, ambiguous[:3])
        )

    financial_versions = sorted({str(r.get("financial_rip_v4_version")) for r in cohort})
    overall_versions = sorted({str(r.get("overall_rip_v10_version")) for r in cohort})
    appeal_versions = sorted({str(r.get("collector_appeal_version")) for r in cohort})
    for label, values in (
        ("financial_rip_v4_version", financial_versions),
        ("overall_rip_v10_version", overall_versions),
        ("collector_appeal_version", appeal_versions),
    ):
        if len(values) != 1:
            raise AuthorityResolutionError(
                "MIXED AUTHORITY: cohort %s carries %d distinct %s values: %s"
                % (pinned_as_of, len(values), label, values)
            )

    missing_scores = [
        str(r["sealed_product_id"]) for r in cohort
        if r.get("financial_rip_v4_score") is None or r.get("collector_appeal_score") is None
    ]
    if missing_scores:
        raise AuthorityResolutionError(
            "%d V4-ready SKU(s) in cohort %s are missing a financial or collector-appeal score (e.g. %s)"
            % (len(missing_scores), pinned_as_of, missing_scores[:3])
        )

    for row in cohort:
        if row.get("accessory_value_included") is True:
            raise AuthorityResolutionError(
                "product %s unexpectedly includes accessory value" % row["sealed_product_id"]
            )
        if int(row.get("random_pack_count") or row.get("pack_count") or 0) < 1:
            raise AuthorityResolutionError(
                "product %s has no positive random pack count" % row["sealed_product_id"]
            )

    excluded = [
        {
            "sealedProductId": str(r["sealed_product_id"]),
            "productName": r.get("product_name"),
            "calculationRunId": str(r["calculation_run_id"]),
            "priceAsOf": str(r.get("price_as_of")),
            "reason": "outside_pinned_price_as_of",
        }
        for key, group in by_as_of.items() if key != pinned_as_of for r in group
    ]

    prices = [float(r["product_market_cost"]) for r in cohort]
    authority = {
        "authorityResolverVersion": AUTHORITY_RESOLVER_VERSION,
        "pinnedPriceAsOf": pinned_as_of,
        "pinMode": pin_mode,
        "candidateCohorts": dict(sorted(coverage.items())),
        "productCount": len(cohort),
        "calculationRunIds": sorted({str(r["calculation_run_id"]) for r in cohort}),
        "financialRipVersion": financial_versions[0],
        "overallRipVersion": overall_versions[0],
        "collectorAppealVersion": appeal_versions[0],
        "minimumSkuPrice": min(prices),
        "maximumSkuPrice": max(prices),
        "excludedRowCount": len(excluded),
        "excludedRunCount": len({e["calculationRunId"] for e in excluded}),
        "excludedRows": excluded,
    }
    return cohort, authority


def assert_expected_model_versions(authority: Mapping[str, Any]) -> List[str]:
    """Model-drift guard. Returns human-readable drift warnings (never raises).

    The builder decides whether drift blocks a publish; this function only
    reports, so an audit run can surface drift without failing.
    """
    warnings: List[str] = []
    if authority.get("financialRipVersion") != EXPECTED_FINANCIAL_RIP_VERSION:
        warnings.append(
            "financial_rip_version drift: expected %s, found %s"
            % (EXPECTED_FINANCIAL_RIP_VERSION, authority.get("financialRipVersion"))
        )
    if authority.get("overallRipVersion") != EXPECTED_OVERALL_RIP_VERSION:
        warnings.append(
            "overall_rip_version drift: expected %s, found %s"
            % (EXPECTED_OVERALL_RIP_VERSION, authority.get("overallRipVersion"))
        )
    appeal = str(authority.get("collectorAppealVersion") or "")
    if not appeal.startswith(EXPECTED_COLLECTOR_APPEAL_VERSION_PREFIX):
        warnings.append(
            "collector_appeal_version drift: expected prefix %s, found %s"
            % (EXPECTED_COLLECTOR_APPEAL_VERSION_PREFIX, appeal)
        )
    return warnings
