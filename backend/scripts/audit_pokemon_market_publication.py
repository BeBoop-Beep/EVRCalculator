"""Read-only audit: is every public market surface actually on the promoted date?

Why this exists
---------------
The pipeline already verifies simulation freshness and Opening Profit vs Cost
(``audit_opening_analytics_publication.py``), but only for the small set of
simulation-supported sets. Nothing verified the OTHER user-facing market surfaces
— Set Value, Top Chase, Sealed Market, card prices, and the set-page header — for
every publication-required set. A section can silently freeze a generation behind
while the header advertises the newer date, and the daily job would still send a
success notification.

Two rules shape everything here:

* **The authoritative target date is the PROMOTED batch market date**, never the
  machine's wall clock. A job that runs after midnight, or on a box in another
  timezone, must audit the date the pipeline actually published.
* **Carried-forward points cannot establish freshness.** Copying yesterday's
  value onto today's date and calling it published is precisely the failure this
  audit exists to detect, so a carried-forward point is only ever accepted where
  it is explicitly allowed AND retains its real ``sourceDate``.

This module never writes. It reports, and it returns nonzero so the caller can
refuse to announce success.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

AUDIT_TAG = "[market-publication-audit]"
CANONICAL_DASHBOARD_WINDOW = "365d"

# Section identifiers. Callers branch on these, never on prose.
SECTION_SET_VALUE = "set_value"
SECTION_TOP_CHASE = "top_chase"
SECTION_OPENING_PROFIT_VS_COST = "opening_profit_vs_cost"
SECTION_SEALED_MARKET = "sealed_market"
SECTION_CARD_PRICES = "card_prices"
SECTION_HEADER_SUMMARY = "header_summary"

ALL_SECTIONS: Tuple[str, ...] = (
    SECTION_SET_VALUE,
    SECTION_TOP_CHASE,
    SECTION_OPENING_PROFIT_VS_COST,
    SECTION_SEALED_MARKET,
    SECTION_CARD_PRICES,
    SECTION_HEADER_SUMMARY,
)

MIN_GRAPH_POINTS = 2


# --------------------------------------------------------------------------
# Pure helpers
# --------------------------------------------------------------------------
def _to_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _date_key(value: Any) -> Optional[str]:
    text = _to_text(value)
    if not text:
        return None
    candidate = text[:10]
    return candidate if len(candidate) == 10 and candidate[4] == "-" and candidate[7] == "-" else None


def _is_carried_forward(point: Dict[str, Any]) -> bool:
    return bool(point.get("isCarriedForward") or point.get("is_carried_forward"))


def _source_date(point: Dict[str, Any]) -> Optional[str]:
    return _date_key(point.get("sourceDate") or point.get("source_date"))


def _finite(value: Any) -> Optional[float]:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if numeric == numeric else None  # NaN check


def _points(history: Any) -> List[Dict[str, Any]]:
    return [point for point in (history or []) if isinstance(point, dict)] if isinstance(history, list) else []


def latest_real_point_date(history: Any, *, value_keys: Sequence[str]) -> Optional[str]:
    """Latest date carrying a REAL (not carried-forward) value."""
    latest: Optional[str] = None
    for point in _points(history):
        if _is_carried_forward(point):
            continue
        date_key = _date_key(point.get("date") or point.get("snapshot_date"))
        if not date_key:
            continue
        if any(_finite(point.get(key)) is not None for key in value_keys):
            if latest is None or date_key > latest:
                latest = date_key
    return latest


def latest_any_point_date(history: Any) -> Optional[str]:
    latest: Optional[str] = None
    for point in _points(history):
        date_key = _date_key(point.get("date") or point.get("snapshot_date"))
        if date_key and (latest is None or date_key > latest):
            latest = date_key
    return latest


def _as_obj(value: Any) -> Dict[str, Any]:
    """Tolerant JSON-object coercion.

    Snapshot columns are jsonb, but a client may hand back an already-decoded
    dict or a raw string. A non-object is reported as empty rather than raising —
    this audit must never fail on shape, only report.
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


def _dig(obj: Any, path: str) -> Any:
    """Read a dotted path out of nested JSON objects."""
    current: Any = obj
    for segment in path.split("."):
        current = _as_obj(current).get(segment)
        if current is None:
            return None
    return current


