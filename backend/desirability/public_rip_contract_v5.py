"""Public RIP contract v5 — the canonical projection after the V3/V5 cutover.

WHAT CHANGED FROM v4
--------------------
v4 published Financial RIP V2 (60/25/15 Profit/Safety/Stability) as
``financialRip`` and Overall RIP v4 as ``overallRip``. v5 publishes the
six-component Financial RIP V3 and Overall RIP V5 under those same public names,
because those are now the canonical models:

    Overall RIP V5 = 0.90 * Financial RIP V3 + 0.10 * CA7 Opening Desirability

The 90/10 relationship is UNCHANGED. Only the financial input changed.

v4 IS NOT TOUCHED. :mod:`backend.desirability.public_rip_contract_v4` still
builds the identical object it always did, still keyed ``publicRipContractV4``,
for every existing consumer. v5 is a NEW, additive key.

LEGACY IS LABELLED, NOT HIDDEN
------------------------------
Financial RIP V2 and Overall RIP v4 remain fully published here, under
``legacy.financialRipV2`` and ``legacy.overallRipV4``. They are deliberately
placed behind a ``legacy`` namespace so that:

  * no fallback path can select them by accident - a consumer reading
    ``financialRip`` gets V3 or gets an explicit unavailable block, and can
    never silently receive a V2 number wearing the canonical label,
  * a comparison surface that WANTS V2 has to name it, which is exactly the
    honesty the V3/V2 toggle needs.

A missing V3 never degrades to V2. ``financialRip`` reports
``status="unavailable"`` with a reason and a null score instead.

NOTHING IS RECOMPUTED HERE
--------------------------
Every number is lifted verbatim from the canonical objects the ranking service
already produced. This module renames and reshapes; it does not score.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Optional

from backend.calculations.evr.financial_rip_v3_config import (
    FINANCIAL_RIP_V3_COMPONENT_ORDER,
    FINANCIAL_RIP_V3_NORMALIZATION_VERSION,
    FINANCIAL_RIP_V3_PUBLIC_COMPONENT_KEYS,
    FINANCIAL_RIP_V3_VERSION,
    OVERALL_RIP_V5_VERSION,
    OVERALL_RIP_V5_WEIGHTS,
    PUBLIC_RIP_CONTRACT_V5_VERSION,
)
from backend.desirability.public_rip_contract_v4 import build_public_rip_contract_v4

PUBLIC_RIP_CONTRACT_V5_KEY = "publicRipContractV5"
CONTRACT_VERSION = PUBLIC_RIP_CONTRACT_V5_VERSION


def _num(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _int(value: Any) -> Optional[int]:
    parsed = _num(value)
    return int(round(parsed)) if parsed is not None else None


def _obj(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _v3_component(block: Mapping[str, Any]) -> Dict[str, Any]:
    """One V3 component for the public contract.

    Carries the component score, its cohort rank and denominator, and the raw
    user-facing metrics the card renders. The WEIGHT is deliberately absent from
    this block: the six cards show no weighting percentage, and a weight the
    frontend does not render is a field that can only drift. Weights live in the
    ``audit`` block instead, where they stay checkable.
    """
    return {
        "score": _num(block.get("score")),
        "rank": _int(block.get("rank")),
        "rankedSetCount": _int(block.get("cohortSize")),
        "tier": block.get("tier"),
        "available": bool(block.get("available", block.get("score") is not None)),
        "raw": _obj(block.get("raw")),
    }


def _build_financial_v3(financial_v3: Mapping[str, Any]) -> Dict[str, Any]:
    """The canonical Financial RIP block: absolute, fixed-anchor, V3.

    ``score`` is the ABSOLUTE fixed-anchor V3 score - the same number
    ``absoluteScore`` carries. Unlike v4's Financial RIP block, ``score`` is NOT
    a cohort min-max relative score: V3's whole point is that adding or removing
    another set cannot change it. A relative score is still published, clearly
    named, for diagnostics only.
    """
    components_source = _obj(financial_v3.get("components"))
    components = {
        FINANCIAL_RIP_V3_PUBLIC_COMPONENT_KEYS[key]: _v3_component(_obj(components_source.get(key)))
        for key in FINANCIAL_RIP_V3_COMPONENT_ORDER
    }
    absolute = _num(financial_v3.get("score"))
    status = financial_v3.get("status")

    block: Dict[str, Any] = {
        "score": absolute,
        "absoluteScore": absolute,
        # Diagnostic only, and never the canonical score. Present so a surface
        # that wants cohort position has it without inventing one.
        "relativeScore": _num(financial_v3.get("relativeScore")),
        "rank": _int(financial_v3.get("rank")),
        "rankedSetCount": _int(financial_v3.get("cohortSize")),
        "tier": financial_v3.get("tier"),
        "version": financial_v3.get("scoreVersion") or FINANCIAL_RIP_V3_VERSION,
        "normalizationVersion": (
            financial_v3.get("normalizationVersion") or FINANCIAL_RIP_V3_NORMALIZATION_VERSION
        ),
        "normalizationMode": "fixed_absolute_anchors",
        "status": status,
        "rankable": bool(financial_v3.get("rankable")),
        "components": components,
        "depthAndRobustness": _obj(financial_v3.get("depthAndRobustness")),
        "distributionDisclosures": _obj(financial_v3.get("distributionDisclosures")),
        "sessionOpeningProfile": financial_v3.get("sessionOpeningProfile"),
        "sourceRun": _obj(financial_v3.get("sourceRun")),
    }
    if absolute is None:
        block["statusReason"] = financial_v3.get("statusReason") or "financial_rip_v3_unavailable"
        block["statusDetail"] = financial_v3.get("statusDetail")
        # Said explicitly so no consumer invents a fallback of its own.
        block["fallbackPolicy"] = (
            "Financial RIP V3 is unavailable for this set. It is NEVER replaced "
            "by Financial RIP V2; see legacy.financialRipV2 if a legacy value is "
            "wanted, and label it as legacy."
        )
    return block


def _build_overall_v5(overall_v5: Mapping[str, Any], financial_v3: Mapping[str, Any]) -> Dict[str, Any]:
    """The canonical Overall RIP block: 90% Financial RIP V3 + 10% CA7."""
    components_source = _obj(overall_v5.get("components"))
    absolute = _num(overall_v5.get("score"))
    block: Dict[str, Any] = {
        "score": absolute,
        "absoluteScore": absolute,
        "relativeScore": _num(overall_v5.get("relativeScore")),
        "rank": _int(overall_v5.get("rank")),
        "rankedSetCount": _int(overall_v5.get("cohortSize")),
        "tier": overall_v5.get("tier"),
        "version": overall_v5.get("version") or OVERALL_RIP_V5_VERSION,
        "normalizationMode": "fixed_absolute_anchors",
        "components": {
            "financialRipV3": {
                "score": _num(_obj(components_source.get("financialRipV3")).get("score")),
                "weight": OVERALL_RIP_V5_WEIGHTS["financial_rip"],
                "contribution": _num(_obj(components_source.get("financialRipV3")).get("contribution")),
            },
            "openingDesirability": {
                "score": _num(_obj(components_source.get("openingDesirability")).get("score")),
                "weight": OVERALL_RIP_V5_WEIGHTS["opening_desirability"],
                "contribution": _num(_obj(components_source.get("openingDesirability")).get("contribution")),
            },
        },
    }
    if absolute is None:
        block["status"] = overall_v5.get("status") or "unavailable_missing_input"
        block["statusReason"] = overall_v5.get("statusReason")
        block["missingInputs"] = list(overall_v5.get("missingInputs") or [])
        block["fallbackPolicy"] = (
            "Overall RIP V5 requires Financial RIP V3 and CA7. It never falls "
            "back to Financial RIP V2 or to Universal Set Desirability."
        )
        _ = financial_v3
    return block


def build_public_rip_contract_v5(target: Mapping[str, Any]) -> Dict[str, Any]:
    """Project one ranked target row into the canonical public v5 contract.

    ``target`` must already carry the canonical ``financialRipV3``,
    ``overallRipV5``, ``rip`` (legacy v4), ``ripCore`` (legacy V2),
    ``universalSetDesirability`` and ``openingExperience`` objects. Nothing is
    recomputed.

    The legacy blocks are lifted from the SAME v4 contract builder the existing
    surfaces use, so the legacy comparison view and the v4 consumers cannot
    disagree about a legacy number.
    """
    legacy_v4_contract = build_public_rip_contract_v4(target)
    financial_v3 = _obj(target.get("financialRipV3"))
    overall_v5 = _obj(target.get("overallRipV5"))

    return {
        "contractVersion": CONTRACT_VERSION,
        "canonicalFinancialRipVersion": FINANCIAL_RIP_V3_VERSION,
        "canonicalOverallRipVersion": OVERALL_RIP_V5_VERSION,
        # The canonical public blocks. `financialRip` IS Financial RIP V3 and
        # `overallRip` IS Overall RIP V5 after the cutover.
        "overallRip": _build_overall_v5(overall_v5, financial_v3),
        "financialRip": _build_financial_v3(financial_v3),
        # Unchanged by this task; lifted verbatim from the v4 projection.
        "openingDesirability": legacy_v4_contract["openingDesirability"],
        "universalSetDesirability": legacy_v4_contract["universalSetDesirability"],
        # Explicitly namespaced so nothing selects these by fallback.
        "legacy": {
            "label": "Legacy models. Retained for comparison, audit and rollback; not canonical.",
            "financialRipV2": legacy_v4_contract["financialRip"],
            "overallRipV4": legacy_v4_contract["overallRip"],
        },
        # Weights and transform parameters live here, not on the render path.
        "audit": _obj(financial_v3.get("audit")),
    }
