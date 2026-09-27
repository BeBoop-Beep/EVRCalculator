"""EBAY E2.15 -- LANGUAGE-v1 structured-aspect evidence normalizer.

RESEARCH / DEVELOPMENT ARTIFACT ONLY. See
`backend/artifacts/index_fair_value/EBAY_E2_15_WRONG_LANGUAGE_VETO_RESEARCH.md`
for the phase A-L research writeup this module supports.

LANGUAGE-v1 is NOT part of the frozen identity stack (D3-v5 / IMAGE-v2 /
COMBINED-IDENTITY-v2 / CAPTURE-ALLOCATION-v2) and is NOT wired into any
production acceptance path. It exists to evaluate feasibility of a future
LANGUAGE_MISMATCH veto.

Contract (per E2.15 spec):
    LANGUAGE_MATCH        -- explicit evidence the printed card language
                             equals the expected language (English, for
                             this project's cohort).
    LANGUAGE_MISMATCH     -- explicit evidence the printed card language
                             differs from the expected language. Only this
                             state may ever justify a reject.
    LANGUAGE_UNVERIFIED   -- no sufficiently authoritative evidence either
                             way. MUST NOT reject.

Evidence authority order (highest first):
    1. seller-provided structured `localizedAspects` "Language" value, as
       returned by eBay Browse `item/{id}` (getItem).
    2. eBay-inferred aspect equivalent, IF the response distinguishes it
       from seller-provided data (see LIMITATION note below).
    3. local image/OCR language evidence (NOT implemented in this module;
       see the E2.15 report, Phase F -- OCR was researched but not built
       because no free local OCR engine was available in this environment
       and there were no confirmed foreign-language development examples
       to validate against).
    4. UNVERIFIED.

LIMITATION (documented, not silently assumed): the live Browse `item/{id}`
responses captured during E2.15 Phase B exposed only a single
`localizedAspects` array with no `inferredLocalizedAspects` sibling and no
per-aspect provenance/source flag. This module therefore treats every
`localizedAspects` "Language" value as tier-1 (seller-provided) evidence;
it does NOT claim to distinguish seller-provided from eBay-inferred
aspects, because the schema observed does not carry that distinction. This
invalidates part of the Phase C authority-hierarchy assumption and is
called out explicitly in the E2.15 report rather than papered over.

Never inferred from: seller country, item location, marketplace ID, or
listing title text. Those signals are explicitly rejected as language
authority per the task specification.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

LANGUAGE_MATCH = "LANGUAGE_MATCH"
LANGUAGE_MISMATCH = "LANGUAGE_MISMATCH"
LANGUAGE_UNVERIFIED = "LANGUAGE_UNVERIFIED"

VALID_STATES = frozenset({LANGUAGE_MATCH, LANGUAGE_MISMATCH, LANGUAGE_UNVERIFIED})

# Normalization table for the small set of language names eBay's Pokemon
# card aspect taxonomy actually uses. Anything not recognized is treated
# as ambiguous -> UNVERIFIED, never guessed into a mismatch.
_KNOWN_LANGUAGES = {
    "english": "English",
    "japanese": "Japanese",
    "korean": "Korean",
    "german": "German",
    "french": "French",
    "spanish": "Spanish",
    "italian": "Italian",
    "portuguese": "Portuguese",
    "chinese": "Chinese",
    "chinese (simplified)": "Chinese",
    "chinese (traditional)": "Chinese",
    "indonesian": "Indonesian",
    "thai": "Thai",
}


def _find_language_aspect(localized_aspects: Sequence[Mapping[str, Any]] | None) -> str | None:
    if not localized_aspects:
        return None
    for aspect in localized_aspects:
        if not isinstance(aspect, Mapping):
            continue
        name = aspect.get("name")
        if isinstance(name, str) and name.strip().lower() == "language":
            value = aspect.get("value")
            return value if isinstance(value, str) else None
    return None


def normalize_language_value(raw_value: str | None) -> str | None:
    """Map a raw aspect string to a canonical language name, or None if unrecognized."""
    if not raw_value or not isinstance(raw_value, str):
        return None
    return _KNOWN_LANGUAGES.get(raw_value.strip().lower())


def classify_structured_language_evidence(
    item_detail: Mapping[str, Any],
    *,
    expected_language: str = "English",
) -> dict[str, Any]:
    """Classify an eBay Browse `item/{id}` payload into a LANGUAGE-v1 state.

    Parameters
    ----------
    item_detail:
        The parsed JSON body of a Browse `item/{item_id}` (getItem) call, or
        an equivalent mapping carrying a `localizedAspects` list. Only the
        `localizedAspects` field is consulted -- `title`, seller country,
        item location, and marketplace are explicitly NOT authority and are
        never read for this decision.
    expected_language:
        The language the listing is expected to match (this project's
        cohort target is always English).

    Returns
    -------
    dict with keys: state, raw_value, normalized_value, evidence_source,
    reason.
    """
    if not isinstance(item_detail, Mapping):
        return {
            "state": LANGUAGE_UNVERIFIED,
            "raw_value": None,
            "normalized_value": None,
            "evidence_source": "none",
            "reason": "item_detail_missing_or_malformed",
        }

    localized_aspects = item_detail.get("localizedAspects")
    raw_value = _find_language_aspect(localized_aspects)

    if raw_value is None:
        return {
            "state": LANGUAGE_UNVERIFIED,
            "raw_value": None,
            "normalized_value": None,
            "evidence_source": "none",
            "reason": "no_language_aspect_present",
        }

    normalized = normalize_language_value(raw_value)
    if normalized is None:
        return {
            "state": LANGUAGE_UNVERIFIED,
            "raw_value": raw_value,
            "normalized_value": None,
            "evidence_source": "structured_aspect_seller_provided",
            "reason": "language_aspect_value_unrecognized",
        }

    expected_norm = _KNOWN_LANGUAGES.get(expected_language.strip().lower(), expected_language)
    if normalized == expected_norm:
        state = LANGUAGE_MATCH
        reason = "structured_aspect_matches_expected_language"
    else:
        state = LANGUAGE_MISMATCH
        reason = "structured_aspect_contradicts_expected_language"

    return {
        "state": state,
        "raw_value": raw_value,
        "normalized_value": normalized,
        "evidence_source": "structured_aspect_seller_provided",
        "reason": reason,
    }


def apply_combined_identity_v3(
    combined_v2_eligible: bool,
    combined_v2_reason: str,
    language_state: str,
) -> dict[str, Any]:
    """COMBINED-IDENTITY-v3 (design/spec only -- see E2.15 report Phase J).

    v3 = v2 semantics, plus: if LANGUAGE-v1 == LANGUAGE_MISMATCH, reject
    with REJECT_LANGUAGE_CONTRADICTION regardless of the v2 decision, applied
    BEFORE tier A/B eligibility. LANGUAGE_UNVERIFIED (and LANGUAGE_MATCH)
    must reproduce v2 behavior exactly -- no other change.

    This function is NOT wired into any production or certification path.
    It is provided so the E2.15 post-hoc diagnostics (Phase K) can be run
    mechanically and reproducibly against existing frozen prediction
    artifacts, read-only.
    """
    if language_state not in VALID_STATES:
        raise ValueError(f"unknown language_state: {language_state!r}")

    if language_state == LANGUAGE_MISMATCH:
        return {
            "eligible": False,
            "reason": "REJECT_LANGUAGE_CONTRADICTION",
            "language_state": language_state,
        }

    # LANGUAGE_MATCH and LANGUAGE_UNVERIFIED both preserve v2 behavior
    # exactly -- v3 never grants eligibility v2 didn't, it can only ever
    # remove it, and it only removes it on MISMATCH.
    return {
        "eligible": combined_v2_eligible,
        "reason": combined_v2_reason,
        "language_state": language_state,
    }
