"""Chase Accessibility V1 - snapshot builder and read model.

Builds and reads `pokemon_set_chase_accessibility_snapshot_latest` (migration
077). The metric itself lives in ``backend.desirability.chase_accessibility``;
this module only resolves authority, persists and projects.

AUTHORITY
---------
One set, one calculation run. Values and probabilities are the SAME rows of
`simulation_card_variant_pull_rates` for that run - `price_used` and
`modeled_probability`, 1:1, no canonical-card fan-out and no product input.

Accessibility is never refreshed independently of the run it describes. If card
prices move, the value does not change until a new run is scored, because the
probabilities it is averaging belong to that run's pack model. Refreshing prices
against last week's probabilities would silently mix two states.

PUBLICATION SEVERITY
--------------------
The distinction the publication contract turns on:

* a set with **no pull model** is *structurally unsupported*. Its unavailable row
  is a correct outcome and must not fail publication.
* a set that **is** simulation-supported but whose Accessibility is missing,
  stale or bound to the wrong run is an **integrity error**, because the data
  that should have produced it exists.

:func:`publication_integrity_failures` draws that line explicitly rather than
leaving each caller to guess.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence

from backend.desirability.chase_accessibility import (
    CHASE_ACCESSIBILITY_VERSION,
    MIN_MAPPED_HC_MASS,
    STATUS_NO_PULL_MODEL,
    STATUS_READY,
    compute_chase_accessibility,
)

SNAPSHOT_TABLE = "pokemon_set_chase_accessibility_snapshot_latest"
PULL_RATES_TABLE = "simulation_card_variant_pull_rates"

#: PostgREST caps a response at 1000 rows; the largest set is ~465 variants, but
#: the loader pages anyway so a bigger set cannot silently truncate.
PAGE_SIZE = 1000


def _rows(response: Any) -> List[Dict[str, Any]]:
    return list(getattr(response, "data", None) or [])


def _optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def load_drawable_variants(client: Any, *, calculation_run_id: str
                           ) -> List[Dict[str, Any]]:
    """Every drawable variant row for one run.

    ``pull_count > 0`` is the drawable filter: a variant the simulation never
    produced is not part of the pack's reachable universe. It is applied in the
    query rather than in Python so the coverage denominator and the probability
    numerator are drawn from exactly one definition.
    """
    collected: List[Dict[str, Any]] = []
    page = 0
    while True:
        response = (client.table(PULL_RATES_TABLE)
                    .select("calculation_run_id,set_id,card_variant_id,price_used,"
                            "modeled_probability,effective_pull_rate,pull_count,"
                            "pack_presence_count,simulation_count")
                    .eq("calculation_run_id", calculation_run_id)
                    .gt("pull_count", 0)
                    .order("card_variant_id")
                    .range(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE - 1)
                    .execute())
        batch = _rows(response)
        collected.extend(batch)
        if len(batch) < PAGE_SIZE:
            return collected
        page += 1


def build_chase_accessibility_snapshot_row(
    *, set_id: Any, calculation_run_id: Any, client: Any,
    market_date: Any = None,
) -> Dict[str, Any]:
    """The persistable row for one set at one run. Idempotent.

    A set with no run, or a run with no drawable variants, produces an explicit
    unavailable row rather than no row: a reader must be able to tell "built and
    unavailable" from "never built".
    """
    resolved_set_id = _optional_str(set_id)
    if resolved_set_id is None:
        raise ValueError("set_id is required")
    resolved_run_id = _optional_str(calculation_run_id)
    built_at = datetime.now(timezone.utc).isoformat()

    variants: List[Dict[str, Any]] = []
    if resolved_run_id is not None:
        variants = load_drawable_variants(client, calculation_run_id=resolved_run_id)

    result = compute_chase_accessibility(
        variants=variants,
        has_pull_model=bool(variants),
        set_id=resolved_set_id,
        calculation_run_id=resolved_run_id,
    )
    return {
        "set_id": resolved_set_id,
        "calculation_run_id": resolved_run_id,
        "market_date": _optional_str(market_date),
        "accessibility": result.get("accessibility"),
        "chase_depth": result.get("chaseDepth"),
        "mapped_hc_mass": result.get("mappedHcMass"),
        "status": result["status"],
        "status_reason": result.get("statusReason"),
        "version": result["version"],
        "significance_version": result.get("significanceVersion"),
        "depth_version": result.get("depthVersion"),
        "eligible_variant_count": result.get("eligibleVariantCount"),
        "priced_variant_count": result.get("pricedVariantCount"),
        "probability_mapped_variant_count": result.get("probabilityMappedVariantCount"),
        "parity_delta": result.get("parityDelta"),
        "built_at": built_at,
        "updated_at": built_at,
    }


def persist_chase_accessibility_snapshot(row: Mapping[str, Any], *, client: Any
                                         ) -> Dict[str, Any]:
    """Upsert one set's row. One row per set, keyed by ``set_id``."""
    payload = dict(row)
    response = (client.table(SNAPSHOT_TABLE)
                .upsert(payload, on_conflict="set_id")
                .execute())
    written = _rows(response)
    return written[0] if written else payload