def _first_date_at(obj: Any, paths: Sequence[str]) -> Optional[str]:
    """First parseable date found along an ordered list of contract paths."""
    for path in paths:
        date_key = _date_key(_dig(obj, path))
        if date_key:
            return date_key
    return None


# Ordered contract paths for the CARDS snapshot's own market date. The pricing
# contract is authoritative; the shared movement/market as-of date is the
# coordinated fallback written by pokemon_snapshot_builders.with_snapshot_meta.
CARDS_SNAPSHOT_DATE_PATHS: Tuple[str, ...] = (
    "meta.pricingContract.latestMarketDate",
    "meta.snapshot.marketAsOfDate",
    "meta.snapshot.movementAsOfDate",
    "meta.marketAsOfDate",
    "latestMarketDate",
    "marketDate",
)

# Ordered contract paths for the SET PAGE snapshot's generation date.
PAGE_SNAPSHOT_DATE_PATHS: Tuple[str, ...] = (
    "meta.snapshot.marketAsOfDate",
    "meta.snapshot.movementAsOfDate",
    "meta.asOfDate",
    "marketSummary.latestMarketDate",
    "marketSummary.marketDate",
    "titleCard.marketAsOfDate",
    "titleCard.asOfDate",
)

# Ordered contract paths for the DISPLAYED set-value summary number. Compared
# only when one of these actually exists — see `_audit_set_value`.
DISPLAYED_SET_VALUE_PATHS: Tuple[str, ...] = (
    "marketSummary.setValue",
    "marketSummary.set_value",
    "marketSummary.latestSetValue",
    "summary.setValue",
    "setValue",
)


def cards_snapshot_market_date(cards_row: Optional[Dict[str, Any]]) -> Optional[str]:
    """The Cards snapshot's OWN authoritative market date.

    Derived from its payload/meta contract. The market-dashboard row's
    ``latest_market_date`` is deliberately NOT consulted: using a different
    table's date as proof that this one is current is precisely how a frozen
    Cards snapshot passed the audit while the dashboard advanced.
    """
    if not cards_row:
        return None
    payload = _as_obj(cards_row.get("payload_json"))
    observed = _first_date_at(payload, CARDS_SNAPSHOT_DATE_PATHS)
    if observed:
        return observed

    # Last resort: the newest per-card price date actually published in the row.
    cards = cards_row.get("cards_json")
    cards = cards if isinstance(cards, list) else payload.get("cards")
    latest: Optional[str] = None
    for card in cards if isinstance(cards, list) else []:
        if not isinstance(card, dict):
            continue
        for key in ("priceUpdatedAt", "priceAsOf", "marketDate", "priceSourceDate"):
            date_key = _date_key(card.get(key))
            if date_key and (latest is None or date_key > latest):
                latest = date_key
    return latest


def page_snapshot_generation_date(page_row: Optional[Dict[str, Any]]) -> Optional[str]:
    """The set-page/header snapshot's own advertised generation date."""
    if not page_row:
        return None
    observed = _first_date_at(
        {
            "meta": _dig(page_row.get("payload_json"), "meta") or {},
            "marketSummary": _as_obj(page_row.get("market_summary_json")),
            "titleCard": _as_obj(page_row.get("title_card_json")),
        },
        PAGE_SNAPSHOT_DATE_PATHS,
    )
    if observed:
        return observed
    # `as_of` is the simulation run date the page header is generated from.
    return _date_key(page_row.get("as_of"))


def displayed_set_value(page_row: Optional[Dict[str, Any]]) -> Optional[float]:
    """The set-value number the page actually displays, when it publishes one.

    Returns ``None`` when no such field exists, so the caller can SKIP the
    comparison explicitly instead of silently comparing against an absent (never
    selected) column — the defect this replaces.
    """
    if not page_row:
        return None
    source = {
        "marketSummary": _as_obj(page_row.get("market_summary_json")),
        "summary": _dig(page_row.get("payload_json"), "summary") or {},
        "setValue": _dig(page_row.get("payload_json"), "setValue"),
    }
    for path in DISPLAYED_SET_VALUE_PATHS:
        value = _finite(_dig(source, path))
        if value is not None:
            return value
    return None


