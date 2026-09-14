"""D3 v5: a bounded, downgrade-only safety revision of v4.

Triggered by the two catastrophic false accepts found in D3-v4's genuine
fresh single-reviewer blind certification (EBAY_D3_V4_NOT_CERTIFIED):

D4-0375 "Roaring Moon ex - 162/131 - ... Special Illustration NM"
    human class: WRONG_CARD_NUMBER, matcher: HIGH_CONFIDENCE (false accept)
D4-0415 "Team Rocket's Nidoking ex 233/182 Sv10 Destined Rivals SIR Holo Full Art Auto"
    human class: OTHER_MISMATCH, matcher: HIGH_CONFIDENCE (false accept)

ROOT CAUSE, D4-0375 (see EBAY_E2_3 report for full evidence):
    The target's own recorded collector number is "162" and the listing's
    title shows the exact, standard "162/131" fraction for this card --
    verified against SIX independent DEVELOPMENT-partition listings for the
    SAME target card, two of which show the identical "162/131" numerator/
    denominator and are human-gold-labeled EXACT_TARGET_MATCH. There is no
    generalizable TEXT signal distinguishing this false accept from those
    true accepts: "162/131" is the normal, correct numbering for this card,
    both in the blind row and in development. This is therefore an
    IMAGE-ONLY IDENTITY RISK -- structurally undetectable from title/
    condition/aspect text alone, exactly analogous to the repository's
    already-documented IMAGE_ONLY_GRADED_RISK precedent (D2-0310 in the v3
    development study). No text rule is added for this failure; inventing
    one would be a title-specific special case with no development support,
    which this task explicitly forbids. It is documented as a residual,
    irreducible limitation instead.

ROOT CAUSE, D4-0415 (Guard 4 below):
    The row's structural fields (single_card_or_lot, raw_or_graded,
    card_or_sealed_nonshcard) are all at their ordinary single/raw/card
    defaults and the human's own NO-reason selection produced no taxonomy
    override (OTHER_MISMATCH is exactly what the review UI's "OTHER" catch-
    all reason yields) -- meaning name/number/set/variant all checked out,
    and the disqualifying evidence was something the existing taxonomy had
    no field for. The listing title's own text is the only evidence
    available and ends in the bare word "Auto" -- the standard TCG-market
    abbreviation for an on-card or sticker AUTOGRAPH. An autographed copy is
    a materially different, altered instrument from a standard raw card
    (closer in kind to the existing GRADED-vs-RAW distinction than to any
    identity mismatch) and was never in the existing product-object
    ontology's scope at all. DEVELOPMENT contains zero examples of
    auto/autograph/signed terminology (searched and confirmed empty), so
    this guard is new ontology, not a tuned fit to any example -- it is
    built the same way v4's sealed/accessory ontology extension was built:
    add the missing, clearly-scoped general term to the existing mechanism.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

from backend.scripts import ebay_d3_matcher_v4 as v4

MATCHER_VERSION = "index_fair_value_ebay_d3_v5"
QUERY_CONTRACT_VERSION = v4.QUERY_CONTRACT_VERSION
ALTERED_OR_AUTOGRAPH_GUARD_VERSION = "ebay_d3_v5_altered_autograph_guard_v1"

# Guard 4: an autographed/signed/inscribed copy is not a standard raw comp.
# Word-boundaried to avoid "auto" as a substring of an unrelated word.
_ALTERED_OR_AUTOGRAPH_RE = re.compile(
    r"\bauto(?:s|graph(?:ed|s)?)?\b|\bsigned\b|\bsignature\b|\bartist[- ]signed\b|\binscri(?:bed|ption)\b",
    re.I,
)
# Legitimate false-positive guard: "auto" as part of a clearly unrelated
# compound term some listings do use (none identified in development, but
# the guard exists so a future genuine false positive has a documented,
# narrow escape hatch rather than a widened/loosened pattern).
_ALTERED_FALSE_POSITIVE_RE = re.compile(r"\bauto\s*(?:draft|complete|checklist)\b", re.I)


def altered_or_autograph_guard(listing: Mapping[str, Any]) -> dict[str, Any]:
    title = str(listing.get("title") or "")
    hit = bool(_ALTERED_OR_AUTOGRAPH_RE.search(title)) and not _ALTERED_FALSE_POSITIVE_RE.search(title)
    return {"altered_or_autograph_detected": hit, "guard_version": ALTERED_OR_AUTOGRAPH_GUARD_VERSION}


def classify_listing(target: Mapping[str, Any], listing: Mapping[str, Any]) -> dict[str, Any]:
    base = dict(v4.classify_listing(target, listing))
    base["matcher_version"] = MATCHER_VERSION
    base["v4_identity_state"] = base.get("identity_state")

    if base["identity_state"] == "REJECTED":
        return base  # nothing to downgrade; v4's own guards already fired

    altered_check = altered_or_autograph_guard(listing)
    if altered_check["altered_or_autograph_detected"]:
        return {
            **base, "identity_state": "REJECTED", "reason": "ALTERED_OR_AUTOGRAPHED_V5",
            "evidence": dict(base.get("evidence", {}), v5_altered_autograph=altered_check),
        }

    return base


def rule_fingerprint() -> str:
    material = {
        "matcher_version": MATCHER_VERSION,
        "v4_fingerprint": v4.rule_fingerprint(),
        "altered_autograph_guard_version": ALTERED_OR_AUTOGRAPH_GUARD_VERSION,
        "altered_autograph_pattern": _ALTERED_OR_AUTOGRAPH_RE.pattern,
        "altered_false_positive_pattern": _ALTERED_FALSE_POSITIVE_RE.pattern,
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
