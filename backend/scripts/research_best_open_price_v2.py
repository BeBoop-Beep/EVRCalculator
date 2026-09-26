"""Best-Open Price V2 dual-threshold research engine (no persistence, no publication).

Computes RIP (OVERALL_V12) and Financial (FINANCIAL_V4) exact thresholds for
the Full Market cohort. Deliberately has no checkpoint/resume or deterministic-
replay machinery -- this is an unpublished in-memory research artifact; that
production-hardening belongs to a later publication phase, not this one.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.calculations.evr.best_open_price import (
    BEST_OPEN_PRICE_V2_METHOD_VERSION,
    DualBestOpenPriceSearch,
    PreparedCanonicalCandidate,
)
from backend.calculations.evr.budget_normalized_product_ranking import build_budget_strategy_values
from backend.calculations.evr.financial_rip_v3 import PreparedFinancialRipDistribution
from backend.calculations.evr.sealed_product_distribution import build_single_q_parity_distributions
from backend.db.services.best_open_price_authority import validate_source
from backend.db.services.pack_outcome_artifact_service import load_pack_outcome_artifact
from backend.scripts.build_budget_normalized_product_rankings import build_stage1_distributions_cached
from backend.scripts.research_best_open_price_bucket0 import (
    _comparator_row,
    _competitor,
    _financial_competitor,
    _historical_authority,
    _load_exact_source_products,
    _load_source,
    _verify_v12_parity,
    validate_financial_only_rank_reconstructs,
    validate_rank_column_contiguous,
)


def build_v2_row(
    dual_result: Mapping[str, Any],
    *,
    source_row: Mapping[str, Any],
    rip_benchmark: Optional[Mapping[str, Any]] = None,
    financial_benchmark: Optional[Mapping[str, Any]] = None,
    current_price_cents: Optional[int] = None,
) -> Dict[str, Any]:
    """Assemble one V2 result row from a DualBestOpenPriceSearch.search() output.

    Every threshold-evidence field is copied verbatim from the actual scored
    threshold candidate the exact engine returned -- never recomputed here.

    ``rip_benchmark``/``financial_benchmark`` are the raw comparator-row
    mapping dicts (as produced by ``_comparator_row()``) used to construct
    each search's ``benchmark`` argument. They are threaded through as extra
    keyword parameters because ``ExactBestOpenPriceSearch._payload()`` does
    not itself expose a ``benchmarkFinancialRipV4Score`` field on its search
    result (verified against the current implementation) -- rather than
    inventing a new field on the search engine, this reads the value directly
    from the raw benchmark mapping the caller already has in hand.
    """
    rip = dual_result["ripResult"]
    financial = dual_result["financialResult"]
    rip_threshold = rip.get("threshold") or {}
    financial_threshold = financial.get("threshold") or {}
    rip_resolved = rip.get("status") == "exact"
    financial_resolved = financial.get("status") == "exact"
    rip_benchmark = rip_benchmark or {}
    financial_benchmark = financial_benchmark or {}
    if current_price_cents is None and source_row.get("product_market_price") is not None:
        current_price_cents = int(round(float(source_row["product_market_price"]) * 100))

    row: Dict[str, Any] = {
        "methodVersion": BEST_OPEN_PRICE_V2_METHOD_VERSION,
        "sealedProductId": str(source_row["sealed_product_id"]),
        # Identity + current-state fields the persistence layer needs
        # (parity with research_best_open_price_bucket2.py's execute_product()
        # V1 engine_row construction) -- straight copies from the source row
        # this function already has in hand, never recomputed.
        "setId": str(source_row["set_id"]) if source_row.get("set_id") is not None else None,
        "productFamily": source_row.get("product_family"),
        "sourceCalculationRunId": source_row.get("source_calculation_run_id"),
        "currentQuantity": int(source_row["quantity"]) if source_row.get("quantity") is not None else None,
        "currentOverallRipV12Score": source_row.get("overall_rip_v12_score"),
        "currentFinancialRipV4Score": source_row.get("financial_rip_v4_score"),
        "currentCollectorAppealScore": source_row.get("collector_appeal_score"),
        "currentChaseAccessibilityRaw": source_row.get("chase_accessibility_raw"),
        "currentChanceToRecoverCapital": source_row.get("chance_to_recover_capital"),
        "currentActualCommittedCapital": source_row.get("actual_committed_capital"),
        "currentBudgetRank": int(source_row["budget_rank_v12"]),
        "currentFinancialOnlyRank": int(source_row["financial_only_rank"]),
        "resolved": bool(rip_resolved and financial_resolved),
        "ripResolved": rip_resolved,
        "financialResolved": financial_resolved,
        "diagnostics": dict(dual_result.get("diagnostics") or {}),
    }
    if current_price_cents is not None:
        row["currentMarketPrice"] = current_price_cents / 100.0
    elif source_row.get("product_market_price") is not None:
        row["currentMarketPrice"] = float(source_row["product_market_price"])

    # --- RIP fields: both the backward-compatible generic aliases AND the
    # explicit rip* names, per Phase 5's contract. ---
    rip_price_cents = rip_threshold.get("priceCents")
    # Mirrors research_best_open_price_bucket2.py's execute_product() exactly:
    # gap_dollars = (current_cents - threshold_cents) / 100.0
    # gap_percent = (current_cents - threshold_cents) / current_cents
    if rip_price_cents is not None and current_price_cents:
        price_gap_dollars = (current_price_cents - rip_price_cents) / 100.0
        price_gap_percent = (current_price_cents - rip_price_cents) / current_price_cents
    else:
        price_gap_dollars = price_gap_percent = None
    row.update({
        "bestOpenPrice": (rip_price_cents / 100.0) if rip_price_cents is not None else None,
        "bestOpenPriceCents": rip_price_cents,
        "status": rip.get("status"),
        "thresholdQuantity": rip_threshold.get("quantity"),
        "benchmarkSealedProductId": rip.get("benchmarkProductId"),
        "benchmarkOverallRipV12Score": rip.get("benchmarkOverallRipV12Score"),
        # Generic (RIP-aliased) benchmark evidence + diagnostics counts the
        # persistence layer needs (same keys/meaning as V1's engine_row) --
        # sourced from the RIP benchmark mapping and the RIP search's own
        # _payload() diagnostics, never recomputed.
        "benchmarkFinancialRipV4Score": rip_benchmark.get("financialRipV4Score"),
        "benchmarkChanceToRecoverCapital": rip_benchmark.get("chanceToRecoverCapital"),
        "benchmarkActualCommittedCapital": rip_benchmark.get("actualCommittedCapital"),
        "candidatePriceEvaluations": rip.get("evaluationCount", 0),
        "bracketExpansions": rip.get("bracketExpansions", 0),
        "bracketRefinements": rip.get("bracketRefinements", 0),
        "fallbackCount": rip.get("monotonicityFallbackCount", 0),
        "searchWallSeconds": rip.get("wallSeconds", 0.0),
        "exactness": rip.get("exactness"),
        "priceGapDollars": price_gap_dollars,
        "priceGapPercent": price_gap_percent,

        "ripBestOpenPrice": (rip_price_cents / 100.0) if rip_price_cents is not None else None,
        "ripBestOpenPriceCents": rip_price_cents,
        "ripStatus": rip.get("status"),
        "ripThresholdQuantity": rip_threshold.get("quantity"),
        "ripBenchmarkSealedProductId": rip.get("benchmarkProductId"),
        "ripBenchmarkOverallRipV12Score": rip.get("benchmarkOverallRipV12Score"),
        "ripBenchmarkFinancialRipV4Score": rip_benchmark.get("financialRipV4Score"),
        "ripExactness": rip.get("exactness"),
        "ripThresholdFinancialRipV4Score": rip_threshold.get("financialRipV4Score"),
        "ripThresholdOverallRipV12Score": rip_threshold.get("overallRipV12Score"),
        "ripThresholdChanceToRecoverCapital": rip_threshold.get("chanceToRecoverCapital"),
        "ripThresholdActualCommittedCapital": rip_threshold.get("actualCommittedCapital"),
        "ripPriceGapDollars": price_gap_dollars,
        "ripPriceGapPercent": price_gap_percent,
    })

    # --- Financial fields: explicit financial* names only (no generic alias
    # -- the generic/legacy names mean RIP, per the backward-compatibility
    # requirement). ---
    financial_price_cents = financial_threshold.get("priceCents")
    # Same formula pattern as the RIP gap fields above, computed against the
    # Financial threshold instead of the RIP threshold.
    if financial_price_cents is not None and current_price_cents:
        financial_price_gap_dollars = (current_price_cents - financial_price_cents) / 100.0
        financial_price_gap_percent = (current_price_cents - financial_price_cents) / current_price_cents
    else:
        financial_price_gap_dollars = financial_price_gap_percent = None
    row.update({
        "financialBestOpenPrice": (financial_price_cents / 100.0) if financial_price_cents is not None else None,
        "financialBestOpenPriceCents": financial_price_cents,
        "financialStatus": financial.get("status"),
        "financialThresholdQuantity": financial_threshold.get("quantity"),
        "financialBenchmarkSealedProductId": financial.get("benchmarkProductId"),
        "financialBenchmarkFinancialRipV4Score": financial_benchmark.get("financialRipV4Score"),
        "financialBenchmarkOverallRipV12Score": financial.get("benchmarkOverallRipV12Score"),
        "financialExactness": financial.get("exactness"),
        "financialThresholdFinancialRipV4Score": financial_threshold.get("financialRipV4Score"),
        "financialThresholdOverallRipV12Score": financial_threshold.get("overallRipV12Score"),
        "financialThresholdChanceToRecoverCapital": financial_threshold.get("chanceToRecoverCapital"),
        "financialThresholdActualCommittedCapital": financial_threshold.get("actualCommittedCapital"),
        "financialPriceGapDollars": financial_price_gap_dollars,
        "financialPriceGapPercent": financial_price_gap_percent,
    })

    return row


def run(
    client: Any,
    *,
    source_snapshot_id: str,
    expected_source_authority_fingerprint: str,
    product_ids: Optional[Sequence[str]] = None,
    max_quantity_to_construct: int = 4096,
    skip_product_ids: Optional[set[str]] = None,
    checkpoint_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    enable_quantity_prefetch: bool = False,
    bounded_batching: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Per-cohort V2 engine entry point.

    Deliberately simpler than V1's research_best_open_price_bucket2.run(): NO
    checkpoint/resume machinery and NO deterministic-replay subset in this
    landing -- those are V1 production-hardening concerns; this phase is
    explicitly "engine + in-memory contract only, does not publish", so
    checkpointing an unpublished research artifact is out of scope (YAGNI).
    """
    snapshot, source_rows, all_rows = _load_source(client, source_snapshot_id)
    validate_source(snapshot)
    validate_rank_column_contiguous(source_rows, "budget_rank_v12")
    validate_rank_column_contiguous(source_rows, "financial_only_rank")
    validate_financial_only_rank_reconstructs(source_rows)
    # RIP-axis fail-closed guard, equivalent to the Financial-axis
    # validate_financial_only_rank_reconstructs() check above: reconstructs
    # overall_rip_v12_score from its components and raises on any mismatch,
    # before any expensive per-product search work runs. Mirrors
    # research_best_open_price_bucket2.py's run(), which calls this on the
    # whole source snapshot before proceeding.
    _verify_v12_parity(all_rows, label="V2 whole source snapshot")

    authority = _historical_authority(snapshot, source_rows)
    if authority["fingerprint"] != expected_source_authority_fingerprint:
        raise RuntimeError("source authority fingerprint mismatch")

    budget = float(snapshot["full_market_budget"])
    budget_cents = round(budget * 100)
    products = _load_exact_source_products(client, source_rows, str(snapshot["pinned_price_as_of"]))
    product_by_id = {str(p["sealed_product_id"]): p for p in products}
    source_by_id = {str(r["sealed_product_id"]): r for r in source_rows}

    ordered = sorted(source_rows, key=lambda r: int(r["budget_rank_v12"]))
    if product_ids is not None:
        product_ids = [str(pid) for pid in product_ids]
        missing = [pid for pid in product_ids if pid not in source_by_id]
        if missing:
            raise RuntimeError(f"requested product_ids not in cohort: {missing}")
        wanted = set(product_ids)
        ordered = [r for r in ordered if str(r["sealed_product_id"]) in wanted]

    rows_out = []
    for source in ordered:
        pid = str(source["sealed_product_id"])
        if skip_product_ids and pid in skip_product_ids:
            continue
        product = product_by_id[pid]
        rip_competitor = _competitor(source, source_rows)
        rip_benchmark = _comparator_row(rip_competitor, budget)
        financial_competitor = _financial_competitor(source, source_rows)
        financial_benchmark = _comparator_row(financial_competitor, budget)

        # Mirrors research_best_open_price_bucket2.py's execute_product()
        # artifact-loading + factory/batch_factory closure construction
        # (lines ~277-365 there) exactly, up to but not including its
        # ExactBestOpenPriceSearch(...) construction. That construction is
        # deliberately NOT reused here: DualBestOpenPriceSearch builds and
        # runs its own pair of ExactBestOpenPriceSearch instances internally,
        # sharing ONE quantity-level candidate cache and ONE SharedScoreCache
        # across the RIP and Financial searches for this product. Calling
        # execute_product() as-is would construct and run a single V1 engine
        # internally, defeating that shared-construction requirement.
        run_id = str(product["calculation_run_id"])
        # Bounded retry, mirroring research_best_open_price_bucket2.py's
        # execute_product() exactly: a single transient artifact-fetch
        # failure (this project's Pokemon TCG API provider has documented
        # ~50% random 500s) must not abort the entire cohort run.
        artifact_error = None
        for attempt in range(3):
            try:
                artifact = load_pack_outcome_artifact(client, run_id)
                artifact_error = None
                break
            except Exception as exc:  # bounded retry; final exception remains fail-closed
                artifact_error = exc
                if attempt < 2:
                    time.sleep(attempt + 1)
        if artifact_error is not None:
            raise artifact_error
        random_count = int(product.get("random_pack_count") or product["pack_count"])
        base = build_stage1_distributions_cached(artifact, random_count, run_id)

        def factory(quantity: int, *, _product=product, _pid=pid, _source=source, _base=base) -> PreparedCanonicalCandidate:
            random_values = build_budget_strategy_values(
                base_random_pack_values=_base, quantity=quantity,
                guaranteed_component_market_value=None,
                canonical_set_key=f"budget:{_pid}", run_fingerprint=None,
            )
            prepared = PreparedFinancialRipDistribution.prepare(
                random_values,
                value_offset=float(_product.get("guaranteed_component_market_value") or 0) * quantity,
            )
            return PreparedCanonicalCandidate(
                _pid, quantity, prepared, float(_source["collector_appeal_score"]),
                float(authority["rawBySet"][str(_product["set_id"])]), budget,
            )

        def batch_factory(
            quantities: Sequence[int], *, _product=product, _pid=pid, _source=source, _base=base,
        ) -> Mapping[int, PreparedCanonicalCandidate]:
            built = build_single_q_parity_distributions(
                _base, quantities=quantities, canonical_set_key=f"budget:{_pid}",
                run_fingerprint=None,
            )
            prepared_batch: Dict[int, PreparedCanonicalCandidate] = {}
            values_by_quantity = built["distributions"]
            for quantity in quantities:
                values = values_by_quantity.pop(quantity)
                prepared = PreparedFinancialRipDistribution.prepare(
                    values,
                    value_offset=float(_product.get("guaranteed_component_market_value") or 0) * quantity,
                )
                prepared_batch[quantity] = PreparedCanonicalCandidate(
                    _pid, quantity, prepared, float(_source["collector_appeal_score"]),
                    float(authority["rawBySet"][str(_product["set_id"])]), budget,
                )
            return prepared_batch

        bounded_kwargs: Dict[str, Any] = {}
        if bounded_batching is not None:
            # Opt-in bounded look-ahead engine (best_open_price_v2_fused_batched).
            # Raw blocks come from the same exact single-q parity builder;
            # prepared scorers are built lazily, one quantity at a time.
            def block_builder(
                quantities: Sequence[int], *, _pid=pid, _base=base, **build_kwargs: Any,
            ) -> Mapping[str, Any]:
                return build_single_q_parity_distributions(
                    _base, quantities=quantities, canonical_set_key=f"budget:{_pid}",
                    run_fingerprint=None, **build_kwargs,
                )

            _bounded_options = dict(bounded_batching)
            _prepare_variant = _bounded_options.pop("prepare_variant", "canonical")
            if _prepare_variant not in ("canonical", "accelerated"):
                raise ValueError(f"unknown prepare_variant {_prepare_variant!r}")
            _prepare = (PreparedFinancialRipDistribution.prepare_exact_accelerated
                        if _prepare_variant == "accelerated" else PreparedFinancialRipDistribution.prepare)

            def prepare_values(
                quantity: int, values: Any, *, _product=product, _pid=pid, _source=source,
            ) -> PreparedCanonicalCandidate:
                prepared = _prepare(
                    values,
                    value_offset=float(_product.get("guaranteed_component_market_value") or 0) * quantity,
                )
                return PreparedCanonicalCandidate(
                    _pid, quantity, prepared, float(_source["collector_appeal_score"]),
                    float(authority["rawBySet"][str(_product["set_id"])]), budget,
                )

            bounded_kwargs = {
                "build_block": block_builder,
                "prepare_from_values": prepare_values,
                "rng_outcome_count": len(base),
                **_bounded_options,
            }

        dual = DualBestOpenPriceSearch(
            product_id=pid, budget_cents=budget_cents,
            current_price_cents=int(round(float(source["product_market_price"]) * 100)),
            current_quantity=int(source["quantity"]),
            rip_current_rank=int(source["budget_rank_v12"]), rip_benchmark=rip_benchmark,
            financial_current_rank=int(source["financial_only_rank"]), financial_benchmark=financial_benchmark,
            prepare_quantity=factory,
            prepare_quantities=batch_factory,
            source_authority_fingerprint=authority["fingerprint"],
            expected_source_authority_fingerprint=expected_source_authority_fingerprint,
            max_quantity_to_construct=max_quantity_to_construct,
            **({"enable_quantity_prefetch": True} if enable_quantity_prefetch else {}),
            **bounded_kwargs,
        )
        if enable_quantity_prefetch:
            from backend.calculations.evr.sealed_product_distribution import single_q_parity_batch_width
            dual.quantity_batch_size = single_q_parity_batch_width(
                len(base), requested_width=8,
                maximum_quantity=max_quantity_to_construct,
            )
            dual.rng_outcome_count = len(base)
        result = dual.search()
        row = build_v2_row(
            result, source_row=source, rip_benchmark=rip_benchmark, financial_benchmark=financial_benchmark,
            current_price_cents=int(round(float(source["product_market_price"]) * 100)),
        )
        rows_out.append(row)
        if checkpoint_callback is not None:
            checkpoint_callback(row)

    attempted = len(rows_out)
    rip_resolved = sum(1 for r in rows_out if r["ripResolved"])
    financial_resolved = sum(1 for r in rows_out if r["financialResolved"])
    unresolved = sum(1 for r in rows_out if not r["resolved"])
    status = "complete" if (rip_resolved == attempted and financial_resolved == attempted and unresolved == 0) else "incomplete"

    return {
        "status": status,
        "methodVersion": BEST_OPEN_PRICE_V2_METHOD_VERSION,
        "products": rows_out,
        "cohortAnalysis": {
            "attempted": attempted, "ripResolved": rip_resolved,
            "financialResolved": financial_resolved, "unresolved": unresolved,
        },
    }
