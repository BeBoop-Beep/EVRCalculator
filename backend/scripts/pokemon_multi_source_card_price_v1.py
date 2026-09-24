"""P5B: frozen multi-source Pokemon card price authority (TCGplayer + eBayActiveAsk), derived shadow.

Selection/fallback only. There is deliberately NO numeric blend or calibration: the selected price is
always exactly one provider's value (TCGPLAYER or EBAY_ACTIVE_ASK) or absent. The result is a DERIVED
authority; it is never written to provider observation/event/current tables and never replaces
pokemon_canonical_card_market_prices_latest.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Mapping

POLICY_VERSION = "pokemon_multi_source_card_price_v1"
EBAY_SOURCE = "eBayActiveAsk"
EBAY_ESTIMATOR_VERSION = "ebay_active_ask_lower3_seller_median_v1"
TCG_SOURCE = "TCGPlayer"

# TCG freshness contract (age = market_date - last observed date, in days).
# Live distribution 2026-09-20: 99.02% of 19,813 priced cards are <=1 day old (daily scrape cadence);
# a thin 2..7 day shoulder (13 cards) then a >=8 day long tail (181 cards, most >30 days).
FRESH_MAX_AGE_DAYS = 1
AGING_MAX_AGE_DAYS = 7

# Source-agreement contract. Anchored to the frozen eBay estimator's own sampling noise: the shift in the
# lower-three median when any single contributing seller is removed (25 paired cards: P75=0.084, max=0.348),
# plus a dollar tolerance for shipping-inclusive landed asks vs TCGplayer Market Price (P90 of shipping on
# eligible sub-$5 listings = $1.51, n=76).
AGREE_MAX_PCT = Decimal("0.08")
MODERATE_MAX_PCT = Decimal("0.35")
SHIPPING_TOLERANCE_USD = Decimal("1.51")

FRESHNESS_STATES = ("FRESH", "AGING", "STALE", "MISSING")
AGREEMENT_STATES = ("AGREE", "MODERATE_DISAGREEMENT", "SEVERE_DISAGREEMENT", "SINGLE_SOURCE_ONLY")
DECISION_STATES = (
    "TCGPLAYER_PRIMARY", "TCGPLAYER_PRIMARY_EBAY_CORROBORATED",
    "TCGPLAYER_PRIMARY_EBAY_MODERATE_DISAGREEMENT", "TCGPLAYER_PRIMARY_SOURCE_DISAGREEMENT",
    "TCGPLAYER_AGING_RETAINED", "TCGPLAYER_STALE_RETAINED",
    "EBAY_ACTIVE_ASK_FALLBACK", "UNPRICED",
)
SELECTED_SOURCES = ("TCGPLAYER", "EBAY_ACTIVE_ASK")
CENT = Decimal("0.01")


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                                     default=str).encode()).hexdigest()


def _money(value: Any) -> Decimal | None:
    if value is None:
        return None
    result = Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
    return result if result > 0 else None


def tcg_age_days(observed: Any, market_date: date) -> int | None:
    if observed is None:
        return None
    return (market_date - date.fromisoformat(str(observed)[:10])).days


def classify_freshness(age_days: int | None, price: Any) -> str:
    if _money(price) is None or age_days is None:
        return "MISSING"
    if age_days <= FRESH_MAX_AGE_DAYS:
        return "FRESH"
    return "AGING" if age_days <= AGING_MAX_AGE_DAYS else "STALE"


def classify_agreement(tcg_price: Any, ebay_price: Any) -> dict[str, Any]:
    """Agreement is descriptive, not a claim that either source is correct."""
    tcg, ebay = _money(tcg_price), _money(ebay_price)
    if tcg is None or ebay is None:
        return {"state": "SINGLE_SOURCE_ONLY", "ratio": None, "difference_pct": None, "difference_usd": None}
    diff = ebay - tcg
    pct = diff / tcg
    absolute = abs(diff)
    if absolute <= SHIPPING_TOLERANCE_USD or abs(pct) <= AGREE_MAX_PCT:
        state = "AGREE"
    elif abs(pct) <= MODERATE_MAX_PCT:
        state = "MODERATE_DISAGREEMENT"
    else:
        state = "SEVERE_DISAGREEMENT"
    return {"state": state, "ratio": (ebay / tcg).quantize(Decimal("0.0001")),
            "difference_pct": pct.quantize(Decimal("0.0001")), "difference_usd": diff.quantize(CENT)}


def ebay_usable(tcg: Mapping[str, Any] | None, ebay: Mapping[str, Any] | None) -> tuple[bool, str]:
    if not ebay or _money(ebay.get("estimated_price")) is None:
        return False, "EBAY_NO_NUMERIC_ESTIMATE"
    if ebay.get("estimator_version") != EBAY_ESTIMATOR_VERSION:
        return False, "EBAY_ESTIMATOR_VERSION_MISMATCH"
    if ebay.get("depth_state") != "SUFFICIENT":
        return False, f"EBAY_DEPTH_{ebay.get('depth_state')}"
    if not ebay.get("card_variant_id"):
        return False, "EBAY_VARIANT_UNRESOLVED"
    if tcg and tcg.get("card_variant_id") and tcg["card_variant_id"] != ebay["card_variant_id"]:
        return False, "EBAY_VARIANT_MISMATCH"
    return True, "EBAY_SUFFICIENT"


def decide(tcg: Mapping[str, Any] | None, ebay: Mapping[str, Any] | None, market_date: date,
           condition_id: str | None = None) -> dict[str, Any]:
    """One deterministic decision row. `tcg`: canonical TCG price row; `ebay`: frozen estimator output."""
    tcg_price = _money(tcg.get("market_price")) if tcg else None
    age = tcg_age_days(tcg.get("captured_at"), market_date) if tcg else None
    freshness = classify_freshness(age, tcg_price)
    usable, ebay_reason = ebay_usable(tcg if tcg_price else None, ebay)
    agreement = classify_agreement(tcg_price, ebay["estimated_price"] if usable else None)
    if tcg_price is not None:
        selected_price, selected_source, variant = tcg_price, "TCGPLAYER", tcg["card_variant_id"]
        if freshness == "FRESH":
            state = {"AGREE": "TCGPLAYER_PRIMARY_EBAY_CORROBORATED",
                     "MODERATE_DISAGREEMENT": "TCGPLAYER_PRIMARY_EBAY_MODERATE_DISAGREEMENT",
                     "SEVERE_DISAGREEMENT": "TCGPLAYER_PRIMARY_SOURCE_DISAGREEMENT",
                     "SINGLE_SOURCE_ONLY": "TCGPLAYER_PRIMARY"}[agreement["state"]]
            reason = "TCG_FRESH_PRIMARY;" + ebay_reason
        else:
            state = "TCGPLAYER_AGING_RETAINED" if freshness == "AGING" else "TCGPLAYER_STALE_RETAINED"
            reason = f"TCG_{freshness}_RETAINED_NO_EBAY_OVERRIDE;" + ebay_reason
    elif usable:
        selected_price, selected_source = _money(ebay["estimated_price"]), "EBAY_ACTIVE_ASK"
        variant = ebay["card_variant_id"]
        state, reason = "EBAY_ACTIVE_ASK_FALLBACK", "TCG_MISSING_EBAY_SUFFICIENT_FALLBACK"
    else:
        selected_price = selected_source = variant = None
        state, reason = "UNPRICED", "TCG_MISSING;" + ebay_reason
    ebay_variant = ebay.get("card_variant_id") if ebay else None
    canonical_card_id = (tcg or ebay or {}).get("canonical_card_id")
    row = {
        "canonical_card_id": canonical_card_id, "card_variant_id": variant or ebay_variant,
        "condition_id": condition_id, "market_date": market_date.isoformat(),
        "selected_price": str(selected_price) if selected_price is not None else None,
        "selected_price_source": selected_source, "policy_version": POLICY_VERSION,
        "decision_state": state, "decision_reason": reason,
        "tcgplayer_price": str(tcg_price) if tcg_price is not None else None,
        "tcgplayer_date": str(tcg.get("captured_at"))[:10] if tcg and tcg.get("captured_at") else None,
        "tcgplayer_age_days": age, "tcgplayer_freshness_state": freshness,
        "ebay_price": str(_money(ebay.get("estimated_price"))) if ebay and _money(ebay.get("estimated_price")) else None,
        "ebay_market_date": ebay.get("market_date") if ebay else None,
        "ebay_seller_count": ebay.get("distinct_seller_count") if ebay else None,
        "ebay_listing_count": ebay.get("eligible_listing_count") if ebay else None,
        "ebay_depth_state": ebay.get("depth_state") if ebay else None,
        "ebay_estimator_version": ebay.get("estimator_version") if ebay else None,
        "source_ratio": str(agreement["ratio"]) if agreement["ratio"] is not None else None,
        "source_difference_pct": str(agreement["difference_pct"]) if agreement["difference_pct"] is not None else None,
        "source_agreement_state": agreement["state"],
    }
    row["input_fingerprint"] = digest({
        "policy": POLICY_VERSION, "market_date": row["market_date"], "tcg": [row["tcgplayer_price"], row["tcgplayer_date"],
        tcg.get("card_variant_id") if tcg else None], "ebay": [row["ebay_price"], row["ebay_market_date"],
        ebay_variant, row["ebay_depth_state"], row["ebay_seller_count"], row["ebay_listing_count"],
        row["ebay_estimator_version"], (ebay or {}).get("estimator_fingerprint")], "condition_id": condition_id})
    row["decision_fingerprint"] = digest({k: v for k, v in row.items() if k != "decision_fingerprint"})
    return row


def build_shadow_rows(tcg_rows: Iterable[Mapping[str, Any]], ebay_rows: Iterable[Mapping[str, Any]],
                      market_date: date, condition_id: str | None = None) -> list[dict[str, Any]]:
    """Join by canonical card (variant equality enforced inside `decide`). Deterministic and idempotent."""
    tcg_by = {str(r["canonical_card_id"]): r for r in tcg_rows}
    ebay_by = {str(r["canonical_card_id"]): r for r in ebay_rows}
    rows = [decide(tcg_by.get(cid), ebay_by.get(cid), market_date, condition_id) for cid in sorted(set(tcg_by) | set(ebay_by))]
    # The persisted grain requires a resolved variant; identity-unresolved cards are reported, not persisted.
    return [r for r in rows if r["card_variant_id"] is not None]


def frozen_contract() -> dict[str, Any]:
    return {"policy_version": POLICY_VERSION, "ebay_estimator_version": EBAY_ESTIMATOR_VERSION,
            "fresh_max_age_days": FRESH_MAX_AGE_DAYS, "aging_max_age_days": AGING_MAX_AGE_DAYS,
            "agree_max_pct": str(AGREE_MAX_PCT), "moderate_max_pct": str(MODERATE_MAX_PCT),
            "shipping_tolerance_usd": str(SHIPPING_TOLERANCE_USD), "ebay_required_depth": "SUFFICIENT",
            "decision_states": list(DECISION_STATES), "numeric_blend": False}


POLICY_FINGERPRINT = digest(frozen_contract())
