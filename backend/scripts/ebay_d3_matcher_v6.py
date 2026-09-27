"""D3-v6 (EBAY_E2_11): a narrow, purely-defensive wrapper around frozen D3-v5.

BACKGROUND (EBAY_E2_10 -> EBAY_E2_11): the fresh-blind coverage shortfall's
dominant recoverable class was D3-v5's `BASE_PARALLEL_NOT_EXPLICIT` reason --
a base-treatment target (common/uncommon/rare) whose listing title contains
no treatment/parallel language D3-v5 recognizes gets capped at
MEDIUM_CONFIDENCE rather than promoted to HIGH_CONFIDENCE.

The full development corpus (V4 + V5 + consumed E2.9B, 43 rows sharing this
exact reason with every other identity gate already clean) was inspected
before writing a single line of this module. It showed the originally
hypothesized fix -- "promote to HIGH_CONFIDENCE when the title contains no
treatment/parallel language at all" -- is UNSAFE: 3 of the 8 real, human-
confirmed wrong-variant (`variant_treatment=INCONSISTENT`) NO rows in that
corpus (`D4-0271`, `D4-0405`, `D5-0402`) have titles with ZERO distinguishing
treatment/parallel language -- textually indistinguishable from the genuine
true-positive rows in the same bucket. No text-only rule can safely tell
these apart; promoting on "blank treatment language" would inject confirmed
false accepts. THIS MODULE THEREFORE DOES NOT ATTEMPT THAT PROMOTION.

What IS safe, and what this module does: 4 of those same 8 hard-negative NO
rows (`D4-0230`, `D5-0166`, `D5-0225`, and the fresh-blind's own `E9B-0165`)
contain the EXPLICIT phrase "reverse holofoil" -- a genuine, unambiguous
parallel-print claim -- that frozen D3-v5's `PARALLEL_TERMS` list fails to
recognize purely because of a word-boundary artifact: its "reverse holo"
phrase-match requires a non-alphanumeric character immediately after "holo",
which "holofoil" never has. D3-v6 recognizes this same phrase and DOWNGRADES
(never promotes) any row D3-v5 left at MEDIUM_CONFIDENCE via
`BASE_PARALLEL_NOT_EXPLICIT` to REJECTED when it is present. Verified against
the full 43-row corpus: this affects exactly 4 rows (the 4 named above), all
NO, zero YES rows -- it can only ever remove a row from eligibility, never
add one, and is therefore safe by construction with respect to catastrophic
false accepts.

D3-v6 makes NO other change to D3-v5's behavior. Wrong collector number,
wrong set, lot/bundle, graded, sealed/non-card, altered/autograph, language
contradiction, explicit wrong (non-base-parallel) treatment, and every other
reason code pass through completely unchanged -- this module never even
inspects those evidence fields.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

from backend.scripts import ebay_d3_matcher_v5 as v5
from backend.scripts.index_fair_value_ebay_supply import normalize

MATCHER_VERSION = "index_fair_value_ebay_d3_v6"
QUERY_CONTRACT_VERSION = v5.QUERY_CONTRACT_VERSION

# Explicit parallel-print phrases that a genuine base/regular target can
# never legitimately carry, but that D3-v5's own PARALLEL_TERMS list fails
# to recognize due to its strict word-boundary phrase match on "reverse
# holo" (never matches "reverse holofoil", "reverse holographic", etc.).
# Deliberately NOT a bare "holo" -- see module docstring and
# EBAY_E2_11 report for why that would be unsafe (D5-0268 is a confirmed
# human-labeled wrong-variant NO row containing only bare "Holo", but two
# other confirmed-correct YES rows also contain bare "Holo"/"Holo Rare" --
# bare "holo" is genuinely ambiguous for a base target and must remain
# capped at MEDIUM_CONFIDENCE, not rejected and not promoted).
SUPPLEMENTAL_EXPLICIT_PARALLEL_TERMS = (
    "reverse holofoil",
    "reverse holographic",
)
D3_V6_REJECTION_REASON = "WRONG_VARIANT_V6_EXPLICIT_PARALLEL_SUPPLEMENTAL"
D3_V6_GUARD_VERSION = "ebay_d3_v6_base_parallel_supplemental_guard_v1"


def _contains_supplemental_parallel_term(title: str) -> str | None:
    text = normalize(title)
    for term in SUPPLEMENTAL_EXPLICIT_PARALLEL_TERMS:
        if term in text:
            return term
    return None


def classify_listing(target: Mapping[str, Any], listing: Mapping[str, Any]) -> dict[str, Any]:
    base = dict(v5.classify_listing(target, listing))
    base["matcher_version"] = MATCHER_VERSION
    base["v5_identity_state"] = base.get("identity_state")

    if base["identity_state"] != "MEDIUM_CONFIDENCE" or base.get("reason") != "BASE_PARALLEL_NOT_EXPLICIT":
        return base

    matched_term = _contains_supplemental_parallel_term(str(listing.get("title") or ""))
    if matched_term is None:
        return base

    return {
        **base,
        "identity_state": "REJECTED",
        "reason": D3_V6_REJECTION_REASON,
        "evidence": dict(base.get("evidence", {}), v6_supplemental_parallel_term=matched_term),
    }


def rule_fingerprint() -> str:
    material = {
        "matcher_version": MATCHER_VERSION,
        "v5_fingerprint": v5.rule_fingerprint(),
        "guard_version": D3_V6_GUARD_VERSION,
        "supplemental_parallel_terms": list(SUPPLEMENTAL_EXPLICIT_PARALLEL_TERMS),
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
