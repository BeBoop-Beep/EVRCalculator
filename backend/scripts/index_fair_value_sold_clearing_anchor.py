"""EXPLICIT_NM_SOLD_CLEARING_ANCHOR_V1 -- pure, side-effect-free research logic.

This module has NO database, network, provider, or filesystem access. It holds
only the deterministic rules so they can be unit tested and re-run offline.

Boundaries (see docs/research/index_fair_value/FV_S2_*.md):

* This is a research eligibility rule, NOT a production condition-normalization
  authority and NOT the production inDex Fair Value.
* The target TCGplayer market price is never an input to eligibility or window
  selection. ``select_anchor`` has no price-of-target parameter at all; the
  leakage guard additionally rejects any comp row that carries target-derived keys.
* Every rule fails closed: an ambiguous title is rejected, never accepted.
"""
from __future__ import annotations

import re
import statistics
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

RULE_VERSION = "EXPLICIT_NM_SOLD_CLEARING_ANCHOR_V1"
RULE_CONTRACT_VERSION = "fv_s2_explicit_nm_sold_clearing_anchor_v1.0"
EVIDENCE_SEMANTICS = "RETROSPECTIVE_BACKFILLED_EVIDENCE"
WINDOWS_DAYS: tuple[int, ...] = (7, 30, 60, 90, 180)
MIN_COMPS = 10

# Keys that would let the evaluation outcome influence anchoring.
FORBIDDEN_COMP_KEYS = frozenset({
    "target_market_price", "target_nm_market_price", "target_market_price_usd",
    "market_price", "tcgplayer_market_price", "target_price",
})

# --- exclusion reason codes (stable; part of the contract) -------------------
NOT_IN_PANEL = "NOT_IN_PANEL"
IDENTITY_NOT_EXACT = "IDENTITY_NOT_EXACT"
ATTRIBUTION_NOT_EXACT = "ATTRIBUTION_NOT_EXACT"
GRADED_FLAG = "GRADED_FLAG"
NON_USD = "NON_USD"
INVALID_PRICE = "INVALID_PRICE"
INVALID_SOLD_DATE = "INVALID_SOLD_DATE"
FUTURE_DATED = "FUTURE_DATED_SOLD_AT"
NOT_YET_COLLECTED = "NOT_COLLECTED_AS_OF_CUTOFF"
CARD_NUMBER_ABSENT = "CARD_NUMBER_NOT_IN_TITLE"
CARD_NUMBER_CONFLICT = "CARD_NUMBER_CONFLICT"
NM_CUE_ABSENT = "NO_EXPLICIT_NM"
WORSE_CONDITION = "WORSE_OR_CONFLICTING_CONDITION"
GRADE_EVIDENCE = "GRADER_OR_GRADE_EVIDENCE"
WRONG_OBJECT = "NON_CARD_OR_WRONG_OBJECT"
DUPLICATE_LISTING = "DUPLICATE_PROVIDER_LISTING"

# --- title rules -------------------------------------------------------------
_NM_CUE = re.compile(r"(?<![A-Za-z0-9])(?:nm|near[\s_-]*mint)(?![A-Za-z0-9])", re.I)
_WORSE_CONDITION = re.compile(
    r"(?<![A-Za-z0-9])(?:"
    r"lp|lightly[\s_-]*played|mp|moderately[\s_-]*played|hp|heavily[\s_-]*played|"
    r"damaged|dmg|creases?|creased|torn|water[\s_-]*damage(?:d)?"
    r")(?![A-Za-z0-9])",
    re.I,
)
# Graders that are unambiguous on their own. TAG / ACE are ordinary words and
# are only grade evidence when followed by a numeric grade.
_GRADER_NAMES = re.compile(
    r"(?<![A-Za-z0-9])(?:psa|bgs|beckett|cgc|sgc|ags)(?![A-Za-z0-9])", re.I
)
_GRADER_WITH_GRADE = re.compile(
    r"(?<![A-Za-z0-9])(?:tag|ace)[\s_-]*(?:grade[d]?[\s_:-]*)?#?\d{1,2}(?:\.\d)?(?![A-Za-z0-9])",
    re.I,
)
_GRADE_PHRASES = re.compile(
    r"(?<![A-Za-z0-9])(?:gem[\s_-]*mint|black[\s_-]*label|pristine)(?![A-Za-z0-9])", re.I
)
_WRONG_OBJECT = re.compile(
    r"(?<![A-Za-z0-9])(?:"
    r"proxy|proxies|fan[\s_-]*art|custom[\s_-]*(?:card|cards|case|cases)|"
    r"extended[\s_-]*art[\s_-]*case|no[\s_-]*card|stickers?|digital|"
    r"code[\s_-]*cards?|lots?|bundles?|repacks?|metal[\s_-]*cards?"
    r")(?![A-Za-z0-9])",
    re.I,
)
_SLASH_NUMBER = re.compile(r"(?<![0-9A-Za-z/])([0-9]{1,3})\s*/\s*([0-9]{1,3})(?![0-9])")
_HASH_NUMBER = re.compile(r"#\s*([0-9]{1,3})(?![0-9])")


