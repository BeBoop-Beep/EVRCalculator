"""D3 v3 deterministic eBay identity matcher developed on all 1,050 labels."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

from backend.scripts import ebay_d2m_matcher as v1
from backend.scripts.ebay_d2m_matcher_v2 import (
    ACCESSORY_ONTOLOGY_VERSION, ACCESSORY_PATTERNS, ACCESSORY_RES,
    SEALED_PRODUCT_RE,
)
from backend.scripts.index_fair_value_ebay_supply import normalize

MATCHER_VERSION = "index_fair_value_ebay_d3_v3"
QUERY_CONTRACT_VERSION = "ebay_browse_query_d1_unchanged_v1"
SET_ALIAS_REGISTRY_VERSION = v1.SET_ALIAS_REGISTRY_VERSION
VARIANT_RULE_VERSION = v1.VARIANT_RULE_VERSION
CONDITION_POLICY_VERSION = v1.CONDITION_POLICY_VERSION
PRODUCT_OBJECT_RULE_VERSION = "ebay_d3_product_object_rules_v3"
GRADED_RULE_VERSION = "ebay_d3_graded_detection_rules_v3"
MULTIPLICITY_RULE_VERSION = "ebay_d3_multiplicity_rules_v3"
CONFIDENCE_POLICY_VERSION = "ebay_d3_confidence_policy_v3"

MULTIPLICITY_RE = re.compile(
    r"\b(?:lot|bundle|playset|collection|complete set|choose (?:a|your) card|"
    r"pick your card|you ?pick|you choose|singles?|multi[- ]?variation|bulk savings|"
    r"multiple cards?|pair(?: of cards?)?|(?:[2-9]|two) cards?|set of (?:2|two))\b|"
    r"\bcard\(s\)|(?<![a-z0-9])x\s*[2-9](?!\d)|(?<!\d)[2-9]\s*x\b|"
    r"\breverse holo\s+and\s+holo\b|"
    r"\b(?:[2-9]|two)[ -]?pack\b(?=.{0,30}\bcards?\b)|"
    r"\bcards?\b(?=.{0,30}\b(?:[2-9]|two)[ -]?pack\b)",
    re.I,
)

GRADE_ASPECT_KEYS = frozenset({
    "grader", "grading company", "professional grader", "grade", "card grade",
    "certification number", "certification", "graded",
})
MULTI_QUANTITY_KEYS = frozenset({"lot_size", "number_of_cards", "package_quantity"})
MULTI_FLAG_KEYS = frozenset({"multi_variation", "selectable_listing", "variation_listing"})


def _aspect_pairs(value: Any) -> list[tuple[str, str]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return []
    pairs: list[tuple[str, str]] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(item, list):
                pairs.extend((str(key), str(entry)) for entry in item)
            else:
                pairs.append((str(key), str(item)))
    elif isinstance(value, list):
        for item in value:
            if not isinstance(item, Mapping):
                continue
            key = item.get("name") or item.get("localizedName") or item.get("key") or ""
            values = item.get("values") or item.get("localizedValues") or item.get("value") or []
            if not isinstance(values, list):
                values = [values]
            pairs.extend((str(key), str(entry)) for entry in values)
    return pairs


def graded_evidence(listing: Mapping[str, Any]) -> dict[str, Any]:
    title = " ".join(str(listing.get(key) or "") for key in ("title", "subtitle"))
    condition = str(listing.get("condition") or "")
    condition_id = str(listing.get("conditionId") or listing.get("condition_id") or "")
    aspects = _aspect_pairs(listing.get("aspects"))
    aspect_hits = [
        {"name": key, "value": value} for key, value in aspects
        if normalize(key) in GRADE_ASPECT_KEYS
        and normalize(value) not in {"", "no", "none", "not graded", "ungraded", "false", "0"}
    ]
    reasons = []
    if v1.GRADE_RE.search(f"{title} {condition}"):
        reasons.append("TITLE_OR_CONDITION_TEXT")
    if normalize(condition) in {"graded", "bewertet"} or condition_id == "2750":
        reasons.append("STRUCTURED_GRADED_CONDITION")
    if aspect_hits:
        reasons.append("STRUCTURED_GRADING_ASPECT")
    category = str(listing.get("category") or "")
    if re.search(r"\bgraded\b|\bslab(?:bed)?\b", category, re.I):
        reasons.append("STRUCTURED_GRADED_CATEGORY")
    return {"affirmative": bool(reasons), "reasons": reasons, "aspect_hits": aspect_hits}


def multiplicity_evidence(listing: Mapping[str, Any]) -> dict[str, Any]:
    title = " ".join(str(listing.get(key) or "") for key in ("title", "subtitle"))
    reasons = []
    if MULTIPLICITY_RE.search(title):
        reasons.append("CONTEXTUAL_TITLE_MULTIPLICITY")
    for key in MULTI_QUANTITY_KEYS:
        try:
            if int(listing.get(key) or 0) > 1:
                reasons.append("STRUCTURED_OFFER_QUANTITY")
                break
        except (TypeError, ValueError):
            pass
    if any(str(listing.get(key) or "").lower() in {"1", "true", "yes"} for key in MULTI_FLAG_KEYS):
        reasons.append("STRUCTURED_SELECTABLE_OFFER")
    return {"affirmative": bool(reasons), "reasons": reasons}


def classify_product_object(listing: Mapping[str, Any]) -> dict[str, Any]:
    title = " ".join(str(listing.get(key) or "") for key in ("title", "subtitle"))
    graded = graded_evidence(listing)
    if graded["affirmative"]:
        return {"state": "GRADED_CARD", "reason": "AFFIRMATIVE_GRADED_EVIDENCE", "evidence": graded}
    matches = [name for name, pattern in ACCESSORY_RES.items() if pattern.search(title)]
    if matches:
        return {"state": "CARD_ACCESSORY", "reason": "ACCESSORY_PRODUCT_CONTEXT", "ontology_matches": matches}
    if SEALED_PRODUCT_RE.search(title):
        return {"state": "SEALED_TCG_PRODUCT", "reason": "SEALED_PRODUCT_CONTEXT"}
    multiple = multiplicity_evidence(listing)
    if multiple["affirmative"]:
        return {"state": "MULTI_CARD_OFFER", "reason": "SELECTABLE_OR_MULTI_CARD_CONTEXT", "evidence": multiple}
    return {"state": "SINGLE_RAW_CARD", "reason": "NO_NON_CARD_OBJECT_EVIDENCE"}


def classify_listing(target: Mapping[str, Any], listing: Mapping[str, Any]) -> dict[str, Any]:
    product_object = classify_product_object(listing)
    if product_object["state"] != "SINGLE_RAW_CARD":
        condition_state = "GRADED" if product_object["state"] == "GRADED_CARD" else "NOT_APPLICABLE_NON_SINGLE_CARD"
        return {
            "identity_state": "REJECTED", "condition_state": condition_state,
            "reason": product_object["state"], "product_object": product_object,
            "evidence": {"product_object": product_object}, "matcher_version": MATCHER_VERSION,
        }
    result = dict(v1.classify_listing(target, listing))
    result["identity_state"] = "REJECTED" if result["identity_state"] == "REJECT" else result["identity_state"]
    result["product_object"] = product_object
    result["evidence"] = dict(result["evidence"], product_object=product_object)
    result["matcher_version"] = MATCHER_VERSION
    return result


def rule_fingerprint() -> str:
    material = {
        "matcher_version": MATCHER_VERSION, "v1_fingerprint": v1.rule_fingerprint(),
        "query_contract": QUERY_CONTRACT_VERSION, "product_object_version": PRODUCT_OBJECT_RULE_VERSION,
        "graded_rule_version": GRADED_RULE_VERSION, "multiplicity_rule_version": MULTIPLICITY_RULE_VERSION,
        "accessory_ontology_version": ACCESSORY_ONTOLOGY_VERSION,
        "confidence_policy_version": CONFIDENCE_POLICY_VERSION,
        "multiplicity_pattern": MULTIPLICITY_RE.pattern, "grade_aspect_keys": sorted(GRADE_ASPECT_KEYS),
        "multi_quantity_keys": sorted(MULTI_QUANTITY_KEYS), "multi_flag_keys": sorted(MULTI_FLAG_KEYS),
        "sealed_pattern": SEALED_PRODUCT_RE.pattern, "accessory_patterns": ACCESSORY_PATTERNS,
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
