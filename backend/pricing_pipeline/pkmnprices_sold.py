"""Normalization and identity rules for PkmnPrices eBay sold evidence.

Important boundary: an ungraded eBay sale is NOT assumed to be Near Mint.
PkmnPrices sold rows currently carry printing attribution but no raw-card
condition field, so sold evidence is research/Fair-Value input only until an
independent condition-equivalence contract is validated.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

ATTRIBUTIONS = {"exact", "shared", "unknown"}

_EDITION_ALIASES = (
    ("1st-edition", re.compile(r"\b(?:1st|first)\s*edition\b", re.I)),
    ("shadowless", re.compile(r"\bshadowless\b", re.I)),
    ("unlimited", re.compile(r"\bunlimited\b", re.I)),
)
_PRINTING_ALIASES = (
    ("reverse-holo", re.compile(r"\breverse\s*holo(?:foil)?\b", re.I)),
    ("holo", re.compile(r"\bholo(?:foil)?\b", re.I)),
    ("non-holo", re.compile(r"\b(?:non[- ]?holo|normal)\b", re.I)),
)


def _money(value: Any) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("invalid sold price") from exc
    if not result.is_finite() or result <= 0 or result.as_tuple().exponent < -2:
        raise ValueError("invalid sold price")
    return result.quantize(Decimal("0.01"))


def parse_provider_variant(value: Any) -> dict[str, str | None]:
    text = str(value or "").strip()
    edition = next((name for name, pattern in _EDITION_ALIASES if pattern.search(text)), None)
    printing = next((name for name, pattern in _PRINTING_ALIASES if pattern.search(text)), None)
    return {"raw": text or None, "edition": edition, "printing_type": printing}


def _norm(value: Any) -> str | None:
    text = str(value or "").strip().casefold().replace("_", "-")
    return text or None


def resolve_internal_variant(
    provider_variant: Any,
    internal_variants: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Resolve only when provider dimensions select exactly one internal variant."""
    parsed = parse_provider_variant(provider_variant)
    candidates = [dict(row) for row in internal_variants if row.get("id")]
    if parsed["edition"]:
        candidates = [row for row in candidates if _norm(row.get("edition")) == parsed["edition"]]
    if parsed["printing_type"]:
        candidates = [row for row in candidates if _norm(row.get("printing_type")) == parsed["printing_type"]]
    if len(candidates) == 1:
        return {"state": "EXACT", "card_variant_id": str(candidates[0]["id"]), "parsed": parsed}
    if not candidates:
        return {"state": "NO_MATCH", "card_variant_id": None, "parsed": parsed}
    return {"state": "AMBIGUOUS", "card_variant_id": None, "parsed": parsed}


def normalize_sold_listing(
    row: Mapping[str, Any],
    *,
    provider_card_id: str | int,
    canonical_card_id: str,
    internal_variants: Sequence[Mapping[str, Any]],
    collected_at: str,
) -> dict[str, Any]:
    listing_id = row.get("id")
    if listing_id is None:
        raise ValueError("sold listing id missing")
    price = _money(row.get("price"))
    currency = str(row.get("currency") or "").upper()
    if currency not in {"USD", "EUR"}:
        raise ValueError("unsupported sold currency")
    attribution = str(row.get("attribution") or "unknown").casefold()
    if attribution not in ATTRIBUTIONS:
        raise ValueError("invalid sold attribution")
    sold_at = str(row.get("sold_at") or "")[:10]
    try:
        date.fromisoformat(sold_at)
    except ValueError as exc:
        raise ValueError("invalid sold_at") from exc
    ingested_at = str(row.get("ingested_at") or "")
    if ingested_at:
        try:
            datetime.fromisoformat(ingested_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("invalid ingested_at") from exc

    grader = str(row.get("grader") or "").strip() or None
    # Grades are opaque provider identifiers. In particular, half grades must
    # never pass through float conversion ("8.5" is not "8.50").
    grade = str(row.get("grade") or "").strip() or None
    grade_qualifier = str(row.get("grade_qualifier") or "").strip() or None
    graded = bool(grader or grade or grade_qualifier)
    resolution = resolve_internal_variant(row.get("variant"), internal_variants)
    exact_identity = attribution == "exact" and resolution["state"] == "EXACT"
    fair_value_signal_eligible = bool(exact_identity and not graded and currency == "USD")
    if graded:
        exclusion = "GRADED"
    elif currency != "USD":
        exclusion = "NON_USD"
    elif attribution != "exact":
        exclusion = "ATTRIBUTION_" + attribution.upper()
    elif resolution["state"] != "EXACT":
        exclusion = "VARIANT_" + resolution["state"]
    else:
        exclusion = None

    return {
        "provider_listing_id": int(listing_id),
        "provider_card_id": int(provider_card_id),
        "canonical_card_id": str(canonical_card_id),
        "card_variant_id": resolution["card_variant_id"],
        "title": str(row.get("title") or ""),
        "price": str(price),
        "currency": currency,
        "grader": grader,
        "grade": grade,
        "grade_qualifier": grade_qualifier,
        "graded": graded,
        "provider_variant": str(row.get("variant") or "").strip() or None,
        "attribution": attribution,
        "sold_at": sold_at,
        "ingested_at": ingested_at or None,
        "listing_url": str(row.get("listing_url") or "").strip() or None,
        "identity_state": resolution["state"],
        "fair_value_signal_eligible": fair_value_signal_eligible,
        # Explicit fail-closed boundary: the sold endpoint has no raw-card condition.
        "set_value_nm_eligible": False,
        "condition_state": "UNKNOWN",
        "exclusion_reason": exclusion,
        "collected_at": collected_at,
        "provider_payload": dict(row),
    }
