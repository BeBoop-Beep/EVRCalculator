"""Public RIP contract V11 - CANONICAL projection carrying Overall RIP V12.

Public contract numbering is its OWN lineage, separate from Overall RIP model
numbering: the highest existing contract file is `public_rip_contract_v10.py`
(``public_rip_contract_v10``), so the next honest, unused contract identity is
V11 - NOT "v12" - even though the Overall RIP model it carries is V12. Do not
conflate the two counters.

CANONICAL. `canonical_public_rip_contract_version()`
(`backend/desirability/scoring_config.py`) resolves to
`PUBLIC_RIP_CONTRACT_V11_VERSION`, and `CANONICAL_OVERALL_RIP_VERSION` resolves
to Overall RIP V12. This contract remains additive over V10: every key the V10
contract emits is unchanged and embedded verbatim under `publicRipContractV10`
(see `build_public_rip_contract_v11` below), so an explicit V10 consumer (or
any earlier version) keeps receiving exactly what it always has - V10 is kept
as historical/rollback lineage, not deleted. `publicRipContractV11` is the
top-level key current Set/Explore consumers read for the canonical Overall RIP.

WHAT IT ADDS OVER V10
----------------------
* ``overallRipV12``: score / rank / tier / cohortSize / relativeScore /
  leaderNormalizedScore / publicTier / rankable / status / version for the
  CANONICAL Overall RIP V12 lineage (0.86 Financial RIP V4 + 0.04 Chase
  Accessibility V1 score + 0.10 Collector Appeal V5). The rank/standing fields
  are attached upstream, by the same one ranking authority every other public
  metric uses (`_rank_within_cohort` / `_attach_relative_scores` in
  `explore_rip_statistics_service.py`), before this contract is built - this
  module only projects them, it never computes a second rank. An unavailable
  V12 (missing/mismatched/non-ready Chase Accessibility authority, or missing
  Financial/Collector input) is reported as an explicit non-ready status and
  simply has no rank - never a fabricated one, and never coerced into a
  neighboring version's slot.
* ``chaseAccessibility``: the PUBLIC RAW metric (a decimal fraction / percent,
  unchanged shape from ``project_chase_accessibility`` in
  ``backend.db.services.chase_accessibility_service``), together with its
  status/version and (diagnostic only) Chase Depth. Chase Depth is NEVER a
  scored Overall RIP input here or anywhere else.
* ``overallRipV12Composition``: audit metadata naming the three Overall V12
  inputs and their validated weights - present so a consumer auditing V10 vs
  V12 does not have to hand-derive the weights from the score alone.

SCALE SEPARATION (do not violate)
----------------------------------
``chaseAccessibility.value`` / ``chaseAccessibility.percent`` are the PUBLIC
RAW Chase Accessibility (``A_raw`` and ``A_raw * 100``) - the same numbers the
set page already publishes. The Overall-RIP-internal ``A_score`` transform
(``100 * A_raw / (A_raw + 0.002)``) is a DISTINCT, larger-scale quantity and is
serialized ONLY inside ``overallRipV12.components.chaseAccessibility.score`` /
``overallRipV12Composition`` - it is never written into the ``chaseAccessibility``
block under a name that could be mistaken for the raw public metric.

COPY (locked, reused from the Chase Accessibility research - never invented
here): the approved public question is *"How reachable are this set's most
important cards from a pack?"*; the technical tooltip is *"How accessible the
set's most important collectible value is from one pack."* Neither this module
nor any consumer may describe Chase Accessibility as "the chance of a chase" or
any variant implying a discrete chase-card event.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from backend.desirability.public_rip_contract_v10 import (
    PUBLIC_RIP_CONTRACT_V10_KEY,
    build_public_rip_contract_v10,
)
from backend.desirability.scoring_config import (
    OVERALL_RIP_V12_EFFECTIVE_WEIGHTS,
    OVERALL_RIP_V12_VERSION,
    OVERALL_RIP_V12_WEIGHTS,
)

PUBLIC_RIP_CONTRACT_V11_KEY = "publicRipContractV11"
PUBLIC_RIP_CONTRACT_V11_VERSION = "public_rip_contract_v11"

#: Approved public copy - reused verbatim, not re-authored here. Any consumer
#: rendering a question/tooltip for Chase Accessibility MUST source it from
#: here (or the identical strings already published by the set page), never
#: draft new wording ad hoc.
CHASE_ACCESSIBILITY_PUBLIC_QUESTION = (
    "How reachable are this set's most important cards from a pack?"
)
CHASE_ACCESSIBILITY_TECHNICAL_TOOLTIP = (
    "How accessible the set's most important collectible value is from one pack."
)

#: Forbidden phrasing - defensive constant so a future edit that reintroduces
#: this language fails an obvious grep/test rather than shipping quietly.
_FORBIDDEN_CHASE_PHRASE = "chance of a chase"


def _chase_accessibility_block(target: Mapping[str, Any]) -> Dict[str, Any]:
    """The PUBLIC RAW Chase Accessibility block - never the Overall-scoring A_score."""
    raw = target.get("chaseAccessibility") or {}
    return {
        "value": raw.get("chaseAccessibility"),
        "percent": raw.get("chaseAccessibilityPct"),
        "status": raw.get("chaseAccessibilityStatus"),
        "statusReason": raw.get("chaseAccessibilityStatusReason"),
        "version": raw.get("chaseAccessibilityVersion"),
        # Diagnostic/context ONLY - never a scored Overall RIP input, per the
        # research closure and per compute_overall_rip_v12's own signature.
        "chaseDepth": raw.get("chaseDepth"),
        "mappedHcMass": raw.get("mappedHcMass"),
        "publicQuestion": CHASE_ACCESSIBILITY_PUBLIC_QUESTION,
        "technicalTooltip": CHASE_ACCESSIBILITY_TECHNICAL_TOOLTIP,
    }


def _overall_rip_v12_block(target: Mapping[str, Any]) -> Dict[str, Any]:
    """Project the already-ranked canonical `overallRipV12` object.

    `rank`/`tier`/`cohortSize`/`relativeScore`/`leaderNormalizedScore`/
    `publicTier` are read verbatim off `target["overallRipV12"]` - they were
    written by `_rank_within_cohort` / `_attach_relative_scores` in
    `explore_rip_statistics_service.py` before this contract is built. This
    function never computes or re-derives a rank of its own.
    """
    overall_v12 = dict(target.get("overallRipV12") or {})
    return {
        "score": overall_v12.get("score"),
        "status": overall_v12.get("status"),
        "statusReason": overall_v12.get("statusReason"),
        "rankable": bool(overall_v12.get("rankable")),
        "version": overall_v12.get("version") or OVERALL_RIP_V12_VERSION,
        "components": overall_v12.get("components") or {},
        "missingInputs": overall_v12.get("missingInputs") or [],
        "rank": overall_v12.get("rank"),
        "tier": overall_v12.get("tier"),
        "cohortSize": overall_v12.get("cohortSize"),
        "relativeScore": overall_v12.get("relativeScore"),
        "leaderNormalizedScore": overall_v12.get("leaderNormalizedScore"),
        "publicTier": overall_v12.get("publicTier"),
        # CANONICAL: this is the Overall RIP V12 lineage,
        # `CANONICAL_OVERALL_RIP_VERSION` in scoring_config.py. A non-ready row
        # still reports `canonical: True` with an explicit unavailable status -
        # canonical describes the MODEL, not whether this particular row is
        # currently rankable.
        "canonical": True,
    }


def build_public_rip_contract_v11(target: Mapping[str, Any]) -> Dict[str, Any]:
    """Project a ranked target into the CANONICAL public V11 contract.

    Builds on top of V10 (every V10 key is present, byte-for-byte unchanged)
    and adds the V12/Accessibility blocks described above. `target` is
    expected to already carry `overallRipV12` and `chaseAccessibility` (set by
    the Explore RIP statistics service before contracts are attached), exactly
    as V10 expects `overallRipV10`/`financialRipV4` to already be present.
    """
    contract = dict(build_public_rip_contract_v10(target))
    # V10's own contract is embedded verbatim under its own key, so a consumer
    # of V11 never has to fetch V10 separately to get the canonical shape.
    contract[PUBLIC_RIP_CONTRACT_V10_KEY] = target.get(PUBLIC_RIP_CONTRACT_V10_KEY) or contract
    contract["contractVersion"] = PUBLIC_RIP_CONTRACT_V11_VERSION
    contract["overallRipV12"] = _overall_rip_v12_block(target)
    contract["chaseAccessibility"] = _chase_accessibility_block(target)
    contract["overallRipV12Composition"] = {
        "version": OVERALL_RIP_V12_VERSION,
        "inputs": {
            "financialRip": "financial_rip_v4",
            "chaseAccessibility": "chase_accessibility_v1",
            "collectorAppeal": "collector_appeal_v5",
        },
        "weights": dict(OVERALL_RIP_V12_WEIGHTS),
        "effectiveWeights": dict(OVERALL_RIP_V12_EFFECTIVE_WEIGHTS),
    }
    return contract
