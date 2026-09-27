"""EXPLICIT (non-default, non-scheduled) Best-Open Price V3 orchestration.

V3 thresholds are searched with the unchanged exact-cent fused engine against Financial RIP V5 and Overall
RIP V14, seeded from a persisted ``budget_product_ranking_v2`` snapshot, and published through the versioned
RPC branch validated on real PostgreSQL. Nothing here is imported by the current/scheduled Best-Open publisher
and no public read service or selector is changed: V3 does not become the public method until an explicitly
authorized activation.

CURRENTNESS IS METHOD-AWARE. A persisted V3 snapshot is current only when bound to the exact live Ranking V2
snapshot (id, publication timestamp, cohort fingerprint) and carrying the exact V3 method, Financial V5 and
Overall V14 identities. A V1/V2 Best-Open publication is a different method and can neither satisfy nor mask
a V3 candidate; and a V3 snapshot never stands in for the public V1/V2 result.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from backend.calculations.evr.best_open_price import BestOpenPriceSearchError
from backend.calculations.evr.best_open_price_v3 import (
    BEST_OPEN_PRICE_V3_METHOD_VERSION,
    PreparedV5Candidate,
    build_dual_best_open_v3_search,
    require_ranking_v2_source,
    run_dual_best_open_v3,
)
from backend.calculations.evr.budget_normalized_product_ranking import (
    BUDGET_NORMALIZED_RANKING_METHOD_VERSION_V2,
    build_budget_strategy_values,
)
from backend.calculations.evr.financial_rip_v3 import PreparedFinancialRipDistribution
from backend.calculations.evr.financial_rip_v5_config import FINANCIAL_RIP_V5_VERSION
from backend.db.services.budget_v2_v3_publication_payloads import (
    build_best_open_v3_row,
    build_best_open_v3_snapshot,
)
from backend.desirability.scoring_config import OVERALL_RIP_V14_VERSION


class BestOpenV3NotReady(RuntimeError):
    def __init__(self, reason: str, details: Sequence[Any] = ()):
        super().__init__(f"{reason}: {list(details)[:5]}" if details else reason)
        self.reason, self.details = reason, list(details)


def require_ranking_v2_snapshot(snapshot: Optional[Mapping[str, Any]]) -> None:
    """The V3 source must be a live Ranking V2 snapshot ranked under V14 - never V1/V12."""
    if not snapshot:
        raise BestOpenV3NotReady("no_live_ranking_v2_snapshot")
    try:
        require_ranking_v2_source(snapshot.get("ranking_method_version"))
    except BestOpenPriceSearchError as exc:
        raise BestOpenV3NotReady("source_is_not_ranking_v2", [str(exc)]) from exc
    bad = []
    if snapshot.get("ranked_under_v14_authority") is not True:
        bad.append("not ranked under V14 authority")
    if snapshot.get("overall_rip_v14_version") != OVERALL_RIP_V14_VERSION:
        bad.append("overall=%r" % (snapshot.get("overall_rip_v14_version"),))
    if snapshot.get("financial_rip_v5_version") != FINANCIAL_RIP_V5_VERSION:
        bad.append("financial=%r" % (snapshot.get("financial_rip_v5_version"),))
    if bad:
        raise BestOpenV3NotReady("ranking_v2_authority_mismatch", bad)


def is_v3_snapshot_current(v3_snapshot: Optional[Mapping[str, Any]], live_ranking_v2: Mapping[str, Any]) -> Dict[str, Any]:
    """Method-aware currentness of a persisted V3 snapshot. Returns ``{"current": bool, "reasons": [...]}``."""
    if not v3_snapshot:
        return {"current": False, "reasons": ["no_v3_snapshot"]}
    reasons = []
    if v3_snapshot.get("best_open_price_method_version") != BEST_OPEN_PRICE_V3_METHOD_VERSION:
        reasons.append("method=%r is not V3" % (v3_snapshot.get("best_open_price_method_version"),))
    if str(v3_snapshot.get("source_budget_snapshot_id")) != str(live_ranking_v2.get("id")):
        reasons.append("bound to a different Ranking V2 snapshot")
    if v3_snapshot.get("source_budget_published_at") != live_ranking_v2.get("published_at"):
        reasons.append("Ranking V2 publication timestamp differs")
    if v3_snapshot.get("source_cohort_fingerprint") != live_ranking_v2.get("cohort_fingerprint"):
        reasons.append("Ranking V2 cohort fingerprint differs")
    if v3_snapshot.get("financial_rip_version") != FINANCIAL_RIP_V5_VERSION:
        reasons.append("financial=%r" % (v3_snapshot.get("financial_rip_version"),))
    if v3_snapshot.get("overall_rip_v14_version") != OVERALL_RIP_V14_VERSION:
        reasons.append("overall=%r" % (v3_snapshot.get("overall_rip_v14_version"),))
    return {"current": not reasons, "reasons": reasons}


def make_v3_candidate_factories(
    *, product_id: str, base_values: Any, budget: float, guaranteed_per_unit: float, collector_score: float,
    chase_accessibility_raw: float, single_q_builder_fn: Callable[..., Any],
) -> Dict[str, Callable[..., Any]]:
    """Single-q and batched candidate factories. Same construction as the frozen-parity run."""

    def wrap(q: int, values: Any) -> PreparedV5Candidate:
        prepared = PreparedFinancialRipDistribution.prepare(values, value_offset=guaranteed_per_unit * q)
        return PreparedV5Candidate(product_id, q, prepared, collector_score, chase_accessibility_raw, budget)

    @lru_cache(maxsize=8)
    def prepare_quantity(q: int) -> PreparedV5Candidate:
        values = build_budget_strategy_values(
            base_random_pack_values=base_values, quantity=q, guaranteed_component_market_value=None,
            canonical_set_key=f"budget:{product_id}", run_fingerprint=None)
        return wrap(q, values)

    def prepare_quantities(quantities: Sequence[int]) -> Dict[int, PreparedV5Candidate]:
        built = single_q_builder_fn(base_values, quantities=quantities,
                                    canonical_set_key=f"budget:{product_id}", run_fingerprint=None)
        return {q: wrap(q, built["distributions"].pop(q)) for q in quantities}

    return {"prepare_quantity": prepare_quantity, "prepare_quantities": prepare_quantities}


def search_product_v3(
    *, current: Mapping[str, Any], overall_benchmark: Mapping[str, Any], financial_benchmark: Mapping[str, Any],
    budget_cents: int, factories: Mapping[str, Callable[..., Any]], source_authority_fingerprint: str,
    ranking_method_version: str, engine_kwargs: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Run the fused exact-cent search for one product against its OWN benchmark on each axis.

    ``current`` / benchmarks are persisted Ranking V2 rows (snake_case). The benchmark for an axis is the
    #1 row of that axis's own ranking authority (or #2 for that axis's leader), never a V4/V12 benchmark.
    """
    search = build_dual_best_open_v3_search(
        product_id=str(current["sealed_product_id"]), budget_cents=budget_cents,
        current_price_cents=round(float(current["product_market_price"]) * 100),
        current_quantity=int(current["quantity"]),
        overall_v14_current_rank=int(current["budget_rank_v14"]),
        overall_v14_benchmark=_engine_row(overall_benchmark),
        financial_v5_current_rank=int(current["financial_only_rank_v5"]),
        financial_v5_benchmark=_engine_row(financial_benchmark),
        source_ranking_method_version=ranking_method_version,
        prepare_quantity=factories["prepare_quantity"], prepare_quantities=factories.get("prepare_quantities"),
        source_authority_fingerprint=source_authority_fingerprint,
        expected_source_authority_fingerprint=source_authority_fingerprint, **dict(engine_kwargs or {}))
    return run_dual_best_open_v3(search)