def set_has_supported_sealed_product(product_names: Sequence[Any]) -> bool:
    """Reuse the sealed snapshot builder's own mapping contract.

    A set can carry a sealed URL and still publish NO sealed section: the builder
    only emits products whose classified family is overview-eligible. Treating
    "has any sealed URL" as "owes a sealed section" made the audit demand a
    section that could never exist.
    """
    from backend.domain.pokemon.sealed_product_classifier import classify_sealed_product

    for name in product_names or []:
        try:
            if classify_sealed_product(name).get("isOverviewEligible"):
                return True
        except Exception:  # pragma: no cover - a broken name must not hide the rest
            continue
    return False


# --------------------------------------------------------------------------
# Verdict types
# --------------------------------------------------------------------------
@dataclass
class SectionVerdict:
    section: str
    applicable: bool = True
    passed: bool = True
    observed_date: Optional[str] = None
    detail: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "section": self.section,
            "applicable": self.applicable,
            "passed": self.passed,
            "observed_date": self.observed_date,
            "detail": self.detail,
        }


@dataclass
class MarketSetAuditRow:
    canonical_key: Optional[str]
    set_id: Optional[str]
    set_name: Optional[str]
    sections: List[SectionVerdict] = field(default_factory=list)

    @property
    def failed_sections(self) -> List[str]:
        return [v.section for v in self.sections if v.applicable and not v.passed]

    @property
    def passed(self) -> bool:
        return not self.failed_sections

    def to_dict(self) -> Dict[str, Any]:
        return {
            "canonical_key": self.canonical_key,
            "set_id": self.set_id,
            "set_name": self.set_name,
            "passed": self.passed,
            "failed_sections": self.failed_sections,
            "sections": [v.to_dict() for v in self.sections],
        }


@dataclass
class MarketAuditReport:
    market_date: Optional[str]
    rows: List[MarketSetAuditRow] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def passed(self) -> bool:
        # An unreadable authority is a failure, never a pass (fail-closed).
        if self.error is not None:
            return False
        if not self.rows:
            return False
        return all(row.passed for row in self.rows)

    @property
    def failed_rows(self) -> List[MarketSetAuditRow]:
        return [row for row in self.rows if not row.passed]

    def to_dict(self) -> Dict[str, Any]:
        failed_by_section: Dict[str, List[str]] = {section: [] for section in ALL_SECTIONS}
        for row in self.failed_rows:
            for section in row.failed_sections:
                failed_by_section.setdefault(section, []).append(row.canonical_key or row.set_id or "?")

        return {
            "market_date": self.market_date,
            "passed": self.passed,
            "error": self.error,
            "set_count": len(self.rows),
            "failed_set_count": len(self.failed_rows),
            "failed_sets": [row.canonical_key or row.set_id for row in self.failed_rows],
            "failed_by_section": {k: v for k, v in failed_by_section.items() if v},
            "sets": [row.to_dict() for row in self.rows],
        }


# --------------------------------------------------------------------------
# Per-section pure checks
# --------------------------------------------------------------------------
def _audit_set_value(
    market_date: str,
    value_history: Any,
    page_row: Optional[Dict[str, Any]] = None,
) -> SectionVerdict:
    verdict = SectionVerdict(section=SECTION_SET_VALUE)
    latest = latest_any_point_date(value_history)
    verdict.observed_date = latest

    if latest is None:
        verdict.passed = False
        verdict.detail = "no published set value history"
        return verdict
    if latest < market_date:
        verdict.passed = False
        verdict.detail = f"set value history ends {latest}, behind promoted market date {market_date}"
        return verdict
    if latest > market_date:
        verdict.passed = False
        verdict.detail = f"set value history contains a future date {latest} beyond {market_date}"
        return verdict

    # The value the page displays must agree with the canonical value: the FINAL
    # standard set-value history point.
    #
    # Previously the "displayed" side was read from `dashboard_row["set_value"]`
    # / `["latest_set_value"]` — columns the dashboard projection never selects.
    # Both were therefore always None and the comparison was silently skipped,
    # so this check could never fail. It now reads the real published payload and
    # SAYS SO when no displayed field exists, instead of quietly passing.
    final_point = None
    for point in _points(value_history):
        if _date_key(point.get("date") or point.get("snapshot_date")) == market_date:
            final_point = point
    final_value = _finite((final_point or {}).get("setValue") or (final_point or {}).get("set_value"))
    displayed = displayed_set_value(page_row)

    if displayed is None:
        verdict.detail = "set page publishes no displayed set-value field; compared history only"
        return verdict
    if final_value is None:
        verdict.passed = False
        verdict.detail = f"no canonical standard set-value point published for {market_date}"
        return verdict
    if round(displayed, 2) != round(final_value, 2):
        verdict.passed = False
        verdict.detail = (
            f"displayed set value {displayed} disagrees with final published history point {final_value}"
        )
    return verdict


