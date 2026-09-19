"""Explicit (non-default) publication payload builders for Ranking V2 and Best-Open V3.

Pure functions: they turn the already-verified V2/V3 engine output into the exact JSON
the versioned publication RPCs accept. Nothing here reads or writes a database and
nothing is wired into a scheduled/current publisher; selecting V2/V3 is an explicit act.
Every identity is imported from its owning module so SQL literals cannot drift silently
(a test pins the SQL literals to these constants).
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from backend.calculations.evr.best_open_price_v3 import BEST_OPEN_PRICE_V3_METHOD_VERSION
from backend.calculations.evr.budget_normalized_product_ranking import (
    ALLOCATION_METHOD_VERSION,
    BUDGET_COMPARISON_SCOPE_VERSION,
    BUDGET_NORMALIZED_RANKING_METHOD_VERSION_V2,
)
from backend.calculations.evr.financial_rip_v5_config import FINANCIAL_RIP_V5_VERSION
from backend.db.services.budget_chase_accessibility_authority import CHASE_ACCESSIBILITY_TRANSFORM_VERSION
from backend.db.services.budget_product_ranking_authority import (
    EXPECTED_CHASE_ACCESSIBILITY_VERSION,
    EXPECTED_COLLECTOR_APPEAL_VERSION,
)
from backend.desirability.scoring_config import OVERALL_RIP_V14_VERSION

RANKING_V2_IDENTITY: Dict[str, str] = {
    "ranking_method_version": BUDGET_NORMALIZED_RANKING_METHOD_VERSION_V2,
    "allocation_method_version": ALLOCATION_METHOD_VERSION,
    "comparison_scope_version": BUDGET_COMPARISON_SCOPE_VERSION,
    "financial_rip_version": FINANCIAL_RIP_V5_VERSION,
    "financial_rip_v5_version": FINANCIAL_RIP_V5_VERSION,
    "overall_rip_version": OVERALL_RIP_V14_VERSION,
    "overall_rip_v14_version": OVERALL_RIP_V14_VERSION,
    "collector_appeal_version": EXPECTED_COLLECTOR_APPEAL_VERSION,
    "chase_accessibility_version": EXPECTED_CHASE_ACCESSIBILITY_VERSION,
    "chase_accessibility_transform_version": CHASE_ACCESSIBILITY_TRANSFORM_VERSION,
}


def build_ranking_v2_snapshot(
    *, market_date: str, built_at: str, pinned_price_as_of: str, eligible_cohort_count: int,
    cohort_fingerprint: str, full_market_budget: float, max_eligible_sku_price: float,
    full_market_rounding_increment: float, full_market_rounding_rule_version: str,
    diagnostics_json: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        **RANKING_V2_IDENTITY,
        "ranked_under_v14_authority": True,
        "market_date": market_date, "built_at": built_at,
        "pinned_price_as_of": pinned_price_as_of,
        "eligible_cohort_count": int(eligible_cohort_count),
        "cohort_fingerprint": cohort_fingerprint,
        "full_market_budget": full_market_budget,
        "max_eligible_sku_price": max_eligible_sku_price,
        "full_market_rounding_increment": full_market_rounding_increment,
        "full_market_rounding_rule_version": full_market_rounding_rule_version,
        "diagnostics_json": dict(diagnostics_json or {}),
    }


def build_ranking_v2_rows(
    ranked: Sequence[Mapping[str, Any]],
    context_by_product: Mapping[str, Mapping[str, Any]],
    *, budget_type: str = "full_market",
) -> List[Dict[str, Any]]:
    """Rows from ``rank_budget_cohort_v2`` output plus per-product source context.

    ``context`` supplies what the engine does not own: ``set_id``, ``product_family``,
    ``product_market_price``, ``price_as_of``, ``collector_appeal_score``,
    ``chase_accessibility_raw``, ``source_calculation_run_id`` and the Full Market anchor
    metadata. No V4/V10/V12 key is ever emitted.
    """
    rows: List[Dict[str, Any]] = []
    for entry in ranked:
        pid = str(entry["sealedProductId"])
        ctx = context_by_product[pid]
        target = float(entry["targetBudget"])
        committed = float(entry["actualCommittedCapital"])
        unused = target - committed
        rows.append({
            "sealed_product_id": pid, "set_id": ctx["set_id"], "product_family": ctx["product_family"],
            "target_budget": target, "budget_type": budget_type, "quantity": int(entry["quantity"]),
            "actual_committed_capital": committed, "unused_capital": unused,
            "unused_capital_percent": unused / target, "capital_utilization": committed / target,
            "financial_rip_v5_score": entry["financialRipV5Score"],
            "financial_rip_v5_status": entry["financialRipV5Status"],
            "financial_rip_v5_rankable": entry["financialRipV5Rankable"],
            "overall_rip_v14_score": entry["overallRipV14Score"],
            "overall_rip_v14_status": entry["overallRipV14Status"],
            "overall_rip_v14_rankable": entry["overallRipV14Rankable"],
            "budget_rank_v14": entry["budgetRankV14"],
            "budget_cohort_size_v14": entry["budgetCohortSizeV14"],
            "budget_tier_v14": entry["budgetTierV14"],
            "financial_only_rank_v5": entry["financialOnlyRankV5"],
            "collector_appeal_score": ctx["collector_appeal_score"],
            "chase_accessibility_raw": ctx["chase_accessibility_raw"],
            "chance_to_recover_capital": entry["chanceToRecoverCapital"],
            "expected_value": entry["expectedValue"], "median_value": entry["medianValue"],
            "top1_outcome_value_share": entry["topOneOutcomeValueShare"],
            "product_market_price": ctx["product_market_price"], "price_as_of": ctx["price_as_of"],
            "full_market_anchor": ctx.get("full_market_anchor"),
            "max_eligible_sku_price": ctx.get("max_eligible_sku_price"),
            "full_market_rounding_rule": ctx.get("full_market_rounding_rule"),
            "full_market_rounding_increment": ctx.get("full_market_rounding_increment"),
            "full_market_rounding_rule_version": ctx.get("full_market_rounding_rule_version"),
            "source_calculation_run_id": ctx["source_calculation_run_id"],
        })
    return rows


BEST_OPEN_V3_IDENTITY: Dict[str, str] = {
    "ranking_method_version": BUDGET_NORMALIZED_RANKING_METHOD_VERSION_V2,
    "allocation_method_version": ALLOCATION_METHOD_VERSION,
    "comparison_scope_version": BUDGET_COMPARISON_SCOPE_VERSION,
    "financial_rip_version": FINANCIAL_RIP_V5_VERSION,
    "overall_rip_v14_version": OVERALL_RIP_V14_VERSION,
    "collector_appeal_version": EXPECTED_COLLECTOR_APPEAL_VERSION,
    "chase_accessibility_version": EXPECTED_CHASE_ACCESSIBILITY_VERSION,
    "chase_accessibility_transform_version": CHASE_ACCESSIBILITY_TRANSFORM_VERSION,
    "best_open_price_method_version": BEST_OPEN_PRICE_V3_METHOD_VERSION,
}
