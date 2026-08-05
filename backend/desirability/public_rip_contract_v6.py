"""Public RIP contract v6 — the canonical projection after the 80/20 cutover.

WHAT CHANGED FROM v5
--------------------
v5 published ``overallRip`` as ``0.90 * Financial RIP V3 + 0.10 * CA7``. v6
publishes the canonical model:

    Overall RIP V6 = 0.80 * Financial RIP V3 + 0.20 * Collector Appeal

Two things moved: the split, and the appeal input (legacy CA7 -> the canonical
D/F/P Collector Appeal). The financial side is UNCHANGED - the same absolute
fixed-anchor Financial RIP V3, with the same six components and the same
weights.

v4 AND v5 ARE NOT TOUCHED. Both builders still produce exactly what they always
did, under their own keys, for every existing consumer. v6 is a NEW, additive
key.

COLLECTOR APPEAL IS NOW A FIRST-CLASS PUBLIC BLOCK
--------------------------------------------------
It carries its own score, rank, denominator and version, and its three inputs:

    D = Roster Desirability            (how desirable the roster is)
    F = Desirable Outcome Frequency    (how often a pack delivers one)
    P = Dual-Path Depth                (attainable printing AND elite chase)

F IS NOT A FINANCIAL METRIC. The contract carries that statement explicitly, on
the block itself, because the number is a probability in the same shape as True
Win Frequency and the two would otherwise be trivially confusable. A desirable
outcome may still be worth less than the pack price.

LEGACY IS LABELLED AND NEVER FABRICATED
---------------------------------------
``legacy`` carries Financial RIP V2, Overall RIP v4, Overall RIP V5 and legacy
CA7 - but only when the underlying object actually exists. A legacy block is
never synthesised from a canonical value to make the shape look complete: a
fabricated legacy number would be indistinguishable from a real one and would
corrupt exactly the comparison the block exists to support.

NOTHING IS RECOMPUTED HERE
--------------------------
Every number is lifted verbatim from the authoritative backend objects. This
module reshapes and renames; it does not score. In particular it never
recomputes Collector Appeal, Desirable Outcome Frequency, Financial RIP or
Overall RIP.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Optional

from backend.calculations.evr.financial_rip_v3_config import (
    OVERALL_RIP_V5_VERSION,
)
from backend.desirability.collector_appeal import (
    COLLECTOR_APPEAL_CA7_VERSION,
    COLLECTOR_APPEAL_V2_FORMULA_VERSION,
    COLLECTOR_APPEAL_V2_VERSION,
)
from backend.desirability.public_rip_contract_v5 import build_public_rip_contract_v5
from backend.desirability.scoring_config import (
    OVERALL_RIP_V6_EFFECTIVE_WEIGHTS,
    OVERALL_RIP_V6_VERSION,
    OVERALL_RIP_V6_WEIGHTS,
)

PUBLIC_RIP_CONTRACT_V6_KEY = "publicRipContractV6"
PUBLIC_RIP_CONTRACT_V6_VERSION = "public_rip_contract_v6"
CONTRACT_VERSION = PUBLIC_RIP_CONTRACT_V6_VERSION


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


def _build_overall_v6(overall_v6: Mapping[str, Any]) -> Dict[str, Any]:
    """The canonical Overall RIP block: 80% Financial RIP V3 + 20% Collector Appeal."""
    components_source = _obj(overall_v6.get("components"))
    absolute = _num(overall_v6.get("score"))
    block: Dict[str, Any] = {
        "score": absolute,
        "absoluteScore": absolute,
        # Diagnostic only, and never the formula input. A cohort-relative score
        # is a presentation of position, not a score; using it as the 80/20
        # input would make a set's Overall RIP depend on which sets exist.
        "relativeScore": _num(overall_v6.get("relativeScore")),
        "rank": _int(overall_v6.get("rank")),
        "rankedSetCount": _int(overall_v6.get("cohortSize")),
        "tier": overall_v6.get("tier"),
        "version": overall_v6.get("version") or OVERALL_RIP_V6_VERSION,
        "normalizationMode": "fixed_absolute_anchors",
        "components": {
            "financialRipV3": {
                "score": _num(_obj(components_source.get("financialRipV3")).get("score")),
                "weight": OVERALL_RIP_V6_WEIGHTS["financial_rip"],
                "contribution": _num(
                    _obj(components_source.get("financialRipV3")).get("contribution")
                ),
            },
            "collectorAppeal": {
                "score": _num(_obj(components_source.get("collectorAppeal")).get("score")),
                "weight": OVERALL_RIP_V6_WEIGHTS["collector_appeal"],
                "contribution": _num(
                    _obj(components_source.get("collectorAppeal")).get("contribution")
                ),
            },
        },
        "effectiveWeights": dict(OVERALL_RIP_V6_EFFECTIVE_WEIGHTS),
    }
    if absolute is None:
        block["status"] = overall_v6.get("status") or "unavailable_missing_input"
        block["statusReason"] = overall_v6.get("statusReason")
        block["missingInputs"] = list(overall_v6.get("missingInputs") or [])
        block["fallbackPolicy"] = (
            "Overall RIP V6 requires Financial RIP V3 and Collector Appeal. It "
            "never falls back to Overall RIP V5/v4/V2, to legacy CA7, or to "
            "Universal Set Desirability."
        )
    return block


def _build_collector_appeal(
    collector: Mapping[str, Any],
    universal: Mapping[str, Any],
) -> Dict[str, Any]:
    """The canonical Collector Appeal block: score, rank, and its D/F/P inputs.

    ``collector`` is the Collector Appeal service's per-set payload, already
    enriched with rank/tier/cohortSize by the ranking layer.

    D is read from TWO places for two different purposes, and neither is a
    recomputation: the 0-1 ``rawValue`` is the exact number the formula consumed
    (from the appeal's own decomposition), and the 0-100 ``score`` is the
    published Universal Set Desirability. Roster desirability is deliberately
    not republished on the opening-experience block - see the note there.
    """
    appeal = _obj(collector.get("collectorAppeal"))
    roster = {"score": _obj(universal).get("score"), "version": _obj(universal).get("version")}
    frequency = _obj(collector.get("desirableOutcomeFrequency"))
    dual_path = _obj(collector.get("dualPathDepth"))
    inputs = _obj(appeal.get("inputs"))

    absolute = _num(appeal.get("score"))
    block: Dict[str, Any] = {
        "score": absolute,
        "absoluteScore": absolute,
        "rank": _int(appeal.get("rank")),
        "rankedSetCount": _int(appeal.get("cohortSize")),
        "tier": appeal.get("tier"),
        "version": appeal.get("version") or COLLECTOR_APPEAL_V2_VERSION,
        "formulaVersion": appeal.get("formulaVersion") or COLLECTOR_APPEAL_V2_FORMULA_VERSION,
        "formula": appeal.get("formula"),
        "components": {
            "rosterDesirability": {
                "score": _num(roster.get("score")),
                "rawValue": _num(inputs.get("rosterDesirability")),
                "version": roster.get("version"),
                "interpretation": (
                    "How desirable the Pokemon roster is before pull difficulty is "
                    "considered."
                ),
            },
            "desirableOutcomeFrequency": {
                "rawValue": _num(frequency.get("rawValue")),
                "displayPercent": _num(frequency.get("displayPercent")),
                "impliedOddsOneInN": _num(frequency.get("impliedOddsOneInN")),
                "eligibleCardCount": _int(frequency.get("eligibleCardCount")),
                "eligibleSubjectCount": _int(frequency.get("eligibleSubjectCount")),
                "coveredDemandShare": _num(frequency.get("coveredDemandShare")),
                "slotGroupCount": _int(frequency.get("slotGroupCount")),
                "status": frequency.get("status"),
                "statusReason": frequency.get("statusReason"),
                "version": frequency.get("version"),
                # Carried on the block itself, not only in documentation. This
                # number has the same shape as True Win Frequency and would
                # otherwise be read as a financial claim.
                "isFinancialMetric": False,
                "interpretation": (
                    "How often the modeled pack can deliver at least one card tied "
                    "to a currently desirable Pokemon."
                ),
                "disclaimer": "A desirable outcome can still be worth less than the pack price.",
            },
            "dualPathDepth": {
                "rawValue": _num(dual_path.get("rawValue")),
                "displayPercent": _num(dual_path.get("displayPercent")),
                "subjectsWithMultiplePaths": _int(dual_path.get("subjectsWithMultiplePaths")),
                "coveredDemandShare": _num(dual_path.get("coveredDemandShare")),
                "version": dual_path.get("version"),
                "interpretation": (
                    "Whether desirable Pokemon offer both an attainable printing and "
                    "a true elite chase."
                ),
            },
        },
        "structuralOpeningAppeal": _num(appeal.get("structuralOpeningAppeal")),
        "headroomBonus": _num(appeal.get("headroomBonus")),
        "topSubjects": list(collector.get("topSubjects") or []),
        "coverage": _obj(collector.get("coverage")),
        # Stated once, on the canonical block, so a consumer never has to infer
        # it from field names.
        "subjectScope": {
            "modeled": ["pokemon"],
            "notYetModeled": ["trainer", "artist"],
            "note": (
                "Trainer and artist desirability are not yet modeled. They are "
                "omitted from this metric rather than scored as zero."
            ),
        },
    }
    if absolute is None:
        block["status"] = "unavailable"
        reasons = [str(reason) for reason in (_obj(collector.get("coverage")).get("reasons") or [])]
        block["statusReason"] = "; ".join(reasons) or None
    return block


def _build_legacy(target: Mapping[str, Any], v5_contract: Mapping[str, Any]) -> Dict[str, Any]:
    """Legacy blocks, included ONLY when the underlying object actually exists.

    A fabricated legacy value would be indistinguishable from a measured one and
    would corrupt the very comparison the block exists to support, so an absent
    model is simply absent from this dict.
    """
    legacy: Dict[str, Any] = {
        "label": "Legacy models. Retained for comparison, audit and rollback; not canonical.",
        # These two always exist: the V2 pillars and Overall RIP v4 are computed
        # for every ranked target by the same service that computes V6.
        "financialRipV2": _obj(v5_contract.get("legacy")).get("financialRipV2") or {},
        "overallRipV4": _obj(v5_contract.get("legacy")).get("overallRipV4") or {},
    }

    overall_v5 = _obj(target.get("overallRipV5"))
    if overall_v5 and _num(overall_v5.get("score")) is not None:
        legacy["overallRipV5"] = {
            "score": _num(overall_v5.get("score")),
            "rank": _int(overall_v5.get("rank")),
            "rankedSetCount": _int(overall_v5.get("cohortSize")),
            "tier": overall_v5.get("tier"),
            "version": overall_v5.get("version") or OVERALL_RIP_V5_VERSION,
            "note": "Superseded 90/10 blend of Financial RIP V3 and legacy CA7.",
        }

    legacy_ca7 = _obj(_obj(target.get("openingExperience")).get("legacyCollectorAppealCA7"))
    if legacy_ca7 and _num(legacy_ca7.get("score")) is not None:
        legacy["collectorAppealCA7"] = {
            "score": _num(legacy_ca7.get("score")),
            "rawValue": _num(legacy_ca7.get("rawValue")),
            "version": legacy_ca7.get("version") or COLLECTOR_APPEAL_CA7_VERSION,
            "note": legacy_ca7.get("note"),
        }
    return legacy


def build_public_rip_contract_v6(target: Mapping[str, Any]) -> Dict[str, Any]:
    """Project one ranked target row into the canonical public v6 contract.

    ``target`` must already carry the canonical ``financialRipV3``,
    ``overallRipV6``, ``openingExperience`` (the Collector Appeal payload),
    ``universalSetDesirability``, and the legacy ``rip`` / ``ripCore`` /
    ``overallRipV5`` objects. Nothing is recomputed.

    The Financial RIP block and the legacy V2/v4 blocks are lifted from the v5
    contract builder, so the canonical and legacy surfaces cannot disagree about
    a financial number.
    """
    v5_contract = build_public_rip_contract_v5(target)
    collector = _obj(target.get("openingExperience"))

    return {
        "contractVersion": CONTRACT_VERSION,
        "canonicalOverallRipVersion": OVERALL_RIP_V6_VERSION,
        "canonicalCollectorAppealVersion": COLLECTOR_APPEAL_V2_VERSION,
        "overallRip": _build_overall_v6(_obj(target.get("overallRipV6"))),
        # Unchanged by this task: the same six-component Financial RIP V3 block
        # v5 publishes, lifted verbatim.
        "financialRip": v5_contract["financialRip"],
        "collectorAppeal": _build_collector_appeal(
            collector, _obj(target.get("universalSetDesirability"))
        ),
        "universalSetDesirability": v5_contract["universalSetDesirability"],
        "legacy": _build_legacy(target, v5_contract),
        "metricDistinction": {
            "trueWinFrequency": "P(simulated monetary pack value >= pack cost).",
            "desirableOutcomeFrequency": (
                "P(modeled pack contains at least one card tied to an eligible "
                "desirable subject)."
            ),
            "note": (
                "Financial RIP measures monetary pack outcomes. Collector Appeal "
                "measures how desirable the modeled cards are and how often the "
                "pack can deliver them. A desirable outcome may still be a "
                "financial loss."
            ),
        },
        "audit": v5_contract.get("audit") or {},
    }