def _norm_number(value: Any) -> str:
    text = str(value if value is not None else "").strip()
    stripped = text.lstrip("0")
    return stripped if stripped else ("0" if text else "")


_NUMBER_TOKEN = re.compile(r"(?<![0-9A-Za-z/])([0-9]{1,3})(?![0-9])")


def card_number_verdict(title: str, card_number: Any) -> str | None:
    """Return None when the title explicitly carries this card number.

    V1 contract ("card number explicitly occurs in the title"): the number must
    appear as a standalone numeric token -- the numerator of ``N/M``, ``#N``, or a
    bare token. It must NOT be glued to digits or letters, and a slash
    denominator never counts (so ``144/131`` does not carry card 131). Leading
    zeros are insignificant. A non-numeric card number never matches (fail closed).
    """
    target = _norm_number(card_number)
    if not target or not target.isdigit():
        return CARD_NUMBER_ABSENT
    for m in _NUMBER_TOKEN.finditer(str(title or "")):
        if _norm_number(m.group(1)) == target:
            return None
    return CARD_NUMBER_ABSENT


def title_has_conflicting_card_number(title: str, card_number: Any) -> bool:
    """True when the title also carries a DIFFERENT ``N/M`` numerator or ``#K``.

    Diagnostic / strict-mode signal only. It is not part of the V1 eligibility
    contract because the reproduced October 1 study did not apply it.
    """
    target = _norm_number(card_number)
    text = str(title or "")
    others = {_norm_number(m.group(1)) for m in _SLASH_NUMBER.finditer(text)}
    others |= {_norm_number(m.group(1)) for m in _HASH_NUMBER.finditer(text)}
    return bool(others - {target})


def title_verdict(
    title: str, card_number: Any, *, reject_conflicting_numbers: bool = False
) -> str | None:
    """Apply every title rule. Return the first exclusion code, or None if eligible."""
    text = str(title or "")
    if _GRADER_NAMES.search(text) or _GRADER_WITH_GRADE.search(text) or _GRADE_PHRASES.search(text):
        return GRADE_EVIDENCE
    if _WRONG_OBJECT.search(text):
        return WRONG_OBJECT
    if _WORSE_CONDITION.search(text):
        return WORSE_CONDITION
    number = card_number_verdict(text, card_number)
    if number is not None:
        return number
    if reject_conflicting_numbers and title_has_conflicting_card_number(text, card_number):
        return CARD_NUMBER_CONFLICT
    if not _NM_CUE.search(text):
        return NM_CUE_ABSENT
    return None


