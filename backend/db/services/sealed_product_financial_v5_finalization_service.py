"""Exact-artifact Financial RIP V5 finalization + Overall RIP V14 per-row computation.

WHY THIS IS A SEPARATE, ARTIFACT-BACKED PATH
--------------------------------------------
Financial RIP V5 cannot be projected from a persisted V3/V4 payload: those payloads lack
E[(0.50 - R)+] (proved in Prompt 1). So V5 is rebuilt from the exact
``simulation_pack_outcome_artifacts`` row of the exact ``calculation_run_id`` that produced
the sealed-product row, never from summaries and never from another run.

Authority chain per current sealed-product row::

    opening-simulation gate -> exact current calculation_run_id -> exact artifact (loaded
    ONCE per run) -> product distribution (built ONCE per distinct pack count per run,
    same seed identity as Stage 1 / opening-economics-v3) -> guaranteed-component offset
    -> lineage gates -> build_financial_rip_v5 -> V5-only persistence.

Lineage gates (each fails CLOSED to a row-level ``unavailable``; nothing is fabricated):
  * the artifact loads and its outcome count equals the row's ``simulation_count``;
  * the regenerated vector reproduces the row's persisted EV / median / P05 / P95 / P99;
  * when a persisted Financial V4 score exists, recomputing V4 on the same vector and cost
    reproduces it (proves the seed identity, so V5 and V4 describe the SAME distribution);
  * the V5 payload validates and reconstructs its own Shortfall Resilience.

ROW-LEVEL vs COHORT-LEVEL
-------------------------
One unavailable row leaves only that row unavailable (its V4/V12 columns are untouched and
other rows still finalize). It does NOT make a partially V14-ranked cohort look complete:
the report's ``cohortComplete`` is true only when EVERY row of EVERY current run is ready,
and :func:`assert_v5_cohort_complete` is the gate a V14 publication must pass.

V5 is additive: this module writes only ``financial_rip_v5_*`` columns through the
dedicated repository path and never touches V3/V4/V9/V10/V12 fields.
"""

from __future__ import annotations

import logging
import math
import time
from collections import Counter
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

import numpy as np

from backend.calculations.evr.financial_rip_v3 import PreparedFinancialRipDistribution
from backend.calculations.evr.financial_rip_v4 import build_financial_rip_v4
from backend.calculations.evr.financial_rip_v5 import (
    build_financial_rip_v5,
    validate_financial_rip_v5_payload,
)
from backend.calculations.evr.financial_rip_v5_config import FINANCIAL_RIP_V5_VERSION
from backend.calculations.evr.guaranteed_component_value import add_guaranteed_components
from backend.calculations.evr.sealed_product_distribution import build_stage1_product_distributions
from backend.db.services.pack_outcome_artifact_service import (
    PackOutcomeArtifactCorrupt,
    PackOutcomeArtifactError,
    PackOutcomeArtifactUnavailable,
    load_pack_outcome_artifact,
)
from backend.db.services.sealed_product_rip_finalization_service import resolve_finalization_cohort
from backend.desirability.chase_accessibility import CHASE_ACCESSIBILITY_VERSION
from backend.desirability.overall_rip_v14 import compute_overall_rip_v14
from backend.desirability.scoring_config import (
    OVERALL_RIP_V14_VERSION,
    overall_rip_v14_required_chase_accessibility_version,
    overall_rip_v14_required_collector_appeal_version,
)

logger = logging.getLogger(__name__)

V5_FINALIZER_VERSION = "sealed-product-financial-v5-finalization-v1"
STATUS_OK = "ok"
STATUS_CANNOT_START = "cannot_start"
STATUS_NO_COHORT = "no_current_calculation_runs"
STATUS_NO_ROWS = "no_product_rows_in_cohort"

V5_STATUS_READY = "ready"
V5_STATUS_UNAVAILABLE = "unavailable"

_STAT_FIELDS = ("expected_value", "median_value", "p05_value", "p95_value", "p99_value")
_STAT_TOLERANCE = 1e-6
_V4_PARITY_TOLERANCE = 5e-5  # scores are published to 4 dp