# --------------------------------------------------------------------------
# Read model
# --------------------------------------------------------------------------

def project_chase_accessibility(row: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """The public set-level shape.

    ``chaseAccessibility`` is NULL for every unavailable state - never 0.0. Zero
    is a measured zero and means something entirely different. Internal
    diagnostics (variant counts, parity delta) are deliberately not projected.
    """
    if not row:
        return {
            "chaseAccessibility": None,
            "chaseAccessibilityPct": None,
            "chaseAccessibilityStatus": STATUS_NO_PULL_MODEL,
            "chaseAccessibilityVersion": CHASE_ACCESSIBILITY_VERSION,
            "chaseDepth": None,
            "mappedHcMass": None,
        }
    value = row.get("accessibility")
    return {
        "chaseAccessibility": value,
        "chaseAccessibilityPct": None if value is None else float(value) * 100.0,
        "chaseAccessibilityStatus": row.get("status"),
        "chaseAccessibilityStatusReason": row.get("status_reason"),
        "chaseAccessibilityVersion": row.get("version"),
        "chaseDepth": row.get("chase_depth"),
        "mappedHcMass": row.get("mapped_hc_mass"),
        "chaseAccessibilityCalculationRunId": row.get("calculation_run_id"),
        "chaseAccessibilityMarketDate": row.get("market_date"),
    }


def read_chase_accessibility_snapshot(*, set_id: Any, client: Any) -> Dict[str, Any]:
    """One set's published Chase Accessibility, projected for a reader."""
    resolved = _optional_str(set_id)
    if resolved is None:
        return project_chase_accessibility(None)
    response = (client.table(SNAPSHOT_TABLE)
                .select("*")
                .eq("set_id", resolved)
                .limit(1)
                .execute())
    rows = _rows(response)
    return project_chase_accessibility(rows[0] if rows else None)


# --------------------------------------------------------------------------
# Publication
# --------------------------------------------------------------------------

def publication_integrity_failures(
    rows: Sequence[Mapping[str, Any]], *,
    simulation_supported_set_ids: Sequence[str],
    expected_run_by_set: Optional[Mapping[str, str]] = None,
) -> List[Dict[str, Any]]:
    """Reasons Chase Accessibility should BLOCK a coordinated publication.

    Only a simulation-supported set can raise one. A set with no pull model is a
    deliberate model boundary - vintage eras are not estimated - and its
    unavailable row is a correct outcome, not a failure.
    """
    supported = {str(value) for value in simulation_supported_set_ids}
    by_set = {str(row.get("set_id")): row for row in rows}
    failures: List[Dict[str, Any]] = []

    for set_id in sorted(supported):
        row = by_set.get(set_id)
        if row is None:
            failures.append({"setId": set_id, "reason": "missing_chase_accessibility_row",
                             "detail": "set is simulation-supported but has no built row"})
            continue
        if row.get("version") != CHASE_ACCESSIBILITY_VERSION:
            failures.append({"setId": set_id, "reason": "wrong_model_version",
                             "detail": "row declares %r, canonical is %r"
                                       % (row.get("version"), CHASE_ACCESSIBILITY_VERSION)})
        if row.get("status") != STATUS_READY:
            failures.append({"setId": set_id, "reason": "not_ready",
                             "detail": "status %r on a simulation-supported set"
                                       % row.get("status")})
            continue
        mass = row.get("mapped_hc_mass")
        if mass is None or float(mass) < MIN_MAPPED_HC_MASS:
            failures.append({"setId": set_id, "reason": "insufficient_mapped_hc_mass",
                             "detail": "mapped_hc_mass %r below %.2f"
                                       % (mass, MIN_MAPPED_HC_MASS)})
        if row.get("accessibility") is None:
            failures.append({"setId": set_id, "reason": "ready_without_value",
                             "detail": "status is ready but accessibility is null"})
        if expected_run_by_set:
            expected = expected_run_by_set.get(set_id)
            actual = _optional_str(row.get("calculation_run_id"))
            if expected and actual != str(expected):
                failures.append({
                    "setId": set_id, "reason": "stale_calculation_run",
                    "detail": "row belongs to run %s, publication is scoring %s"
                              % (actual, expected)})
    return failures
