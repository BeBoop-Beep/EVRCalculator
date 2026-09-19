"""COMBINED-IDENTITY-v2 (EBAY_E2_9): image-veto / tiered-identity policy.

This module is POLICY ONLY. It contains no text-matching or image-
verification logic of its own and reuses D3-v5 and IMAGE-v2 exactly as
frozen -- neither is imported for its internals, only called (or, for
IMAGE-v2, consumed via its already-emitted `image_identity_state` values).

Motivation (EBAY_E2_8 -> EBAY_E2_9): COMBINED-IDENTITY-v1 required IMAGE-v2
MATCH for every HIGH_CONFIDENCE-text listing to reach its strongest state.
Measured against both consumed historical cohorts (V4 n=420, V5 n=417),
IMAGE-v2 returned UNVERIFIED (never MISMATCH) for the overwhelming majority
of listings v1 discarded for coverage reasons: 88/70 cards (V4) and 99/70
cards (V5) genuine human-YES listings. Critically, the number of
HIGH_CONFIDENCE-text + UNVERIFIED-image + human-NO listings measured across
both cohorts is exactly ZERO -- see
EBAY_E2_9_IMAGE_VETO_TIERED_IDENTITY_POLICY.md Section 3 for the full
accounting. This is the empirical basis for treating IMAGE-v2 as a
NEGATIVE SAFETY VETO (a MISMATCH still hard-rejects) rather than a
mandatory POSITIVE CONFIRMATION gate for HIGH_CONFIDENCE text.

COMBINED-IDENTITY-v2 therefore separates HIGH_CONFIDENCE-text listings into
two named, differently-trusted tiers instead of one binary accept/hold:

  TIER_A_IMAGE_VERIFIED               -- HIGH_CONFIDENCE text, no
                                          contradiction, IMAGE-v2 MATCH.
  TIER_B_TEXT_VERIFIED_IMAGE_UNVERIFIED -- HIGH_CONFIDENCE text, no
                                          contradiction, IMAGE-v2 UNVERIFIED
                                          (plain, target-not-in-gallery, or
                                          visually-indistinguishable).

Tier B is NEVER labeled or treated as image-verified. It is a distinct,
lower-trust identity tier, reported and gated separately from Tier A in
every metric this module or its callers compute. E3 (not this module)
decides whether/how Tier A and Tier B receive different financial
treatment; this module establishes identity eligibility only.

IMAGE-v2 MISMATCH remains an unconditional hard veto in both tiers -- a
visual MATCH can promote HIGH_CONFIDENCE text to Tier A, but IMAGE-v2 is
never permitted to relabel its own UNVERIFIED result as MATCH, and this
policy never does either. A text contradiction (wrong collector number,
wrong set, lot/bundle, graded, sealed/non-card, altered/autograph) is
checked first, unconditionally, exactly as in v1, and is never overridden
by any image signal.

Candidate "selective UNVERIFIED salvage using IMAGE-v2 diagnostics" (target
rank / margin / crop state) was investigated conceptually for EBAY_E2_9 but
NOT implemented here: the consumed V4/V5 cohorts do not carry a persisted
per-row IMAGE-v2 diagnostic (target_rank, target_similarity, margin) join
-- only the aggregate cross-tab in
ebay_combined_identity_v1_historical_post_hoc_diagnostic.json survives from
that run. Building a fresh per-row diagnostic join was judged out of scope
for this pass (see EBAY_E2_9 report Section 12); Tier B is therefore a
single, flat, diagnostics-blind tier in this version, not a graded one.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

from backend.scripts.ebay_combined_identity_policy_v1 import (
    CONTRADICTION_VALUES,
    IMAGE_MATCH,
    IMAGE_MISMATCH,
    TEXT_CONTRADICTION_FIELDS,
    has_text_contradiction,
)

METHOD_VERSION = "ebay_combined_identity_policy_v2"

# --------------------------------------------------------------------------
# Combined-state vocabulary. Tier B's name spells out its own limitation --
# it must never be confused with, or silently treated as, image-verified.
# --------------------------------------------------------------------------

TIER_A_IMAGE_VERIFIED = "TIER_A_IMAGE_VERIFIED"
TIER_B_TEXT_VERIFIED_IMAGE_UNVERIFIED = "TIER_B_TEXT_VERIFIED_IMAGE_UNVERIFIED"
REJECTED_IMAGE_CONTRADICTION = "REJECTED_IMAGE_CONTRADICTION"
REJECTED_TEXT = "REJECTED_TEXT"
TEXT_AMBIGUOUS_NOT_PROMOTED = "TEXT_AMBIGUOUS_NOT_PROMOTED"

ELIGIBLE_STATES = (TIER_A_IMAGE_VERIFIED, TIER_B_TEXT_VERIFIED_IMAGE_UNVERIFIED)


@dataclass
class CombinedResultV2:
    combined_state: str
    method_version: str = METHOD_VERSION
    text_state: str = ""
    image_state: str = ""
    text_contradiction_present: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def is_eligible(self) -> bool:
        return self.combined_state in ELIGIBLE_STATES

    @property
    def is_image_verified(self) -> bool:
        """True only for Tier A. Tier B must never report True here --
        this is the single property every caller and test must use to
        confirm Tier B is never treated as image-verified."""
        return self.combined_state == TIER_A_IMAGE_VERIFIED


def combine(text_state: str, image_state: str, text_row_fields: Optional[Mapping[str, str]] = None) -> CombinedResultV2:
    """The fixed, hand-specified v2 decision table. Consumes D3-v5's
    `identity_state` and IMAGE-v2's `image_identity_state` exactly as
    emitted -- never redefines, retunes, or reinterprets either.
    """
    contradiction = has_text_contradiction(text_row_fields or {})

    if contradiction:
        return CombinedResultV2(
            combined_state=REJECTED_TEXT, text_state=text_state, image_state=image_state,
            text_contradiction_present=True, reason="explicit_text_contradiction_never_overridden_by_image",
        )

    if text_state == "REJECTED":
        return CombinedResultV2(
            combined_state=REJECTED_TEXT, text_state=text_state, image_state=image_state,
            reason="text_rejected",
        )

    if text_state != "HIGH_CONFIDENCE":
        return CombinedResultV2(
            combined_state=TEXT_AMBIGUOUS_NOT_PROMOTED, text_state=text_state, image_state=image_state,
            reason="image_similarity_alone_never_promotes_weak_text_identity",
        )

    # text_state == HIGH_CONFIDENCE from here on -- image acts as a
    # negative safety veto (MISMATCH still rejects) rather than a
    # mandatory positive gate (UNVERIFIED is now an eligible, named,
    # explicitly-lower-trust tier instead of a discard).
    if image_state == IMAGE_MATCH:
        return CombinedResultV2(
            combined_state=TIER_A_IMAGE_VERIFIED, text_state=text_state, image_state=image_state,
            reason="text_high_confidence_and_image_match",
        )
    if image_state == IMAGE_MISMATCH:
        return CombinedResultV2(
            combined_state=REJECTED_IMAGE_CONTRADICTION, text_state=text_state, image_state=image_state,
            reason="text_high_confidence_but_image_mismatch_hard_veto",
        )
    # Every UNVERIFIED_* variant (plain, target-not-in-gallery, or
    # visually-indistinguishable) lands in Tier B -- eligible, but never
    # called image-verified.
    return CombinedResultV2(
        combined_state=TIER_B_TEXT_VERIFIED_IMAGE_UNVERIFIED, text_state=text_state, image_state=image_state,
        reason="text_high_confidence_image_unresolved_tier_b_not_image_verified",
    )


# --------------------------------------------------------------------------
# Freeze fingerprinting. Recorded once, at freeze time, by
# freeze_ebay_combined_identity_v2.py; this module only knows how to
# compute the pieces, not when to freeze.
# --------------------------------------------------------------------------


def policy_source_hash() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def policy_fingerprint(text_matcher_fingerprint: str, image_verifier_fingerprint: str) -> str:
    material = {
        "method_version": METHOD_VERSION,
        "policy_source_sha256": policy_source_hash(),
        "text_matcher_fingerprint": text_matcher_fingerprint,
        "image_verifier_fingerprint": image_verifier_fingerprint,
        "contradiction_fields": list(TEXT_CONTRADICTION_FIELDS),
        "contradiction_values": sorted(CONTRADICTION_VALUES),
        "eligible_states": list(ELIGIBLE_STATES),
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
