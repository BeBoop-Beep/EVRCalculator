"""LANGUAGE-v1 (EBAY_E2_15): structured-metadata language-contradiction veto.

RESEARCH CONTEXT (EBAY_E2_15): E2.14's fresh-blind certification
(`ebay_e2_14_fresh_blind_certification.json`) is CONSUMED and
NOT CERTIFIED. Its one catastrophic false accept, row `E13-0127`
(listing `v1|407215142815|0`), is a WRONG_LANGUAGE failure: the seller's
title is plain English ("PIKACHU EX #277 POKEMON ASCENDED HEROES -
MINT/NEAR MINT") with no text contradiction D3-v5 can detect, and the
photographed card is visually near-identical in embedding space to its
English counterpart, so IMAGE-v2 correctly (per its own contract)
returned UNVERIFIED rather than a false MISMATCH. Neither existing
identity layer is designed to catch a language mismatch invisible to
both text-contradiction regex and visual-similarity embedding distance.

LANGUAGE-v1 is a NEW, SEPARATE evidence source -- it is not a change to
D3-v5, IMAGE-v2, or CAPTURE-ALLOCATION-v2, none of which this module
imports for policy logic (D3-v5's own contradiction fields are reused
read-only, exactly as COMBINED-v2 does).

EVIDENCE BASIS (bounded, development-only, NOT E2.14 labels):
A bounded live eBay Browse `getItem` study (~41 calls total, well inside
existing request-budget controls; see
`EBAY_E2_15_WRONG_LANGUAGE_VETO_RESEARCH.md` Sections 3-5) found:

  - `item_summary/search` (the endpoint the existing evidence collector
    already calls) NEVER returns `localizedAspects` -- confirmed by
    scanning all 42,319 rows across all 7 existing raw evidence capture
    files: `have_localizedAspects_count == 0`. Structured language
    metadata is available ONLY via the per-item `getItem` endpoint,
    which the existing collector does not call today.
  - Of a random bounded sample of 25 historical listing ids drawn from
    existing raw evidence (development population, not E2.14
    certification labels), 20/25 (80%) carried an explicit `Language`
    aspect; all 20 explicit values in that random sample were "English"
    (the sampled population is overwhelmingly English-market listings).
  - A second, targeted bounded sample (12 listings from live searches
    for Japanese / French / German cards) showed explicit `Language`
    aspect coverage is uneven by language: Japanese 4/4 explicit,
    French 4/4 explicit, German 0/4 explicit (titles said "German" but
    no structured aspect was present for any of the 4 German-search
    results). This means real-world coverage of the MISMATCH-relevant
    (non-English) case is not uniform, and is a known, disclosed
    limitation -- see report Section 4.
  - `getItem`'s `localizedAspects` response carries no field that
    distinguishes a seller-typed aspect from an eBay-catalog-inferred
    one (no `aspectValueType`, `source`, or equivalent key was observed
    on any inspected item; see report Section 5). PHASE C's candidate
    3-tier hierarchy (seller-provided > eBay-inferred > OCR > unverified)
    is therefore NOT separable with the fields eBay actually returns in
    this endpoint version -- this module treats "explicit `Language`
    aspect present" as ONE combined structured-authority tier (tier
    1+2 merged), which is a documented, honest limitation, not an
    invented distinction.
  - Local OCR (Phase F) was NOT implemented: structured-aspect coverage
    was judged high enough, and -- critically -- because
    LANGUAGE_UNVERIFIED never rejects, incomplete coverage degrades
    only RECALL of the veto, never its safety. OCR remains a documented
    future option if broader coverage is later required (see report
    Section 6), not a MUST-HAVE for a safe, conservative first version.

CONTRACT (frozen, Phase I/E):
  - LANGUAGE-v1 outputs exactly one of LANGUAGE_MATCH, LANGUAGE_MISMATCH,
    LANGUAGE_UNVERIFIED. Only LANGUAGE_MISMATCH may ever reject.
  - Evidence source: eBay Browse `getItem` `localizedAspects` entry named
    "Language" (case-insensitive name match), normalized value compared
    against the single expected target language (this deployment: the
    "English" printing is Tier A/B eligible identity's implicit
    assumption throughout D3-v5/COMBINED-v2 -- LANGUAGE-v1 makes that
    assumption explicit and checkable for the first time).
  - Missing aspect, empty aspect list, unmapped/unknown value string,
    or a `getItem` call failure => LANGUAGE_UNVERIFIED. Never inferred
    from seller country, `itemLocation`, `marketplace`, or any word
    appearing in the listing title.
  - An explicit, normalized non-English `Language` aspect value =>
    LANGUAGE_MISMATCH (when the expected language is English).
  - An explicit, normalized English `Language` aspect value =>
    LANGUAGE_MATCH.
  - Title text is NEVER used as language evidence in this version (Phase
    G/H finding: a title containing a foreign word, e.g. "French" as a
    Pokemon name translation like "Dracaufeu", does not reliably imply
    card language -- see report Section 4 for a real observed case,
    item `v1|158291222488|0`, where the title says "French" but the
    structured `Language` aspect says "English").
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

METHOD_VERSION = "ebay_language_policy_v1"

LANGUAGE_MATCH = "LANGUAGE_MATCH"
LANGUAGE_MISMATCH = "LANGUAGE_MISMATCH"
LANGUAGE_UNVERIFIED = "LANGUAGE_UNVERIFIED"

VALID_STATES = (LANGUAGE_MATCH, LANGUAGE_MISMATCH, LANGUAGE_UNVERIFIED)

# Normalization table: eBay's observed `Language` aspect values map onto a
# small closed vocabulary. Anything not in this table is UNVERIFIED, never
# guessed. Keys are lowercased for case-insensitive matching.
_LANGUAGE_NORMALIZATION: dict[str, str] = {
    "english": "ENGLISH",
    "en": "ENGLISH",
    "eng": "ENGLISH",
    "japanese": "JAPANESE",
    "jp": "JAPANESE",
    "jpn": "JAPANESE",
    "korean": "KOREAN",
    "kr": "KOREAN",
    "german": "GERMAN",
    "de": "GERMAN",
    "french": "FRENCH",
    "fr": "FRENCH",
    "spanish": "SPANISH",
    "es": "SPANISH",
    "italian": "ITALIAN",
    "it": "ITALIAN",
    "portuguese": "PORTUGUESE",
    "pt": "PORTUGUESE",
    "chinese": "CHINESE",
    "chinese (simplified)": "CHINESE",
    "chinese (traditional)": "CHINESE",
    "dutch": "DUTCH",
    "polish": "POLISH",
    "indonesian": "INDONESIAN",
    "thai": "THAI",
}

DEFAULT_EXPECTED_LANGUAGE = "ENGLISH"


@dataclass
class LanguageResult:
    language_state: str
    method_version: str = METHOD_VERSION
    expected_language: str = DEFAULT_EXPECTED_LANGUAGE
    observed_language: Optional[str] = None
    raw_aspect_value: Optional[str] = None
    evidence_source: str = ""
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def may_reject(self) -> bool:
        """Only LANGUAGE_MISMATCH may ever cause a downstream reject --
        this is the single property every caller/test uses to confirm
        LANGUAGE_UNVERIFIED never rejects."""
        return self.language_state == LANGUAGE_MISMATCH


def normalize_language_value(raw_value: Optional[str]) -> Optional[str]:
    """Maps a raw aspect string onto the closed vocabulary, or None if
    unrecognized. Never raises; never guesses from substrings."""
    if not raw_value:
        return None
    key = str(raw_value).strip().lower()
    return _LANGUAGE_NORMALIZATION.get(key)


def extract_language_aspect(localized_aspects: Optional[Iterable[Mapping[str, Any]]]) -> Optional[str]:
    """Finds the first aspect literally named "Language" (case-insensitive)
    in a `getItem` `localizedAspects` list and returns its raw value, or
    None if absent. This is the ONLY function that reads provider
    metadata for language evidence in LANGUAGE-v1 -- title text, seller
    country, item location, and marketplace are never consulted here or
    anywhere else in this module."""
    if not localized_aspects:
        return None
    for aspect in localized_aspects:
        name = str(aspect.get("name") or "").strip().lower()
        if name == "language":
            value = aspect.get("value")
            if value:
                return str(value)
    return None


def evaluate_structured_aspect(
    localized_aspects: Optional[Iterable[Mapping[str, Any]]],
    expected_language: str = DEFAULT_EXPECTED_LANGUAGE,
) -> LanguageResult:
    """PHASE E: structured-aspect guard. The sole production entry point
    for LANGUAGE-v1 in this frozen version (no OCR fallback is wired in
    -- see module docstring)."""
    raw_value = extract_language_aspect(localized_aspects)
    if raw_value is None:
        return LanguageResult(
            language_state=LANGUAGE_UNVERIFIED,
            expected_language=expected_language,
            evidence_source="structured_aspect_absent",
            reason="no_explicit_language_aspect_in_getitem_localizedaspects",
        )

    normalized = normalize_language_value(raw_value)
    if normalized is None:
        return LanguageResult(
            language_state=LANGUAGE_UNVERIFIED,
            expected_language=expected_language,
            raw_aspect_value=raw_value,
            evidence_source="structured_aspect_unrecognized_value",
            reason="language_aspect_value_not_in_closed_vocabulary",
        )

    if normalized == expected_language.upper():
        return LanguageResult(
            language_state=LANGUAGE_MATCH,
            expected_language=expected_language,
            observed_language=normalized,
            raw_aspect_value=raw_value,
            evidence_source="structured_aspect_seller_or_catalog",
            reason="explicit_language_aspect_matches_expected",
        )

    return LanguageResult(
        language_state=LANGUAGE_MISMATCH,
        expected_language=expected_language,
        observed_language=normalized,
        raw_aspect_value=raw_value,
        evidence_source="structured_aspect_seller_or_catalog",
        reason="explicit_language_aspect_contradicts_expected",
    )


def evaluate_getitem_call_failure(reason: str = "getitem_call_failed") -> LanguageResult:
    """A `getItem` network/HTTP failure is always UNVERIFIED, never
    MISMATCH -- the veto must never reject because evidence collection
    itself failed (Phase F/H hard rule, applied identically to the
    structured-aspect call path as it would to any future OCR path)."""
    return LanguageResult(
        language_state=LANGUAGE_UNVERIFIED,
        evidence_source="getitem_call_failed",
        reason=reason,
    )


# --------------------------------------------------------------------------
# Explicitly-forbidden non-evidence. These functions exist ONLY so tests
# can assert LANGUAGE-v1 never consults them for a language verdict --
# they are not used by evaluate_structured_aspect above.
# --------------------------------------------------------------------------

FORBIDDEN_EVIDENCE_FIELDS = ("seller_country", "item_location", "marketplace", "title")


def policy_source_hash() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def policy_fingerprint(development_corpus_fingerprint: str, source_fingerprint: Optional[str] = None) -> str:
    material = {
        "method_version": METHOD_VERSION,
        "policy_source_sha256": policy_source_hash(),
        "valid_states": list(VALID_STATES),
        "default_expected_language": DEFAULT_EXPECTED_LANGUAGE,
        "normalization_keys": sorted(_LANGUAGE_NORMALIZATION.keys()),
        "development_corpus_fingerprint": development_corpus_fingerprint,
        "source_fingerprint": source_fingerprint or policy_source_hash(),
        "forbidden_evidence_fields": list(FORBIDDEN_EVIDENCE_FIELDS),
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
