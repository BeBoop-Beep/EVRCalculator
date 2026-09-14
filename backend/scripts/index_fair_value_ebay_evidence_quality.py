"""Provider-neutral, non-probabilistic evidence-quality contract for eBay active asks.

This assigns a typed status -- INSUFFICIENT / LOW / MEDIUM / HIGH -- to a
bundle of active-ask evidence for one target instrument. It is NOT a
probability of correctness and it is NOT a statement that any ask equals a
sale. It must never be described as "N% confidence" unless calibration
someday supports that (it does not here).

Because ebay_d3_matcher_v3 is NOT production-certified
(see ebay_d3_v3_final_certification_manifest.json:
"EBAY_IDENTITY_MATCHER_V3_NOT_VALIDATED"), matcher-derived identity signal
alone can never earn the HIGH status here -- it is capped at MEDIUM until an
independently certified matcher version exists.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence


class EvidenceQuality(str, Enum):
    INSUFFICIENT = "INSUFFICIENT"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

    def __lt__(self, other: "EvidenceQuality") -> bool:
        order = [EvidenceQuality.INSUFFICIENT, EvidenceQuality.LOW, EvidenceQuality.MEDIUM, EvidenceQuality.HIGH]
        return order.index(self) < order.index(other)


MIN_ACCEPTED_FOR_MEDIUM = 5
MIN_ACCEPTED_FOR_HIGH = 15
MIN_SELLERS_FOR_HIGH = 5
MAX_SELLER_CONCENTRATION_FOR_HIGH = 0.5  # top seller's share of accepted listings
MAX_PRICE_CV_FOR_HIGH = 0.60  # coefficient of variation on accepted prices
MAX_EVIDENCE_AGE_HOURS_FOR_HIGH = 48


@dataclass(frozen=True)
class EvidenceQualityAssessment:
    status: EvidenceQuality
    reasons: list[str]
    caps_applied: list[str]
    features: dict[str, Any]


def _seller_concentration(sellers: Sequence[str | None]) -> float | None:
    named = [s for s in sellers if s]
    if not named:
        return None
    from collections import Counter

    counts = Counter(named)
    top = counts.most_common(1)[0][1]
    return top / len(named)


def _price_cv(prices: Sequence[float]) -> float | None:
    values = [p for p in prices if p is not None]
    if len(values) < 2:
        return None
    mean = statistics.mean(values)
    if not mean:
        return None
    return statistics.pstdev(values) / mean


def assess_evidence_quality(
    accepted_listings: Sequence[Mapping[str, Any]],
    *,
    matcher_certified: bool,
    ambiguous_count: int = 0,
    rejected_count: int = 0,
    evidence_age_hours: float | None = None,
    target_condition_known: bool = True,
) -> EvidenceQualityAssessment:
    """`accepted_listings` are raw evidence rows already filtered to matcher-accepted
    (HIGH_CONFIDENCE/MEDIUM_CONFIDENCE) rows for one target instrument. Each row is
    expected to carry `price_value`, `seller_username`, `condition`.
    """
    reasons: list[str] = []
    caps: list[str] = []

    n_accepted = len(accepted_listings)
    total_seen = n_accepted + ambiguous_count + rejected_count
    conditions_known = sum(1 for r in accepted_listings if r.get("condition") is not None)
    condition_unknown_rate = 1 - (conditions_known / n_accepted) if n_accepted else 1.0
    prices = [r.get("price_value") for r in accepted_listings if r.get("price_value") is not None]
    sellers = [r.get("seller_username") for r in accepted_listings]
    concentration = _seller_concentration(sellers)
    price_cv = _price_cv(prices)
    unique_sellers = len({s for s in sellers if s})
    ambiguous_rate = ambiguous_count / total_seen if total_seen else 0.0

    features = {
        "accepted_count": n_accepted,
        "unique_seller_count": unique_sellers,
        "seller_concentration": concentration,
        "price_cv": price_cv,
        "condition_unknown_rate": round(condition_unknown_rate, 4),
        "ambiguous_rate": round(ambiguous_rate, 4),
        "evidence_age_hours": evidence_age_hours,
        "matcher_certified": matcher_certified,
    }

    if n_accepted < MIN_ACCEPTED_FOR_MEDIUM:
        reasons.append(f"only {n_accepted} accepted listings, below medium floor {MIN_ACCEPTED_FOR_MEDIUM}")
        return EvidenceQualityAssessment(EvidenceQuality.INSUFFICIENT, reasons, caps, features)

    if not target_condition_known or condition_unknown_rate > 0.5:
        caps.append("condition_unknown_or_mostly_unknown -> capped at LOW")
        status = EvidenceQuality.LOW
    elif ambiguous_rate > 0.3:
        caps.append("high ambiguous-identity rate -> capped at LOW")
        status = EvidenceQuality.LOW
    else:
        status = EvidenceQuality.MEDIUM

    if n_accepted < MIN_ACCEPTED_FOR_HIGH:
        reasons.append(f"accepted_count {n_accepted} below HIGH floor {MIN_ACCEPTED_FOR_HIGH}")
    elif unique_sellers < MIN_SELLERS_FOR_HIGH:
        reasons.append(f"unique_seller_count {unique_sellers} below HIGH floor {MIN_SELLERS_FOR_HIGH}")
    elif concentration is not None and concentration > MAX_SELLER_CONCENTRATION_FOR_HIGH:
        caps.append(f"seller_concentration {concentration:.2f} exceeds cap -> not HIGH")
    elif price_cv is not None and price_cv > MAX_PRICE_CV_FOR_HIGH:
        caps.append(f"price_cv {price_cv:.2f} exceeds cap -> not HIGH")
    elif evidence_age_hours is not None and evidence_age_hours > MAX_EVIDENCE_AGE_HOURS_FOR_HIGH:
        caps.append(f"evidence_age_hours {evidence_age_hours} exceeds cap -> not HIGH")
    elif not matcher_certified:
        caps.append("matcher_version not production-certified -> capped at MEDIUM")
    elif status == EvidenceQuality.MEDIUM:
        status = EvidenceQuality.HIGH

    return EvidenceQualityAssessment(status, reasons, caps, features)