def _audit_top_chase(market_date: str, dashboard_row: Dict[str, Any], set_id: Optional[str]) -> SectionVerdict:
    verdict = SectionVerdict(section=SECTION_TOP_CHASE)

    cards = dashboard_row.get("top_chase_cards_json")
    cards = [c for c in cards if isinstance(c, dict)] if isinstance(cards, list) else []
    histories = dashboard_row.get("top_chase_card_histories_json")
    histories = histories if isinstance(histories, dict) else {}

    # Structural rules mirror the backend/client Top Chase contract exactly
    # (pokemon_public_snapshot_service._classify_top_chase_candidate and
    # frontend/lib/pokemon/topChasePayloadContract.mjs): a card counts only with a
    # STABLE IDENTITY and a VALID PRICE, its history must MATCH one of its identity
    # keys, and an ESTABLISHED set needs at least MIN_GRAPH_POINTS usable points.
    def _identity_keys(card: Dict[str, Any]) -> List[str]:
        return [
            key
            for key in (
                _to_text(card.get(k))
                for k in ("cardVariantId", "card_variant_id", "cardId", "card_id", "id")
            )
            if key
        ]

    # Applicability is decided on PRICE ALONE, never on identity. Deriving it
    # from identified cards let a row whose priced cards all lacked identities
    # report "no priced Top Chase cards" and pass as non-applicable — the exact
    # defect that hid a broken row. The three states are distinct:
    #   no positively priced cards at all   -> non-applicable (settled empty)
    #   priced cards missing identity       -> FAILURE
    #   priced identified cards, bad history-> FAILURE
    priced_all = [c for c in cards if (_finite(c.get("marketPrice") or c.get("market_price")) or 0) > 0]
    if not priced_all:
        verdict.applicable = False
        verdict.detail = "no priced Top Chase cards"
        return verdict

    priced = [c for c in priced_all if _identity_keys(c)]
    unidentified = len(priced_all) - len(priced)

    problems: List[str] = []
    latest_seen: Optional[str] = None
    usable_counts: List[int] = []
    end_dates: List[Optional[str]] = []

    if unidentified:
        problems.append(f"{unidentified} positively priced card(s) carry no stable identity")

    for card in priced:
        keys = _identity_keys(card)

        card_set_id = _to_text(card.get("setId") or card.get("set_id"))
        if set_id and card_set_id and card_set_id != set_id:
            problems.append(f"card {keys[:1]} carries foreign set_id {card_set_id}")
            continue

        # History must MATCH the card's own identity keys — never the longest
        # series in the row.
        series = _points(card.get("priceHistory") or card.get("price_history"))
        for key in keys:
            candidate = _points(histories.get(key))
            if len(candidate) > len(series):
                series = candidate

        usable = [p for p in series if _date_key(p.get("date")) and _finite(p.get("marketPrice") or p.get("market_price")) is not None]
        usable_counts.append(len(usable))

        # Track every priced card's end date, including short ones — proving the
        # one-point exception is CURRENT depends on it.
        card_latest = max((_date_key(p.get("date")) for p in usable), default=None)
        end_dates.append(card_latest)
        if card_latest and (latest_seen is None or card_latest > latest_seen):
            latest_seen = card_latest

        if len(usable) < MIN_GRAPH_POINTS:
            problems.append(f"card {keys[:1]} has {len(usable)} usable history point(s)")
            continue

        if card_latest > market_date:
            problems.append(f"card {keys[:1]} has future history date {card_latest}")
            continue
        if card_latest < market_date:
            problems.append(f"card {keys[:1]} history ends {card_latest}, behind {market_date}")
            continue

        final = [p for p in usable if _date_key(p.get("date")) == market_date][-1]
        if _is_carried_forward(final) and not _source_date(final):
            problems.append(f"card {keys[:1]} carried-forward point has no real sourceDate")

    verdict.observed_date = latest_seen

    # A genuinely NEW set is a settled `insufficient_history`, not a publication
    # defect — but it must be PROVEN CURRENT. A single point that does not reach
    # the promoted market date is a stalled feed and must FAIL rather than be
    # excused as a new set. Every condition is required:
    #   - every positively priced card is identified
    #   - every one has at least one point and fewer than two
    #   - every one's series ENDS on the promoted market date
    if (
        usable_counts
        and not unidentified
        and len(usable_counts) == len(priced_all)
        and min(usable_counts) >= 1
        and max(usable_counts) < MIN_GRAPH_POINTS
        and all(end_date == market_date for end_date in end_dates)
    ):
        verdict.applicable = False
        verdict.detail = (
            f"set is too new for a trend ({max(usable_counts)} of {MIN_GRAPH_POINTS} points on "
            f"every card, all current to {market_date})"
        )
        return verdict

    if problems:
        verdict.passed = False
        verdict.detail = "; ".join(problems[:5]) + (f" (+{len(problems) - 5} more)" if len(problems) > 5 else "")
    return verdict


