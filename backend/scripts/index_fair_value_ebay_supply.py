"""Deterministic eBay Browse query, listing-match, and supply aggregation helpers."""
from __future__ import annotations

import math
import re
import statistics
import unicodedata
from collections import Counter
from typing import Any

VERSION = "index_fair_value_ebay_supply_d1_v1"
GRADED = re.compile(r"\b(psa|bgs|cgc|sgc|ace)\s*(?:[1-9]|10)|\bgraded\b|\bslab(?:bed)?\b", re.I)
LOT = re.compile(r"\b(lot|bundle|playset|complete set|collection)\b|\b[2-9]\s*x\b", re.I)
SEALED = re.compile(r"\b(booster\s+(?:box|pack)|display box|etb|elite trainer box|factory sealed)\b", re.I)
ACCESSORY = re.compile(r"\b(sleeves?|binder|proxy|custom|metal card|case|stand|poster)\b", re.I)
NON_ENGLISH = re.compile(r"\b(japanese|japan|korean|chinese|german|french|spanish|italian|portuguese)\b", re.I)
POOR_CONDITION = re.compile(r"\b(damaged|played|poor|creased|crease|moderately played|heavily played)\b", re.I)


def normalize(text: Any) -> str:
    value = re.sub(r"[^\w]+", " ", unicodedata.normalize("NFKD", str(text or "")), flags=re.UNICODE).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


def number_forms(number: Any) -> set[str]:
    raw = str(number or "").strip().lower()
    if not raw:
        return set()
    normalized = normalize(raw)
    forms = {normalized, normalized.lstrip("0") or "0"}
    if "/" in raw:
        left, right = raw.split("/", 1)
        forms |= {normalize(left), normalize(f"{left}/{right}"), normalize(f"{left} {right}")}
    return {x for x in forms if x}


def build_query(card: dict[str, Any]) -> dict[str, Any]:
    name = str(card["card_name"]).strip()
    set_name = str(card["set_name"]).strip()
    number = str(card.get("card_number") or "").strip()
    terms = [name, number, set_name, "Pokemon card"]
    edition = str(card.get("edition") or "").strip()
    printing = str(card.get("printing_type") or "").strip()
    if edition and normalize(edition) not in {"unlimited", "none"}:
        terms.append(edition)
    if any(x in normalize(printing) for x in ("reverse", "stamped")):
        terms.append(printing)
    query = " ".join(x for x in terms if x)
    return {"query": query, "marketplace": "EBAY_US", "category_id": "183454", "limit": 100,
            "filters": "buyingOptions:{FIXED_PRICE|AUCTION}", "version": VERSION}


def classify_listing(card: dict[str, Any], listing: dict[str, Any]) -> dict[str, Any]:
    title = str(listing.get("title") or "")
    nt = normalize(title)
    if ACCESSORY.search(title): state = "ACCESSORY"
    elif SEALED.search(title): state = "SEALED_PRODUCT"
    elif LOT.search(title): state = "LOT_OR_BUNDLE"
    elif GRADED.search(title): state = "GRADED"
    elif NON_ENGLISH.search(title): state = "NON_ENGLISH"
    elif POOR_CONDITION.search(title): state = "RAW_NON_NM"
    else:
        name_tokens = [x for x in normalize(card["card_name"]).split() if len(x) > 1]
        name_ok = all(x in nt.split() for x in name_tokens)
        number_ok = any(re.search(rf"(?<!\d){re.escape(x)}(?!\d)", nt) for x in number_forms(card.get("card_number")))
        set_tokens = [x for x in normalize(card["set_name"]).split() if len(x) > 2 and x not in {"pokemon", "card"}]
        set_ok = bool(set_tokens) and sum(x in nt.split() for x in set_tokens) >= max(1, math.ceil(len(set_tokens) * .6))
        if name_ok and number_ok and set_ok: state = "EXACT_MATCH"
        elif name_ok and number_ok: state = "LIKELY_MATCH"
        elif name_ok and (number_ok or set_ok): state = "AMBIGUOUS"
        else: state = "WRONG_CARD"
    condition = normalize(listing.get("condition"))
    condition_bad = any(x in condition.split() for x in ("poor", "damaged", "graded"))
    raw_condition = "RAW_ELIGIBLE_CONDITION" if state in {"EXACT_MATCH", "LIKELY_MATCH"} and not condition_bad else "INELIGIBLE_OR_UNKNOWN"
    confidence = {"EXACT_MATCH": .98, "LIKELY_MATCH": .80, "AMBIGUOUS": .50}.get(state, 0.0)
    return {"match_state": state, "match_confidence": confidence, "raw_condition_state": raw_condition,
            "evidence": {"title": title, "condition": listing.get("condition"), "item_id": listing.get("itemId")}}


def aggregate(listings: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = [x for x in listings if x["match_state"] == "EXACT_MATCH" and x["raw_condition_state"] == "RAW_ELIGIBLE_CONDITION"]
    prices = sorted(float(x["price"]) for x in accepted if x.get("price") is not None)
    sellers = [x["seller_id"] for x in accepted if x.get("seller_id")]
    buying = Counter(y for x in accepted for y in x.get("buying_options", []))
    trim = max(0, int(len(prices) * .1)); trimmed = prices[trim:len(prices)-trim] if trim and len(prices) > 2 * trim else prices
    q = lambda f: prices[min(len(prices)-1, round((len(prices)-1)*f))] if prices else None
    mean = statistics.mean(prices) if prices else None
    return {"exact_match_listing_count": len(accepted), "unique_seller_count": len(set(sellers)) if sellers else None,
            "median_listing_price": statistics.median(prices) if prices else None,
            "trimmed_mean_listing_price": statistics.mean(trimmed) if trimmed else None,
            "min_listing_price": min(prices) if prices else None, "p25_listing_price": q(.25), "p75_listing_price": q(.75),
            "listing_price_iqr": (q(.75)-q(.25)) if prices else None,
            "listing_price_cv": (statistics.pstdev(prices)/mean) if len(prices)>1 and mean else None,
            "fixed_price_count": buying["FIXED_PRICE"], "auction_count": buying["AUCTION"],
            "seller_concentration_available": bool(sellers)}
