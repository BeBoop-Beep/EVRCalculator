"""Anchor-ladder cross-batch calibration for Pokémon Google Trends evidence.

Fixes a documented defect (docs/research/desirability_incremental_refresh_rollout.md,
"the 51% zero rate in Trends data is untouched") in the existing single-anchor design
(backend/desirability/google_trends.py, backend/desirability/trends_normalization.py):
co-querying every Pokémon against a single universal anchor ("Pikachu") causes Google's
own batch-relative 0-100 quantization to collapse most weaker Pokémon to a reported raw
interest of 0, even in a two-term batch (empirically confirmed live: Pikachu+Torkoal
alone still quantizes Torkoal to ~0.03). This is not a normalization bug downstream --
it is a resolution artifact of pairing distant-magnitude search terms.

This module does not change batch construction, the provider, or the persisted-row
schema (backend.desirability.google_trends, backend.desirability.trends_normalization
are untouched). It adds a calibration layer that:

  1. Chains several stable anchors of adjacent search-interest magnitude ("the ladder")
     so that every batch pairs terms close enough in scale to stay resolvable.
  2. Calibrates each anchor's magnitude relative to a single reference anchor via
     overlapping pairwise bridge queries (Phase 5 math, below).
  3. Recovers a globally-comparable relative-interest value for any target queried
     against its nearest-tier ladder anchor.
  4. Classifies zero outcomes so a resolution-limited zero is never conflated with a
     genuine near-zero measurement, missing evidence, or a failed request.

No price input. No cohort/percentile ranking. Deterministic and monotonic.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Sequence

TREND_SCORING_VERSION_ANCHOR_LADDER_V2 = "pokemon_google_trends_anchor_ladder_v2"

# A zero raw value below this floor cannot be distinguished from quantization noise
# under Google Trends' integer-scaled batch response; a genuine zero must survive a
# retry at the most sensitive (closest-magnitude) rung before being trusted.
RESOLUTION_FLOOR = 0.5


class ZeroClassification(str, Enum):
    """Deterministic classification of a returned zero/near-zero interest value."""

    SCORED_ZERO_HIGH_CONFIDENCE = "scored_zero_high_confidence"
    """Zero (or near-zero) persisted after retry against the most sensitive
    available ladder rung -- treated as a genuine observed near-zero."""

    RESOLUTION_LIMITED_ZERO = "resolution_limited_zero"
    """Zero returned only because the queried anchor's magnitude overwhelmed the
    target's true (non-zero) signal; must be retried at a lower rung, never persisted
    as a final value."""

    MISSING_EVIDENCE = "missing_evidence"
    """No data returned for the target at all (absent from interest_by_term)."""

    FAILED = "failed"
    """The underlying provider call failed or was rate-limited."""

    INSUFFICIENT_CALIBRATION = "insufficient_calibration"
    """No ladder rung could be assigned to this target (no tier signal available,
    and the ladder itself has insufficient bridge coverage to fall back to)."""


@dataclass(frozen=True)
class LadderAnchor:
    """One rung of the anchor ladder.

    `rung` is ordered ascending by expected search-interest magnitude (0 = lowest
    tier). `global_scale` is populated by `calibrate_ladder()` -- it is the anchor's
    magnitude expressed relative to the single reference anchor (rung 0), i.e. how
    many times larger this anchor's raw interest is than the reference anchor's, on a
    common scale. Anchors are identified by name only; membership/order is a fixed,
    versioned configuration, never derived from price.
    """

    name: str
    rung: int
    global_scale: Optional[float] = None


@dataclass(frozen=True)
class BridgeObservation:
    """One pairwise (or small joint) query used to calibrate two adjacent rungs.

    `raw_lower`/`raw_higher` are the mean interest values pytrends returned for the
    lower-rung and higher-rung anchor respectively, from a single joint query
    containing both terms (see google_trends.fetch_interest / TrendBatch.terms for the
    existing query mechanics this reuses unchanged).
    """

    lower_anchor: str
    higher_anchor: str
    raw_lower: float
    raw_higher: float

    @property
    def ratio_higher_over_lower(self) -> float:
        if self.raw_lower <= 0:
            raise ValueError(
                f"Bridge {self.lower_anchor}->{self.higher_anchor} is unusable: "
                "lower-rung anchor raw value is zero or negative, cannot calibrate "
                "a scale factor from it."
            )
        return self.raw_higher / self.raw_lower


def calibrate_ladder(
    anchors_ascending: Sequence[str],
    bridges: Sequence[BridgeObservation],
) -> Dict[str, float]:
    """Compute each anchor's global_scale relative to `anchors_ascending[0]` (rung 0).

    Requires exactly one bridge observation between each consecutive pair of anchors
    in `anchors_ascending` (a simple chain, not a general graph -- Candidate C from the
    research pass, not the more expensive Candidate D pairwise-graph least-squares
    design, which is not pursued unless a future pass shows the chain is insufficient).

    global_scale[anchors_ascending[0]] = 1.0 by definition.
    global_scale[anchors_ascending[i]] = product of ratio_higher_over_lower for every
    bridge from rung 0 up through rung i.

    Deterministic, monotonic (every ratio is >0 so cumulative products only grow),
    reproducible from the same bridge inputs. No price input.
    """
    if len(anchors_ascending) < 2:
        raise ValueError("Ladder must have at least 2 anchors to calibrate.")
    bridge_by_pair = {(b.lower_anchor, b.higher_anchor): b for b in bridges}
    scale: Dict[str, float] = {anchors_ascending[0]: 1.0}
    cumulative = 1.0
    for lower, higher in zip(anchors_ascending, anchors_ascending[1:]):
        bridge = bridge_by_pair.get((lower, higher))
        if bridge is None:
            raise ValueError(
                f"Missing calibration bridge between adjacent rungs '{lower}' and "
                f"'{higher}'; ladder cannot be calibrated end-to-end."
            )
        cumulative *= bridge.ratio_higher_over_lower
        scale[higher] = cumulative
    return scale


def recover_global_relative(
    raw_target: float,
    raw_local_anchor: float,
    local_anchor_global_scale: float,
) -> float:
    """Recover a target's globally-comparable relative-interest value.

    `raw_target`/`raw_local_anchor` come from a single joint query where the target
    was batched against its nearest-tier ladder anchor (the existing
    google_trends.fetch_interest/TrendBatch mechanics, unchanged -- only the anchor
    choice and the post-hoc rescaling are new).

    local_relative = raw_target / raw_local_anchor   (target's share of its own,
        well-matched, resolvable local anchor -- this is the value Google's batch
        quantization can actually represent with precision, because target and anchor
        are close in magnitude).
    global_relative = local_relative * local_anchor_global_scale   (project that local
        share onto the common reference-anchor scale via the calibrated ladder).

    Monotonic in raw_target; deterministic; no percentile/cohort dependency (the
    calibration inputs are the ladder's own bridge observations, never the currently
    eligible Pokémon population).
    """
    if raw_local_anchor <= 0:
        raise ValueError("raw_local_anchor must be > 0 to recover a global relative value.")
    local_relative = raw_target / raw_local_anchor
    return local_relative * local_anchor_global_scale


def classify_zero_outcome(
    raw_target: Optional[float],
    is_lowest_available_rung: bool,
    request_failed: bool,
    request_missing: bool,
    ladder_assignment_available: bool,
) -> ZeroClassification:
    """Deterministic zero-outcome classifier (Phase 6 of the research spec).

    A returned zero is only ever trusted as SCORED_ZERO_HIGH_CONFIDENCE once the
    target has been queried against the most sensitive (closest-magnitude, lowest
    available) ladder rung it could be assigned to. Any zero observed against a
    higher/coarser rung is RESOLUTION_LIMITED_ZERO and must trigger escalation to the
    next-lower rung by the caller -- this function does not perform the retry itself,
    it only classifies one observation.
    """
    if request_failed:
        return ZeroClassification.FAILED
    if not ladder_assignment_available:
        return ZeroClassification.INSUFFICIENT_CALIBRATION
    if request_missing or raw_target is None:
        return ZeroClassification.MISSING_EVIDENCE
    if raw_target > RESOLUTION_FLOOR:
        raise ValueError(
            "classify_zero_outcome called on a non-zero, above-resolution-floor "
            f"value ({raw_target}); this classifier is for zero/near-zero outcomes "
            "only -- treat above-floor values as directly scored."
        )
    if is_lowest_available_rung:
        return ZeroClassification.SCORED_ZERO_HIGH_CONFIDENCE
    return ZeroClassification.RESOLUTION_LIMITED_ZERO


def assign_nearest_rung(
    tier_hint: Optional[float],
    anchors_ascending: Sequence[LadderAnchor],
) -> Optional[LadderAnchor]:
    """Pick the ladder anchor whose expected magnitude is closest to `tier_hint`.

    `tier_hint` is a coarse, non-price signal only used to choose which anchor a
    target is *batched* with (per the research spec: "the grouping source may only
    determine batching, not the final Trends score") -- e.g. existing fan-popularity
    evidence or a prior Trends snapshot. It never contributes to the final calibrated
    value itself, which comes entirely from `recover_global_relative`. Returns None
    (INSUFFICIENT_CALIBRATION territory) if no tier hint or no calibrated anchors are
    available.
    """
    if tier_hint is None:
        return None
    calibrated = [a for a in anchors_ascending if a.global_scale is not None]
    if not calibrated:
        return None
    return min(calibrated, key=lambda a: abs(math.log1p(a.global_scale or 0.0) - math.log1p(max(tier_hint, 0.0))))
