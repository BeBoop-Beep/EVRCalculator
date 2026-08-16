"""Batch Collector Appeal / Overall RIP finalization for Stage 1 product rows.

WHY THIS EXISTS
---------------
The canonical Collector Appeal service is built around ONE bundle for ALL sets,
cached in-process. The daily opening publication launches every set simulation as
its OWN subprocess. Resolving Collector Appeal inside the per-set Stage 1 path
therefore defeated that cache by construction:

    process 1 -> full cold Collector Appeal build -> exit
    process 2 -> full cold Collector Appeal build -> exit
    ...

Stage 1.5 measured that cold build at ~105 s, ~98.9% of Stage 1 wall time, while
the entire financial half of Stage 1 (bootstrap + Financial RIP V3 + statistics)
came to well under a second. So per-set Stage 1 now persists Financial RIP and
stops, marking rows `pending_batch_enrichment`, and this service attaches the
appeal-dependent half ONCE for the whole cohort.

WHAT IT DOES NOT DO
-------------------
No formula lives here. Collector Appeal comes from `get_collector_appeal_bundle`,
the version check is Stage 1's own `interpret_collector_appeal_payload`, and the
blend is `compute_overall_rip_v8`. Nothing re-runs a simulation, regenerates a Y
distribution, recomputes a statistic, touches a market price or rewrites
Financial RIP V3. This is a join and two writes.

THE COHORT
----------
Enrichment is bounded to the calculation runs the opening-simulation gate already
considers CURRENT for the promoted market date - the same authority the daily
publication uses to decide it may publish at all. Rows are selected by
`calculation_run_id`, never by "Collector Appeal is null", because that predicate
has no boundary and would rewrite historical rows from older runs.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Mapping, Optional, Sequence

from backend.db.services.opening_simulation_gate import (
    STATUS_CURRENT,
    evaluate_opening_simulation_freshness,
)
from backend.db.services.sealed_product_rip_service import (
    COLLECTOR_APPEAL_STATUS_AVAILABLE,
    COLLECTOR_APPEAL_STATUS_UNAVAILABLE,
    interpret_collector_appeal_payload,
)
from backend.desirability.weighted_rip import compute_overall_rip_v8
from backend.domain.pokemon.sealed_product_comparison_scope import (
    sealed_product_comparison_scope_contract,
)

logger = logging.getLogger(__name__)

FINALIZER_VERSION = "sealed-product-rip-finalization-v1"

TAG = "[sealed-product-finalizer]"

STATUS_OK = "ok"
STATUS_NO_COHORT = "no_current_calculation_runs"
STATUS_NO_ROWS = "no_product_rows_in_cohort"
STATUS_CANNOT_START = "cannot_start"


def resolve_finalization_cohort(
    client: Any,
    *,
    market_date: Any,
    canonical_keys: Optional[Sequence[str]] = None,
    unsupported_keys: Sequence[str] = (),
) -> Dict[str, Any]:
    """The (set_id -> calculation_run_id) map the publication calls current.

    Reuses the opening-simulation gate rather than re-deriving freshness: two
    definitions of "the current run for this date" are one definition too many,
    and the one that already decides whether publication may proceed is the one
    that should decide what gets enriched.
    """
    report = evaluate_opening_simulation_freshness(
        client,
        market_date=market_date,
        canonical_keys=canonical_keys,
        unsupported_keys=unsupported_keys,
    )
    if report.error:
        return {"error": report.error, "marketDate": report.market_date, "runIdBySetId": {}}

    run_id_by_set_id: Dict[str, str] = {}
    set_key_by_run_id: Dict[str, str] = {}
    for status in report.statuses:
        if status.status != STATUS_CURRENT:
            continue
        if not status.set_id or not status.calculation_run_id:
            continue
        run_id_by_set_id[str(status.set_id)] = str(status.calculation_run_id)
        set_key_by_run_id[str(status.calculation_run_id)] = str(status.canonical_key or status.set_id)

    return {
        "error": None,
        "marketDate": report.market_date,
        "runIdBySetId": run_id_by_set_id,
        "setKeyByRunId": set_key_by_run_id,
        "verificationPassed": report.ok,
    }


def _enrichment_for(
    row: Mapping[str, Any],
    appeal: Mapping[str, Any],
) -> Dict[str, Any]:
    """The six enrichment columns for one row. Pure; performs no I/O."""
    appeal_score = appeal.get("score")
    overall = compute_overall_rip_v8(row.get("financial_rip_v3_score"), appeal_score)
    return {
        "collector_appeal_score": appeal_score,
        "collector_appeal_version": appeal.get("version"),
        "overall_rip_score": overall.get("score"),
        "overall_rip_version": overall.get("version"),
        "overall_rip_rankable": bool(overall.get("rankable")),
        "overall_rip_payload": overall,
    }


def finalize_sealed_product_rip(
    client: Any,
    *,
    market_date: Any,
    canonical_keys: Optional[Sequence[str]] = None,
    unsupported_keys: Sequence[str] = (),
    require_verified_cohort: bool = True,
    bundle_fn=None,
    read_rows_fn=None,
    update_fn=None,
) -> Dict[str, Any]:
    """Attach Collector Appeal + Overall RIP V8 to one coordinated cohort.

    Idempotent: the inputs are the persisted Financial RIP V3 score and the
    canonical bundle, and the write is a fixed function of those two. Re-running
    against the same run and the same bundle recomputes the same six values and
    writes them to the same rows - no new row, no new simulation, no new
    distribution.
    """
    started = time.perf_counter()

    if bundle_fn is None:
        from backend.db.services.collector_appeal_service import get_collector_appeal_bundle

        bundle_fn = get_collector_appeal_bundle
    if read_rows_fn is None:
        from backend.db.repositories.sealed_product_results_repository import (
            get_sealed_product_results_for_runs as read_rows_fn,  # type: ignore[misc]
        )
    if update_fn is None:
        from backend.db.repositories.sealed_product_results_repository import (
            update_sealed_product_enrichment as update_fn,  # type: ignore[misc]
        )

    cohort = resolve_finalization_cohort(
        client,
        market_date=market_date,
        canonical_keys=canonical_keys,
        unsupported_keys=unsupported_keys,
    )
    if cohort.get("error"):
        return _report(
            status=STATUS_CANNOT_START,
            market_date=cohort.get("marketDate"),
            error=cohort["error"],
            started=started,
        )

    if require_verified_cohort and not cohort.get("verificationPassed"):
        # An incomplete cohort must not be enriched as though it were complete:
        # the resulting rows would be indistinguishable from a fully coordinated
        # day while representing a partial one.
        return _report(
            status=STATUS_CANNOT_START,
            market_date=cohort.get("marketDate"),
            error="opening-simulation freshness did not pass; refusing to finalize a partial cohort",
            started=started,
        )

    run_id_by_set_id: Dict[str, str] = cohort["runIdBySetId"]
    if not run_id_by_set_id:
        return _report(
            status=STATUS_NO_COHORT,
            market_date=cohort.get("marketDate"),
            started=started,
        )

    rows = list(read_rows_fn(sorted(set(run_id_by_set_id.values()))))
    if not rows:
        return _report(
            status=STATUS_NO_ROWS,
            market_date=cohort.get("marketDate"),
            started=started,
            set_count=len(run_id_by_set_id),
        )

    # ---- exactly ONE canonical Collector Appeal build for the whole cohort ---
    bundle_started = time.perf_counter()
    bundle = bundle_fn(force_refresh=True) or {}
    bundle_ms = (time.perf_counter() - bundle_started) * 1000.0
    payloads = bundle.get("payloads") or {}

    # Interpreted once per SET, then shared by every product row of that set.
    # Two SKUs from one set inheriting two different appeal scores would be a
    # contradiction, so the interpretation cannot live in the row loop.
    appeal_by_set_id: Dict[str, Dict[str, Any]] = {
        set_id: interpret_collector_appeal_payload(payloads.get(str(set_id)))
        for set_id in run_id_by_set_id
    }

    finalized = 0
    unavailable = 0
    skipped: List[Dict[str, Any]] = []
    sets_touched = set()

    for row in rows:
        set_id = str(row.get("set_id") or "")
        row_id = row.get("id")
        expected_run_id = run_id_by_set_id.get(set_id)
        if row_id is None or expected_run_id is None or str(row.get("calculation_run_id")) != expected_run_id:
            # Belongs to a run outside the cohort, or to a set the gate did not
            # call current. Reported, never written.
            skipped.append(
                {
                    "id": row_id,
                    "setId": set_id,
                    "calculationRunId": row.get("calculation_run_id"),
                    "reason": "row_outside_current_cohort",
                }
            )
            continue

        appeal = appeal_by_set_id.get(set_id) or {
            "score": None,
            "version": None,
            "available": False,
            "status": COLLECTOR_APPEAL_STATUS_UNAVAILABLE,
        }
        # A set with no canonical Collector Appeal does NOT fail the cohort. Its
        # Financial RIP is untouched and still valid; Overall RIP stays
        # explicitly unavailable rather than being filled with a zero.
        if appeal.get("status") != COLLECTOR_APPEAL_STATUS_AVAILABLE:
            unavailable += 1

        # A genuine DB contract error here is allowed to raise: a finalizer that
        # swallowed write failures would report a finalized cohort that is not.
        update_fn(row_id, _enrichment_for(row, appeal))
        finalized += 1
        sets_touched.add(set_id)

    report = _report(
        status=STATUS_OK,
        market_date=cohort.get("marketDate"),
        started=started,
        rows_considered=len(rows),
        rows_finalized=finalized,
        rows_collector_appeal_unavailable=unavailable,
        skipped=skipped,
        set_count=len(sets_touched),
        cohort_set_count=len(run_id_by_set_id),
        bundle_ms=bundle_ms,
        bundle_identity=(bundle.get("identity") or {}).get("collectorAppealVersion"),
    )
    logger.info(
        "%s market_date=%s sets=%s rows_considered=%s finalized=%s ca_unavailable=%s "
        "skipped=%s bundle_ms=%.1f total_ms=%.1f",
        TAG,
        report["marketDate"],
        report["setCount"],
        report["rowsConsidered"],
        report["rowsFinalized"],
        report["rowsCollectorAppealUnavailable"],
        report["rowsSkipped"],
        report["collectorAppealBundleMs"],
        report["elapsedMs"],
    )
    return report


def _report(
    *,
    status: str,
    market_date: Any,
    started: float,
    error: Optional[str] = None,
    rows_considered: int = 0,
    rows_finalized: int = 0,
    rows_collector_appeal_unavailable: int = 0,
    skipped: Optional[Sequence[Mapping[str, Any]]] = None,
    set_count: int = 0,
    cohort_set_count: int = 0,
    bundle_ms: float = 0.0,
    bundle_identity: Any = None,
) -> Dict[str, Any]:
    skipped_list = list(skipped or [])
    return {
        "finalizerVersion": FINALIZER_VERSION,
        "status": status,
        "error": error,
        "marketDate": market_date,
        "rowsConsidered": int(rows_considered),
        "rowsFinalized": int(rows_finalized),
        "rowsCollectorAppealUnavailable": int(rows_collector_appeal_unavailable),
        "rowsSkipped": len(skipped_list),
        "skipped": skipped_list,
        "setCount": int(set_count),
        "cohortSetCount": int(cohort_set_count),
        # The whole point of the refactor, measured rather than asserted: this is
        # the cost paid ONCE for N sets instead of once per set.
        "collectorAppealBundleMs": round(bundle_ms, 1),
        "collectorAppealBundleBuilds": 1 if bundle_ms else 0,
        "collectorAppealVersion": bundle_identity,
        "elapsedMs": round((time.perf_counter() - started) * 1000.0, 3),
        **sealed_product_comparison_scope_contract(),
    }