def _engine_row(row: Mapping[str, Any]) -> Dict[str, Any]:
    """A persisted Ranking V2 row as the comparator's benchmark record (V5/V14 fields only)."""
    return {"sealedProductId": str(row["sealed_product_id"]),
            "financialRipV5Score": float(row["financial_rip_v5_score"]),
            "overallRipV14Score": float(row["overall_rip_v14_score"]), "overallRipV14Rankable": True,
            "chanceToRecoverCapital": float(row["chance_to_recover_capital"]),
            "actualCommittedCapital": float(row["actual_committed_capital"]),
            "targetBudget": float(row["target_budget"])}


def pick_benchmarks(current_row: Mapping[str, Any], by_overall_rank: Mapping[int, Mapping[str, Any]],
                    by_financial_rank: Mapping[int, Mapping[str, Any]]):
    """#1 of each axis's own authority, or #2 when the product is that axis's current leader."""
    overall = by_overall_rank[2 if int(current_row["budget_rank_v14"]) == 1 else 1]
    financial = by_financial_rank[2 if int(current_row["financial_only_rank_v5"]) == 1 else 1]
    return overall, financial


def assemble_best_open_v3_publication(
    *, source_ranking_snapshot: Mapping[str, Any], entries: Sequence[Mapping[str, Any]], built_at: str,
    runtime_seconds: float, source_full_market_row_fingerprint: str,
) -> Dict[str, Any]:
    """``entries``: dicts with current/overall_result/financial_result/overall_benchmark/financial_benchmark.
    A non-exact or non-V3 axis result raises (in the row builder); nothing unverified is published."""
    rows: List[Dict[str, Any]] = [build_best_open_v3_row(**e) for e in entries]
    snapshot = build_best_open_v3_snapshot(
        source_ranking_snapshot=source_ranking_snapshot, built_at=built_at, runtime_seconds=runtime_seconds,
        source_full_market_row_fingerprint=source_full_market_row_fingerprint, resolved_count=len(rows))
    return {"snapshot": snapshot, "rows": rows}


def publish_best_open_v3(client: Any, publication: Mapping[str, Any]) -> Any:
    """Commit through the versioned RPC dispatcher. Never touches the V1/V2 latest pointers."""
    if publication["snapshot"].get("best_open_price_method_version") != BEST_OPEN_PRICE_V3_METHOD_VERSION:
        raise BestOpenV3NotReady("snapshot_is_not_best_open_v3")
    if publication["snapshot"].get("ranking_method_version") != BUDGET_NORMALIZED_RANKING_METHOD_VERSION_V2:
        raise BestOpenV3NotReady("snapshot_source_is_not_ranking_v2")
    return client.rpc("publish_budget_product_best_open_price_snapshot",
                      {"p_snapshot": publication["snapshot"], "p_rows": publication["rows"]}).execute()