class V5RowUnavailable(Exception):
    """A row cannot honestly receive Financial V5; carries a stable machine reason."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


def v5_unavailable_fields(reason: str, detail: str = "") -> Dict[str, Any]:
    """The V5-only column set for an unavailable row (no score, not rankable)."""
    payload = {
        "scoreVersion": FINANCIAL_RIP_V5_VERSION, "status": V5_STATUS_UNAVAILABLE,
        "statusReason": reason, "statusDetail": detail, "rankable": False, "score": None,
        "components": {},
    }
    return {
        "financial_rip_v5_score": None, "financial_rip_v5_status": V5_STATUS_UNAVAILABLE,
        "financial_rip_v5_rankable": False, "financial_rip_v5_version": FINANCIAL_RIP_V5_VERSION,
        "financial_rip_v5_payload": payload,
    }


def _verify_regenerated_vector(row: Mapping[str, Any], vector: np.ndarray) -> None:
    """The regenerated vector must reproduce what Stage 1 persisted for this row."""
    actual = {
        "expected_value": float(vector.mean()), "median_value": float(np.median(vector)),
        "p05_value": float(np.percentile(vector, 5)), "p95_value": float(np.percentile(vector, 95)),
        "p99_value": float(np.percentile(vector, 99)),
    }
    for field in _STAT_FIELDS:
        stored = row.get(field)
        if stored is None or not math.isclose(float(stored), actual[field],
                                              rel_tol=_STAT_TOLERANCE, abs_tol=_STAT_TOLERANCE):
            raise V5RowUnavailable(
                "regenerated_distribution_mismatch", f"{field} stored={stored} actual={actual[field]}")


def score_row_v5(row: Mapping[str, Any], vector: np.ndarray) -> Dict[str, Any]:
    """Financial V5 (V5-only column set) for one row on its exact regenerated vector."""
    cost = row.get("product_market_cost")
    try:
        cost = float(cost)
    except (TypeError, ValueError):
        raise V5RowUnavailable("invalid_product_cost", repr(cost))
    if not math.isfinite(cost) or cost <= 0:
        raise V5RowUnavailable("invalid_product_cost", repr(cost))
    if vector.size != int(row.get("simulation_count") or -1):
        raise V5RowUnavailable(
            "simulation_count_mismatch", f"stored={row.get('simulation_count')} regenerated={vector.size}")
    _verify_regenerated_vector(row, vector)

    prepared = PreparedFinancialRipDistribution.prepare(vector)
    control = build_financial_rip_v4(prepared, cost)
    stored_v4 = row.get("financial_rip_v4_score")
    v4_parity = "not_available"
    if stored_v4 is not None:
        if control.get("score") is None or abs(float(control["score"]) - float(stored_v4)) > _V4_PARITY_TOLERANCE:
            raise V5RowUnavailable(
                "v4_lineage_mismatch", f"stored={stored_v4} recomputed={control.get('score')}")
        v4_parity = "exact"
    v5 = build_financial_rip_v5(prepared, cost, control_payload=control)
    ok, problems = validate_financial_rip_v5_payload(v5)
    if v5.get("status") != V5_STATUS_READY or not ok or v5.get("score") is None:
        raise V5RowUnavailable("v5_payload_invalid", "; ".join(problems) or str(v5.get("statusReason")))
    v5["audit"] = {**(v5.get("audit") or {}), "finalizerVersion": V5_FINALIZER_VERSION,
                   "v4LineageParity": v4_parity}
    return {
        "financial_rip_v5_score": v5["score"], "financial_rip_v5_status": V5_STATUS_READY,
        "financial_rip_v5_rankable": True, "financial_rip_v5_version": v5["scoreVersion"],
        "financial_rip_v5_payload": v5,
    }


def _declared_count(row: Mapping[str, Any]) -> int:
    """The pack count Stage 1 requested for this row (random_pack_count, else pack_count)."""
    try:
        return int(row.get("random_pack_count") or row.get("pack_count") or 0)
    except (TypeError, ValueError):
        return 0


def _row_pack_count(row: Mapping[str, Any]) -> int:
    """Mirror opening-economics-v3: the random-pack distribution IS the product's pack count."""
    pack_count = int(row.get("pack_count") or 0)
    random_count = int(row.get("random_pack_count") or pack_count)
    if pack_count < 1 or random_count != pack_count:
        raise V5RowUnavailable("invalid_or_mismatched_pack_count", f"pack={pack_count} random={random_count}")
    if row.get("accessory_value_included") is True:
        raise V5RowUnavailable("accessory_value_must_be_excluded")
    return random_count


