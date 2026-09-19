"""Best-Open Price V3 - Financial RIP V5 + Overall RIP V14 (EXPLICIT, NON-CANONICAL).

V3 reuses the exact-cent fused engine (``DualBestOpenPriceSearch``) UNCHANGED.
Only the scoring/ranking authority differs: the candidate scorer runs the
production ``build_financial_rip_v5`` and ``compute_overall_rip_v14`` on the same
prepared candidate distribution, and each axis compares against ITS OWN Ranking
V2 benchmark. V1 and V2 keep their meanings; nothing here relabels V2 output.

A V3 search must be seeded from a ``budget_product_ranking_v2`` source. Records
here carry only V5/V14-named fields; there is no fallback to V4/V12 evidence.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Mapping

from backend.calculations.evr.best_open_price import (
    BEST_OPEN_PRICE_METHOD_VERSION,
    BestOpenPriceSearchError,
    PreparedCanonicalCandidate,
)
from backend.calculations.evr.best_open_price_v2_fused import DualBestOpenPriceSearch
from backend.calculations.evr.budget_normalized_product_ranking import (
    BUDGET_NORMALIZED_RANKING_METHOD_VERSION_V2,
    _tier_sort_key_v14,
    financial_only_comparator_key_v5,
)
from backend.calculations.evr.financial_rip_v4 import project_financial_rip_v4_from_v3_payload
from backend.calculations.evr.financial_rip_v5 import build_financial_rip_v5

BEST_OPEN_PRICE_V3_METHOD_VERSION = (
    "budget_product_best_open_price_full_market_v3_dual_financial_v5_overall_v14"
)
COMPARISON_AUTHORITY_OVERALL_V14 = "overall_v14"
COMPARISON_AUTHORITY_FINANCIAL_V5 = "financial_v5"
V3_REQUIRED_SOURCE_RANKING_METHOD = BUDGET_NORMALIZED_RANKING_METHOD_VERSION_V2


def require_ranking_v2_source(source_ranking_method_version: str) -> None:
    """V3 must never be seeded from a V1 (or any non-V2) ranking snapshot."""
    if source_ranking_method_version != V3_REQUIRED_SOURCE_RANKING_METHOD:
        raise BestOpenPriceSearchError(
            "Best-Open V3 requires a "
            f"{V3_REQUIRED_SOURCE_RANKING_METHOD!r} source; got {source_ranking_method_version!r}"
        )


@dataclass
class PreparedV5Candidate(PreparedCanonicalCandidate):
    """Candidate scorer for V3: Financial V5 then Overall V14, from one distribution."""

    def score_candidate(self, price_cents: int) -> Dict[str, Any]:
        from backend.desirability.overall_rip_v14 import compute_overall_rip_v14
        from backend.desirability.scoring_config import (
            FINANCIAL_RIP_V5_VERSION,
            overall_rip_v14_required_chase_accessibility_version,
            overall_rip_v14_required_collector_appeal_version,
        )

        started = time.perf_counter()
        # Same IEEE-754 order as whole_unit_allocation() (see PreparedCanonicalCandidate).
        capital = self.quantity * (price_cents / 100.0)
        kwargs = {} if not self.min_simulation_count else {"min_simulation_count": self.min_simulation_count}
        v3 = self.distribution.score(capital, **kwargs)
        control = project_financial_rip_v4_from_v3_payload(v3)
        v5 = build_financial_rip_v5(self.distribution, capital, control_payload=control)
        rankable = bool(v5.get("rankable")) and v5.get("score") is not None
        overall = None
        if rankable:
            overall = compute_overall_rip_v14(
                v5["score"], self.chase_accessibility_raw, self.collector_appeal_score,
                financial_version=FINANCIAL_RIP_V5_VERSION,
                chase_accessibility_version=overall_rip_v14_required_chase_accessibility_version(),
                collector_appeal_version=overall_rip_v14_required_collector_appeal_version(),
            )
        raw = {k: r.get("raw") for k, r in ((v3.get("audit") or {}).get("normalizedInputs") or {}).items()}
        return {
            "sealedProductId": self.product_id,
            "priceCents": price_cents,
            "quantity": self.quantity,
            "targetBudget": self.target_budget,
            "actualCommittedCapital": capital,
            "financialRipV5Score": v5.get("score"),
            "financialRipV5Rankable": rankable,
            "overallRipV14Score": overall.get("score") if overall else None,
            "overallRipV14Rankable": bool(overall.get("rankable")) if overall else False,
            "shortfallResilienceScore": ((v5.get("components") or {})
                                         .get("shortfall_resilience", {}).get("score")),
            "chanceToRecoverCapital": raw.get("true_win_probability"),
            "scoringSeconds": time.perf_counter() - started,
        }

    def compare(self, score_record: Mapping[str, Any], benchmark: Mapping[str, Any], *,
                authority: str) -> bool:
        started = time.perf_counter()
        if authority == COMPARISON_AUTHORITY_FINANCIAL_V5:
            wins = (score_record.get("financialRipV5Score") is not None
                    and financial_only_comparator_key_v5(score_record)
                    < financial_only_comparator_key_v5(benchmark))
        elif authority == COMPARISON_AUTHORITY_OVERALL_V14:
            wins = (score_record.get("overallRipV14Rankable") is True
                    and score_record.get("overallRipV14Score") is not None
                    and _tier_sort_key_v14(score_record) < _tier_sort_key_v14(benchmark))
        else:
            # Deliberately no delegation to V4/V12 authorities.
            raise ValueError(f"unknown Best-Open V3 comparison authority {authority!r}")
        self._last_comparator_seconds = time.perf_counter() - started
        return wins

    def evaluate(self, price_cents: int, benchmark: Mapping[str, Any], *,
                 comparison_authority: str) -> Dict[str, Any]:
        record = self.score_candidate(price_cents)
        return {**record, "wins": self.compare(record, benchmark, authority=comparison_authority),
                "comparisonAuthority": comparison_authority}


def build_dual_best_open_v3_search(*, overall_v14_benchmark: Mapping[str, Any],
                                   financial_v5_benchmark: Mapping[str, Any],
                                   overall_v14_current_rank: int,
                                   financial_v5_current_rank: int,
                                   source_ranking_method_version: str,
                                   **engine_kwargs: Any) -> DualBestOpenPriceSearch:
    """Construct the unchanged fused engine bound to the V5/V14 authorities."""
    require_ranking_v2_source(source_ranking_method_version)
    return DualBestOpenPriceSearch(
        rip_current_rank=overall_v14_current_rank,
        rip_benchmark=overall_v14_benchmark,
        financial_current_rank=financial_v5_current_rank,
        financial_benchmark=financial_v5_benchmark,
        rip_comparison_authority=COMPARISON_AUTHORITY_OVERALL_V14,
        financial_comparison_authority=COMPARISON_AUTHORITY_FINANCIAL_V5,
        **engine_kwargs,
    )


def _relabel_axis(axis: Mapping[str, Any], benchmark: Mapping[str, Any]) -> Dict[str, Any]:
    out = dict(axis)
    out["methodVersion"] = BEST_OPEN_PRICE_V3_METHOD_VERSION
    out.pop("benchmarkOverallRipV12Score", None)
    out["benchmarkFinancialRipV5Score"] = benchmark.get("financialRipV5Score")
    out["benchmarkOverallRipV14Score"] = benchmark.get("overallRipV14Score")
    return out


def run_dual_best_open_v3(search: DualBestOpenPriceSearch) -> Dict[str, Any]:
    """Run the fused search and relabel the result as V3 (no V1/V2 identity leaks)."""
    if (search.rip_comparison_authority, search.financial_comparison_authority) != (
            COMPARISON_AUTHORITY_OVERALL_V14, COMPARISON_AUTHORITY_FINANCIAL_V5):
        raise BestOpenPriceSearchError("search is not bound to the V3 authorities")
    raw = search.search()
    if BEST_OPEN_PRICE_METHOD_VERSION == BEST_OPEN_PRICE_V3_METHOD_VERSION:
        raise BestOpenPriceSearchError("V3 identity collides with V1")
    return {
        "overallResult": _relabel_axis(raw["ripResult"], search.rip_benchmark),
        "financialResult": _relabel_axis(raw["financialResult"], search.financial_benchmark),
        "diagnostics": raw["diagnostics"],
    }