def _audit_opvc(market_date: str, dashboard_row: Dict[str, Any], supports_simulation: bool) -> SectionVerdict:
    verdict = SectionVerdict(section=SECTION_OPENING_PROFIT_VS_COST)
    if not supports_simulation:
        verdict.applicable = False
        verdict.detail = "set does not support opening simulation"
        return verdict

    # Only a REAL point counts: the trend view carries values forward by design,
    # so a carried-forward row must never be able to establish freshness.
    latest_real = latest_real_point_date(
        dashboard_row.get("performance_vs_cost_history_json"),
        value_keys=(
            "simulatedMeanPackValueVsPackCost",
            "simulated_mean_pack_value_vs_pack_cost",
            "simulatedMedianPackValueVsPackCost",
            "simulated_median_pack_value_vs_pack_cost",
        ),
    )
    verdict.observed_date = latest_real
    if latest_real != market_date:
        verdict.passed = False
        verdict.detail = (
            f"latest REAL simulation point is {latest_real or 'nowhere'}, "
            f"not the promoted market date {market_date}"
        )
    return verdict


def _audit_sealed(market_date: str, sealed_row: Optional[Dict[str, Any]], has_sealed_product: bool) -> SectionVerdict:
    verdict = SectionVerdict(section=SECTION_SEALED_MARKET)
    if not has_sealed_product:
        # No mapped supported sealed product: nothing is owed here.
        verdict.applicable = False
        verdict.detail = "no mapped supported sealed product"
        return verdict

    if not sealed_row:
        verdict.passed = False
        verdict.detail = "set has a sealed product but no published sealed snapshot"
        return verdict

    observed = _date_key(sealed_row.get("market_date"))
    verdict.observed_date = observed
    if observed is None or observed < market_date:
        verdict.passed = False
        verdict.detail = f"sealed snapshot date {observed or 'missing'} is behind {market_date}"
    elif observed > market_date:
        verdict.passed = False
        verdict.detail = f"sealed snapshot date {observed} is ahead of promoted date {market_date}"
    return verdict


def _audit_card_prices(market_date: str, cards_row: Optional[Dict[str, Any]]) -> SectionVerdict:
    """Card prices are audited against the CARDS snapshot's own contract.

    Source: ``pokemon_set_cards_snapshot_latest``. The market-dashboard row's
    ``latest_market_date`` is no longer accepted as proof that the Cards surface
    is current — that is a different table, and using it as a proxy is how a
    frozen Cards snapshot passed while the dashboard advanced.
    """
    verdict = SectionVerdict(section=SECTION_CARD_PRICES)
    if not cards_row:
        verdict.passed = False
        verdict.detail = "no published card prices snapshot row"
        return verdict

    observed = cards_snapshot_market_date(cards_row)
    verdict.observed_date = observed
    if observed != market_date:
        verdict.passed = False
        verdict.detail = (
            f"cards snapshot market date {observed or 'missing'} "
            f"does not match promoted date {market_date}"
        )
    return verdict