# --- comp model ---------------------------------------------------------------
def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _parse_ts(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _price(value: Any) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except Exception:
        return None
    return result if result.is_finite() and result > 0 else None


@dataclass(frozen=True)
class Comp:
    provider_listing_id: int
    price: Decimal
    sold_at: date
    collected_at: datetime | None
    ingested_at: datetime | None
    title: str


def classify_row(
    row: Mapping[str, Any],
    *,
    card_number: Any,
    observation_date: date,
    information_cutoff: datetime | None = None,
    reject_conflicting_numbers: bool = False,
) -> tuple[Comp | None, str | None]:
    """Classify one persisted sold-evidence row for one panel card.

    ``information_cutoff`` (forward replay only): rows whose ``collected_at`` is
    after the cutoff were not available at evaluation time and are excluded.
    It is None for the retrospective study, which is labeled
    RETROSPECTIVE_BACKFILLED_EVIDENCE.
    """
    leaked = FORBIDDEN_COMP_KEYS.intersection(row.keys())
    if leaked:
        raise RuntimeError(f"FV_S2_TARGET_LEAKAGE_GUARD: {sorted(leaked)}")
    if str(row.get("identity_state") or "") != "EXACT":
        return None, IDENTITY_NOT_EXACT
    if str(row.get("attribution") or "") != "exact":
        return None, ATTRIBUTION_NOT_EXACT
    if row.get("graded") is not False:
        return None, GRADED_FLAG
    if str(row.get("currency") or "") != "USD":
        return None, NON_USD
    price = _price(row.get("price"))
    if price is None:
        return None, INVALID_PRICE
    sold_at = _parse_date(row.get("sold_at"))
    if sold_at is None:
        return None, INVALID_SOLD_DATE
    if sold_at > observation_date:
        return None, FUTURE_DATED
    collected_at = _parse_ts(row.get("collected_at"))
    if information_cutoff is not None and (collected_at is None or collected_at > information_cutoff):
        return None, NOT_YET_COLLECTED
    reason = title_verdict(
        str(row.get("title") or ""), card_number,
        reject_conflicting_numbers=reject_conflicting_numbers,
    )
    if reason is not None:
        return None, reason
    try:
        listing_id = int(row["provider_listing_id"])
    except (KeyError, TypeError, ValueError):
        return None, INVALID_PRICE
    return Comp(
        provider_listing_id=listing_id, price=price, sold_at=sold_at,
        collected_at=collected_at, ingested_at=_parse_ts(row.get("ingested_at")),
        title=str(row.get("title") or ""),
    ), None


def _q(value: float | Decimal, places: str = "0.0001") -> str:
    return str(Decimal(str(value)).quantize(Decimal(places), rounding=ROUND_HALF_EVEN))


def window_start(observation_date: date, window_days: int, extra_days: int = 0) -> date:
    """First sale day inside a trailing window of exactly ``window_days`` calendar days.

    ``extra_days`` > 0 widens the boundary (sensitivity diagnostics only).
    """
    return observation_date - timedelta(days=window_days - 1 + extra_days)


def _stats(comps: Sequence[Comp]) -> dict[str, Any]:
    prices = sorted(c.price for c in comps)
    median = statistics.median(prices)
    floats = np.array([float(p) for p in prices], dtype=float)
    q1, q3 = (float(x) for x in np.percentile(floats, [25, 75]))
    mad = statistics.median(sorted(abs(p - median) for p in prices))
    days = sorted(c.sold_at for c in comps)
    return {
        "median": _q(median),
        "median_usd_2dp": str(median.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "q1": round(q1, 4), "q3": round(q3, 4), "iqr": round(q3 - q1, 4),
        "mad": _q(mad),
        "min": str(prices[0]), "max": str(prices[-1]),
        "distinct_sale_days": len({c.sold_at for c in comps}),
        "oldest_sold_at": days[0].isoformat(), "newest_sold_at": days[-1].isoformat(),
    }


def select_anchor(
    comps: Iterable[Comp],
    observation_date: date,
    *,
    windows: Sequence[int] = WINDOWS_DAYS,
    min_comps: int = MIN_COMPS,
    boundary_extra_days: int = 0,
) -> dict[str, Any]:
    """Shortest trailing window with >= ``min_comps`` eligible comps; median price.

    Inputs are comps and a date only. There is intentionally no parameter that
    could carry a target price.
    """
    pool = sorted(comps, key=lambda c: (c.sold_at, c.provider_listing_id))
    counts: dict[str, int] = {}
    chosen: tuple[int, list[Comp]] | None = None
    for w in windows:
        start = window_start(observation_date, w, boundary_extra_days)
        inside = [c for c in pool if start <= c.sold_at <= observation_date]
        counts[str(w)] = len(inside)
        if chosen is None and len(inside) >= min_comps:
            chosen = (w, inside)
    result: dict[str, Any] = {
        "rule_version": RULE_VERSION,
        "observation_date": observation_date.isoformat(),
        "min_comps": min_comps,
        "eligible_counts_by_window": counts,
    }
    if chosen is None:
        result.update({"status": "INSUFFICIENT_COMPS", "selected_window_days": None,
                       "comp_count": 0, "anchor_usd": None})
        return result
    window, inside = chosen
    stats = _stats(inside)
    result.update({
        "status": "ANCHORED", "selected_window_days": window, "comp_count": len(inside),
        "anchor_usd": float(Decimal(stats["median"])), **stats,
        "comp_listing_ids": [c.provider_listing_id for c in inside],
    })
    return result


def build_card_result(
    rows: Sequence[Mapping[str, Any]],
    *,
    card_number: Any,
    observation_date: date,
    information_cutoff: datetime | None = None,
    reject_conflicting_numbers: bool = False,
    boundary_extra_days: int = 0,
) -> dict[str, Any]:
    """Classify all persisted rows for one card, then select the anchor."""
    comps: list[Comp] = []
    exclusions: Counter[str] = Counter()
    seen: set[tuple[Any, Any]] = set()
    for row in rows:
        key = (row.get("provider_card_id"), row.get("provider_listing_id"))
        if key in seen:
            exclusions[DUPLICATE_LISTING] += 1
            continue
        seen.add(key)
        comp, reason = classify_row(
            row, card_number=card_number, observation_date=observation_date,
            information_cutoff=information_cutoff,
            reject_conflicting_numbers=reject_conflicting_numbers,
        )
        if comp is None:
            exclusions[str(reason)] += 1
        else:
            comps.append(comp)
    anchor = select_anchor(comps, observation_date, boundary_extra_days=boundary_extra_days)
    # Provenance of the evidence timing (RETROSPECTIVE unless a cutoff was enforced).
    if anchor.get("comp_listing_ids"):
        ids = set(anchor["comp_listing_ids"])
        used = [c for c in comps if c.provider_listing_id in ids]
        collected = [c.collected_at for c in used if c.collected_at]
        anchor["collected_at_min"] = min(collected).isoformat() if collected else None
        anchor["collected_at_max"] = max(collected).isoformat() if collected else None
    anchor["selected_comps_with_conflicting_card_number"] = sum(
        1 for c in comps
        if c.provider_listing_id in set(anchor.get("comp_listing_ids") or [])
        and title_has_conflicting_card_number(c.title, card_number)
    )
    anchor.update({
        "rows_seen": len(rows),
        "eligible_rows_all_time": len(comps),
        "exclusion_counts": dict(sorted(exclusions.items())),
        "evidence_semantics": (
            "AS_KNOWN_AT_CUTOFF" if information_cutoff is not None else EVIDENCE_SEMANTICS
        ),
    })
    return anchor
