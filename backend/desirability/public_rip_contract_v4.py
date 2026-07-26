"""Compact public RIP contract (v4) — the authoritative snapshot projection.

ONE PROJECTION, TWO SURFACES
----------------------------
Explore and the set page must never disagree about a score, a rank, or a
denominator, so both read ONE object built here from the already-ranked
runtime target. Nothing is recomputed: every number is lifted verbatim from the
canonical ``rip`` / ``ripCore`` / ``universalSetDesirability`` /
``openingExperience`` objects the explore service already produced.

WHY A SEPARATE COMPACT SHAPE
----------------------------
The runtime objects use internal field names (``score`` for the absolute,
``cohortSize`` for the denominator) and carry weight-disclosure, effective-weight
and formula metadata a public card does not need. The compact v4 shape renames
to the public contract (``absoluteScore`` / ``relativeScore`` / ``rank`` /
``rankedSetCount``) and keeps ONLY the fields a surface renders, so:

  * absolute and relative are NEVER the same field and never conflated,
  * every ranked block carries its OWN ``rankedSetCount`` denominator,
  * CA7 stays REQUIRED for Overall RIP — a missing CA7 yields an explicit
    unavailable Overall block while Financial RIP and Universal Set Desirability
    remain fully populated,
  * no multi-megabyte JSONB rollups are added; each block is a handful of scalars.

The shape is additive. The legacy ``rip`` / ``ripCore`` objects are left intact
for backward compatibility; this is a NEW ``publicRipContractV4`` key.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Optional

from backend.desirability.scoring_config import (
    FINANCIAL_RIP_V2_VERSION,
    OVERALL_RIP_V4_VERSION,
)

PUBLIC_RIP_CONTRACT_V4_KEY = "publicRipContractV4"
CONTRACT_VERSION = "public_rip_contract_v4"


def _num(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _int(value: Any) -> Optional[int]:
    """Ranks and denominators are counts; keep them integers, never floats."""
    parsed = _num(value)
    return int(round(parsed)) if parsed is not None else None


def _obj(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _weighted_component(block: Mapping[str, Any]) -> Dict[str, Any]:
    """A compact {score, weight, contribution} for an Overall RIP input."""
    return {
        "score": _num(block.get("score")),
        "weight": _num(block.get("weight")),
        "contribution": _num(block.get("contribution")),
    }


def _pillar_component(block: Mapping[str, Any]) -> Dict[str, Any]:
    """A Financial RIP pillar: absolute + relative + rank + weight + contribution.

    Pillars carry an absolute component score and a cohort rank but no
    cohort-relative score, so ``relativeScore`` is deliberately ``None`` rather
    than fabricated.
    """
    return {
        "absoluteScore": _num(block.get("score")),
        "relativeScore": _num(block.get("relativeScore")),
        "rank": _int(block.get("rank")),
        "rankedSetCount": _int(block.get("cohortSize")),
        "weight": _num(block.get("weight")),
        "contribution": _num(block.get("contribution")),
    }


def _build_overall(rip: Mapping[str, Any]) -> Dict[str, Any]:
    components_source = _obj(rip.get("components"))
    components = {
        "financialRip": _weighted_component(_obj(components_source.get("financialRip"))),
        "openingDesirability": _weighted_component(_obj(components_source.get("openingDesirability"))),
    }
    absolute = _num(rip.get("score"))
    relative = _num(rip.get("relativeScore"))
    block = {
        # `score` is the canonical PUBLIC score: the cohort-relative 0-100
        # standardization, for backward-compatible production semantics. The raw
        # 90/10 formula output is preserved separately as `absoluteScore`.
        "score": relative,
        "relativeScore": relative,
        "absoluteScore": absolute,
        "rank": _int(rip.get("rank")),
        "rankedSetCount": _int(rip.get("cohortSize")),
        "tier": rip.get("tier"),
        "version": rip.get("version") or OVERALL_RIP_V4_VERSION,
        "normalizationMode": "cohort_min_max",
        "components": components,
    }
    if absolute is None:
        # CA7 (or a financial pillar) missing: Overall RIP is unavailable with a
        # reason, and it NEVER falls back to Universal Set Desirability.
        block["status"] = rip.get("status") or "unavailable_missing_input"
        block["statusReason"] = rip.get("statusReason")
    return block


def _build_financial(rip_core: Mapping[str, Any]) -> Dict[str, Any]:
    components_source = _obj(rip_core.get("components"))
    components = {
        pillar: _pillar_component(_obj(components_source.get(pillar)))
        for pillar in ("profit", "safety", "stability")
    }
    absolute = _num(rip_core.get("score"))
    relative = _num(rip_core.get("relativeScore"))
    block = {
        # `score` is the canonical PUBLIC score: the cohort-relative 0-100
        # standardization of the 60/25/15 Financial RIP. The raw formula output
        # is preserved separately as `absoluteScore`.
        "score": relative,
        "relativeScore": relative,
        "absoluteScore": absolute,
        "rank": _int(rip_core.get("rank")),
        "rankedSetCount": _int(rip_core.get("cohortSize")),
        "tier": rip_core.get("tier"),
        "version": rip_core.get("version") or FINANCIAL_RIP_V2_VERSION,
        "normalizationMode": "cohort_min_max",
        "components": components,
    }
    if absolute is None:
        block["status"] = rip_core.get("status") or "unavailable_missing_financial_pillar"
        block["statusReason"] = rip_core.get("statusReason")
    return block


def _build_opening_desirability(
    opening_experience: Mapping[str, Any],
    universal: Mapping[str, Any],
) -> Dict[str, Any]:
    """CA7 Opening Desirability, plus the three price-independent input signals.

    CA7 = D + lambda*P*(1-D). The three component signals below are the honest
    breakdown available on the merged object:
      * universalRoster        <- D, the Universal Set Desirability roster base
      * obtainableDesirableCards <- P (Dual-Path Depth): the reachable-and-chaseable
                                    structure over desirable subjects
      * chaseIntensity         <- M* elite scarcity of desirable subjects
    None of these is a price or set-value quantity.
    """
    collector = _obj(opening_experience.get("collectorAppeal"))
    dual_path = _obj(opening_experience.get("dualPathDepth"))
    chase = _obj(opening_experience.get("chaseAppeal"))

    absolute = _num(collector.get("score"))
    block = {
        "absoluteScore": absolute,
        # CA7 is not cohort-min-max normalized; there is no relative CA7 score to
        # publish, so this stays null rather than being fabricated.
        "relativeScore": None,
        "rank": _int(collector.get("rank")),
        "rankedSetCount": _int(collector.get("cohortSize")),
        "tier": collector.get("tier"),
        "version": collector.get("version") or opening_experience.get("version"),
        "components": {
            "universalRoster": _num(universal.get("score")),
            "obtainableDesirableCards": _num(dual_path.get("rawValue")),
            "chaseIntensity": _num(chase.get("eliteScarcity")),
        },
    }
    if absolute is None:
        coverage = _obj(opening_experience.get("coverage"))
        block["status"] = "unavailable"
        block["statusReason"] = "; ".join(str(r) for r in (coverage.get("reasons") or [])) or None
    return block


def _build_universal(universal: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "score": _num(universal.get("score")),
        "rank": _int(universal.get("rank")),
        "rankedSetCount": _int(universal.get("rankedSetCount")),
        "percentile": _num(universal.get("percentile")),
        "version": universal.get("version"),
    }


def build_public_rip_contract_v4(target: Mapping[str, Any]) -> Dict[str, Any]:
    """Project one ranked target row into the compact public v4 contract.

    ``target`` must already carry the canonical ``rip``, ``ripCore``,
    ``universalSetDesirability`` and ``openingExperience`` objects (i.e. it has
    passed through ``_attach_public_rip_contract``). Nothing is recomputed.
    """
    universal = _obj(target.get("universalSetDesirability"))
    return {
        "contractVersion": CONTRACT_VERSION,
        "overallRip": _build_overall(_obj(target.get("rip"))),
        "financialRip": _build_financial(_obj(target.get("ripCore"))),
        "openingDesirability": _build_opening_desirability(
            _obj(target.get("openingExperience")), universal
        ),
        "universalSetDesirability": _build_universal(universal),
    }