def _audit_header_summary(
    market_date: str,
    page_row: Optional[Dict[str, Any]],
    sections: Sequence[SectionVerdict],
) -> SectionVerdict:
    """The header must never advertise a generation newer than its dependencies.

    Source: ``pokemon_set_page_snapshot_latest``, read through its own
    payload/title-card/market-summary metadata.
    """
    verdict = SectionVerdict(section=SECTION_HEADER_SUMMARY)
    if not page_row:
        verdict.passed = False
        verdict.detail = "no published set page snapshot row"
        return verdict

    header_date = page_snapshot_generation_date(page_row)
    verdict.observed_date = header_date
    if header_date is None:
        verdict.passed = False
        verdict.detail = "set page header has no derivable generation date"
        return verdict

    # A header LAGGING its dependencies is legitimate (the page snapshot is
    # simulation-driven and rebuilds on its own cadence). A header that advertises
    # a date NEWER than the promoted date, or newer than a section it depends on,
    # is the silent contradiction this audit exists to catch.
    if header_date > market_date:
        verdict.passed = False
        verdict.detail = (
            f"header advertises {header_date}, ahead of the promoted market date {market_date}"
        )
        return verdict

    behind = [
        f"{v.section}@{v.observed_date}"
        for v in sections
        if v.applicable and v.observed_date and v.observed_date < header_date
    ]
    if behind:
        verdict.passed = False
        verdict.detail = f"header advertises {header_date} but these sections are older: {', '.join(behind)}"
    return verdict


def audit_market_set_row(
    *,
    canonical_key: Optional[str],
    set_id: Optional[str],
    set_name: Optional[str],
    market_date: str,
    dashboard_row: Optional[Dict[str, Any]],
    value_history: Any = None,
    sealed_row: Optional[Dict[str, Any]] = None,
    cards_row: Optional[Dict[str, Any]] = None,
    page_row: Optional[Dict[str, Any]] = None,
    supports_simulation: bool = False,
    has_sealed_product: bool = False,
) -> MarketSetAuditRow:
    """Pure per-set verdict across every publication-required market surface.

    Each section reads its OWN source table:
      set_value    -> pokemon_set_value_daily_history (+ page snapshot for the
                      displayed number)
      top_chase    -> pokemon_set_market_dashboard_snapshot_latest
      opvc         -> pokemon_set_market_dashboard_snapshot_latest
      sealed       -> pokemon_set_sealed_market_snapshot_latest
      card_prices  -> pokemon_set_cards_snapshot_latest
      header       -> pokemon_set_page_snapshot_latest
    """
    row = MarketSetAuditRow(canonical_key=canonical_key, set_id=set_id, set_name=set_name)

    if dashboard_row is None:
        # The dashboard row backs Top Chase and OPvC only. The other surfaces have
        # their own sources and are still audited truthfully rather than being
        # blanket-failed on a dependency they do not share.
        dependent = [
            _audit_set_value(market_date, value_history, page_row),
            SectionVerdict(section=SECTION_TOP_CHASE, passed=False, detail="no published market dashboard row"),
            SectionVerdict(
                section=SECTION_OPENING_PROFIT_VS_COST,
                applicable=supports_simulation,
                passed=not supports_simulation,
                detail="no published market dashboard row" if supports_simulation else "set does not support opening simulation",
            ),
            _audit_sealed(market_date, sealed_row, has_sealed_product),
            _audit_card_prices(market_date, cards_row),
        ]
        row.sections.extend(dependent)
        row.sections.append(_audit_header_summary(market_date, page_row, dependent))
        return row

    dependent = [
        _audit_set_value(market_date, value_history, page_row),
        _audit_top_chase(market_date, dashboard_row, set_id),
        _audit_opvc(market_date, dashboard_row, supports_simulation),
        _audit_sealed(market_date, sealed_row, has_sealed_product),
        _audit_card_prices(market_date, cards_row),
    ]
    row.sections.extend(dependent)
    row.sections.append(_audit_header_summary(market_date, page_row, dependent))
    return row


