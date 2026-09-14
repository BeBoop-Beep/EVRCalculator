"""COMBINED-IDENTITY-v1 (EBAY_E2_8): a fixed, non-tunable decision table
combining the frozen D3-v5 text matcher's `identity_state` with the frozen
IMAGE-v2 retrieval verifier's `image_identity_state`.

This module contains NO text-matching or image-verification logic of its
own. It consumes only the already-frozen outputs of:

  - ebay_d3_matcher_v5.classify_listing()          (TEXT authority, frozen)
  - ebay_image_retrieval_verifier.verify_by_retrieval()  (IMAGE-v2, frozen)

and combines them via a small, explicit, hand-specified decision table --
never a data-derived/tuned rule. Neither D3-v5 nor IMAGE-v2 is imported for
its logic and re-implemented here; both are called as-is.

IMAGE-v2 is a SAFETY GUARD, not a promoter: this phase's policy never lets
image similarity alone promote weak/ambiguous/rejected textual identity to
a strongest state, and never lets a visual MATCH override an explicit
textual contradiction (wrong collector number, wrong set, lot/bundle,
graded, sealed/non-card, altered/autograph).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional

METHOD_VERSION = "ebay_combined_identity_policy_v1"

# --------------------------------------------------------------------------
# Image-state vocabulary (extends IMAGE-v2's own MATCH/MISMATCH/UNVERIFIED
# with the two gallery-coverage/duplicate-art states this policy layer is
# responsible for -- IMAGE-v2 itself has no notion of "is the target even
# in my gallery" or "are these two canonical entries visually identical";
# that bookkeeping belongs here, one layer up.)
# --------------------------------------------------------------------------

IMAGE_MATCH = "MATCH"
IMAGE_MISMATCH = "MISMATCH"
IMAGE_UNVERIFIED = "UNVERIFIED"
IMAGE_UNVERIFIED_TARGET_NOT_IN_GALLERY = "UNVERIFIED_TARGET_NOT_IN_GALLERY"
IMAGE_UNVERIFIED_VISUALLY_INDISTINGUISHABLE = "UNVERIFIED_VISUALLY_INDISTINGUISHABLE"

# Text-level contradictions that must NEVER be overridden by a visual MATCH.
# These mirror certify_ebay_d3_v5_fresh_blind._human_error_class()'s
# taxonomy field names -- this module does not invent a new taxonomy.
TEXT_CONTRADICTION_FIELDS = (
    "collector_number_consistency", "set_consistency", "single_card_or_lot",
    "raw_or_graded", "card_or_sealed_nonshcard",
)
CONTRADICTION_VALUES = {"inconsistent", "lot", "lot_or_bundle", "graded", "sealed", "accessory", "non-card", "noncard", "sealed_or_non_card"}


def has_text_contradiction(row_fields: Mapping[str, str]) -> bool:
    for field in TEXT_CONTRADICTION_FIELDS:
        value = str(row_fields.get(field, "")).strip().lower()
        if value in CONTRADICTION_VALUES:
            return True
    return False


def resolve_image_state(
    gallery, target_card_id: str, listing_image_url: str,
    indistinguishable_groups: Optional[list[set[str]]] = None, cache_dir=None,
) -> dict[str, Any]:
    """Wraps IMAGE-v2's verify_by_retrieval() with the two gallery-coverage
    checks this policy layer owns. Never calls verify_by_retrieval() for a
    target IMAGE-v2's gallery cannot represent at all.
    """
    from backend.scripts.ebay_image_retrieval_verifier import verify_by_retrieval

    gallery_ids = {e.canonical_card_id for e in gallery.entries}
    if target_card_id not in gallery_ids:
        return {
            "image_identity_state": IMAGE_UNVERIFIED_TARGET_NOT_IN_GALLERY,
            "verification_reason": "target_canonical_identity_absent_from_frozen_gallery",
        }

    for group in (indistinguishable_groups or []):
        if target_card_id in group and len(group) > 1:
            return {
                "image_identity_state": IMAGE_UNVERIFIED_VISUALLY_INDISTINGUISHABLE,
                "verification_reason": "target_shares_canonical_artwork_with_other_identities",
                "indistinguishable_group": sorted(group),
            }

    result = verify_by_retrieval(gallery, target_card_id, listing_image_url, cache_dir=cache_dir)
    return result.to_dict()


# --------------------------------------------------------------------------
# The fixed combination table
# --------------------------------------------------------------------------

VERIFIED_MATCH = "VERIFIED_MATCH"
REJECTED_IMAGE_CONTRADICTION = "REJECTED_IMAGE_CONTRADICTION"
TEXT_MATCH_IMAGE_UNVERIFIED = "TEXT_MATCH_IMAGE_UNVERIFIED"
REJECTED_TEXT = "REJECTED_TEXT"
TEXT_AMBIGUOUS_NOT_PROMOTED = "TEXT_AMBIGUOUS_NOT_PROMOTED"


@dataclass
class CombinedResult:
    combined_state: str
    method_version: str = METHOD_VERSION
    text_state: str = ""
    image_state: str = ""
    text_contradiction_present: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def combine(text_state: str, image_state: str, text_row_fields: Optional[Mapping[str, str]] = None) -> CombinedResult:
    """The fixed, hand-specified decision table. `text_state` is D3-v5's
    own `identity_state` vocabulary (HIGH_CONFIDENCE / MEDIUM_CONFIDENCE /
    AMBIGUOUS / REJECTED). `image_state` is one of the five IMAGE_* values
    above. Never tuned against data -- every branch below is exactly what
    the E2.8 task specification wrote.
    """
    contradiction = has_text_contradiction(text_row_fields or {})

    # A known textual contradiction is never erased by a visual MATCH --
    # checked first, unconditionally, regardless of text_state.
    if contradiction:
        return CombinedResult(
            combined_state=REJECTED_TEXT, text_state=text_state, image_state=image_state,
            text_contradiction_present=True, reason="explicit_text_contradiction_never_overridden_by_image",
        )

    if text_state == "REJECTED":
        return CombinedResult(
            combined_state=REJECTED_TEXT, text_state=text_state, image_state=image_state,
            reason="text_rejected",
        )

    if text_state != "HIGH_CONFIDENCE":
        # MEDIUM_CONFIDENCE / AMBIGUOUS: image evidence is never used to
        # promote weak textual identity to a strongest state in this phase.
        return CombinedResult(
            combined_state=TEXT_AMBIGUOUS_NOT_PROMOTED, text_state=text_state, image_state=image_state,
            reason="image_similarity_alone_never_promotes_weak_text_identity",
        )

    # text_state == HIGH_CONFIDENCE from here on.
    if image_state == IMAGE_MATCH:
        return CombinedResult(
            combined_state=VERIFIED_MATCH, text_state=text_state, image_state=image_state,
            reason="text_high_confidence_and_image_match",
        )
    if image_state == IMAGE_MISMATCH:
        return CombinedResult(
            combined_state=REJECTED_IMAGE_CONTRADICTION, text_state=text_state, image_state=image_state,
            reason="text_high_confidence_but_image_mismatch",
        )
    # every UNVERIFIED_* variant (plain, target-not-in-gallery, or
    # visually-indistinguishable) lands here -- never promoted, never rejected.
    return CombinedResult(
        combined_state=TEXT_MATCH_IMAGE_UNVERIFIED, text_state=text_state, image_state=image_state,
        reason="text_high_confidence_but_image_unresolved",
    )
