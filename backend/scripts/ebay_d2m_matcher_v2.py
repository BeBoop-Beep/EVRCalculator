"""Frozen-candidate D2M v2 matcher developed on the 700-row expanded corpus."""
from __future__ import annotations
import hashlib, json, re
from typing import Any, Mapping
from backend.scripts import ebay_d2m_matcher as v1
from backend.scripts.index_fair_value_ebay_supply import normalize

MATCHER_VERSION="index_fair_value_ebay_d2m_v2"
QUERY_CONTRACT_VERSION="ebay_browse_query_d1_unchanged_v1"
SET_ALIAS_REGISTRY_VERSION=v1.SET_ALIAS_REGISTRY_VERSION
VARIANT_RULE_VERSION=v1.VARIANT_RULE_VERSION
CONDITION_POLICY_VERSION=v1.CONDITION_POLICY_VERSION
PRODUCT_OBJECT_RULE_VERSION="ebay_product_object_rules_v2"
ACCESSORY_ONTOLOGY_VERSION="ebay_accessory_ontology_v2"
CONFIDENCE_POLICY_VERSION="ebay_d2m_v2_confidence_policy_v1"

MULTI_CARD_RE=re.compile(
 r"\b(?:lot|bundle|playset|collection|complete set|set of [2-9]|choose (?:a|your) card|"
 r"pick your card|you ?pick|singles?|multi[- ]?variation|bulk savings)\b|"
 r"\bcard\(s\)|\b[2-9]\s*x\b",re.I)
SEALED_PRODUCT_RE=re.compile(
 r"\b(?:booster (?:box|pack|bundle)|elite trainer box|etb|display box|factory sealed|"
 r"collection box|tin|blister)\b",re.I)
ACCESSORY_PATTERNS={
 "ART_CASE":r"\b(?:extended|full)[- ]?art(?:work)?\s+(?:custom\s+)?(?:display\s+)?case\b",
 "DISPLAY_CASE":r"\b(?:acrylic|magnetic|custom|display)\s+(?:card\s+)?(?:case|holder|frame)\b",
 "HOLDER_FRAME":r"\b(?:card\s+protector|card\s+holder|framed\s+display|card\s+stand|top ?loader)\b",
 "STORAGE_DISPLAY":r"\b(?:binder(?:\s+insert)?|sleeves?|deck\s+box|storage\s+(?:box|case))\b",
 "NON_CARD_REPLICA":r"\b(?:blanket|poster|proxy|custom card|metal card)\b",
 "NO_CARD":r"\bno\s+card\b",
}
ACCESSORY_RES={name:re.compile(pattern,re.I) for name,pattern in ACCESSORY_PATTERNS.items()}

def classify_product_object(listing:Mapping[str,Any])->dict[str,Any]:
    title=str(listing.get("title") or "");condition=str(listing.get("condition") or "")
    combined=f"{title} {condition}"
    if v1.GRADE_RE.search(combined) or normalize(condition)=="graded":
        return {"state":"GRADED_CARD","reason":"GRADE_OR_SLAB_EVIDENCE"}
    matches=[name for name,pattern in ACCESSORY_RES.items() if pattern.search(title)]
    if matches:return {"state":"CARD_ACCESSORY","reason":"ACCESSORY_PRODUCT_CONTEXT","ontology_matches":matches}
    if SEALED_PRODUCT_RE.search(title):return {"state":"SEALED_TCG_PRODUCT","reason":"SEALED_PRODUCT_CONTEXT"}
    if MULTI_CARD_RE.search(title):return {"state":"MULTI_CARD_OFFER","reason":"SELECTABLE_OR_MULTI_CARD_CONTEXT"}
    return {"state":"SINGLE_RAW_CARD","reason":"NO_NON_CARD_OBJECT_EVIDENCE"}

def classify_listing(target:Mapping[str,Any],listing:Mapping[str,Any])->dict[str,Any]:
    product_object=classify_product_object(listing)
    if product_object["state"]!="SINGLE_RAW_CARD":
        condition_state="GRADED" if product_object["state"]=="GRADED_CARD" else "NOT_APPLICABLE_NON_SINGLE_CARD"
        return {"identity_state":"REJECTED","condition_state":condition_state,
          "reason":product_object["state"],"product_object":product_object,
          "evidence":{"product_object":product_object},"matcher_version":MATCHER_VERSION}
    result=v1.classify_listing(target,listing)
    result=dict(result)
    result["identity_state"]="REJECTED" if result["identity_state"]=="REJECT" else result["identity_state"]
    result["product_object"]=product_object
    result["evidence"]=dict(result["evidence"],product_object=product_object)
    result["matcher_version"]=MATCHER_VERSION
    return result

def rule_fingerprint()->str:
    material={"matcher_version":MATCHER_VERSION,"v1_fingerprint":v1.rule_fingerprint(),
      "query_contract":QUERY_CONTRACT_VERSION,"product_object_version":PRODUCT_OBJECT_RULE_VERSION,
      "accessory_ontology_version":ACCESSORY_ONTOLOGY_VERSION,
      "confidence_policy_version":CONFIDENCE_POLICY_VERSION,
      "multi":MULTI_CARD_RE.pattern,"sealed":SEALED_PRODUCT_RE.pattern,
      "accessory_patterns":ACCESSORY_PATTERNS}
    return hashlib.sha256(json.dumps(material,sort_keys=True,separators=(",",":")).encode()).hexdigest()
