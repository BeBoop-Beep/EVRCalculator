"""COMBINED-IDENTITY-v3 (EBAY_E2_15): COMBINED-v2 + LANGUAGE-v1 veto.

Per the EBAY_E2_15 task spec Phase J: COMBINED-IDENTITY-v3 = COMBINED-v2
plus one additional check --

    if LANGUAGE-v1 == LANGUAGE_MISMATCH: REJECT_LANGUAGE_CONTRADICTION

This veto is evaluated BEFORE Tier A/Tier B eligibility (i.e. before
COMBINED-v2's own text/image logic ever runs), exactly as specified.
LANGUAGE_UNVERIFIED (and LANGUAGE_MATCH) fall straight through to
COMBINED-v2's existing `combine()` unchanged -- this module does not
alter, re-tune, or reinterpret ANY COMBINED-v2 behavior. It only adds
one new rejecting branch ahead of it.

This module is FUTURE / RESEARCH policy per EBAY_E2_15 -- it carries no
production authority and is not wired into any live pricing or
certification pipeline. See
`backend/artifacts/index_fair_value/EBAY_E2_15_WRONG_LANGUAGE_VETO_RESEARCH.md`.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

from backend.scripts.ebay_combined_identity_policy_v2 import (
    CombinedResultV2,
    combine as combine_v2,
)
from backend.scripts.ebay_language_policy_v1 import (
    LANGUAGE_MISMATCH,
    LanguageResult,
)

METHOD_VERSION = "ebay_combined_identity_policy_v3"

REJECTED_LANGUAGE_CONTRADICTION = "REJECTED_LANGUAGE_CONTRADICTION"


@dataclass
class CombinedResultV3:
    combined_state: str
    method_version: str = METHOD_VERSION
    text_state: str = ""
    image_state: str = ""
    language_state: str = ""
    text_contradiction_present: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def is_eligible(self) -> bool:
        # ELIGIBLE_STATES is identical to v2's -- the language veto only
        # ever subtracts eligibility (by rejecting before v2 runs), it
        # never adds a new eligible state.
        from backend.scripts.ebay_combined_identity_policy_v2 import ELIGIBLE_STATES

        return self.combined_state in ELIGIBLE_STATES

    @property
    def is_image_verified(self) -> bool:
        from backend.scripts.ebay_combined_identity_policy_v2 import TIER_A_IMAGE_VERIFIED

        return self.combined_state == TIER_A_IMAGE_VERIFIED


def combine(
    text_state: str,
    image_state: str,
    language_result: LanguageResult,
    text_row_fields: Optional[Mapping[str, str]] = None,
) -> CombinedResultV3:
    """LANGUAGE-v1 veto gate, evaluated first. Only LANGUAGE_MISMATCH
    rejects; LANGUAGE_UNVERIFIED and LANGUAGE_MATCH both fall through
    unchanged into COMBINED-v2, preserving v2 behavior exactly for every
    row where LANGUAGE-v1 does not have a confident mismatch."""
    if language_result.language_state == LANGUAGE_MISMATCH:
        return CombinedResultV3(
            combined_state=REJECTED_LANGUAGE_CONTRADICTION,
            text_state=text_state,
            image_state=image_state,
            language_state=language_result.language_state,
            reason="language_v1_explicit_mismatch_hard_veto_before_tier_eligibility",
        )

    v2_result: CombinedResultV2 = combine_v2(text_state, image_state, text_row_fields)
    return CombinedResultV3(
        combined_state=v2_result.combined_state,
        text_state=v2_result.text_state,
        image_state=v2_result.image_state,
        language_state=language_result.language_state,
        text_contradiction_present=v2_result.text_contradiction_present,
        reason=v2_result.reason,
    )


def policy_source_hash() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def policy_fingerprint(
    text_matcher_fingerprint: str,
    image_verifier_fingerprint: str,
    language_policy_fingerprint: str,
) -> str:
    from backend.scripts.ebay_combined_identity_policy_v2 import (
        ELIGIBLE_STATES,
        policy_fingerprint as v2_fingerprint,
    )

    material = {
        "method_version": METHOD_VERSION,
        "policy_source_sha256": policy_source_hash(),
        "combined_v2_fingerprint": v2_fingerprint(text_matcher_fingerprint, image_verifier_fingerprint),
        "language_policy_fingerprint": language_policy_fingerprint,
        "eligible_states": list(ELIGIBLE_STATES),
        "veto_state": REJECTED_LANGUAGE_CONTRADICTION,
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
