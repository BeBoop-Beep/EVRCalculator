"""The single place that decides whether a component row may be ranked.

WHY THIS MODULE EXISTS
----------------------
``pokemon_set_desirability_component_scores`` stores its score columns NOT NULL.
An unscoreable set therefore stores ``0.0`` on every component - numerically
identical to a genuinely unappealing set. Nothing in the number distinguishes
"we measured no appeal" from "we could not measure". A consumer that sorts on
the raw column ranks 36 fixed-contents products (Trainer Kits, McDonald's
Collections, Black Star Promos) as the least appealing products in the
catalogue.

As of 2026-07-15 no consumer does this: the 36 sets have no simulation rows and
so never enter Explore's ranked cohort, and both RIP paths null-guard already.
The stored zero is a **latent trap**, not a live bug. This module exists so that
the next consumer to read the table cannot fall into it - the trap is closed at
the accessor, not by asking every future caller to remember a convention.

THE CONTRACT
------------
Read scores through :func:`rankable_score`. It returns ``None`` - never ``0.0``
- for a row that must not be ranked. ``None`` propagates into "unavailable"
everywhere downstream; ``0.0`` silently propagates into "worst".

    rankable = True    -> may participate in scores and rankings
    rankable = False   -> no numeric rank, not zero appeal, RIP must not
                          silently treat the metric as zero

:func:`rank_rankable_rows` is the guarded ranking entry point: it raises rather
than assign a rank to an unrankable row, so the failure is loud in a test run
instead of quiet in production.

GENUINE ZEROES ARE PRESERVED
----------------------------
A set that is fully covered and genuinely scores 0.0 stays ``rankable=True`` and
keeps its rank. This module distinguishes rows by their *status*, never by their
*value*: filtering on ``score == 0`` would discard exactly the honest zeroes we
must keep.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from backend.desirability.product_support import (
    PRODUCT_SUPPORT_VERSION,
    classify_product_support,
)

RANKABILITY_VERSION = "rankability_contract_v1"

# metric_status values that may be ranked.
RANKABLE_STATUSES = frozenset({"valid", "partial"})

STATUS_UNSUPPORTED_PRODUCT_TYPE = "unsupported_product_type"
STATUS_MISSING_RARITY_MAPPING = "unavailable_missing_rarity_mapping"
STATUS_MISSING_SUBJECT_LINKS = "unavailable_missing_subject_links"
STATUS_NO_ELIGIBLE_HIT_STRUCTURE = "unavailable_no_eligible_hit_structure"


class UnrankableRowError(ValueError):
    """Raised when a caller tries to rank a row the contract forbids ranking."""


def _diagnostics(row: Mapping[str, Any]) -> Dict[str, Any]:
    diagnostics = row.get("diagnostics_json")
    return dict(diagnostics) if isinstance(diagnostics, Mapping) else {}


def availability(row: Mapping[str, Any]) -> Dict[str, Any]:
    """The availability contract for one component row.

    Reads ``diagnostics_json`` when the builder has written a status. When it
    has not - which is true of every production row written before this
    contract shipped - falls back to classifying the row's **product type** from
    its canonical key.

    That fallback matters: it means the guard is correct against today's
    un-migrated production data, so closing the trap does not depend on first
    running a rebuild. The fallback only ever classifies *product support*; it
    never invents a data-quality verdict, because product type is knowable from
    metadata alone while data quality is not.
    """
    diagnostics = _diagnostics(row)
    status = diagnostics.get("metric_status")

    if isinstance(status, str) and status:
        return {
            "metric_status": status,
            "availability_reason": diagnostics.get("availability_reason"),
            "product_support_type": diagnostics.get("product_support_type"),
            "rankable": bool(diagnostics.get("rankable", status in RANKABLE_STATUSES)),
            "rarity_coverage_pct": diagnostics.get("rarity_coverage_pct"),
            "subject_link_coverage_pct": diagnostics.get("subject_link_coverage_pct"),
            "source": "diagnostics_json",
            "version": RANKABILITY_VERSION,
        }

    support = classify_product_support(
        set_canonical_key=row.get("set_canonical_key") or row.get("canonical_key"),
        set_name=row.get("set_name") or row.get("name"),
    )
    if not support["supported"]:
        return {
            "metric_status": STATUS_UNSUPPORTED_PRODUCT_TYPE,
            "availability_reason": support["product_support_reason"],
            "product_support_type": support["product_support_type"],
            "rankable": False,
            "rarity_coverage_pct": None,
            "subject_link_coverage_pct": None,
            "source": "product_support_fallback",
            "version": RANKABILITY_VERSION,
            "product_support_version": PRODUCT_SUPPORT_VERSION,
        }

    # A supported product with no stored status: assume rankable. A booster set
    # must never be silently dropped from rankings by a missing diagnostic.
    return {
        "metric_status": "valid",
        "availability_reason": None,
        "product_support_type": support["product_support_type"],
        "rankable": True,
        "rarity_coverage_pct": None,
        "subject_link_coverage_pct": None,
        "source": "product_support_fallback",
        "version": RANKABILITY_VERSION,
        "product_support_version": PRODUCT_SUPPORT_VERSION,
    }


def is_rankable(row: Mapping[str, Any]) -> bool:
    return bool(availability(row)["rankable"])


def rankable_score(row: Mapping[str, Any], column: str = "set_desirability_score") -> Optional[float]:
    """The score of ``column``, or ``None`` when the row must not be ranked.

    This is the guard. Returning ``None`` (not ``0.0``) for an unrankable row is
    the whole point: ``None`` means "unavailable" to every downstream consumer,
    while ``0.0`` means "worst in catalogue".
    """
    if not is_rankable(row):
        return None
    try:
        parsed = float(row.get(column))
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def filter_rankable(rows: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Only the rows that may take part in a ranking cohort."""
    return [dict(row) for row in rows if is_rankable(row)]


def partition_rankable(rows: Iterable[Mapping[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Split rows into ``rankable`` / ``unrankable``, each carrying availability."""
    rankable: List[Dict[str, Any]] = []
    unrankable: List[Dict[str, Any]] = []
    for row in rows:
        enriched = {**dict(row), "availability": availability(row)}
        (rankable if enriched["availability"]["rankable"] else unrankable).append(enriched)
    return {"rankable": rankable, "unrankable": unrankable}


def rank_rankable_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    column: str = "set_desirability_score",
    rank_key: str = "rank",
    id_key: str = "set_id",
) -> List[Dict[str, Any]]:
    """Rank a cohort, refusing to assign a rank to an unrankable row.

    Raises :class:`UnrankableRowError` if the caller passes an unrankable row.
    Silently skipping it would be friendlier and worse: a caller that believes
    it ranked 171 sets but ranked 135 should find out at the call site.
    """
    materialized = [dict(row) for row in rows]
    offenders = [
        str(row.get(id_key) or row.get("set_name") or "?")
        for row in materialized
        if not is_rankable(row)
    ]
    if offenders:
        raise UnrankableRowError(
            f"Refusing to rank {len(offenders)} unrankable row(s): {', '.join(offenders[:5])}"
            f"{' ...' if len(offenders) > 5 else ''}. "
            "Filter with filter_rankable() first; do not rank a stored 0.0 as low appeal."
        )

    scored = [row for row in materialized if rankable_score(row, column) is not None]
    scored.sort(key=lambda row: (-(rankable_score(row, column) or 0.0), str(row.get(id_key) or "")))
    for rank, row in enumerate(scored, start=1):
        row[rank_key] = rank
        row["ranked_set_count"] = len(scored)
    return scored
