"""Tiered anchor selection for Google Trends (fixes the zero-inflation defect).

THE DEFECT THIS FIXES
---------------------
Google Trends returns a RELATIVE index: within one request, the most-searched
term is scaled to 100 and everything else is expressed against it. The existing
pipeline anchors every batch on ``Pikachu``, which is so dominant that the rest
of the roster rounds into the bottom bin.

Measured directly (``today 1-m``, geo US, 2026-07-15) - same three subjects,
only the anchor changed:

    anchor=Pikachu   Brambleghast=0.00   Varoom=0.03   Rabsca=0.06
    anchor=Bisharp   Brambleghast=3.29   Varoom=10.90  Rabsca=10.74

The signal is real. The Pikachu anchor destroys it. This is the cause of the
"49.7% of subjects have trend score 0" finding, which in turn is why the
desirability composite collapses onto its static fan-popularity component
(corr(D, fan_popularity) = 0.9887) and why 16 of 21 sets sit in a 0.15-wide band.

A zero produced this way is a MEASUREMENT ARTIFACT, not an observation of
"nobody searches for this Pokemon". Recording it as a genuine zero is exactly
the "unsafe interpretation of missing data as zero" the research standard
forbids.

THE FIX
-------
Assign each subject to a popularity TIER and anchor each batch with a term drawn
from that tier, so the anchor is within a usable dynamic range of its batch.
Tiers are then chained back onto a single common scale through a BRIDGE term
that appears in both an adjacent tier's batches and its own.

    tier 0 (mega)   anchor: Pikachu        <- bridge: Charizard
    tier 1 (high)   anchor: Charizard      <- bridge: Lucario
    tier 2 (mid)    anchor: Lucario        <- bridge: Bisharp
    tier 3 (low)    anchor: Bisharp        <- bridge: Klefki
    tier 4 (niche)  anchor: Klefki

Each tier's scores are multiplied by its cumulative bridge ratio to land on the
tier-0 scale, so a cross-tier comparison remains meaningful. When a bridge ratio
cannot be measured the tier is reported as UNSCALED rather than silently
assumed - an unbridgeable tier is a known-unknown, not a zero.

PURITY
------
Tier assignment uses the STATIC fan-popularity ranking only. It never uses price,
and it never uses the trend score being measured - using the measurement to pick
its own anchor would be circular.

Tier boundaries and anchors are fixed module constants. They are reasoned
defaults chosen from fan-popularity rank, not fitted to any outcome.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

TREND_ANCHOR_TIER_VERSION = "trend_anchor_tiers_v1"

# Status values. A failure must never be recorded as a genuine zero.
STATUS_VALID = "valid"
STATUS_GENUINE_ZERO = "genuine_zero"
STATUS_MISSING = "missing"
STATUS_RATE_LIMITED = "rate_limited"
STATUS_INCOMPLETE = "incomplete"
STATUS_ANCHOR_FAILURE = "anchor_failure"
STATUS_STALE_FALLBACK = "stale_fallback"
STATUS_UNSCALED = "unscaled_tier"

SOURCE_FAILURE_STATUSES = frozenset(
    {STATUS_MISSING, STATUS_RATE_LIMITED, STATUS_INCOMPLETE, STATUS_ANCHOR_FAILURE}
)


@dataclass(frozen=True)
class AnchorTier:
    """One popularity band and the anchor term used to measure it."""

    index: int
    name: str
    anchor_term: str
    # Inclusive fan-popularity rank bounds. Rank 1 = most popular.
    min_rank: int
    max_rank: int
    # Term shared with the NEXT tier down, used to chain scales together.
    bridge_term: Optional[str]

    def contains(self, rank: int) -> bool:
        return self.min_rank <= rank <= self.max_rank


# Fixed, documented, cohort-independent. Anchors are chosen so that each is
# within roughly one order of magnitude of its tier's typical subject - the
# condition under which Trends' 0-100 scale retains resolution.
ANCHOR_TIERS: Tuple[AnchorTier, ...] = (
    AnchorTier(0, "mega", "Pikachu", 1, 25, "Charizard"),
    AnchorTier(1, "high", "Charizard", 26, 100, "Lucario"),
    AnchorTier(2, "mid", "Lucario", 101, 300, "Bisharp"),
    AnchorTier(3, "low", "Bisharp", 301, 650, "Klefki"),
    AnchorTier(4, "niche", "Klefki", 651, 10_000, None),
)

# Below this, a Trends reading is at the edge of the index's resolution and is
# reported as low confidence rather than trusted as a precise value.
RESOLUTION_FLOOR = 1.0


def tier_for_rank(rank: Any) -> Optional[AnchorTier]:
    """Which tier a subject belongs to, by STATIC fan-popularity rank.

    Returns None when the rank is unusable - never a default tier, because
    silently bucketing an unranked subject would anchor it arbitrarily.
    """
    try:
        parsed = int(rank)
    except (TypeError, ValueError):
        return None
    if parsed < 1:
        return None
    for tier in ANCHOR_TIERS:
        if tier.contains(parsed):
            return tier
    return ANCHOR_TIERS[-1]


def assign_tiers(subjects: Sequence[Mapping[str, Any]]) -> Dict[int, List[Mapping[str, Any]]]:
    """Group subjects by tier using ``fan_popularity_rank``.

    Subjects with no usable rank are returned under key -1 so the caller must
    decide explicitly; they are never folded into a real tier.
    """
    grouped: Dict[int, List[Mapping[str, Any]]] = {tier.index: [] for tier in ANCHOR_TIERS}
    grouped[-1] = []
    for subject in subjects:
        tier = tier_for_rank(subject.get("fan_popularity_rank"))
        grouped[-1 if tier is None else tier.index].append(subject)
    return grouped


def build_batches(
    subjects: Sequence[Mapping[str, Any]],
    *,
    batch_size: int = 5,
) -> List[Dict[str, Any]]:
    """Tier-anchored request batches.

    Every batch carries its tier's anchor plus ``batch_size - 1`` subjects, so
    the anchor is always within usable range of its batch. The tier's bridge term
    is added to the FIRST batch of each tier so the tier can be rescaled onto the
    tier above.
    """
    if batch_size < 2:
        raise ValueError("batch_size must leave room for an anchor plus one term")

    grouped = assign_tiers(subjects)
    batches: List[Dict[str, Any]] = []
    for tier in ANCHOR_TIERS:
        members = grouped.get(tier.index) or []
        if not members:
            continue
        # The anchor never occupies a subject slot, and a subject that IS the
        # anchor term must not be requested alongside itself (Trends rejects the
        # duplicate outright).
        payload = [s for s in members if str(s.get("query_term")) != tier.anchor_term]
        capacity = batch_size - 1
        for index in range(0, len(payload), capacity):
            chunk = payload[index:index + capacity]
            terms = [str(s.get("query_term")) for s in chunk]
            include_bridge = index == 0 and tier.bridge_term is not None
            if include_bridge and tier.bridge_term not in terms:
                # The bridge occupies a subject slot on the first batch only.
                terms = terms[: capacity - 1] + [tier.bridge_term]
                chunk = chunk[: capacity - 1]
            batches.append({
                "tier_index": tier.index,
                "tier_name": tier.name,
                "anchor_term": tier.anchor_term,
                "bridge_term": tier.bridge_term if include_bridge else None,
                "terms": terms,
                "subjects": chunk,
                "request_terms": [tier.anchor_term] + terms,
            })
    return batches


def bridge_ratio(
    upper_tier_readings: Mapping[str, float],
    lower_tier_readings: Mapping[str, float],
    bridge_term: str,
) -> Optional[float]:
    """Scale factor mapping a lower tier's readings onto the tier above.

    The bridge term is measured in BOTH tiers. Its ratio is the conversion. When
    it reads at or below the resolution floor in either tier the ratio is not
    computable, and None is returned so the caller marks the tier UNSCALED rather
    than inventing a factor.
    """
    upper = upper_tier_readings.get(bridge_term)
    lower = lower_tier_readings.get(bridge_term)
    if upper is None or lower is None:
        return None
    if lower <= RESOLUTION_FLOOR or upper <= 0:
        return None
    return float(upper) / float(lower)


def classify_reading(
    value: Any,
    *,
    request_succeeded: bool,
    anchor_present: bool,
    response_complete: bool,
    rate_limited: bool = False,
) -> str:
    """Turn a raw reading into an explicit status.

    The whole point: a zero that came from a FAILED request is not the same fact
    as a zero that came from a SUCCESSFUL request. Only the latter is evidence
    about collector interest, and even then only when the anchor was in range.
    """
    if rate_limited:
        return STATUS_RATE_LIMITED
    if not request_succeeded:
        return STATUS_MISSING
    if not anchor_present:
        return STATUS_ANCHOR_FAILURE
    if not response_complete:
        return STATUS_INCOMPLETE
    if value is None:
        return STATUS_MISSING
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return STATUS_MISSING
    if not math.isfinite(parsed):
        return STATUS_MISSING
    if parsed <= 0.0:
        # A true zero from a healthy, in-range request is real information.
        return STATUS_GENUINE_ZERO
    return STATUS_VALID


def reading_confidence(value: Any, status: str) -> str:
    """How much weight a reading can bear.

    A value below the index's resolution floor is 'low' even when the request
    succeeded: Trends simply cannot resolve it against this anchor.
    """
    if status in SOURCE_FAILURE_STATUSES:
        return "none"
    if status == STATUS_STALE_FALLBACK:
        return "stale"
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return "none"
    if status == STATUS_GENUINE_ZERO:
        return "low"
    return "high" if parsed >= RESOLUTION_FLOOR else "low"


def coverage_report(readings: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    """Quality gate input. Separates real zeros from failures explicitly."""
    rows = list(readings)
    total = len(rows)
    if total == 0:
        return {"total": 0, "usable_ratio": 0.0, "gate_pass": False,
                "reason": "no readings"}
    counts: Dict[str, int] = {}
    for row in rows:
        status = str(row.get("status") or STATUS_MISSING)
        counts[status] = counts.get(status, 0) + 1
    failures = sum(counts.get(s, 0) for s in SOURCE_FAILURE_STATUSES)
    usable = counts.get(STATUS_VALID, 0) + counts.get(STATUS_GENUINE_ZERO, 0)
    low_confidence = sum(1 for r in rows if r.get("confidence") == "low")
    return {
        "total": total,
        "by_status": counts,
        "usable": usable,
        "usable_ratio": round(usable / total, 4),
        "failure_count": failures,
        "failure_ratio": round(failures / total, 4),
        "genuine_zero_count": counts.get(STATUS_GENUINE_ZERO, 0),
        "genuine_zero_ratio": round(counts.get(STATUS_GENUINE_ZERO, 0) / total, 4),
        "low_confidence_count": low_confidence,
        "low_confidence_ratio": round(low_confidence / total, 4),
        "note": (
            "genuine_zero counts a healthy in-range request that returned 0. It is NOT the "
            "same fact as a failed request and must never be pooled with one."
        ),
    }