def _default_run_hashes(client: Any, run_ids: Sequence[str]) -> Dict[str, str]:
    runs = list(client.table("calculation_runs").select("id,calculation_config_id").in_("id", list(run_ids)).execute().data or [])
    config_ids = [str(r["calculation_config_id"]) for r in runs]
    configs = list(client.table("calculation_configs").select("id,config_hash").in_("id", config_ids).execute().data or []) if config_ids else []
    hashes = {str(r["id"]): str(r["config_hash"]) for r in configs}
    return {str(r["id"]): hashes.get(str(r["calculation_config_id"]), "") for r in runs}


def finalize_financial_rip_v5(
    client: Any, *, market_date: Any, canonical_keys: Optional[Sequence[str]] = None,
    unsupported_keys: Sequence[str] = (), require_verified_cohort: bool = True, dry_run: bool = False,
    resolve_cohort_fn: Callable[..., Dict[str, Any]] = resolve_finalization_cohort,
    read_rows_fn: Optional[Callable[[Sequence[str]], Sequence[Mapping[str, Any]]]] = None,
    artifact_loader_fn: Callable[[Any, Any], Any] = load_pack_outcome_artifact,
    run_hash_fn: Optional[Callable[[Any, Sequence[str]], Mapping[str, str]]] = None,
    write_fn: Optional[Callable[[Any, Dict[str, Any]], Any]] = None,
) -> Dict[str, Any]:
    """Finalize Financial V5 for the current cohort from exact artifacts. See module docstring."""
    started = time.perf_counter()
    if read_rows_fn is None:
        from backend.db.repositories.sealed_product_results_repository import (
            get_sealed_product_results_for_runs as read_rows_fn,  # type: ignore[misc]
        )
    if write_fn is None:
        from backend.db.repositories.sealed_product_results_repository import (
            update_sealed_product_financial_v5 as write_fn,  # type: ignore[misc]
        )
    run_hash_fn = run_hash_fn or _default_run_hashes

    cohort = resolve_cohort_fn(client, market_date=market_date, canonical_keys=canonical_keys,
                               unsupported_keys=unsupported_keys)
    if cohort.get("error"):
        return _report(STATUS_CANNOT_START, cohort.get("marketDate"), started, error=cohort["error"])
    if require_verified_cohort and not cohort.get("verificationPassed"):
        return _report(STATUS_CANNOT_START, cohort.get("marketDate"), started,
                       error="opening-simulation freshness did not pass; refusing to finalize a partial cohort")
    run_id_by_set_id: Dict[str, str] = cohort["runIdBySetId"]
    if not run_id_by_set_id:
        return _report(STATUS_NO_COHORT, cohort.get("marketDate"), started)
    set_key_by_run_id: Mapping[str, str] = cohort.get("setKeyByRunId") or {}
    current_runs = sorted(set(run_id_by_set_id.values()))
    expected_run_by_set = dict(run_id_by_set_id)

    rows = list(read_rows_fn(current_runs))
    if not rows:
        return _report(STATUS_NO_ROWS, cohort.get("marketDate"), started, cohort_runs=len(current_runs))
    run_hashes = run_hash_fn(client, current_runs)

    by_run: Dict[str, List[Mapping[str, Any]]] = {}
    skipped: List[Dict[str, Any]] = []
    for row in rows:
        set_id = str(row.get("set_id") or "")
        run_id = str(row.get("calculation_run_id"))
        if row.get("id") is None or expected_run_by_set.get(set_id) != run_id:
            skipped.append({"id": row.get("id"), "setId": set_id, "calculationRunId": run_id,
                            "reason": "row_outside_current_cohort"})
            continue
        by_run.setdefault(run_id, []).append(row)

    artifact_loads = distribution_builds = 0
    reasons: Counter = Counter()
    results: List[Dict[str, Any]] = []

    def record(row: Mapping[str, Any], fields: Dict[str, Any], reason: Optional[str], detail: str = "") -> None:
        if not dry_run:
            write_fn(row["id"], fields)
        results.append({"id": row.get("id"), "sealedProductId": row.get("sealed_product_id"),
                        "calculationRunId": str(row.get("calculation_run_id")),
                        "status": fields["financial_rip_v5_status"], "reason": reason, "detail": detail})
        if reason:
            reasons[reason] += 1

    for run_id in current_runs:
        run_rows = by_run.get(run_id, [])
        if not run_rows:
            continue
        # -- ONE artifact load per calculation run, however many SKUs share it --------
        try:
            artifact_loads += 1
            artifact = artifact_loader_fn(client, run_id)
            if str(artifact.metadata.get("calculation_run_id", run_id)) != run_id:
                raise PackOutcomeArtifactError("artifact belongs to a different calculation run")
        except (PackOutcomeArtifactUnavailable, PackOutcomeArtifactCorrupt, PackOutcomeArtifactError) as exc:
            reason = ("artifact_unavailable" if isinstance(exc, PackOutcomeArtifactUnavailable)
                      else "artifact_corrupt" if isinstance(exc, PackOutcomeArtifactCorrupt)
                      else "artifact_lineage_mismatch")
            for row in run_rows:
                record(row, v5_unavailable_fields(reason, str(exc)), reason, str(exc))
            continue

        # -- distributions: each distinct pack count built ONCE for the whole run -----
        # The bootstrap draws ONE index block backing every requested count (common random
        # numbers), so a count's vector depends on the WHOLE requested set. The request must
        # therefore equal what Stage 1 requested: the counts of ALL the run's persisted rows,
        # including rows this finalizer later refuses. (Same rule as opening-economics-v3.)
        counts = sorted({c for c in (_declared_count(r) for r in run_rows) if c > 0})
        valid_rows: List[tuple] = []
        for row in run_rows:
            try:
                valid_rows.append((row, _row_pack_count(row)))
            except V5RowUnavailable as exc:
                record(row, v5_unavailable_fields(exc.reason, exc.detail), exc.reason, exc.detail)
        if not valid_rows:
            continue
        try:
            distribution_builds += 1
            built = build_stage1_product_distributions(
                artifact.outcomes, pack_counts=counts,
                canonical_set_key=set_key_by_run_id.get(run_id), run_fingerprint=run_hashes.get(run_id))
        except (ValueError, TypeError) as exc:
            for row, _ in valid_rows:
                record(row, v5_unavailable_fields("distribution_build_failed", str(exc)),
                       "distribution_build_failed", str(exc))
            continue

        for row, count in valid_rows:
            try:
                vector = np.asarray(built["distributions"][count], dtype=np.float64)
                guaranteed = float(row.get("guaranteed_component_market_value") or 0.0)
                if guaranteed:
                    vector = add_guaranteed_components(vector, guaranteed)  # deterministic offset
                fields = score_row_v5(row, vector)
                record(row, fields, None)
            except V5RowUnavailable as exc:
                record(row, v5_unavailable_fields(exc.reason, exc.detail), exc.reason, exc.detail)
            except Exception as exc:  # a scoring bug must not masquerade as a value; and must not kill the cohort
                logger.exception("V5 finalization failed for row %s", row.get("id"))
                record(row, v5_unavailable_fields("scoring_error", type(exc).__name__), "scoring_error", str(exc))

    return _report(
        STATUS_OK, cohort.get("marketDate"), started, cohort_runs=len(current_runs), results=results,
        skipped=skipped, reasons=dict(reasons), artifact_loads=artifact_loads,
        distribution_builds=distribution_builds, dry_run=dry_run,
        runs_without_rows=[r for r in current_runs if r not in by_run])


