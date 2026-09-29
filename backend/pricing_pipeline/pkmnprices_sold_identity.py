"""Strict inDex identity gate for PkmnPrices sold listings.

PkmnPrices attribution is useful provider metadata, but it is not sufficient for
our physical-edition identity standard. Vintage Fair Value evidence must prove
card number, set, edition, printing and single/raw-card object identity from the
listing itself before it can resolve to one internal card_variant_id.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

from backend.pricing_pipeline.pkmnprices_sold import parse_provider_variant
from backend.scripts.ebay_d3_matcher_v3 import classify_product_object
from backend.scripts.index_fair_value_ebay_supply import normalize

MATCHER_VERSION = "pkmnprices_sold_vintage_identity_v1"

_FRACTION_RE = re.compile(r"(?<!\d)0*(\d{1,3})\s*/\s*0*(\d{1,3})(?!\d)")
_FIRST_EDITION_RE = re.compile(r"\b(?:1st|first)\s*edition\b", re.I)
_SHADOWLESS_RE = re.compile(r"\bshadowless\b", re.I)
_UNLIMITED_RE = re.compile(r"\bunlimited\b", re.I)
_BASE_SET_2_RE = re.compile(r"\bbase\s*set\s*2\b|\bbase\s*2\b", re.I)


def _target_fraction(value: Any) -> tuple[int, int] | None:
    match = _FRACTION_RE.search(str(value or ""))
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _fractions(value: Any) -> set[tuple[int, int]]:
    return {(int(a), int(b)) for a, b in _FRACTION_RE.findall(str(value or ""))}


def _name_matches(title: str, name: str) -> bool:
    words = set(normalize(title).split())
    tokens = [
        token for token in normalize(name).split()
        if len(token) > 1 and token not in {"ex"}
    ]
    return bool(tokens) and all(token in words for token in tokens)


def _set_state(title: str, set_name: str | None) -> str:
    text = normalize(title)
    target = normalize(set_name or "")
    if not target:
        return "ABSENT"
    if target == "base":
        if _BASE_SET_2_RE.search(title):
            return "CONFLICT"
        return "MATCH" if re.search(r"\bbase\s*set\b", title, re.I) else "ABSENT"
    return "MATCH" if target in text else "ABSENT"


def _edition_mentions(title: str) -> set[str]:
    out = set()
    if _FIRST_EDITION_RE.search(title):
        out.add("1st-edition")
    if _SHADOWLESS_RE.search(title):
        out.add("shadowless")
    if _UNLIMITED_RE.search(title):
        out.add("unlimited")
    return out


def classify_vintage_sold(
    target: Mapping[str, Any],
    listing: Mapping[str, Any],
) -> dict[str, Any]:
    title = str(listing.get("title") or "")
    product_object = classify_product_object({
        "title": title,
        "condition": "Graded" if listing.get("grader") or listing.get("grade") else "",
    })
    evidence: dict[str, Any] = {
        "product_object": product_object,
        "provider_attribution": str(listing.get("attribution") or "unknown").casefold(),
    }
    if product_object.get("state") != "SINGLE_RAW_CARD":
        return {
            "state": "NO_MATCH",
            "card_variant_id": None,
            "reason": str(product_object.get("state") or "NON_RAW_CARD"),
            "evidence": evidence,
            "matcher_version": MATCHER_VERSION,
        }

    name_ok = _name_matches(title, str(target.get("card_name") or ""))
    evidence["name"] = "MATCH" if name_ok else "CONFLICT"
    if not name_ok:
        return {
            "state": "NO_MATCH", "card_variant_id": None, "reason": "NAME_CONFLICT",
            "evidence": evidence, "matcher_version": MATCHER_VERSION,
        }

    target_fraction = _target_fraction(target.get("card_number"))
    observed = _fractions(title)
    evidence["target_fraction"] = list(target_fraction) if target_fraction else None
    evidence["observed_fractions"] = [list(x) for x in sorted(observed)]
    if len(observed) > 1:
        return {
            "state": "NO_MATCH", "card_variant_id": None, "reason": "MULTIPLE_CARD_NUMBERS",
            "evidence": evidence, "matcher_version": MATCHER_VERSION,
        }
    if target_fraction is None or target_fraction not in observed:
        reason = "WRONG_CARD_NUMBER" if observed else "CARD_NUMBER_NOT_EXPLICIT"
        state = "NO_MATCH" if observed else "AMBIGUOUS"
        return {
            "state": state, "card_variant_id": None, "reason": reason,
            "evidence": evidence, "matcher_version": MATCHER_VERSION,
        }

    set_state = _set_state(title, target.get("set_name"))
    evidence["set"] = set_state
    if set_state == "CONFLICT":
        return {
            "state": "NO_MATCH", "card_variant_id": None, "reason": "WRONG_SET",
            "evidence": evidence, "matcher_version": MATCHER_VERSION,
        }
    if set_state != "MATCH":
        return {
            "state": "AMBIGUOUS", "card_variant_id": None, "reason": "SET_NOT_EXPLICIT",
            "evidence": evidence, "matcher_version": MATCHER_VERSION,
        }

    editions = _edition_mentions(title)
    evidence["edition_mentions"] = sorted(editions)
    if len(editions) != 1:
        return {
            "state": "NO_MATCH" if len(editions) > 1 else "AMBIGUOUS",
            "card_variant_id": None,
            "reason": "EDITION_CONFLICT" if len(editions) > 1 else "EDITION_NOT_EXPLICIT",
            "evidence": evidence,
            "matcher_version": MATCHER_VERSION,
        }
    edition = next(iter(editions))

    gap_variants = [
        dict(row) for row in target.get("gap_variants") or []
        if str(row.get("effective_edition") or "") == edition
    ]
    if not gap_variants:
        return {
            "state": "NO_MATCH", "card_variant_id": None, "reason": "WRONG_EDITION",
            "evidence": evidence, "matcher_version": MATCHER_VERSION,
        }

    provider_printing = parse_provider_variant(listing.get("variant")).get("printing_type")
    evidence["provider_printing_type"] = provider_printing
    if provider_printing:
        gap_variants = [
            row for row in gap_variants
            if str(row.get("printing_type") or "") == provider_printing
        ]
    if len(gap_variants) != 1:
        return {
            "state": "NO_MATCH" if not gap_variants else "AMBIGUOUS",
            "card_variant_id": None,
            "reason": "WRONG_PRINTING" if not gap_variants else "VARIANT_AMBIGUOUS",
            "evidence": evidence, "matcher_version": MATCHER_VERSION,
        }

    if str(listing.get("attribution") or "").casefold() != "exact":
        return {
            "state": "AMBIGUOUS", "card_variant_id": None,
            "reason": "PROVIDER_ATTRIBUTION_NOT_EXACT",
            "evidence": evidence, "matcher_version": MATCHER_VERSION,
        }

    return {
        "state": "EXACT",
        "card_variant_id": str(gap_variants[0]["card_variant_id"]),
        "reason": "STRICT_VINTAGE_IDENTITY",
        "evidence": evidence,
        "matcher_version": MATCHER_VERSION,
    }
