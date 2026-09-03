"""Cohort-level Chase Accessibility authority for the V12 BUDGET ranking.

GATE F ARCHITECTURE RULE (see docs/research/OVERALL_RIP_V12_CANONICAL_PROMOTION_IMPLEMENTATION.md,
"Gate F completion"): Chase Accessibility is SET-level, invariant across
product SKUs of a set and invariant across budget quantity for a given
coherent calculation run. It must be read ONCE per cohort here, at the
orchestration layer - NEVER inside the budget simulation engine
(``backend.calculations.evr.budget_normalized_product_ranking``) and NEVER
per-product or per-budget.

This module is the budget-ranking analogue of
``backend.db.services.sealed_product_rip_finalization_service._overall_rip_v12_for``
- same authority rule (exact ``calculation_run_id`` match, exact version,
``mapped_hc_mass >= MIN_MAPPED_HC_MASS``, never a "latest" fallback) - but
resolved for a WHOLE cohort of sets in one batch read instead of per-row.

It deliberately reuses ``chase_accessibility_service.read_chase_accessibility_snapshots_for_sets``
(the one-query batch reader) and
``chase_accessibility_service.publication_integrity_failures`` (the exact
same failure taxonomy the sealed-product finalizer's coordinated publication
already treats as authoritative) rather than reimplementing either.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Mapping, Sequence

from backend.db.services.chase_accessibility_service import (
    CHASE_ACCESSIBILITY_VERSION,
    publication_integrity_failures,
    read_chase_accessibility_snapshots_for_sets,
)

#: Frozen identity of the additive V12-Overall-over-Accessibility transform.
#: See ``compute_overall_rip_v12`` - the transform itself is NOT reimplemented
#: here, this is only the version string persisted as authority evidence.
CHASE_ACCESSIBILITY_TRANSFORM_VERSION = "chase_accessibility_overall_score_v1_saturating_k002"


def resolve_budget_cohort_accessibility(
    client: Any,
    run_id_by_set_id: Mapping[str, str],
) -> Dict[str, Any]:
    """Resolve coherent set-level Chase Accessibility for a WHOLE budget cohort.

    ONE batch read (``read_chase_accessibility_snapshots_for_sets``) covers
    every set in ``run_id_by_set_id`` - never a query inside a per-product or
    per-budget loop. Returns a dict keyed by ``set_id`` with, for each set,
    either a coherent raw Accessibility value or an explicit rejection reason
    list; a set is NEVER given a fallback value.
    """
    set_ids = sorted({str(s) for s in run_id_by_set_id})
    raw_by_set = read_chase_accessibility_snapshots_for_sets(set_ids=set_ids, client=client)

    failures = publication_integrity_failures(
        list(raw_by_set.values()),
        simulation_supported_set_ids=set_ids,
        expected_run_by_set={str(k): str(v) for k, v in run_id_by_set_id.items()},
    )
    failures_by_set: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for failure in failures:
        failures_by_set[str(failure["setId"])].append(failure)

    by_set: Dict[str, Dict[str, Any]] = {}
    for set_id in set_ids:
        set_failures = failures_by_set.get(set_id) or []
        if set_failures:
            by_set[set_id] = {
                "aRaw": None,
                "ready": False,
                "reasons": set_failures,
                "calculationRunId": (raw_by_set.get(set_id) or {}).get("calculation_run_id"),
                "version": (raw_by_set.get(set_id) or {}).get("version"),
                "mappedHcMass": (raw_by_set.get(set_id) or {}).get("mapped_hc_mass"),
            }
            continue
        row = raw_by_set[set_id]
        by_set[set_id] = {
            "aRaw": row.get("accessibility"),
            "ready": True,
            "reasons": [],
            "calculationRunId": row.get("calculation_run_id"),
            "version": row.get("version"),
            "mappedHcMass": row.get("mapped_hc_mass"),
        }

    return {
        "batchReadCount": 1,
        "requestedSetCount": len(set_ids),
        "readySetCount": sum(1 for v in by_set.values() if v["ready"]),
        "chaseAccessibilityVersion": CHASE_ACCESSIBILITY_VERSION,
        "transformVersion": CHASE_ACCESSIBILITY_TRANSFORM_VERSION,
        "bySet": by_set,
        "failures": failures,
    }


def accessibility_raw_for_product(
    resolved: Mapping[str, Any],
    set_id: Any,
) -> Any:
    """``A_raw`` for one product's set, or ``None`` if unavailable/rejected.

    Pure lookup against an already-resolved cohort - never issues I/O. Callers
    (e.g. the budget build script) must call
    :func:`resolve_budget_cohort_accessibility` exactly once per cohort and
    pass its result here for every product/budget combination, instead of
    re-resolving per row.
    """
    entry = (resolved.get("bySet") or {}).get(str(set_id))
    if not entry or not entry.get("ready"):
        return None
    return entry.get("aRaw")
