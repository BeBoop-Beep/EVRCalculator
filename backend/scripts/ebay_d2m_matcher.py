"""Frozen deterministic D2M eBay listing identity matcher.

Identity evidence is title/aspect/condition metadata only. Price is never an input.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

from backend.scripts.index_fair_value_ebay_supply import normalize

MATCHER_VERSION = "index_fair_value_ebay_d2m_v1"
QUERY_CONTRACT_VERSION = "ebay_browse_query_d1_unchanged_v1"
SET_ALIAS_REGISTRY_VERSION = "ebay_set_alias_registry_v1"
VARIANT_RULE_VERSION = "ebay_variant_identity_rules_v1"
CONDITION_POLICY_VERSION = "ebay_raw_condition_policy_v1"

SET_ALIASES = {
    "Ascended Heroes": ["ascended heroes", "ascended heros", "asc en", "asc"],
    "Black Bolt": ["black bolt", "blk en", "blk"],
    "Chaos Rising": ["chaos rising"],
    "Destined Rivals": ["destined rivals", "destined rival", "dri"],
    "Journey Together": ["journey together", "jit"],
    "Mega Evolution": ["mega evolution", "mega evolutions", "me01"],
    "Obsidian Flames": ["obsidian flames", "obf"],
    "Paldea Evolved": ["paldea evolved", "pal en", "pal"],
    "Paldean Fates": ["paldean fates", "paf"],
    "Paradox Rift": ["paradox rift", "par en", "par"],
    "Phantasmal Flames": ["phantasmal flames"],
    "Pitch Black": ["pitch black"],
    "Prismatic Evolutions": ["prismatic evolutions", "prismatic ev", "pre en", "pre"],
    "Scarlet and Violet 151": ["scarlet violet 151", "sv 151", "mew en"],
    "Scarlet and Violet Base Set": [
        "scarlet violet base set", "scarlet violet base", "sv01", "svi",
    ],
    "Shrouded Fable": ["shrouded fable", "sv6 5"],
    "Stellar Crown": ["stellar crown", "scr en", "scr"],
    "Surging Sparks": ["surging sparks", "ssp"],
    "Temporal Forces": ["temporal forces", "temporal force", "sv05", "tef en", "tef"],
    "Twilight Masquerade": ["twilight masquerade", "sv06", "twm en", "twm"],
    "White Flare": ["white flare", "wht en", "wht"],
}

GRADE_RE = re.compile(
    r"\b(?:psa|bgs|cgc|sgc|ace|tag|dcm)\s*(?:[1-9](?:\.5)?|10)\b|"
    r"\b(?:grade|graded)\s*[:#-]?\s*(?:[1-9](?:\.5)?|10)?\b|"
    r"\bslab(?:bed)?\b|\bgem mint\b|\bpristine\b|\bbewertet\b",
    re.I,
)
LOT_RE = re.compile(
    r"\b(?:lot|bundle|playset|collection|complete set|set of [2-9]|"
    r"choose (?:a|your) card|pick your card|you ?pick|singles?)\b|\b[2-9]\s*x\b",
    re.I,
)
NON_ENGLISH_RE = re.compile(
    r"\b(?:japanese|japan|korean|chinese|german|french|spanish|italian|"
    r"portuguese|indonesian|thai)\b|\b(?:jp|jpn|kr|cn)\s*(?:card|pokemon)\b",
    re.I,
)
SEALED_ACCESSORY_RE = re.compile(
    r"\b(?:booster (?:box|pack)|elite trainer box|etb|display box|factory sealed|"
    r"binder|sleeves?|proxy|custom card|metal card|extended (?:art|artwork) case|"
    r"magnetic case|blanket|framed display|poster|card stand)\b",
    re.I,
)
POOR_CONDITION_RE = re.compile(
    r"\b(?:damaged|poor|creased?|moderately played|heavily played|mp|hp)\b",
    re.I,
)
FRACTION_RE = re.compile(r"(?<!\d)0*(\d{1,3})\s*/\s*0*(\d{1,3})(?!\d)")
HASH_RE = re.compile(r"#\s*0*(\d{1,3})(?!\d)")

TREATMENT_TERMS = {
    "special_illustration_rare": (
        "special illustration rare", "special illus rare", "sir", "sar",
    ),
    "illustration_rare": ("illustration rare", "illus rare", "ir"),
    "mega_hyper_rare": ("mega hyper rare", "mhr"),
    "ultra_rare": ("ultra rare", "full art"),
    "shiny_rare": ("shiny rare", "baby shiny", "shiny"),
    "ace_spec": ("ace spec",),
    "hyper_rare_gold": ("hyper rare", "gold"),
}
PARALLEL_TERMS = (
    "reverse holo", "reverse foil", "pokeball", "poke ball", "master ball",
    "masterball", "stamped", "pokemon center",
)
BASE_TREATMENTS = frozenset({"common", "uncommon", "rare"})


def _phrase(text: str, phrase: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(normalize(phrase))}(?![a-z0-9])", text))


def number_evidence(title: str, target_number: Any) -> dict[str, Any]:
    target_raw = str(target_number or "").strip()
    target_match = re.search(r"\d+", target_raw)
    if not target_match:
        return {"state": "ABSENT", "observed": []}
    target = str(int(target_match.group()))
    observed = {str(int(value)) for value, _ in FRACTION_RE.findall(title)}
    observed.update(str(int(value)) for value in HASH_RE.findall(title))
    normalized = normalize(title)
    if not observed and len(target) >= 3 and re.search(rf"(?<!\d)0*{re.escape(target)}(?!\d)", normalized):
        observed.add(target)
    if target in observed and len(observed) > 1:
        state = "MULTIPLE"
    elif target in observed:
        state = "MATCH"
    elif observed:
        state = "CONFLICT"
    else:
        state = "ABSENT"
    return {"state": state, "observed": sorted(observed, key=int), "target": target}


def set_evidence(title: str, target_set: str) -> dict[str, Any]:
    text = normalize(title)
    target_aliases = SET_ALIASES.get(target_set, [target_set])
    matching_target = [alias for alias in target_aliases if _phrase(text, alias)]
    conflicts = []
    for set_name, aliases in SET_ALIASES.items():
        if set_name != target_set and any(_phrase(text, alias) for alias in aliases):
            conflicts.append(set_name)
    if matching_target:
        canonical = _phrase(text, target_set)
        state = "EXACT" if canonical else "ALIAS"
    elif conflicts:
        state = "CONFLICT"
    else:
        state = "ABSENT"
    return {"state": state, "matched": matching_target, "conflicts": sorted(conflicts)}


def variant_evidence(title: str, treatment: str) -> dict[str, Any]:
    text = normalize(title)
    parallels = [term for term in PARALLEL_TERMS if _phrase(text, term)]
    expected = TREATMENT_TERMS.get(treatment, ())
    matched = [term for term in expected if _phrase(text, term)]
    other = []
    for name, terms in TREATMENT_TERMS.items():
        if name != treatment and any(_phrase(text, term) for term in terms):
            other.append(name)
    if treatment in BASE_TREATMENTS:
        state = "CONFLICT" if parallels else "UNRESOLVED"
    elif matched and not parallels:
        state = "MATCH"
    elif other or parallels:
        state = "CONFLICT"
    else:
        state = "ABSENT"
    return {
        "state": state, "matched": matched, "conflicting_treatments": sorted(other),
        "parallel_terms": parallels,
    }


def _name_matches(title: str, target_name: str) -> bool:
    words = set(normalize(title).split())
    tokens = [token for token in normalize(target_name).split() if len(token) > 1 and token != "ex"]
    return all(token in words for token in tokens)


def classify_listing(
    target: Mapping[str, Any], listing: Mapping[str, Any],
) -> dict[str, Any]:
    title = str(listing.get("title") or "")
    condition = str(listing.get("condition") or "")
    combined = f"{title} {condition}"
    condition_state = (
        "GRADED"
        if GRADE_RE.search(combined) or normalize(condition) == "graded"
        else "RAW_CONDITION_INELIGIBLE"
        if POOR_CONDITION_RE.search(combined)
        else "RAW_CONDITION_STATED_NM"
        if re.search(r"\b(?:near mint|nm)\b", combined, re.I)
        else "RAW_CONDITION_UNGRADED_UNSPECIFIED"
    )
    hard_reason = None
    if condition_state == "GRADED":
        hard_reason = "GRADED"
    elif NON_ENGLISH_RE.search(title):
        hard_reason = "WRONG_LANGUAGE"
    elif LOT_RE.search(title):
        hard_reason = "LOT_OR_BUNDLE"
    elif SEALED_ACCESSORY_RE.search(title):
        hard_reason = "SEALED_OR_ACCESSORY"

    name_ok = _name_matches(title, str(target.get("card_name") or ""))
    number = number_evidence(title, target.get("card_number"))
    set_result = set_evidence(title, str(target.get("set_name") or ""))
    variant = variant_evidence(title, str(target.get("treatment") or ""))

    if hard_reason:
        identity_state, reason = "REJECT", hard_reason
    elif not name_ok:
        identity_state, reason = "REJECT", "NAME_CONFLICT"
    elif number["state"] == "CONFLICT":
        identity_state, reason = "REJECT", "WRONG_CARD_NUMBER"
    elif set_result["state"] == "CONFLICT":
        identity_state, reason = "REJECT", "WRONG_SET"
    elif variant["state"] == "CONFLICT":
        identity_state, reason = "REJECT", "WRONG_VARIANT"
    elif (
        number["state"] == "MATCH"
        and set_result["state"] in {"EXACT", "ALIAS"}
        and variant["state"] in {"MATCH", "ABSENT"}
        and str(target.get("treatment") or "") not in BASE_TREATMENTS
    ):
        identity_state, reason = "HIGH_CONFIDENCE", "THREE_FACTOR_IDENTITY"
    elif (
        number["state"] == "MATCH"
        and set_result["state"] in {"EXACT", "ALIAS"}
        and variant["state"] == "ABSENT"
    ):
        identity_state, reason = "MEDIUM_CONFIDENCE", "VARIANT_NOT_EXPLICIT"
    elif number["state"] == "MATCH" and variant["state"] == "MATCH":
        identity_state, reason = "HIGH_CONFIDENCE", "NAME_NUMBER_VARIANT_IDENTITY"
    elif (
        number["state"] == "MATCH"
        and set_result["state"] in {"EXACT", "ALIAS"}
        and variant["state"] == "UNRESOLVED"
    ):
        identity_state, reason = "MEDIUM_CONFIDENCE", "BASE_PARALLEL_NOT_EXPLICIT"
    else:
        identity_state, reason = "AMBIGUOUS", "INSUFFICIENT_INDEPENDENT_EVIDENCE"

    return {
        "identity_state": identity_state,
        "condition_state": condition_state,
        "reason": reason,
        "evidence": {
            "name": "MATCH" if name_ok else "CONFLICT",
            "number": number,
            "set": set_result,
            "variant": variant,
            "language": "CONFLICT" if NON_ENGLISH_RE.search(title) else "COMPATIBLE",
            "raw": "CONFLICT" if condition_state == "GRADED" else "COMPATIBLE",
        },
        "matcher_version": MATCHER_VERSION,
    }


def rule_fingerprint() -> str:
    material = {
        "matcher_version": MATCHER_VERSION,
        "query_contract_version": QUERY_CONTRACT_VERSION,
        "set_alias_registry_version": SET_ALIAS_REGISTRY_VERSION,
        "variant_rule_version": VARIANT_RULE_VERSION,
        "condition_policy_version": CONDITION_POLICY_VERSION,
        "set_aliases": SET_ALIASES,
        "treatment_terms": TREATMENT_TERMS,
        "parallel_terms": PARALLEL_TERMS,
        "patterns": [
            GRADE_RE.pattern, LOT_RE.pattern, NON_ENGLISH_RE.pattern,
            SEALED_ACCESSORY_RE.pattern, POOR_CONDITION_RE.pattern,
        ],
    }
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
