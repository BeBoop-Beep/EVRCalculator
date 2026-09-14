"""D3 v4: a bounded, downgrade-only safety revision of v3.

Design constraint from the E2.1 remediation brief: v4 must not loosen any v3
safety threshold to recover coverage, and must not be derived by tuning
against the five known historical final-blind catastrophic rows. Instead, v4
is built by auditing v1/v2/v3's own decision logic for structurally
explainable false-accept vectors, and adding three narrow, generalizable
guards that can only ever REJECT or DOWNGRADE a v3 decision -- never upgrade
one. v3's decision tree itself is untouched (imported, not copied) so this
file can never accidentally diverge from v3's already-frozen behavior in the
permissive direction.

Guard 1 -- bare collector-number false-positive control (WRONG_CARD_NUMBER class):
    v1.number_evidence() has a fallback that treats any bare 3+-digit
    substring matching the target's number as a MATCH when no `#N` or `N/M`
    format is present anywhere in the title. That fallback cannot distinguish
    a genuine bare collector number from a price, a year, or other numeric
    noise that happens to coincide with the target's number. v4 refuses to
    trust that specific fallback when the matching digits sit in a price or
    currency context, downgrading the identity decision instead of accepting
    on it.

Guard 2 -- multi-fraction lot control (LOT_OR_BUNDLE class):
    A title containing two or more distinct `N/M`-style collector-number
    fractions is evidence of more than one physical card being offered
    together (e.g. "Pikachu 25/102 + Charizard 4/102"), which v3's
    title-keyword multiplicity detector does not see. v4 treats 2+ distinct
    fractions as an additional, independent multi-card signal.

Guard 3 -- extended sealed/accessory ontology (SEALED_OR_ACCESSORY class):
    v2's SEALED_PRODUCT_RE (reused unchanged by v3) does not cover several
    common sealed/non-card product terms (premium collection box, battle/
    theme deck, playmat, coin, figure, code card). v4 extends the same
    ontology mechanism the repository already uses, rather than inventing a
    parallel blacklist.

None of these guards were derived from, or verified against, the historical
final-blind rows -- see backend/scripts/index_fair_value_ebay_evidence_manifest.py
for the enforced evidence boundary.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

from backend.scripts import ebay_d3_matcher_v3 as v3
from backend.scripts.ebay_d2m_matcher import FRACTION_RE, number_evidence
from backend.scripts.index_fair_value_ebay_supply import normalize

MATCHER_VERSION = "index_fair_value_ebay_d3_v4"
QUERY_CONTRACT_VERSION = v3.QUERY_CONTRACT_VERSION
NUMBER_GUARD_VERSION = "ebay_d3_v4_number_context_guard_v1"
MULTI_FRACTION_GUARD_VERSION = "ebay_d3_v4_multi_fraction_guard_v1"
SEALED_ONTOLOGY_EXTENSION_VERSION = "ebay_d3_v4_sealed_ontology_extension_v1"

# Guard 1: contexts where a bare (non-fraction, non-hash) numeric match to the
# target's collector number is not trustworthy identity evidence.
_PRICE_CONTEXT_RE = re.compile(r"(?:\$\s*\d[\d,]*\s*$|\$\s*\d[\d,]*(?!\d)|\d\s*\.\s*\d{2}\b|\busd\b|\bshipping\b|\bobo\b)", re.I)
_QUANTITY_CONTEXT_RE = re.compile(r"\b(?:lot of|pack of|set of|qty|quantity)\s*\d", re.I)


def _bare_number_is_context_suspect(title: str, target_number: Any) -> bool:
    """True if the ONLY reason number_evidence matched/conflicted is a bare
    digit run that also sits inside a price or quantity phrase.
    """
    target_match = re.search(r"\d+", str(target_number or ""))
    if not target_match:
        return False
    target = str(int(target_match.group()))
    if len(target) < 3:
        return False
    if FRACTION_RE.search(title) or re.search(rf"#\s*0*{re.escape(target)}(?!\d)", title):
        return False  # a structured format is present; bare fallback wasn't the source of evidence
    normalized = normalize(title)
    if not re.search(rf"(?<!\d)0*{re.escape(target)}(?!\d)", normalized):
        return False
    return bool(_PRICE_CONTEXT_RE.search(title) or _QUANTITY_CONTEXT_RE.search(title))


def number_conflict_guard(target: Mapping[str, Any], listing: Mapping[str, Any]) -> dict[str, Any]:
    title = str(listing.get("title") or "")
    suspect = _bare_number_is_context_suspect(title, target.get("card_number"))
    return {"suspect_bare_number_context": suspect, "guard_version": NUMBER_GUARD_VERSION}


def multi_fraction_guard(listing: Mapping[str, Any]) -> dict[str, Any]:
    title = str(listing.get("title") or "")
    fractions = {(num, den) for num, den in FRACTION_RE.findall(title)}
    return {
        "distinct_fraction_count": len(fractions),
        "multiple_distinct_collector_numbers": len(fractions) >= 2,
        "guard_version": MULTI_FRACTION_GUARD_VERSION,
    }


_SEALED_EXTENSION_PATTERNS = {
    "PREMIUM_COLLECTION": r"\bpremium\s+collection(?:\s+box)?\b",
    "BATTLE_OR_THEME_DECK": r"\b(?:battle|theme)\s+deck\b",
    "BUILD_AND_BATTLE": r"\bbuild\s*(?:and|&)\s*battle\s*(?:box|deck|stadium)?\b",
    "PLAYMAT": r"\bplaymat\b",
    "COIN": r"\bcoin\b",
    "FIGURE": r"\b(?:action\s+)?figure\b",
    "CODE_CARD_ONLY": r"\b(?:online\s+)?code\s*card\b(?!.*\bphysical\b)",
    "VALUE_BOX": r"\bvalue\s+box\b",
}
_SEALED_EXTENSION_RES = {name: re.compile(pattern, re.I) for name, pattern in _SEALED_EXTENSION_PATTERNS.items()}


def sealed_accessory_extension_guard(listing: Mapping[str, Any]) -> dict[str, Any]:
    title = str(listing.get("title") or "")
    matches = [name for name, pattern in _SEALED_EXTENSION_RES.items() if pattern.search(title)]
    return {"extended_sealed_matches": matches, "guard_version": SEALED_ONTOLOGY_EXTENSION_VERSION}


def classify_listing(target: Mapping[str, Any], listing: Mapping[str, Any]) -> dict[str, Any]:
    base = dict(v3.classify_listing(target, listing))
    base["matcher_version"] = MATCHER_VERSION
    base["v3_identity_state"] = base.get("identity_state")

    if base["identity_state"] == "REJECTED":
        return base  # nothing to downgrade; v3's own guards already fired

    sealed_check = sealed_accessory_extension_guard(listing)
    if sealed_check["extended_sealed_matches"]:
        return {
            **base, "identity_state": "REJECTED", "reason": "SEALED_OR_ACCESSORY_V4_EXTENDED",
            "evidence": dict(base.get("evidence", {}), v4_sealed_extension=sealed_check),
        }

    multi_check = multi_fraction_guard(listing)
    if multi_check["multiple_distinct_collector_numbers"]:
        return {
            **base, "identity_state": "REJECTED", "reason": "MULTI_CARD_OFFER_V4_MULTI_FRACTION",
            "evidence": dict(base.get("evidence", {}), v4_multi_fraction=multi_check),
        }

    number_check = number_conflict_guard(target, listing)
    if number_check["suspect_bare_number_context"]:
        downgraded = "MEDIUM_CONFIDENCE" if base["identity_state"] == "HIGH_CONFIDENCE" else "AMBIGUOUS"
        return {
            **base, "identity_state": downgraded, "reason": "NUMBER_EVIDENCE_CONTEXT_SUSPECT_V4",
            "evidence": dict(base.get("evidence", {}), v4_number_guard=number_check),
        }

    return base


def rule_fingerprint() -> str:
    material = {
        "matcher_version": MATCHER_VERSION,
        "v3_fingerprint": v3.rule_fingerprint(),
        "number_guard_version": NUMBER_GUARD_VERSION,
        "multi_fraction_guard_version": MULTI_FRACTION_GUARD_VERSION,
        "sealed_extension_version": SEALED_ONTOLOGY_EXTENSION_VERSION,
        "sealed_extension_patterns": _SEALED_EXTENSION_PATTERNS,
        "price_context_pattern": _PRICE_CONTEXT_RE.pattern,
        "quantity_context_pattern": _QUANTITY_CONTEXT_RE.pattern,
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