def _report(status: str, market_date: Any, started: float, *, error: Optional[str] = None,
            cohort_runs: int = 0, results: Sequence[Mapping[str, Any]] = (),
            skipped: Sequence[Mapping[str, Any]] = (), reasons: Optional[Mapping[str, int]] = None,
            artifact_loads: int = 0, distribution_builds: int = 0, dry_run: bool = False,
            runs_without_rows: Sequence[str] = ()) -> Dict[str, Any]:
    ready = sum(1 for r in results if r["status"] == V5_STATUS_READY)
    unavailable = len(results) - ready
    complete = (status == STATUS_OK and bool(results) and unavailable == 0 and not skipped
                and not runs_without_rows)
    return {
        "finalizerVersion": V5_FINALIZER_VERSION, "financialVersion": FINANCIAL_RIP_V5_VERSION,
        "status": status, "error": error, "marketDate": market_date, "dryRun": dry_run,
        "cohortRunCount": cohort_runs, "rowsConsidered": len(results), "rowsReady": ready,
        "rowsUnavailable": unavailable, "unavailableReasons": dict(reasons or {}),
        "rowsSkipped": len(skipped), "skipped": list(skipped),
        "runsWithoutRows": list(runs_without_rows),
        "artifactLoads": artifact_loads, "distributionBuilds": distribution_builds,
        # Row-level unavailability never erases a row's V4/V12; this flag is what a V14
        # publication must consult before treating the cohort as complete.
        "cohortComplete": complete, "results": list(results),
        "elapsedMs": round((time.perf_counter() - started) * 1000.0, 3),
    }


