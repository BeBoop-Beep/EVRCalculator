"""Option B builder: the EV Representativeness research layer, attached to the
authoritative simulation but never blocking it.

WHY A SEPARATE BUILDER RATHER THAN INLINE IN THE PER-SET RUN
------------------------------------------------------------
The per-set EVR run is a subprocess on the daily publication critical path. This
repository already learned what happens when expensive analysis is bolted into
it: sealed-product Collector Appeal was deliberately MOVED OUT of the per-set
subprocess into a single-process finalization step, because building it per set
threw away the shared cache and paid a full cold build for every set.

This builder therefore reopens the exact authoritative run by
``calculation_run_id``, verifies the artifact's ``raw_sha256``, and is attached
to the identical inputs the published numbers came from - while running in its
own process, at its own cadence, with its own failure surface and its own status
vocabulary. A research failure is never a simulation failure.

TIER A AND TIER B
-----------------
Tier A reads the persisted million-pack artifact and is exact. Tier B re-runs the
simulator with a seed and per-card instrumentation, and is only reachable through
``--with-research-resimulation``. Tier B is gated on a reconciliation z-test
against its own Tier A artifact: if the re-simulation does not reproduce the
authoritative distribution, its card attribution is recorded but explicitly
marked non-authoritative rather than silently published.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from backend.calculations.evr.financial_rip_v3_config import (
    FINANCIAL_RIP_V3_TAIL_CONTRACT_VERSION,
)
from backend.db.services.opening_simulation_gate import (
    OpeningSetSimulationStatus,
    evaluate_opening_simulation_freshness,
)
from backend.db.services.pack_outcome_artifact_service import (
    PackOutcomeArtifactUnavailable,
    load_pack_outcome_artifact,
)
from backend.research.ev_representativeness.clt import build_clt_comparison
from backend.research.ev_representativeness.contribution import (
    rarity_contributions_from_pull_summary,
)
from backend.research.ev_representativeness.distribution import (
    compute_baseline_distribution,
    compute_return_ratio_buckets,
)
from backend.research.ev_representativeness.finite_sample import (
    CurvePoint,
    HORIZON_EXCEEDS_CAP,
    SCOPE_PACK_GRID,
    SCOPE_PRODUCT,
    audit_monotonicity,
    build_confirmation_grid,
    confirm_session_count,
    convergence_metric_key,
    evaluate_pack_grid,
    realization_metric_key,
    research_seed,
    resolve_horizon,
)
from backend.research.ev_representativeness.version import (
    BASE_PACK_GRID,
    CI_METHOD,
    COARSE_SESSION_COUNT,
    CONFIDENCE_LEVELS,
    CONFIRM_SESSION_COUNT,
    CONVERGENCE_TOLERANCES,
    EV_REPRESENTATIVENESS_VERSION,
    EXTENSION_GROWTH_FACTOR,
    EXTENSION_SESSION_COUNT,
    HEADLINE_CONFIDENCE,
    HEADLINE_CONVERGENCE_TOLERANCE,
    HEADLINE_REALIZATION_TARGET,
    HORIZON_REALIZATION_TARGETS,
    PACK_GRID_SEARCH_CAP,
    REALIZATION_TARGETS,
    RECONCILIATION_QUANTILES,
    RECONCILIATION_RELATIVE_FLOOR,
    RECONCILIATION_STATUS_FAIL,
    RECONCILIATION_STATUS_PASS,
    RECONCILIATION_STATUS_UNAVAILABLE,
    RECONCILIATION_Z_TOLERANCE,
    REFINE_SESSION_COUNT,
    RETURN_RATIO_BUCKETS,
    SESSION_MODEL_VERSION,
    STAGE_COARSE,
    STAGE_CONFIRM,
    TIER_A_SOURCE,
)

logger = logging.getLogger(__name__)

TAG = "[ev-representativeness]"

SUMMARY_TABLE = "ev_representativeness_run_summary"
CURVE_TABLE = "ev_representativeness_curve"
CARD_TABLE = "ev_representativeness_card_contribution"
COUNTERFACTUAL_TABLE = "ev_representativeness_counterfactual"

PACK_GRID_SENTINEL = "00000000-0000-0000-0000-000000000000"

STATUS_BUILT = "research_built"
STATUS_PARTIAL = "research_partial"
STATUS_FAILED = "research_failed"
STATUS_SKIPPED = "research_skipped"


class EvRepresentativenessError(RuntimeError):
    """A research-layer failure.

    A distinct exception type on purpose: a caller must be able to tell a failed
    RESEARCH calculation from a failed SIMULATION without parsing a message.
    """


# ---------------------------------------------------------------------------
# Cohort resolution
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResearchTarget:
    """One authoritative run this layer will analyse."""

    set_id: str
    canonical_key: str
    set_name: Optional[str]
    calculation_run_id: str
    market_date: str
    pack_cost: float
    simulation_count: int
    simulated_mean: float
    simulated_median: float
    simulated_std_dev: float


def _rows(response: Any) -> List[Dict[str, Any]]:
    return list((response.data if response else []) or [])


def resolve_research_cohort(
    client: Any,
    *,
    market_date: str,
    canonical_keys: Optional[Sequence[str]] = None,
) -> List[ResearchTarget]:
    """The authoritative cohort for a market date.

    Uses ``evaluate_opening_simulation_freshness`` - the same authority
    ``pokemon_rip_stats_service`` consumes - rather than the published
    leaderboard. Two reasons: the leaderboard can lag the simulation cohort by
    days, and joining research to a leaderboard row would introduce cross-date
    and cross-run contamination into every comparison against Financial RIP.

    Only ``current`` sets are analysed. A stale or missing simulation is skipped
    with its reason preserved, never silently analysed at an older date.
    """
    day = str(market_date)[:10]
    report = evaluate_opening_simulation_freshness(
        client, market_date=day, canonical_keys=canonical_keys
    )
    if report.error:
        raise EvRepresentativenessError(f"cohort authority unreadable: {report.error}")

    current = [item for item in report.statuses if item.status == "current" and item.calculation_run_id]
    if not current:
        raise EvRepresentativenessError(f"no current authoritative simulations for {day}")

    run_ids = [str(item.calculation_run_id) for item in current]
    summaries: Dict[str, Dict[str, Any]] = {}
    for start in range(0, len(run_ids), 25):
        chunk = run_ids[start : start + 25]
        for row in _rows(
            client.table("simulation_run_summary")
            .select("calculation_run_id,pack_cost,mean_value,median_value,std_dev,simulation_count")
            .in_("calculation_run_id", chunk)
            .execute()
        ):
            summaries[str(row["calculation_run_id"])] = row

    targets: List[ResearchTarget] = []
    for item in current:
        run_id = str(item.calculation_run_id)
        summary = summaries.get(run_id)
        if not summary:
            raise EvRepresentativenessError(f"run {run_id} has no simulation_run_summary row")
        cost = float(summary.get("pack_cost") or 0.0)
        if not math.isfinite(cost) or cost <= 0.0:
            # A cost-normalized gap computed against an invented cost would look
            # like a measurement while being a guess.
            raise EvRepresentativenessError(f"run {run_id} has no valid pack cost ({cost})")
        targets.append(
            ResearchTarget(
                set_id=str(item.set_id),
                canonical_key=str(item.canonical_key),
                set_name=item.set_name,
                calculation_run_id=run_id,
                market_date=day,
                pack_cost=cost,
                simulation_count=int(summary.get("simulation_count") or 0),
                simulated_mean=float(summary.get("mean_value") or 0.0),
                simulated_median=float(summary.get("median_value") or 0.0),
                simulated_std_dev=float(summary.get("std_dev") or 0.0),
            )
        )
    targets.sort(key=lambda item: item.canonical_key)
    return targets


def resolve_research_target_for_run(client: Any, calculation_run_id: str) -> ResearchTarget:
    """Resolve one already-complete authoritative set run for postprocessing/backfill."""
    run_id = str(calculation_run_id)
    run_rows = _rows(
        client.table("calculation_runs").select("id,target_id,target_type,created_at")
        .eq("id", run_id).limit(1).execute()
    )
    if not run_rows or run_rows[0].get("target_type") != "set":
        raise EvRepresentativenessError(f"run {run_id} is not a persisted set calculation run")
    summary_rows = _rows(
        client.table("simulation_run_summary")
        .select("calculation_run_id,pack_cost,mean_value,median_value,std_dev,simulation_count")
        .eq("calculation_run_id", run_id).limit(1).execute()
    )
    if not summary_rows:
        raise EvRepresentativenessError(f"run {run_id} has no simulation_run_summary row")
    artifact_rows = _rows(
        client.table("simulation_pack_outcome_artifacts").select("calculation_run_id")
        .eq("calculation_run_id", run_id).limit(1).execute()
    )
    if not artifact_rows:
        raise EvRepresentativenessError(f"run {run_id} has no exact pack-outcome artifact")
    run = run_rows[0]
    set_id = str(run.get("target_id") or "")
    set_rows = _rows(
        client.table("sets").select("id,name,canonical_key").eq("id", set_id).limit(1).execute()
    )
    if not set_rows:
        raise EvRepresentativenessError(f"run {run_id} target set {set_id} is missing")
    history_rows = _rows(
        client.table("calculation_history_trend").select("snapshot_date")
        .eq("calculation_run_id", run_id).limit(1).execute()
    )
    market_date = (
        str(history_rows[0].get("snapshot_date"))[:10]
        if history_rows else str(run.get("created_at") or "")[:10]
    )
    summary = summary_rows[0]
    cost = float(summary.get("pack_cost") or 0.0)
    if not market_date or not math.isfinite(cost) or cost <= 0:
        raise EvRepresentativenessError(f"run {run_id} lacks a valid market date or pack cost")
    set_row = set_rows[0]
    return ResearchTarget(
        set_id=set_id,
        canonical_key=str(set_row.get("canonical_key") or set_id),
        set_name=set_row.get("name"),
        calculation_run_id=run_id,
        market_date=market_date,
        pack_cost=cost,
        simulation_count=int(summary.get("simulation_count") or 0),
        simulated_mean=float(summary.get("mean_value") or 0.0),
        simulated_median=float(summary.get("median_value") or 0.0),
        simulated_std_dev=float(summary.get("std_dev") or 0.0),
    )


def build_tier_a_for_run(client: Any, calculation_run_id: str) -> Dict[str, Any]:
    """Idempotent exact-artifact Tier A build for one completed run."""
    build_started = time.perf_counter()
    existing = _rows(
        client.table("ev_representativeness_run_summary")
        .select("calculation_run_id")
        .eq("calculation_run_id", str(calculation_run_id))
        .eq("research_method_version", EV_REPRESENTATIVENESS_VERSION)
        .limit(1).execute()
    )
    if existing:
        return {"status": "already_built", "calculationRunId": str(calculation_run_id)}
    resolve_started = time.perf_counter()
    target = resolve_research_target_for_run(client, calculation_run_id)
    resolve_seconds = time.perf_counter() - resolve_started
    analysis_started = time.perf_counter()
    result = analyse_tier_a(client, target)
    analysis_seconds = time.perf_counter() - analysis_started
    persist_started = time.perf_counter()
    written = persist_research(client, result, tier_b=None)
    persistence_seconds = time.perf_counter() - persist_started
    return {"status": STATUS_BUILT, "calculationRunId": calculation_run_id,
            "marketDate": target.market_date, "written": written,
            "runtimeSeconds": time.perf_counter() - build_started,
            "timings": {"resolveSeconds": resolve_seconds,
                        "analysisSeconds": analysis_seconds,
                        "persistenceSeconds": persistence_seconds,
                        "artifactAndComputationSeconds": result.runtime_seconds}}


def load_product_scopes(client: Any, run_id: str) -> List[Dict[str, Any]]:
    """Real SKUs for one run, with their authoritative pack counts and costs.

    Pack counts come from ``simulation_sealed_product_results.pack_count``, which
    the sealed-product layer resolved from a verified composition. They are NOT
    assumed: the live cohort contains 9-pack Elite Trainer Boxes AND 11-pack
    Pokemon Center Elite Trainer Boxes, so any hardcoded "an ETB is 9 packs"
    would be wrong for half the ETBs in the data.

    ``product_market_cost`` is likewise the SKU's own price. A booster box does
    not cost 36 loose packs, and pretending otherwise would make every
    product-level return ratio wrong.
    """
    products = _rows(
        client.table("simulation_sealed_product_results")
        .select("sealed_product_id,product_name,product_family,pack_count,product_market_cost")
        .eq("calculation_run_id", run_id)
        .execute()
    )
    scopes: List[Dict[str, Any]] = []
    for row in products:
        pack_count = int(row.get("pack_count") or 0)
        cost = float(row.get("product_market_cost") or 0.0)
        if pack_count < 1 or not math.isfinite(cost) or cost <= 0.0:
            continue
        scopes.append(
            {
                "sealed_product_id": str(row["sealed_product_id"]),
                "product_name": row.get("product_name"),
                "product_family": row.get("product_family"),
                "pack_count": pack_count,
                "product_market_cost": cost,
            }
        )
    return scopes


def load_pull_summary(client: Any, run_id: str) -> List[Dict[str, Any]]:
    return _rows(
        client.table("simulation_pull_summary")
        .select("rarity_bucket,pulled_count,total_sampled_value,avg_sampled_value")
        .eq("calculation_run_id", run_id)
        .execute()
    )


# ---------------------------------------------------------------------------
# Pack-count grid
# ---------------------------------------------------------------------------

def build_pack_grid(product_pack_counts: Iterable[int]) -> List[int]:
    """The research grid, unioned with the real product quantities.

    ``BASE_PACK_GRID`` is the research floor; the SKU pack counts are the
    quantities people actually buy. Both are analysed, and the union means a
    product's own number is always an evaluated grid point rather than something
    interpolated between neighbours.
    """
    grid = set(BASE_PACK_GRID)
    grid.update(int(count) for count in product_pack_counts if int(count) >= 1)
    return sorted(grid)


def extend_grid(highest: int, *, cap: int, factor: float = EXTENSION_GROWTH_FACTOR) -> List[int]:
    """Geometric continuation above the base grid, up to the search cap."""
    points: List[int] = []
    current = highest
    while current < cap:
        current = int(round(current * factor))
        if current <= points[-1] if points else current <= highest:
            current += 1
        if current >= cap:
            points.append(cap)
            break
        points.append(current)
    return points


# ---------------------------------------------------------------------------
# Tier A analysis
# ---------------------------------------------------------------------------

@dataclass
class TierAResult:
    target: ResearchTarget
    outcomes: np.ndarray
    artifact_sha256: str
    baseline: Any
    return_ratio_buckets: Dict[str, Any]
    rarity_contributions: Dict[str, Any]
    curve_points: List[CurvePoint]
    horizons: List[Dict[str, Any]]
    monotonicity: List[Dict[str, Any]]
    clt: Dict[str, Any]
    session_seed: int
    confirm_sessions: Optional[int]
    runtime_seconds: float
    diagnostics: Dict[str, Any] = field(default_factory=dict)


def analyse_tier_a(
    client: Any,
    target: ResearchTarget,
    *,
    include_products: bool = True,
    coarse_sessions: int = COARSE_SESSION_COUNT,
    extension_sessions: int = EXTENSION_SESSION_COUNT,
    refine_sessions: int = REFINE_SESSION_COUNT,
    confirm_sessions: int = CONFIRM_SESSION_COUNT,
    search_cap: int = PACK_GRID_SEARCH_CAP,
) -> TierAResult:
    """Everything derivable from the exact persisted million-pack vector."""
    started = time.perf_counter()

    try:
        artifact = load_pack_outcome_artifact(client, target.calculation_run_id)
    except PackOutcomeArtifactUnavailable as exc:
        raise EvRepresentativenessError(
            f"{target.canonical_key}: no exact pack-outcome artifact ({exc})"
        ) from exc

    outcomes = np.asarray(artifact.outcomes, dtype=np.float64)
    sha256 = str(artifact.metadata.get("raw_sha256"))

    # The artifact must be the vector the published summary describes. A silent
    # mismatch here would attach research to one run while labelling it another.
    if abs(float(outcomes.mean()) - target.simulated_mean) > max(
        1e-6, abs(target.simulated_mean) * 1e-6
    ):
        raise EvRepresentativenessError(
            f"{target.canonical_key}: artifact mean {outcomes.mean():.8f} does not match "
            f"simulation_run_summary.mean_value {target.simulated_mean:.8f}"
        )

    ordered = np.sort(outcomes)
    baseline = compute_baseline_distribution(
        outcomes, pack_cost=target.pack_cost, sorted_values=ordered
    )
    buckets = compute_return_ratio_buckets(outcomes, target.pack_cost)
    rarity = rarity_contributions_from_pull_summary(
        load_pull_summary(client, target.calculation_run_id),
        packs_simulated=int(outcomes.size),
        simulated_mean=float(baseline.ev),
    )

    products = load_product_scopes(client, target.calculation_run_id) if include_products else []
    grid = build_pack_grid(scope["pack_count"] for scope in products)

    seed = research_seed(
        [EV_REPRESENTATIVENESS_VERSION, "coarse", target.calculation_run_id, sha256]
    )
    points: List[CurvePoint] = evaluate_pack_grid(
        outcomes,
        grid,
        ev=baseline.ev,
        pack_cost=target.pack_cost,
        realization_targets=REALIZATION_TARGETS,
        convergence_tolerances=CONVERGENCE_TOLERANCES,
        session_count=coarse_sessions,
        seed=seed,
        stage=STAGE_COARSE,
    )

    # ---- extend until the headline horizons resolve, or the cap is reached ---
    extension_points: List[CurvePoint] = []
    headline_keys = [
        realization_metric_key(HEADLINE_REALIZATION_TARGET),
        convergence_metric_key(HEADLINE_CONVERGENCE_TOLERANCE),
    ]
    highest = grid[-1]
    while highest < search_cap:
        unresolved = [
            key
            for key in headline_keys
            if resolve_horizon(
                points + extension_points,
                metric_key=key,
                confidence=HEADLINE_CONFIDENCE,
                search_cap=search_cap,
            ).stable_n
            is None
        ]
        if not unresolved:
            break
        step = extend_grid(highest, cap=search_cap)[:4]
        if not step:
            break
        extension_points.extend(
            evaluate_pack_grid(
                outcomes,
                step,
                ev=baseline.ev,
                pack_cost=target.pack_cost,
                realization_targets=REALIZATION_TARGETS,
                convergence_tolerances=CONVERGENCE_TOLERANCES,
                session_count=extension_sessions,
                seed=research_seed(
                    [EV_REPRESENTATIVENESS_VERSION, "extend", target.calculation_run_id, highest]
                ),
                stage=STAGE_COARSE,
                include_session_distribution=False,
            )
        )
        highest = step[-1]

    all_points = points + extension_points

    # ---- horizons over the full (r, c) and (tau, c) grid ---------------------
    horizons: List[Dict[str, Any]] = []
    empirical_lookup: Dict[str, Optional[int]] = {}
    for target_r in HORIZON_REALIZATION_TARGETS:
        for confidence in CONFIDENCE_LEVELS:
            horizon = resolve_horizon(
                all_points,
                metric_key=realization_metric_key(target_r),
                confidence=confidence,
                search_cap=search_cap,
            )
            horizons.append(horizon.as_payload())
            empirical_lookup[f"{horizon.metric_key}|{confidence:.2f}"] = horizon.stable_n
    for tolerance in CONVERGENCE_TOLERANCES:
        for confidence in CONFIDENCE_LEVELS:
            horizon = resolve_horizon(
                all_points,
                metric_key=convergence_metric_key(tolerance),
                confidence=confidence,
                search_cap=search_cap,
            )
            horizons.append(horizon.as_payload())
            empirical_lookup[f"{horizon.metric_key}|{confidence:.2f}"] = horizon.stable_n

    # ---- refine + confirm, for the two headline horizons only ----------------
    # Refining every (r, c) x (tau, c) cell would multiply runtime by ~30 for
    # numbers the report ranks but does not publish. The two candidates the brief
    # singles out get the full statistical treatment; the rest are reported at
    # coarse-stage precision, and every row carries the stage that produced it so
    # the difference is never invisible.
    confirm_points: List[CurvePoint] = []
    confirmed: Dict[str, Any] = {}
    used_confirm_sessions: Optional[int] = None
    for metric_key in headline_keys:
        coarse_horizon = resolve_horizon(
            all_points, metric_key=metric_key, confidence=HEADLINE_CONFIDENCE, search_cap=search_cap
        )
        if coarse_horizon.stable_n is None:
            confirmed[metric_key] = coarse_horizon.as_payload()
            continue

        refine_grid = _dense_neighbourhood(all_points, metric_key, coarse_horizon.stable_n)
        refine_pts = evaluate_pack_grid(
            outcomes, refine_grid, ev=baseline.ev, pack_cost=target.pack_cost,
            realization_targets=REALIZATION_TARGETS,
            convergence_tolerances=CONVERGENCE_TOLERANCES,
            session_count=refine_sessions,
            seed=research_seed(
                [EV_REPRESENTATIVENESS_VERSION, "refine", target.calculation_run_id, metric_key]
            ),
            stage="refine",
            include_session_distribution=False,
        )
        refined = resolve_horizon(
            refine_pts + all_points, metric_key=metric_key,
            confidence=HEADLINE_CONFIDENCE, search_cap=search_cap, stage="refine",
        )
        candidate = refined.stable_n or coarse_horizon.stable_n

        confirm_grid = build_confirmation_grid(candidate)
        sessions = confirm_session_count(confirm_grid, preferred=confirm_sessions)
        used_confirm_sessions = sessions if used_confirm_sessions is None else min(
            used_confirm_sessions, sessions
        )
        confirm_pts = evaluate_pack_grid(
            outcomes, confirm_grid, ev=baseline.ev, pack_cost=target.pack_cost,
            realization_targets=REALIZATION_TARGETS,
            convergence_tolerances=CONVERGENCE_TOLERANCES,
            session_count=sessions,
            # An INDEPENDENT seed stream. Confirming on the coarse stage's own
            # draws would re-test the same sample and could only agree with it.
            seed=research_seed(
                [EV_REPRESENTATIVENESS_VERSION, "confirm", target.calculation_run_id, metric_key]
            ),
            stage=STAGE_CONFIRM,
            include_session_distribution=False,
        )
        confirm_points.extend(refine_pts)
        confirm_points.extend(confirm_pts)
        final = resolve_horizon(
            confirm_pts, metric_key=metric_key, confidence=HEADLINE_CONFIDENCE,
            search_cap=search_cap, stage=STAGE_CONFIRM,
        )
        payload = final.as_payload()
        payload["coarseStableN"] = coarse_horizon.stable_n
        payload["refinedStableN"] = refined.stable_n
        payload["firstCrossingN"] = coarse_horizon.first_crossing_n
        if payload.get("stableN") is None:
            # The band did not hold under the sharper independent estimate.
            # Report the refined candidate but say the confirmation did not
            # ratify it, rather than quietly falling back.
            payload["status"] = "confirmation_did_not_ratify"
            payload["stableN"] = candidate
        confirmed[metric_key] = payload
        empirical_lookup[f"{metric_key}|{HEADLINE_CONFIDENCE:.2f}"] = payload.get("stableN")

    # ---- product scopes ------------------------------------------------------
    product_points: List[CurvePoint] = []
    for scope in products:
        product_points.extend(
            evaluate_pack_grid(
                outcomes,
                [scope["pack_count"]],
                ev=baseline.ev,
                pack_cost=target.pack_cost,
                realization_targets=REALIZATION_TARGETS,
                convergence_tolerances=CONVERGENCE_TOLERANCES,
                session_count=coarse_sessions,
                seed=research_seed(
                    [
                        EV_REPRESENTATIVENESS_VERSION,
                        "product",
                        target.calculation_run_id,
                        scope["sealed_product_id"],
                    ]
                ),
                stage=STAGE_COARSE,
                scope_kind=SCOPE_PRODUCT,
                sealed_product_id=scope["sealed_product_id"],
                product_cost=scope["product_market_cost"],
            )
        )

    monotonicity = [audit.as_payload() for audit in audit_monotonicity(all_points)]
    clt = build_clt_comparison(
        ev=baseline.ev,
        std_dev=baseline.std_dev,
        realization_targets=HORIZON_REALIZATION_TARGETS,
        convergence_tolerances=CONVERGENCE_TOLERANCES,
        confidence_levels=CONFIDENCE_LEVELS,
        empirical_horizons=empirical_lookup,
    )

    return TierAResult(
        target=target,
        outcomes=outcomes,
        artifact_sha256=sha256,
        baseline=baseline,
        return_ratio_buckets=buckets,
        rarity_contributions=rarity,
        curve_points=all_points + confirm_points + product_points,
        horizons=horizons,
        monotonicity=monotonicity,
        clt=clt,
        session_seed=seed,
        confirm_sessions=used_confirm_sessions,
        runtime_seconds=time.perf_counter() - started,
        diagnostics={
            "tier": TIER_A_SOURCE,
            "gridMax": highest,
            "productScopeCount": len(products),
            "products": products,
            "confirmedHorizons": confirmed,
            "coarseSessionCount": coarse_sessions,
            "extensionSessionCount": extension_sessions,
            "refineSessionCount": refine_sessions,
        },
    )


def _dense_neighbourhood(
    points: Sequence[CurvePoint], metric_key: str, candidate: int, *, steps: int = 6
) -> List[int]:
    """A denser grid between the last failing checkpoint and the candidate.

    The coarse grid is geometric, so a candidate at 250 may really lie anywhere
    in (150, 250]. Refinement subdivides that interval linearly rather than
    binary-searching it - a binary search would presume the curve is monotone in
    N, which is exactly what the brief warns must not be assumed.
    """
    evaluated = sorted(
        {p.pack_count for p in points if p.metric_key == metric_key}
    )
    lower = max([n for n in evaluated if n < candidate], default=max(1, candidate // 2))
    if candidate - lower <= steps:
        return sorted({*range(lower, candidate + 1)})
    span = candidate - lower
    return sorted({lower + int(round(span * i / steps)) for i in range(steps + 1)} | {candidate})


# ---------------------------------------------------------------------------
# Reconciliation (the Tier A <-> Tier B gate)
# ---------------------------------------------------------------------------

def reconcile_tiers(
    *,
    tier_a: np.ndarray,
    tier_b: np.ndarray,
    z_tolerance: float = RECONCILIATION_Z_TOLERANCE,
    relative_floor: float = RECONCILIATION_RELATIVE_FLOOR,
    quantiles: Sequence[float] = RECONCILIATION_QUANTILES,
) -> Dict[str, Any]:
    """Is the Tier B re-simulation the same distribution as the authoritative run?

    Tier A and Tier B are INDEPENDENT samples from the same model, so their means
    differ by Monte Carlo error and nothing else when the re-simulation is
    faithful. That makes the tolerance a measurement, not a preference::

        z = (EV_b - EV_a) / (sigma_pooled * sqrt(1/n_a + 1/n_b))

    which is standard normal under "same model, same prices". A z-threshold
    scales with each set's own volatility automatically - essential here, where
    the cohort's coefficient of variation spans roughly 1.9 to 11.7 and any
    single dollar or percentage tolerance would be far too tight for one end and
    meaningless at the other.

    Quantiles are checked alongside the mean because a mean can reconcile while
    the SHAPE has moved; P50 and P95 would catch instrumentation that changed the
    sampling path without changing its average.

    ``relative_floor`` guards the degenerate sigma -> 0 case, where the z
    denominator vanishes and any difference at all looks infinite.
    """
    a = np.asarray(tier_a, dtype=np.float64)
    b = np.asarray(tier_b, dtype=np.float64)
    n_a, n_b = int(a.size), int(b.size)
    mean_a, mean_b = float(a.mean()), float(b.mean())
    absolute = mean_b - mean_a
    relative = (absolute / mean_a) if mean_a != 0.0 else None

    pooled_var = (a.var() * n_a + b.var() * n_b) / (n_a + n_b)
    sigma = math.sqrt(max(0.0, float(pooled_var)))
    standard_error = sigma * math.sqrt(1.0 / n_a + 1.0 / n_b)

    if standard_error > 0.0:
        z = absolute / standard_error
        passed = abs(z) <= z_tolerance
    else:
        z = None
        passed = abs(relative or 0.0) <= relative_floor

    quantile_diffs: Dict[str, Any] = {}
    for quantile in quantiles:
        qa = float(np.percentile(a, quantile * 100.0))
        qb = float(np.percentile(b, quantile * 100.0))
        quantile_diffs[f"{quantile:.2f}"] = {
            "tierA": qa,
            "tierB": qb,
            "absolute": qb - qa,
            "relative": ((qb - qa) / qa) if qa != 0.0 else None,
        }

    return {
        "status": RECONCILIATION_STATUS_PASS if passed else RECONCILIATION_STATUS_FAIL,
        "passed": passed,
        "tierAEv": mean_a,
        "tierBEv": mean_b,
        "tierACount": n_a,
        "tierBCount": n_b,
        "absoluteDiff": absolute,
        "relativeDiff": relative,
        "pooledSigma": sigma,
        "differenceStandardError": standard_error,
        "z": z,
        "zTolerance": z_tolerance,
        "relativeFloor": relative_floor,
        "quantiles": quantile_diffs,
    }


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _num(value: Any) -> Optional[float]:
    if value is None:
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def build_summary_row(
    result: TierAResult,
    *,
    tier_b: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    baseline = result.baseline
    target = result.target
    confirmed = result.diagnostics.get("confirmedHorizons", {})
    realization = confirmed.get(realization_metric_key(HEADLINE_REALIZATION_TARGET), {})
    convergence = confirmed.get(convergence_metric_key(HEADLINE_CONVERGENCE_TOLERANCE), {})

    violations = sum(int(item["violationCount"]) for item in result.monotonicity)
    max_decrease = max([float(item["maxDecrease"]) for item in result.monotonicity] or [0.0])

    row: Dict[str, Any] = {
        "calculation_run_id": target.calculation_run_id,
        "research_method_version": EV_REPRESENTATIVENESS_VERSION,
        "set_id": target.set_id,
        "set_canonical_key": target.canonical_key,
        "market_date": target.market_date,
        "source_artifact_sha256": result.artifact_sha256,
        "source_outcome_count": int(baseline.sample_size),
        "pack_cost": target.pack_cost,
        "session_model_version": SESSION_MODEL_VERSION,
        "session_seed": int(result.session_seed),
        "session_count_coarse": int(result.diagnostics.get("coarseSessionCount") or 0),
        "session_count_confirm": result.confirm_sessions,
        "metric_config": {
            "realizationTargets": list(REALIZATION_TARGETS),
            "convergenceTolerances": list(CONVERGENCE_TOLERANCES),
            "confidenceLevels": list(CONFIDENCE_LEVELS),
            "basePackGrid": list(BASE_PACK_GRID),
            "searchCap": PACK_GRID_SEARCH_CAP,
            "returnRatioBuckets": [list(edge) for edge in RETURN_RATIO_BUCKETS],
            "ciMethod": CI_METHOD,
        },
        "sample_size": int(baseline.sample_size),
        "ev": _num(baseline.ev),
        "variance": _num(baseline.variance),
        "std_dev": _num(baseline.std_dev),
        "coefficient_of_variation": _num(baseline.coefficient_of_variation),
        "p10": _num(baseline.percentiles.get(10)),
        "p25": _num(baseline.percentiles.get(25)),
        "p50": _num(baseline.percentiles.get(50)),
        "p75": _num(baseline.percentiles.get(75)),
        "p90": _num(baseline.percentiles.get(90)),
        "p95": _num(baseline.percentiles.get(95)),
        "p99": _num(baseline.percentiles.get(99)),
        "ev_typical_gap_absolute": _num(baseline.ev_typical_gap_absolute),
        "ev_typical_gap_cost_normalized": _num(baseline.ev_typical_gap_cost_normalized),
        "typical_capture": _num(baseline.typical_capture),
        "relative_gap": _num(baseline.relative_gap),
        "mean_abs_dev_about_median": _num(baseline.mean_abs_dev_about_median),
        "pearson_skew_2": _num(baseline.pearson_skew_2),
        "groeneveld_meeden_skew": _num(baseline.groeneveld_meeden_skew),
        "top10_outcome_ev_share": _num(baseline.tails[0.10].ev_share),
        "top5_outcome_ev_share": _num(baseline.tails[0.05].ev_share),
        "top1_outcome_ev_share": _num(baseline.tails[0.01].ev_share),
        "top10_conditional_tail_mean": _num(baseline.tails[0.10].conditional_mean),
        "top5_conditional_tail_mean": _num(baseline.tails[0.05].conditional_mean),
        "top1_conditional_tail_mean": _num(baseline.tails[0.01].conditional_mean),
        "tail_selection_method": FINANCIAL_RIP_V3_TAIL_CONTRACT_VERSION,
        "return_ratio_buckets_json": result.return_ratio_buckets,
        "rarity_contributions_json": result.rarity_contributions,
        "horizon_r80_c80_first_crossing": realization.get("firstCrossingN"),
        "horizon_r80_c80_stable": realization.get("stableN"),
        "horizon_r80_c80_status": realization.get("status") or HORIZON_EXCEEDS_CAP,
        "horizon_tau20_c80_first_crossing": convergence.get("firstCrossingN"),
        "horizon_tau20_c80_stable": convergence.get("stableN"),
        "horizon_tau20_c80_status": convergence.get("status") or HORIZON_EXCEEDS_CAP,
        "horizon_search_cap": PACK_GRID_SEARCH_CAP,
        "horizons_json": {"grid": result.horizons, "confirmed": confirmed},
        "clt_comparison_json": result.clt,
        "monotonicity_violation_count": violations,
        "monotonicity_max_decrease": _num(max_decrease),
        "monotonicity_json": result.monotonicity,
        "diagnostics_json": result.diagnostics,
        "runtime_seconds": round(result.runtime_seconds, 3),
        "reconciliation_status": RECONCILIATION_STATUS_UNAVAILABLE,
    }

    if tier_b:
        reconciliation = tier_b["reconciliation"]
        concentration = tier_b["concentration"]
        row.update(
            {
                "sim_top_card_ev_share": _num(concentration.top1_ev_share),
                "sim_top5_card_ev_share": _num(concentration.top5_ev_share),
                "sim_top10_card_ev_share": _num(concentration.top10_ev_share),
                "sim_card_hhi": _num(concentration.hhi),
                "sim_effective_card_count": _num(concentration.effective_card_count),
                "sim_card_count": int(concentration.card_count),
                "sim_pack_count": int(tier_b["pack_count"]),
                "sim_seed": int(tier_b["seed"]),
                "collective_hit_frequencies_json": tier_b.get("collective_hits"),
                "economic_hit_frequencies_json": tier_b.get("economic_hits"),
                "reconciliation_status": reconciliation["status"],
                "reconciliation_tier_a_ev": _num(reconciliation["tierAEv"]),
                "reconciliation_tier_b_ev": _num(reconciliation["tierBEv"]),
                "reconciliation_absolute_diff": _num(reconciliation["absoluteDiff"]),
                "reconciliation_relative_diff": _num(reconciliation["relativeDiff"]),
                "reconciliation_z": _num(reconciliation["z"]),
                "reconciliation_z_tolerance": _num(reconciliation["zTolerance"]),
                "reconciliation_p50_diff": _num(
                    reconciliation["quantiles"].get("0.50", {}).get("absolute")
                ),
                "reconciliation_p50_relative_diff": _num(
                    reconciliation["quantiles"].get("0.50", {}).get("relative")
                ),
                "reconciliation_p95_diff": _num(
                    reconciliation["quantiles"].get("0.95", {}).get("absolute")
                ),
                "reconciliation_p95_relative_diff": _num(
                    reconciliation["quantiles"].get("0.95", {}).get("relative")
                ),
                "card_attribution_authoritative": bool(reconciliation["passed"]),
            }
        )
    return row


def curve_rows(result: TierAResult) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen: set[Tuple[Any, ...]] = set()
    for point in result.curve_points:
        key = (
            point.scope_kind,
            point.sealed_product_id or PACK_GRID_SENTINEL,
            point.pack_count,
            point.metric_key,
            point.stage,
        )
        # A pack count can appear in more than one evaluation pass at the same
        # stage (the refine grid overlaps the coarse grid). Last write wins,
        # deterministically, rather than letting an upsert batch collide with
        # itself - PostgREST rejects a payload containing duplicate keys.
        if key in seen:
            rows = [row for row in rows if row["_key"] != key]
        seen.add(key)
        rows.append(
            {
                "_key": key,
                "calculation_run_id": result.target.calculation_run_id,
                "research_method_version": EV_REPRESENTATIVENESS_VERSION,
                "scope_kind": point.scope_kind,
                "sealed_product_key": point.sealed_product_id or PACK_GRID_SENTINEL,
                "pack_count": int(point.pack_count),
                "metric_key": point.metric_key,
                "estimate": _num(point.estimate),
                "session_count": int(point.session_count),
                "successes": point.successes,
                "monte_carlo_standard_error": _num(point.standard_error),
                "ci_lower": _num(point.ci_lower),
                "ci_upper": _num(point.ci_upper),
                "ci_method": point.ci_method,
                "stage": point.stage,
                "seed": int(point.seed),
            }
        )
    for row in rows:
        row.pop("_key", None)
    return rows


def _chunked_upsert(
    client: Any, table: str, rows: Sequence[Mapping[str, Any]], *, on_conflict: str, chunk: int = 500
) -> int:
    written = 0
    for start in range(0, len(rows), chunk):
        batch = list(rows[start : start + chunk])
        if not batch:
            continue
        client.table(table).upsert(batch, on_conflict=on_conflict).execute()
        written += len(batch)
    return written


def persist_research(
    client: Any,
    result: TierAResult,
    *,
    tier_b: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Write one run's research output, idempotently.

    ORDER MATTERS: the summary row is written LAST. A partial failure therefore
    leaves the run visibly un-built rather than carrying a summary that claims
    completeness over curves that were never written. Reruns upsert on the
    natural key, so the same (run, version) overwrites in place and never
    accumulates duplicates.
    """
    curves = curve_rows(result)
    written_curves = _chunked_upsert(
        client,
        CURVE_TABLE,
        curves,
        on_conflict=(
            "calculation_run_id,research_method_version,scope_kind,"
            "sealed_product_key,pack_count,metric_key,stage"
        ),
    )

    written_cards = 0
    written_scenarios = 0
    if tier_b:
        card_rows = [
            {
                "calculation_run_id": result.target.calculation_run_id,
                "research_method_version": EV_REPRESENTATIVENESS_VERSION,
                "source_row_index": int(item.source_row_index if item.source_row_index is not None else -1),
                "price_column": item.price_column,
                "card_name": item.card_name,
                "card_number": item.card_number,
                "rarity_key": item.rarity_key,
                "price_used": _num(item.price_used),
                "observed_pull_count": int(item.observed_pull_count),
                "expected_copies_per_pack": _num(item.expected_copies_per_pack),
                "ev_contribution_per_pack": _num(item.ev_contribution_per_pack),
                "ev_share": _num(item.ev_share),
                "ev_rank": int(item.ev_rank),
                "sim_pack_count": int(tier_b["pack_count"]),
            }
            for item in tier_b["contributions"]
        ]
        written_cards = _chunked_upsert(
            client,
            CARD_TABLE,
            card_rows,
            on_conflict="calculation_run_id,research_method_version,source_row_index,price_column",
        )

        scenario_rows = [
            {
                "calculation_run_id": result.target.calculation_run_id,
                "research_method_version": EV_REPRESENTATIVENESS_VERSION,
                "scenario_key": scenario.scenario_key,
                "scenario_family": scenario.scenario_family,
                "scenario_params": scenario.scenario_params,
                "ev": _num(scenario.ev),
                "p50": _num(scenario.p50),
                "p95": _num(scenario.p95),
                "std_dev": _num(scenario.std_dev),
                "coefficient_of_variation": _num(scenario.coefficient_of_variation),
                "ev_typical_gap_absolute": _num(scenario.ev_typical_gap_absolute),
                "typical_capture": _num(scenario.typical_capture),
                "top1_outcome_ev_share": _num(scenario.top1_outcome_ev_share),
                "top5_outcome_ev_share": _num(scenario.top5_outcome_ev_share),
                "top10_outcome_ev_share": _num(scenario.top10_outcome_ev_share),
                "delta_vs_baseline": scenario.delta_vs_baseline,
                "baseline_kind": scenario.baseline_kind,
            }
            for scenario in tier_b.get("scenarios", [])
        ]
        written_scenarios = _chunked_upsert(
            client,
            COUNTERFACTUAL_TABLE,
            scenario_rows,
            on_conflict="calculation_run_id,research_method_version,scenario_key",
        )

    client.table(SUMMARY_TABLE).upsert(
        build_summary_row(result, tier_b=tier_b),
        on_conflict="calculation_run_id,research_method_version",
    ).execute()

    return {
        "calculation_run_id": result.target.calculation_run_id,
        "canonical_key": result.target.canonical_key,
        "curve_rows": written_curves,
        "card_rows": written_cards,
        "scenario_rows": written_scenarios,
        "tier_b": bool(tier_b),
    }
