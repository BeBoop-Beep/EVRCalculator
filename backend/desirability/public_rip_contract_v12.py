"""Public RIP contract V12 - the contract that carries Financial RIP V5 and Overall RIP V14.

REGISTERED, NOT CANONICAL. ``canonical_public_rip_contract_version()`` still resolves to
``public_rip_contract_v11``; V12 is explicitly computable and is selected only by the separate,
explicitly authorized activation step. V11 is frozen: it is embedded here VERBATIM under
``publicRipContractV11`` (the real V11 contract built from the untouched target, exactly as V11
embeds V10), so an explicit V11 consumer keeps receiving what it always has.

Contract numbering is its own lineage (contract V12 carries model V14; do not conflate the counters).

WHAT IT ADDS OVER V11
---------------------
* ``financialRipV5`` / ``overallRipV14``: explicit blocks projecting the already-ranked V5/V14 objects
  (score, status, rankable, version, rank/tier/cohort/relative fields) - a projection, never a second
  ranking authority. They FAIL CLOSED: a block whose declared version, component lineage or
  rank/score consistency does not match the exact approved identities is reported unavailable with
  no score and no rank, never projected as canonical-ready.
* ``overallRipV14Composition``: truthful composition metadata (Financial V5 / Chase Accessibility V1 /
  Collector Appeal V5, weights 86/4/10). V11's hard-coded Financial-V4 composition is NOT reused.
* ``chaseAccessibility``: the same public RAW metric block as V11 (unchanged, scale-separated).
* The stable generic ``overallRip`` / ``financialRip`` slots are FORWARDED to V14 / V5 by pure re-keying
  of the explicit blocks. The V10 staging chain is deliberately NOT used: it stamps V4 identities into
  the generic financial slot and would mislabel V5 data.

NO PUBLIC VOCABULARY CHANGE. Public metric names do not move with a model version. "Shortfall
Resilience" is internal methodology: it appears only inside ``financialRipV5.components`` (the
component table) and is never a top-level or primary public metric. Component *presentation* for V5
(Loss Resilience -> Shortfall Resilience) is a frontend-transport concern for a later bucket.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping

from backend.calculations.evr.financial_rip_v5_config import (
    FINANCIAL_RIP_V5_VERSION,
    FINANCIAL_RIP_V5_WEIGHTS,
)
from backend.desirability.public_rip_contract_v11 import (
    PUBLIC_RIP_CONTRACT_V11_KEY,
    _chase_accessibility_block,
    build_public_rip_contract_v11,
)
from backend.desirability.scoring_config import (
    CANONICAL_OVERALL_RIP_VERSION,
    OVERALL_RIP_V14_EFFECTIVE_WEIGHTS,
    OVERALL_RIP_V14_VERSION,
    OVERALL_RIP_V14_WEIGHTS,
    overall_rip_v14_required_chase_accessibility_version,
    overall_rip_v14_required_collector_appeal_version,
)

PUBLIC_RIP_CONTRACT_V12_KEY = "publicRipContractV12"
PUBLIC_RIP_CONTRACT_V12_VERSION = "public_rip_contract_v12"

STATUS_INCONSISTENT = "unavailable_inconsistent_lineage"

_STANDING = ("rank", "tier", "cohortSize", "relativeScore", "leaderNormalizedScore", "publicTier")


def _unavailable(version: str, status: str, reason: str, canonical: bool) -> Dict[str, Any]:
    return {"score": None, "status": status, "statusReason": reason, "rankable": False, "version": version,
            "components": {}, "missingInputs": [], **{k: None for k in _STANDING}, "canonical": canonical}


def _project(obj: Mapping[str, Any], version: str, canonical: bool) -> Dict[str, Any]:
    return {
        "score": obj.get("score"), "status": obj.get("status"), "statusReason": obj.get("statusReason"),
        "rankable": bool(obj.get("rankable")), "version": version,
        "components": obj.get("components") or {}, "missingInputs": obj.get("missingInputs") or [],
        **{k: obj.get(k) for k in _STANDING},
        # canonical describes the MODEL (is it the program-wide canonical selection yet?), not the row.
        "canonical": canonical,
    }


def _lineage_problems_v14(obj: Mapping[str, Any]) -> List[str]:
    problems: List[str] = []
    if obj.get("version") not in (None, OVERALL_RIP_V14_VERSION):
        problems.append("overallRipV14.version=%r" % (obj.get("version"),))
    components = obj.get("components") or {}
    if "financialRipV4" in components:
        problems.append("overallRipV14 carries a financialRipV4 component")
    fin = components.get("financialRipV5") or {}
    if obj.get("score") is not None and not fin:
        problems.append("overallRipV14 score without a financialRipV5 component")
    return problems


def _overall_rip_v14_block(target: Mapping[str, Any]) -> Dict[str, Any]:
    obj = dict(target.get("overallRipV14") or {})
    canonical = CANONICAL_OVERALL_RIP_VERSION == OVERALL_RIP_V14_VERSION
    problems = _lineage_problems_v14(obj)
    ready_claim = obj.get("score") is not None or obj.get("status") == "ready" or bool(obj.get("rankable"))
    if ready_claim and (obj.get("rank") is None or obj.get("status") != "ready"):
        problems.append("V14 score/rankable claimed without a ready status and rank")
    if problems:
        return _unavailable(OVERALL_RIP_V14_VERSION, STATUS_INCONSISTENT, "; ".join(problems), canonical)
    return _project(obj, OVERALL_RIP_V14_VERSION, canonical)


def _financial_rip_v5_block(target: Mapping[str, Any]) -> Dict[str, Any]:
    obj = dict(target.get("financialRipV5") or {})
    canonical = CANONICAL_OVERALL_RIP_VERSION == OVERALL_RIP_V14_VERSION
    problems: List[str] = []
    declared = obj.get("scoreVersion") or obj.get("version")
    if declared not in (None, FINANCIAL_RIP_V5_VERSION):
        problems.append("financialRipV5.version=%r" % (declared,))
    components = obj.get("components") or {}
    if "loss_resilience" in components:
        problems.append("financialRipV5 carries loss_resilience (V4-shaped)")
    if components and set(components) != set(FINANCIAL_RIP_V5_WEIGHTS):
        problems.append("financialRipV5 component set differs from the approved six")
    if obj.get("score") is not None and obj.get("status") != "ready":
        problems.append("V5 score without a ready status")
    if problems:
        return _unavailable(FINANCIAL_RIP_V5_VERSION, STATUS_INCONSISTENT, "; ".join(problems), canonical)
    return _project(obj, FINANCIAL_RIP_V5_VERSION, canonical)


def _forward_generic_slot(block: Mapping[str, Any]) -> Dict[str, Any]:
    """Pure re-keying of an explicit block into the stable generic slot shape."""
    return {
        "score": block["score"], "absoluteScore": block["score"], "relativeScore": block.get("relativeScore"),
        "rank": block.get("rank"), "rankedSetCount": block.get("cohortSize"), "tier": block.get("tier"),
        "version": block["version"], "status": block.get("status"), "rankable": block.get("rankable"),
        "components": block.get("components") or {},
    }


def build_public_rip_contract_v12(target: Mapping[str, Any]) -> Dict[str, Any]:
    """Project a ranked target into the public V12 contract (explicit; not canonical).

    ``target`` is expected to carry ``financialRipV5`` and ``overallRipV14`` (already ranked upstream)
    alongside everything V11 reads. V11 is built from the UNTOUCHED target and embedded verbatim.
    """
    real_v11 = target.get(PUBLIC_RIP_CONTRACT_V11_KEY) or build_public_rip_contract_v11(target)
    v14 = _overall_rip_v14_block(target)
    v5 = _financial_rip_v5_block(target)

    # Everything that is not a model-specific slot is inherited from the real V11 projection
    # (collectorAppeal, personalFit, legacy, metricDistinction, ...), unchanged.
    contract = {k: v for k, v in dict(real_v11).items()
                if k not in ("overallRipV12", "overallRipV12Composition")}
    contract[PUBLIC_RIP_CONTRACT_V11_KEY] = real_v11
    contract["contractVersion"] = PUBLIC_RIP_CONTRACT_V12_VERSION
    contract["canonicalOverallRipVersion"] = OVERALL_RIP_V14_VERSION
    contract["canonicalFinancialRipVersion"] = FINANCIAL_RIP_V5_VERSION
    contract["financialRipV5"] = v5
    contract["overallRipV14"] = v14
    contract["overallRip"] = _forward_generic_slot(v14)
    contract["financialRip"] = _forward_generic_slot(v5)
    contract["chaseAccessibility"] = _chase_accessibility_block(target)
    contract["overallRipV14Composition"] = {
        "version": OVERALL_RIP_V14_VERSION,
        "inputs": {
            "financialRip": FINANCIAL_RIP_V5_VERSION,
            "chaseAccessibility": overall_rip_v14_required_chase_accessibility_version(),
            "collectorAppeal": overall_rip_v14_required_collector_appeal_version(),
        },
        "weights": dict(OVERALL_RIP_V14_WEIGHTS),
        "effectiveWeights": dict(OVERALL_RIP_V14_EFFECTIVE_WEIGHTS),
    }
    return contract