def assert_v5_cohort_complete(report: Mapping[str, Any]) -> None:
    """Gate for V14 publication: a partial V5 cohort must never look complete."""
    if not report.get("cohortComplete"):
        raise ValueError(
            "Financial V5 cohort is incomplete: ready=%s unavailable=%s skipped=%s status=%s"
            % (report.get("rowsReady"), report.get("rowsUnavailable"), report.get("rowsSkipped"),
               report.get("status")))


# ---------------------------------------------------------------------------
# Overall RIP V14 per-row computation (materialized in the generic ledger, not on sealed rows)
# ---------------------------------------------------------------------------

def _v14_unavailable(status: str, reason: str, missing: Sequence[str]) -> Dict[str, Any]:
    return {"score": None, "version": OVERALL_RIP_V14_VERSION, "status": status, "statusReason": reason,
            "missingInputs": list(missing), "components": {}, "weights": {}, "rankable": False}


def overall_rip_v14_for(
    row: Mapping[str, Any], collector_score: Any, collector_version: Any,
    accessibility_row: Optional[Mapping[str, Any]], *, expected_run_id: Optional[str],
) -> Dict[str, Any]:
    """Overall V14 for one row. Same authority discipline as the V12 finalizer.

    Requires the row's OWN exact Financial V5 (never V4), a Chase Accessibility row from the
    SAME calculation run (a stale/other-run row is refused, never "the latest available"),
    exact Chase and Collector Appeal V5 identities, no renormalization, no V4/V12 fallback.
    """
    if (row.get("financial_rip_v5_version") != FINANCIAL_RIP_V5_VERSION
            or row.get("financial_rip_v5_status") != V5_STATUS_READY
            or row.get("financial_rip_v5_score") is None
            or row.get("financial_rip_v5_rankable") is not True):
        return _v14_unavailable(
            "unavailable_missing_input",
            "row has no ready exact Financial RIP V5 (version=%r status=%r)"
            % (row.get("financial_rip_v5_version"), row.get("financial_rip_v5_status")),
            ["financial_rip_v5"])
    if accessibility_row is None:
        return _v14_unavailable("unavailable_missing_input", "no Chase Accessibility row", ["chase_accessibility_v1"])
    if expected_run_id is None or str(accessibility_row.get("calculation_run_id")) != str(expected_run_id):
        return _v14_unavailable(
            "unavailable_authority_mismatch",
            "Chase Accessibility row belongs to calculation_run_id=%r; this row's run is %r. Refused rather "
            "than accepted as the latest available row."
            % (accessibility_row.get("calculation_run_id"), expected_run_id), ["chase_accessibility_v1"])
    if accessibility_row.get("status") != "ready":
        return _v14_unavailable("unavailable_missing_input", "Chase Accessibility row is not ready",
                                ["chase_accessibility_v1"])
    return compute_overall_rip_v14(
        row["financial_rip_v5_score"], accessibility_row.get("accessibility"), collector_score,
        financial_version=row["financial_rip_v5_version"],
        chase_accessibility_version=accessibility_row.get("version"),
        collector_appeal_version=collector_version)


def v14_component_lineage(row: Mapping[str, Any], accessibility_row: Mapping[str, Any],
                          collector_version: Any) -> Dict[str, Any]:
    """The ledger's ``component_lineage`` for a V14 row."""
    return {
        "financialVersion": row.get("financial_rip_v5_version"),
        "financialRunId": str(row.get("calculation_run_id")),
        "chaseVersion": accessibility_row.get("version") or CHASE_ACCESSIBILITY_VERSION,
        "chaseRunId": str(accessibility_row.get("calculation_run_id")),
        "collectorVersion": collector_version,
    }


def required_input_versions() -> Dict[str, str]:
    return {"financial": FINANCIAL_RIP_V5_VERSION,
            "chase": overall_rip_v14_required_chase_accessibility_version(),
            "collector": overall_rip_v14_required_collector_appeal_version()}
