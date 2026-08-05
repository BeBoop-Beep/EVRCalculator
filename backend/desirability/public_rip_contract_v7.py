"""Public RIP contract v7 — the canonical projection after the 90/10 V3 cutover.

WHAT CHANGED FROM v6
--------------------
v6 published ``overallRip`` as ``0.80 * Financial RIP V3 + 0.20 * Collector
Appeal V2``. v7 publishes the canonical model:

    Overall RIP V7 = 0.90 * Financial RIP V3 + 0.10 * Collector Appeal V3

Two things moved: the split, and the appeal input (Collector Appeal V2's bounded
headroom formula -> Collector Appeal V3's balanced weighted sum of D, H and P).
The financial side is UNCHANGED - the same absolute fixed-anchor Financial RIP
V3, with the same six components and the same weights, lifted verbatim from the
v5 builder so the canonical and legacy surfaces cannot disagree about a
financial number.

v4, v5 AND v6 ARE NOT TOUCHED. All three builders still produce exactly what
they always did, under their own keys, for every existing consumer. v7 is a NEW,
additive key.

WHAT THIS CONTRACT DELIBERATELY DOES NOT PUBLISH
------------------------------------------------
Collector Appeal V3's exact weights, an executable formula string, its internal
thresholds, any validation statistic, and any candidate-grid metadata. The
arithmetic is a one-line weighted sum, so publishing the weight vector would be
publishing the formula; and publishing a per-input CONTRIBUTION would be the same
thing by division. What a consumer gets is the score, the status, the three
factor values (which are already published on their own terms), high-level factor
labels, and the version identifiers.

The Overall RIP block DOES carry its 0.90 / 0.10 split. That split is a stated
product fact - the leaderboard says it blends a financial score with a collector
score in those proportions - and hiding it would make the published number
unexplainable. Collector Appeal's INTERNAL composition is the thing that stays
internal.

F IS NOT A FINANCIAL METRIC
---------------------------
The contract carries that statement explicitly, on the block itself, because
Desirable Outcome Frequency is a probability in the same shape as True Win
Frequency and the two would otherwise be trivially confusable. A desirable
outcome may still be worth less than the pack price.

LEGACY IS LABELLED AND NEVER FABRICATED
---------------------------------------
``legacy`` carries Financial RIP V2, Overall RIP v4, Overall RIP V5, Overall RIP
V6, Collector Appeal V2 and legacy CA7 - but only when the underlying object
actually exists. A legacy block is never synthesised from a canonical value to
make the shape look complete: a fabricated legacy number would be
indistinguishable from a real one and would corrupt exactly the comparison the
block exists to support.

NOTHING IS RECOMPUTED HERE
--------------------------
Every number is lifted verbatim from the authoritative backend objects. This
module reshapes and renames; it does not score.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Optional

from backend.desirability.collector_appeal import (
    COLLECTOR_APPEAL_CA7_VERSION,
    COLLECTOR_APPEAL_V2_VERSION,
    COLLECTOR_APPEAL_V3_FORMULA_VERSION,
    COLLECTOR_APPEAL_V3_VERSION,
    collector_appeal_v3_public_identity,
)
from backend.desirability.public_rip_contract_v6 import build_public_rip_contract_v6
from backend.desirability.scoring_config import (
    CANONICAL_FINANCIAL_RIP_VERSION,
    OVERALL_RIP_V6_VERSION,
    OVERALL_RIP_V7_EFFECTIVE_WEIGHTS,
    OVERALL_RIP_V7_VERSION,
    OVERALL_RIP_V7_WEIGHTS,
)

PUBLIC_RIP_CONTRACT_V7_KEY = "publicRipContractV7"
PUBLIC_RIP_CONTRACT_V7_VERSION = "public_rip_contract_v7"
CONTRACT_VERSION = PUBLIC_RIP_CONTRACT_V7_VERSION

# Fields a consumer must never find on the canonical Collector Appeal block.
# Pinned as data so the contract test asserts against the same list the module
# documents, rather than against a hand-written copy that can fall behind.
COLLECTOR_APPEAL_WITHHELD_FIELDS: tuple = (
    "weights",
    "formula",
    "formulaExpression",
    "dContribution",
    "hContribution",
    "pContribution",
    "contributions",
    "thresholds",
    "candidateGrid",
    "validation",
)


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


def _build_overall_v7(
    overall_v7: Mapping[str, Any], cohort_fingerprint: Optional[str] = None
) -> Dict[str, Any]:
    """The canonical Overall RIP block: 90% Financial RIP V3 + 10% Collector Appeal."""
    components_source = _obj(overall_v7.get("components"))
    absolute = _num(overall_v7.get("score"))
    block: Dict[str, Any] = {
        "score": absolute,
        "absoluteScore": absolute,
        # Diagnostic only, and never the formula input. A cohort-relative score
        # is a presentation of position, not a score; using it as the 90/10
        # input would make a set's Overall RIP depend on which sets exist.
        "relativeScore": _num(overall_v7.get("relativeScore")),
        "rank": _int(overall_v7.get("rank")),
        "rankedSetCount": _int(overall_v7.get("cohortSize")),
        "tier": overall_v7.get("tier"),
        # Identifies the population the rank, the tier, the denominator and the
        # relative score all describe. Without it a consumer holding two ranks
        # cannot tell whether they were computed over the same cohort.
        "cohortFingerprint": cohort_fingerprint,
        "version": overall_v7.get("version") or OVERALL_RIP_V7_VERSION,
        "normalizationMode": "fixed_absolute_anchors",
        "components": {
            "financialRipV3": {
                "score": _num(_obj(components_source.get("financialRipV3")).get("score")),
                "weight": OVERALL_RIP_V7_WEIGHTS["financial_rip"],
                "contribution": _num(
                    _obj(components_source.get("financialRipV3")).get("contribution")
                ),
            },
            "collectorAppeal": {
                "score": _num(_obj(components_source.get("collectorAppeal")).get("score")),
                "weight": OVERALL_RIP_V7_WEIGHTS["collector_appeal"],
                "contribution": _num(
                    _obj(components_source.get("collectorAppeal")).get("contribution")
                ),
            },
        },
        "effectiveWeights": dict(OVERALL_RIP_V7_EFFECTIVE_WEIGHTS),
    }
    if absolute is None:
        block["status"] = overall_v7.get("status") or "unavailable_missing_input"
        block["statusReason"] = overall_v7.get("statusReason")
        block["missingInputs"] = list(overall_v7.get("missingInputs") or [])
        block["fallbackPolicy"] = (
            "Overall RIP V7 requires Financial RIP V3 and Collector Appeal V3. A "
            "missing Collector Appeal is not treated as zero, and there is no "
            "fallback to Overall RIP V6/V5/v4/V2, to Collector Appeal V2, to "
            "legacy CA7, or to Universal Set Desirability."
        )
    return block


def _build_collector_appeal_v3(
    collector: Mapping[str, Any],
    universal: Mapping[str, Any],
    cohort_fingerprint: Optional[str] = None,
) -> Dict[str, Any]:
    """The canonical Collector Appeal block: score, rank, and its D/H/P factors.

    ``collector`` is the Collector Appeal service's per-set payload, already
    enriched with rank/tier/cohortSize by the ranking layer.

    D is read from TWO places for two different purposes, and neither is a
    recomputation: the 0-1 value is the exact number the formula consumed (from
    the appeal's own factor block), and the 0-100 score is the published
    Universal Set Desirability.

    No weight, contribution or formula string appears here - see the module
    docstring. The three factor VALUES are published because each is already a
    published metric in its own right; what stays internal is how they combine.
    """
    appeal = _obj(collector.get("collectorAppeal"))
    roster = {"score": _obj(universal).get("score"), "version": _obj(universal).get("version")}
    frequency = _obj(collector.get("desirableOutcomeFrequency"))
    dual_path = _obj(collector.get("dualPathDepth"))
    factors = _obj(appeal.get("factors"))
    identity = collector_appeal_v3_public_identity()

    absolute = _num(appeal.get("score"))
    block: Dict[str, Any] = {
        "score": absolute,
        "absoluteScore": absolute,
        # Presentation only. The 90/10 Overall blend consumes `absoluteScore`;
        # feeding a cohort-relative appeal into the formula would make a set's
        # Overall RIP depend on which other sets exist.
        "relativeScore": _num(appeal.get("relativeScore")),
        "rank": _int(appeal.get("rank")),
        "rankedSetCount": _int(appeal.get("cohortSize")),
        "tier": appeal.get("tier"),
        "cohortFingerprint": cohort_fingerprint,
        "version": appeal.get("version") or COLLECTOR_APPEAL_V3_VERSION,
        "formulaVersion": appeal.get("formulaVersion") or COLLECTOR_APPEAL_V3_FORMULA_VERSION,
        # High-level labels only. `weightsDisclosed: False` is carried on the
        # block itself so a consumer can see that the omission is a decision
        # rather than an oversight, and never goes looking for the numbers.
        "factorLabels": identity["factors"],
        "weightsDisclosed": False,
        "components": {
            "rosterDesirability": {
                "score": _num(roster.get("score")),
                "rawValue": _num(factors.get("rosterDesirability")),
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
        "topSubjects": list(collector.get("topSubjects") or []),
        "coverage": _obj(collector.get("coverage")),
        "excludedInputs": list(identity["excludedInputs"]),
        # Stated once, on the canonical block, so a consumer never has to infer
        # it from field names.
        "subjectScope": {
            **identity["subjectScope"],
            "note": (
                "Trainer and artist desirability are not yet modeled. They are "
                "omitted from this metric rather than scored as zero."
            ),
        },
    }
    if absolute is None:
        block["status"] = "unavailable"
        reasons = [str(reason) for reason in (_obj(collector.get("coverage")).get("reasons") or [])]
        missing = [str(key) for key in (appeal.get("missingInputs") or [])]
        block["statusReason"] = "; ".join(reasons) or None
        block["missingInputs"] = missing
        block["fallbackPolicy"] = (
            "Collector Appeal V3 requires all three of Roster Desirability, "
            "Desirable Outcome Frequency and Dual-Path Depth. A missing input is "
            "never substituted with zero, 0.5, Roster Desirability alone, or a "
            "previous Collector Appeal version."
        )
    return block


def _build_legacy(target: Mapping[str, Any], v6_contract: Mapping[str, Any]) -> Dict[str, Any]:
    """Legacy blocks, included ONLY when the underlying object actually exists.

    A fabricated legacy value would be indistinguishable from a measured one and
    would corrupt the very comparison the block exists to support, so an absent
    model is simply absent from this dict.
    """
    inherited = _obj(v6_contract.get("legacy"))
    legacy: Dict[str, Any] = {
        "label": "Legacy models. Retained for comparison, audit and rollback; not canonical.",
        # These two always exist: the V2 pillars and Overall RIP v4 are computed
        # for every ranked target by the same service that computes V7.
        "financialRipV2": inherited.get("financialRipV2") or {},
        "overallRipV4": inherited.get("overallRipV4") or {},
    }
    for key in ("overallRipV5", "collectorAppealCA7"):
        if inherited.get(key):
            legacy[key] = inherited[key]

    overall_v6 = _obj(target.get("overallRipV6"))
    if overall_v6 and _num(overall_v6.get("score")) is not None:
        legacy["overallRipV6"] = {
            "score": _num(overall_v6.get("score")),
            "rank": _int(overall_v6.get("rank")),
            "rankedSetCount": _int(overall_v6.get("cohortSize")),
            "tier": overall_v6.get("tier"),
            "version": overall_v6.get("version") or OVERALL_RIP_V6_VERSION,
            "note": "Superseded 80/20 blend of Financial RIP V3 and Collector Appeal V2.",
        }

    legacy_v2 = _obj(_obj(target.get("openingExperience")).get("legacyCollectorAppealV2"))
    if legacy_v2 and _num(legacy_v2.get("score")) is not None:
        legacy["collectorAppealV2"] = {
            "score": _num(legacy_v2.get("score")),
            "rawValue": _num(legacy_v2.get("rawValue")),
            "version": legacy_v2.get("version") or COLLECTOR_APPEAL_V2_VERSION,
            "note": legacy_v2.get("note"),
        }
    if not legacy.get("collectorAppealCA7"):
        legacy_ca7 = _obj(_obj(target.get("openingExperience")).get("legacyCollectorAppealCA7"))
        if legacy_ca7 and _num(legacy_ca7.get("score")) is not None:
            legacy["collectorAppealCA7"] = {
                "score": _num(legacy_ca7.get("score")),
                "rawValue": _num(legacy_ca7.get("rawValue")),
                "version": legacy_ca7.get("version") or COLLECTOR_APPEAL_CA7_VERSION,
                "note": legacy_ca7.get("note"),
            }
    return legacy


def build_public_rip_contract_v7(target: Mapping[str, Any]) -> Dict[str, Any]:
    """Project one ranked target row into the canonical public v7 contract.

    ``target`` must already carry the canonical ``financialRipV3``,
    ``overallRipV7``, ``openingExperience`` (the Collector Appeal payload),
    ``universalSetDesirability``, and the legacy ``rip`` / ``ripCore`` /
    ``overallRipV5`` / ``overallRipV6`` objects. Nothing is recomputed.

    The Financial RIP block and the legacy blocks are lifted from the v6/v5
    contract builders, so the canonical and legacy surfaces cannot disagree about
    a financial number.
    """
    v6_contract = build_public_rip_contract_v6(target)
    collector = _obj(target.get("openingExperience"))
    # Stamped on the target by the ranking layer (_attach_cohort_fingerprint).
    # Absent for an unranked target, which is correct: an unranked target has no
    # cohort, and a fabricated fingerprint would claim otherwise.
    cohort_fingerprint = target.get("cohortFingerprint")
    cohort_fingerprint = str(cohort_fingerprint) if cohort_fingerprint else None

    financial = dict(v6_contract["financialRip"])
    financial["cohortFingerprint"] = cohort_fingerprint

    return {
        "contractVersion": CONTRACT_VERSION,
        "canonicalFinancialRipVersion": CANONICAL_FINANCIAL_RIP_VERSION,
        "canonicalOverallRipVersion": OVERALL_RIP_V7_VERSION,
        "canonicalCollectorAppealVersion": COLLECTOR_APPEAL_V3_VERSION,
        "overallRip": _build_overall_v7(
            _obj(target.get("overallRipV7")), cohort_fingerprint
        ),
        # The same six-component Financial RIP V3 block v5 and v6 publish, lifted
        # verbatim and stamped with the cohort its rank/relative score describe.
        # Every one of the six components carries its own absolute, relative,
        # rank, tier and denominator (see public_rip_contract_v5._v3_component).
        "financialRip": financial,
        "collectorAppeal": _build_collector_appeal_v3(
            collector, _obj(target.get("universalSetDesirability")), cohort_fingerprint
        ),
        "universalSetDesirability": v6_contract["universalSetDesirability"],
        "legacy": _build_legacy(target, v6_contract),
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
        # Personal Fit is a PLANNED third pillar and is deliberately not
        # implemented. Declared here so a consumer knows the shape is reserved
        # rather than missing, and so nothing invents a placeholder score for it.
        "personalFit": {
            "status": "not_implemented",
            "note": (
                "Personal Fit is a planned third pillar and is not part of Overall "
                "RIP. It has no score, and no surface substitutes one."
            ),
        },
        "audit": v6_contract.get("audit") or {},
    }
