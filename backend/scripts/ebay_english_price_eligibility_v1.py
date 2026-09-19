"""Conservative eligibility for an English Near Mint fixed-price active ask."""
from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from backend.scripts.ebay_language_policy_v1 import extract_language_aspect, normalize_language_value

VERSION = "ebay_english_price_eligibility_v1"
NM_VALUES = {"near mint", "near mint or better", "near mint or better nm", "mint", "mint or better"}
BAD_CONDITION = re.compile(r"\b(?:graded|slab(?:bed)?|psa|bgs|cgc|sgc|damaged|poor|heavy(?:ily)? played|moderately played|lightly played|excellent|good|fair)\b", re.I)


def _money(value: Any) -> Decimal | None:
    try:
        amount = Decimal(str(value))
        return amount if amount.is_finite() and amount >= 0 else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def _card_condition_values(item: Mapping[str, Any]) -> list[str]:
    values = []
    for descriptor in item.get("conditionDescriptors") or []:
        if str(descriptor.get("name") or "").strip().casefold() != "card condition":
            continue
        for value in descriptor.get("values") or []:
            if value.get("content"):
                values.append(str(value["content"]))
    return values


def resolve(item: Mapping[str, Any], *, text_state: str, image_state: str = "UNVERIFIED",
            ocr_v3_state: str = "UNVERIFIED") -> dict[str, Any]:
    """No title/location-based positive English inference; every veto wins."""
    provider_raw = extract_language_aspect(item.get("localizedAspects"))
    provider = normalize_language_value(provider_raw)
    condition_values = _card_condition_values(item)
    condition_text = str(item.get("condition") or "")
    title = str(item.get("title") or "")
    options = set(item.get("buyingOptions") or [])
    price_obj = item.get("price") or {}
    item_price = _money(price_obj.get("value")) if price_obj.get("currency") == "USD" else None
    shipping = None
    for option in item.get("shippingOptions") or []:
        cost = option.get("shippingCost") or {}
        if cost.get("currency") == "USD":
            shipping = _money(cost.get("value"))
            if shipping is not None:
                break
    landed = item_price + shipping if item_price is not None and shipping is not None else None
    normalized_conditions = {re.sub(r"\s+", " ", value.strip().casefold()) for value in condition_values}
    positive_nm = bool(normalized_conditions & NM_VALUES) or condition_text.strip().casefold() in NM_VALUES
    bad_condition = bool(BAD_CONDITION.search(title + " " + condition_text + " " + " ".join(condition_values)))
    if text_state != "HIGH_CONFIDENCE" or image_state == "MISMATCH":
        state, reason = "IDENTITY_REJECTED", "text_or_image_identity_failed"
    elif (provider is not None and provider != "ENGLISH") or ocr_v3_state == "JAPANESE_MISMATCH":
        state, reason = "NON_ENGLISH_EXCLUDED", "explicit_provider_or_ocr_contradiction"
    elif provider != "ENGLISH" and image_state != "MATCH":
        state, reason = "LANGUAGE_UNRESOLVED", "no_positive_english_evidence"
    elif bad_condition:
        state, reason = "CONDITION_EXCLUDED", "explicit_non_nm_or_graded_evidence"
    elif not positive_nm:
        state, reason = "CONDITION_UNRESOLVED", "no_explicit_nm_compatible_condition"
    elif "FIXED_PRICE" not in options or "AUCTION" in options or landed is None:
        state, reason = "BUYING_FORMAT_EXCLUDED", "no_executable_usd_fixed_landed_ask"
    else:
        state, reason = "ENGLISH_PRICE_ELIGIBLE", "exact_english_nm_fixed_landed_ask"
    return {"version": VERSION, "state": state, "reason": reason,
            "provider_language_raw": provider_raw, "provider_language_normalized": provider,
            "text_state": text_state, "image_state": image_state, "ocr_v3_state": ocr_v3_state,
            "condition": condition_text, "card_condition_values": condition_values,
            "buying_options": sorted(options), "item_price_usd": str(item_price) if item_price is not None else None,
            "shipping_price_usd": str(shipping) if shipping is not None else None,
            "landed_ask_usd": str(landed) if landed is not None else None}


def fingerprint() -> str:
    return hashlib.sha256(json.dumps({"version": VERSION, "nm": sorted(NM_VALUES),
        "bad_condition": BAD_CONDITION.pattern, "rule_order": ["identity", "language_veto", "english_positive",
        "condition_veto", "nm_positive", "fixed_landed"]}, sort_keys=True).encode()).hexdigest()
