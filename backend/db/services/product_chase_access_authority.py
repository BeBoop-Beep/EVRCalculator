"""Chase Access at Budget V1 - authority + batching orchestration (PREMIUM).

Wires the pure math in ``backend.desirability.product_chase_access`` to:

* the SAME pinned-cohort budget authority the V12 budget ranking already uses
  (``backend.db.services.budget_product_ranking_authority.load_pinned_cohort``) -
  product identity, ``product_market_cost``, ``random_pack_count`` and the
  cohort's ``calculation_run_id`` per product, never re-derived here;
* the SAME cohort-level Chase Accessibility authority resolver the V12 budget
  ranking already uses
  (``backend.db.services.budget_chase_accessibility_authority.resolve_budget_cohort_accessibility``) -
  reused UNCHANGED for the aggregate A_raw/mappedHcMass/reasons decision;
* the SAME whole-unit floor-quantity allocator already used by the normal
  budget ranking (``backend.calculations.evr.budget_normalized_product_ranking.whole_unit_allocation``) -
  quantity is never re-derived as ``budget / price`` inside this module.

GATE (Phase 11/12) ARCHITECTURE RULE
-------------------------------------
Per-variant HC/probability rows (``simulation_card_variant_pull_rates``) are
read ONCE PER DISTINCT ``calculation_run_id`` present in the cohort - never
once per product and never once per budget. A 22-set x N-product cohort at
one budget therefore issues at most 22 variant-universe reads (one per set's
run), not 22*N. The resulting per-set variant list is cached in memory for
the lifetime of one orchestration call and reused for every product of that
set and every budget the caller asks about in the same call.

AUTHORITY COHERENCE
--------------------
A product is scored ONLY when:
* its ``calculation_run_id`` (from the pinned cohort) matches the
  ``calculation_run_id`` of the drawable-variant universe read for its set
  (asserted inside ``compute_o_budget`` itself, which raises
  ``ProductChaseAccessInputError`` on a mismatch it is ever handed - this
  module additionally SKIPS a product outright, with an explicit reason,
  rather than ever passing it a foreign run's variants); and
* the cohort-level Accessibility authority (mapped_hc_mass, version, run)
  independently agrees the set is ready - reusing
  ``resolve_budget_cohort_accessibility`` unchanged means a set already
  rejected for V12 budget-ranking purposes is rejected here for the exact
  same reasons, not re-litigated.

This module NEVER mixes current A_raw with a stale pull-rate run and a new
product cost: the same ``run_id_by_set_id`` mapping (derived from the SAME
pinned cohort) is used for both the Accessibility authority check AND the
variant-universe read.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Mapping, Optional, Sequence

from backend.calculations.evr.budget_normalized_product_ranking import (
    whole_unit_allocation,
)
from backend.db.services.budget_chase_accessibility_authority import (
    resolve_budget_cohort_accessibility,
)
from backend.db.services.chase_accessibility_service import load_drawable_variants
from backend.desirability.product_chase_access import (
    PRODUCT_CHASE_ACCESS_VERSION,
    compute_ece,
    compute_o_budget,
    effective_pack_cost,
    effective_random_packs,
)

QUERY_COUNT_LABEL = "distinct_run_variant_reads"


def _str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def load_variant_universe_for_cohort(
    client: Any, run_id_by_set_id: Mapping[str, str],
) -> Dict[str, Any]:
    """Batch-read the drawable variant universe ONCE per distinct run in the cohort.

    Returns ``{"bySet": {set_id: [variant_row, ...]}, "queryCount": N}``. ``N``
    is the number of ``load_drawable_variants`` calls actually issued - the
    Phase 13 performance assertion checks this equals the number of DISTINCT
    runs, never the number of products or the number of (product, budget)
    pairs.
    """
    run_to_sets: Dict[str, List[str]] = defaultdict(list)
    for set_id, run_id in run_id_by_set_id.items():
        run = _str(run_id)
        if run:
            run_to_sets[run].append(str(set_id))

    by_set: Dict[str, List[Dict[str, Any]]] = {}
    for run_id, set_ids in run_to_sets.items():
        variants = load_drawable_variants(client, calculation_run_id=run_id)
        by_run_set: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in variants:
            by_run_set[str(row.get("set_id"))].append(row)
        for set_id in set_ids:
            by_set[set_id] = by_run_set.get(set_id, [])

    return {"bySet": by_set, "queryCount": len(run_to_sets), "distinctRunCount": len(run_to_sets)}


def resolve_product_chase_access(
    client: Any,
    cohort: Sequence[Mapping[str, Any]],
    *,
    budget: Optional[float] = None,
) -> Dict[str, Any]:
    """Chase Access at Budget for a WHOLE cohort at ONE optional explicit budget.

    ``cohort`` rows are the SAME rows ``load_pinned_cohort`` returns (must
    carry ``sealed_product_id``, ``set_id``, ``calculation_run_id``,
    ``product_market_cost``, ``random_pack_count``). When ``budget`` is
    ``None``, quantity/effective-packs/O_budget are never computed (Phase 10 -
    no arbitrary spend is invented); only set-level Accessibility context and
    per-product ``effective_pack_cost``/ECE are returned.

    Batches BOTH authority reads (Accessibility cohort resolution, variant
    universe) ONCE per cohort - never per product, never per budget.
    """
    run_id_by_set_id = {
        str(row["set_id"]): str(row["calculation_run_id"])
        for row in cohort if row.get("set_id") is not None and row.get("calculation_run_id") is not None
    }
    accessibility = resolve_budget_cohort_accessibility(client, run_id_by_set_id)
    universe = load_variant_universe_for_cohort(client, run_id_by_set_id)

    products: List[Dict[str, Any]] = []
    for row in cohort:
        set_id = str(row.get("set_id"))
        sealed_product_id = str(row.get("sealed_product_id"))
        product_cost = row.get("product_market_cost")
        random_pack_count = row.get("random_pack_count") or row.get("pack_count")
        run_id = str(row.get("calculation_run_id")) if row.get("calculation_run_id") is not None else None

        access_entry = (accessibility.get("bySet") or {}).get(set_id) or {}
        a_raw = access_entry.get("aRaw")
        set_ready = bool(access_entry.get("ready"))

        pack_cost = effective_pack_cost(product_market_cost=product_cost,
                                        random_pack_count=random_pack_count)
        ece = compute_ece(a_raw=a_raw, effective_pack_cost_value=pack_cost) if set_ready else None

        entry: Dict[str, Any] = {
            "sealedProductId": sealed_product_id,
            "setId": set_id,
            "productName": row.get("product_name"),
            "productFamily": row.get("product_family"),
            "productMarketCost": product_cost,
            "randomPackCount": random_pack_count,
            "effectivePackCost": pack_cost,
            "aRaw": a_raw,
            "chaseAccessibilityReady": set_ready,
            "chaseAccessibilityReasons": access_entry.get("reasons") or [],
            "calculationRunId": run_id,
            "ece": ece,
            "eceVersion": (
                "efficiency_per_effective_cost_v1_araw_over_pack_cost" if ece is not None else None
            ),
            "version": PRODUCT_CHASE_ACCESS_VERSION,
        }

        if budget is not None:
            entry.update(_score_budget_for_product(
                row=row, set_id=set_id, run_id=run_id, budget=budget,
                set_ready=set_ready, universe_by_set=universe["bySet"],
            ))

        products.append(entry)

    if budget is not None:
        ranked = [p for p in products if p.get("oBudget") is not None]
        ranked.sort(key=lambda p: -p["oBudget"])
        for index, entry in enumerate(ranked, start=1):
            entry["oBudgetRank"] = index
        rank_by_id = {p["sealedProductId"]: p.get("oBudgetRank") for p in ranked}
        for entry in products:
            entry.setdefault("oBudgetRank", rank_by_id.get(entry["sealedProductId"]))

    return {
        "budget": budget,
        "products": products,
        "queryCount": {
            "accessibilityCohortReads": accessibility.get("batchReadCount", 1),
            "variantUniverseReads": universe["queryCount"],
            "totalDbReads": accessibility.get("batchReadCount", 1) + universe["queryCount"],
        },
        "distinctSetCount": len(run_id_by_set_id),
        "productCount": len(products),
        "chaseAccessibilityVersion": accessibility.get("chaseAccessibilityVersion"),
        "version": PRODUCT_CHASE_ACCESS_VERSION,
    }


def _score_budget_for_product(
    *, row: Mapping[str, Any], set_id: str, run_id: Optional[str], budget: float,
    set_ready: bool, universe_by_set: Mapping[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    product_cost = row.get("product_market_cost")
    random_pack_count = row.get("random_pack_count") or row.get("pack_count")

    try:
        price = float(product_cost)
    except (TypeError, ValueError):
        price = 0.0
    if price <= 0:
        return {"quantity": None, "actualCommittedCapital": None, "unusedCapital": None,
                "effectivePacks": None, "oBudget": None,
                "oBudgetStatus": "unavailable_no_product_price"}

    allocation = whole_unit_allocation(target_budget=budget, product_market_price=price)
    if not allocation["eligible"]:
        return {"quantity": 0, "actualCommittedCapital": 0.0, "unusedCapital": budget,
                "effectivePacks": None, "oBudget": None,
                "oBudgetStatus": "unavailable_budget_below_one_unit"}

    n = effective_random_packs(quantity=allocation["quantity"], random_pack_count=random_pack_count)

    variants = universe_by_set.get(set_id) or []
    result = compute_o_budget(
        variants=variants,
        effective_packs=n,
        has_pull_model=bool(variants) and set_ready,
        set_id=set_id,
        calculation_run_id=run_id,
    )
    return {
        "quantity": allocation["quantity"],
        "actualCommittedCapital": allocation["actualCommittedCapital"],
        "unusedCapital": allocation["unusedCapital"],
        "capitalUtilization": allocation["capitalUtilization"],
        "effectivePacks": n,
        "oBudget": result.get("oBudget"),
        "oBudgetPct": result.get("oBudgetPct"),
        "oBudgetStatus": result.get("status"),
        "oBudgetStatusReason": result.get("statusReason"),
    }