# --------------------------------------------------------------------------
# I/O
# --------------------------------------------------------------------------
def resolve_promoted_market_date(client: Any, explicit: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """The promoted batch market date — the only authoritative target."""
    if explicit:
        return _date_key(explicit), None
    try:
        result = (
            client.table("pokemon_scrape_batches")
            .select("market_date,promoted_at,status")
            .not_.is_("promoted_at", "null")
            .order("market_date", desc=True)
            .limit(1)
            .execute()
        )
        rows = list((result.data if result else []) or [])
    except Exception as exc:
        return None, f"promoted batch lookup failed ({exc})"

    if not rows:
        return None, "no promoted scrape batch exists"
    return _date_key(rows[0].get("market_date")), None


def _load_publication_required_sets(client: Any) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """The corrected daily cohort: ready, card-priced, and NOT catalog-only."""
    try:
        result = (
            client.table("sets")
            .select("id,name,canonical_key,supports_opening_simulation,has_sealed_details_url")
            .eq("ready_for_daily_scrape", True)
            .eq("catalog_only", False)
            .execute()
        )
        return list((result.data if result else []) or []), None
    except Exception as exc:
        return [], f"publication-required set lookup failed ({exc})"


def _load_rows(client: Any, table: str, columns: str, set_ids: Sequence[str], **filters: Any) -> Dict[str, Dict[str, Any]]:
    by_set: Dict[str, Dict[str, Any]] = {}
    if not set_ids:
        return by_set
    chunk = 200
    for start in range(0, len(set_ids), chunk):
        query = client.table(table).select(columns).in_("set_id", list(set_ids[start:start + chunk]))
        for key, value in filters.items():
            query = query.eq(key, value)
        result = query.execute()
        for row in list((result.data if result else []) or []):
            set_id = _to_text(row.get("set_id"))
            if set_id and set_id not in by_set:
                by_set[set_id] = row
    return by_set


def _load_value_histories(client: Any, set_ids: Sequence[str], market_date: str) -> Dict[str, List[Dict[str, Any]]]:
    by_set: Dict[str, List[Dict[str, Any]]] = {}
    if not set_ids:
        return by_set
    chunk = 100
    for start in range(0, len(set_ids), chunk):
        result = (
            client.table("pokemon_set_value_daily_history")
            .select("set_id,snapshot_date,set_value,value_scope")
            .in_("set_id", list(set_ids[start:start + chunk]))
            .eq("value_scope", "standard")
            .gte("snapshot_date", market_date)
            .execute()
        )
        for row in list((result.data if result else []) or []):
            set_id = _to_text(row.get("set_id"))
            if set_id:
                by_set.setdefault(set_id, []).append({"date": row.get("snapshot_date"), "setValue": row.get("set_value")})
    return by_set


def _load_sealed_product_names(client: Any, set_ids: Sequence[str]) -> Dict[str, List[Any]]:
    """Raw sealed-product names per set, for the builder's own classifier.

    Read-only. A set with no rows here simply has no sealed products, which makes
    the sealed section non-applicable rather than failed.
    """
    by_set: Dict[str, List[Any]] = {}
    if not set_ids:
        return by_set
    chunk = 200
    for start in range(0, len(set_ids), chunk):
        result = (
            client.table("sealed_products")
            .select("set_id,name")
            .in_("set_id", list(set_ids[start:start + chunk]))
            .execute()
        )
        for row in list((result.data if result else []) or []):
            set_id = _to_text(row.get("set_id"))
            if set_id:
                by_set.setdefault(set_id, []).append(row.get("name"))
    return by_set


def run_market_publication_audit(
    client: Any,
    *,
    market_date: Optional[str] = None,
    canonical_keys: Optional[Sequence[str]] = None,
) -> MarketAuditReport:
    resolved_date, date_error = resolve_promoted_market_date(client, market_date)
    if date_error or not resolved_date:
        return MarketAuditReport(market_date=None, error=date_error or "no promoted market date resolved")

    sets, set_error = _load_publication_required_sets(client)
    if set_error:
        return MarketAuditReport(market_date=resolved_date, error=set_error)
    if canonical_keys is not None:
        wanted = {str(k) for k in canonical_keys}
        sets = [row for row in sets if _to_text(row.get("canonical_key")) in wanted]
    if not sets:
        return MarketAuditReport(market_date=resolved_date, error="no publication-required sets resolved")

    set_ids = [text for row in sets if (text := _to_text(row.get("id")))]

    try:
        dashboards = _load_rows(
            client,
            "pokemon_set_market_dashboard_snapshot_latest",
            "set_id,window_key,latest_market_date,top_chase_cards_json,"
            "top_chase_card_histories_json,performance_vs_cost_history_json",
            set_ids,
            window_key=CANONICAL_DASHBOARD_WINDOW,
        )
        sealed = _load_rows(
            client, "pokemon_set_sealed_market_snapshot_latest", "set_id,market_date,product_count", set_ids
        )
        # A: card prices get their OWN source, not the dashboard row as a proxy.
        cards = _load_rows(
            client,
            "pokemon_set_cards_snapshot_latest",
            # cards_json is required: cards_snapshot_market_date() falls back to
            # the per-card price dates when the payload meta carries no date, and
            # that fallback silently did nothing while the column was unselected.
            "set_id,payload_json,cards_json,card_count,updated_at",
            set_ids,
        )
        # B: the header/set-page summary gets its OWN source too.
        pages = _load_rows(
            client,
            "pokemon_set_page_snapshot_latest",
            "set_id,payload_json,title_card_json,market_summary_json,as_of,updated_at",
            set_ids,
        )
        value_histories = _load_value_histories(client, set_ids, resolved_date)
        # D: sealed applicability comes from the builder's real mapping contract.
        sealed_product_names = _load_sealed_product_names(client, set_ids)
    except Exception as exc:
        return MarketAuditReport(market_date=resolved_date, error=f"publication surface read failed ({exc})")

    report = MarketAuditReport(market_date=resolved_date)
    for set_row in sorted(sets, key=lambda r: str(r.get("canonical_key") or "")):
        set_id = _to_text(set_row.get("id"))
        report.rows.append(
            audit_market_set_row(
                canonical_key=_to_text(set_row.get("canonical_key")),
                set_id=set_id,
                set_name=_to_text(set_row.get("name")),
                market_date=resolved_date,
                dashboard_row=dashboards.get(set_id or ""),
                value_history=value_histories.get(set_id or "", []),
                sealed_row=sealed.get(set_id or ""),
                cards_row=cards.get(set_id or ""),
                page_row=pages.get(set_id or ""),
                # Opening Profit vs Cost applies ONLY to sets the simulation
                # runner actually executes. The flag is authoritative since
                # migration 059; a missing/false value means not applicable.
                supports_simulation=bool(set_row.get("supports_opening_simulation")),
                has_sealed_product=set_has_supported_sealed_product(
                    sealed_product_names.get(set_id or "", [])
                ),
            )
        )
    return report


def format_report_lines(report: MarketAuditReport) -> List[str]:
    lines = [
        f"{AUDIT_TAG} market_date={report.market_date} sets={len(report.rows)} "
        f"failed={len(report.failed_rows)} passed={report.passed}"
    ]
    if report.error:
        lines.append(f"{AUDIT_TAG} authority_error={report.error}")
    for row in report.failed_rows:
        for verdict in row.sections:
            if verdict.applicable and not verdict.passed:
                lines.append(
                    f"{AUDIT_TAG} FAILED set={row.canonical_key or row.set_id} "
                    f"section={verdict.section} detail={verdict.detail}"
                )
    return lines


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-date", default=None, help="Override the promoted market date (recovery only).")
    parser.add_argument("--json", dest="as_json", action="store_true", help="Emit the structured JSON report.")
    parser.add_argument("--set", dest="sets", action="append", default=None, help="Limit to canonical key(s).")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    from backend.db.clients.supabase_client import supabase

    report = run_market_publication_audit(
        supabase, market_date=args.market_date, canonical_keys=args.sets
    )

    if args.as_json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        for line in format_report_lines(report):
            logger.info("%s", line)

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
