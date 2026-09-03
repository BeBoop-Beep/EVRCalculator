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
SECTION_EXPLORE_SET_VALUE = "explore_set_value"
SECTION_GLOBAL_SET_VALUE = "global_market_set_value"

ALL_SECTIONS: Tuple[str, ...] = (
    SECTION_SET_VALUE,
    SECTION_TOP_CHASE,
    SECTION_OPENING_PROFIT_VS_COST,
    SECTION_SEALED_MARKET,
    SECTION_CARD_PRICES,
    SECTION_EXPLORE_SET_VALUE,
    SECTION_GLOBAL_SET_VALUE,
    SECTION_HEADER_SUMMARY,
)

GLOBAL_SET_VALUE_TABLE = "pokemon_explore_set_value_snapshot_latest"

# Every timeframe pill /Market can select. These are pure client-side slices of
# the published payload, so a window absent here is a DEAD control on the page.
#
# Mirrored from pokemon_explore_set_value_service.WINDOWS rather than imported:
# that module builds a Supabase client at import time, and this audit's pure
# layer must stay importable without credentials. A contract test asserts the two
# lists never drift.
EXPECTED_WINDOW_KEYS: Tuple[str, ...] = ("1D", "7D", "30D", "3M", "6M", "1Y", "lifetime")

# Audit phases.
#
# The daily pipeline publishes in TWO phases, and auditing them with one rule set
# is what let a stale surface hide. The early post-scrape phase advances every
# MARKET PRICING surface but deliberately runs no simulations, so Opening Profit
# vs Cost truthfully remains on the previous simulation date. The later coordinated
# publication runs simulations and must satisfy the full contract including OPvC.
#
# OPvC is optional ONLY in the explicit post-scrape phase, and even there it is
# reported as DEFERRED — never as passed or current.
PHASE_FULL = "full"
PHASE_POST_SCRAPE = "post-scrape"
ALL_PHASES: Tuple[str, ...] = (PHASE_FULL, PHASE_POST_SCRAPE)

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


# Ordered contract paths for the EXPLORE rankings snapshot's authoritative market
# date. `meta.snapshot.marketDate` is stamped by
# pokemon_explore_rankings_publisher.publish_explore_rip_rankings_snapshot, and
# `meta.comparisonSnapshots.currentMarketDate` is the value that publication
# contract derives it from. `updated_at` is deliberately NOT accepted: a rebuild
# that republishes yesterday's numbers still bumps it.
EXPLORE_SNAPSHOT_DATE_PATHS: Tuple[str, ...] = (
    "meta.snapshot.marketDate",
    "meta.snapshot.market_date",
    "meta.comparisonSnapshots.currentMarketDate",
    "meta.comparison_snapshots.current_market_date",
)

# Both alias spellings the Explore payload publishes. ExploreTopRankings reads
# `checklistSetValue` straight off this persisted payload — it never re-reads the
# set page — so a stale value here is a stale number on the user's screen.
EXPLORE_SET_VALUE_KEYS: Tuple[str, ...] = ("checklistSetValue", "checklist_set_value")
EXPLORE_SET_VALUE_AS_OF_KEYS: Tuple[str, ...] = (
    "checklistSetValueAsOf",
    "checklist_set_value_as_of",
    "currentChecklistSetValueDate",
    "current_checklist_set_value_date",
)


def _first_present(target: Dict[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if target.get(key) is not None:
            return target.get(key)
    return None


def explore_snapshot_market_date(explore_row: Optional[Dict[str, Any]]) -> Optional[str]:
    """The Explore rankings snapshot's own authoritative market date."""
    if not explore_row:
        return None
    return _first_date_at(_as_obj(explore_row.get("ranking_payload_json")), EXPLORE_SNAPSHOT_DATE_PATHS)


def explore_targets(explore_row: Optional[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
    """The persisted Explore targets array, or ``None`` when malformed.

    ``None`` and ``[]`` are different answers: a payload whose ``targets`` is not
    an array is a MALFORMED publication (hard failure), while an empty array is a
    readable payload that simply ranks nobody.
    """
    if not explore_row:
        return None
    payload = explore_row.get("ranking_payload_json")
    if not isinstance(payload, dict):
        payload = _as_obj(payload)
        if not payload:
            return None
    targets = payload.get("targets")
    if not isinstance(targets, list):
        return None
    return [target for target in targets if isinstance(target, dict)]


def index_explore_targets(targets: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Index targets by every identity a set row can be matched on."""
    index: Dict[str, Dict[str, Any]] = {}
    for target in targets:
        for key in ("set_id", "setId", "target_id", "targetId", "canonical_key", "canonicalKey", "slug"):
            identity = _to_text(target.get(key))
            if identity:
                index.setdefault(identity, target)
    return index


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
    # A section that is legitimately not current YET in this phase. Deferred is a
    # third state on purpose: reporting phase-deferred OPvC as "passed" would be a
    # false statement that the surface is current, and dropping it entirely would
    # hide that it is stale. It never counts as a failure.
    deferred: bool = False

    @property
    def status(self) -> str:
        if self.deferred:
            return "deferred"
        if not self.applicable:
            return "not_applicable"
        return "passed" if self.passed else "failed"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "section": self.section,
            "applicable": self.applicable,
            "passed": self.passed,
            "deferred": self.deferred,
            "status": self.status,
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
    phase: str = PHASE_FULL

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
            "phase": self.phase,
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


def _audit_opvc(
    market_date: str,
    dashboard_row: Dict[str, Any],
    supports_simulation: bool,
    *,
    phase: str = PHASE_FULL,
) -> SectionVerdict:
    verdict = SectionVerdict(section=SECTION_OPENING_PROFIT_VS_COST)
    if not supports_simulation:
        verdict.applicable = False
        verdict.detail = "set does not support opening simulation"
        return verdict

    if phase == PHASE_POST_SCRAPE:
        # The post-scrape phase publishes market pricing only; simulations run in
        # the later coordinated phase. Report the REAL observed date so the log
        # states plainly that OPvC is still on the previous simulation date.
        verdict.applicable = False
        verdict.deferred = True
        verdict.observed_date = latest_real_point_date(
            dashboard_row.get("performance_vs_cost_history_json"),
            value_keys=(
                "simulatedMeanPackValueVsPackCost",
                "simulated_mean_pack_value_vs_pack_cost",
                "simulatedMedianPackValueVsPackCost",
                "simulated_median_pack_value_vs_pack_cost",
            ),
        )
        verdict.detail = (
            f"deferred in post-scrape phase: simulations have not run yet "
            f"(latest real point {verdict.observed_date or 'nowhere'}, promoted market date {market_date})"
        )
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


def _audit_sealed(
    market_date: str,
    sealed_row: Optional[Dict[str, Any]],
    has_sealed_product: bool,
    *,
    sealed_source_latest_date: Optional[str] = None,
) -> SectionVerdict:
    verdict = SectionVerdict(section=SECTION_SEALED_MARKET)

    # A real SOURCE observation for the promoted date is proof the sealed snapshot
    # owes that date, regardless of anything else. This is the August-4 failure:
    # sealed_product_price_observations carried August 4 prices for
    # overview-eligible products while the published snapshot stayed on August 3.
    # Only the sealed builder's own eligibility classifier decides which products
    # count, so excluded cases/displays/collections never manufacture a failure.
    source_owes_market_date = sealed_source_latest_date is not None and sealed_source_latest_date >= market_date

    if not has_sealed_product and not source_owes_market_date:
        # No mapped supported sealed product: nothing is owed here.
        verdict.applicable = False
        verdict.detail = "no mapped supported sealed product"
        return verdict

    if source_owes_market_date:
        observed = _date_key((sealed_row or {}).get("market_date"))
        if observed is None or observed < market_date:
            verdict.observed_date = observed
            verdict.passed = False
            verdict.detail = (
                f"overview-eligible sealed source has an observation for {sealed_source_latest_date} "
                f"but the published sealed snapshot is {observed or 'missing'}"
            )
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


def _audit_explore_set_value(
    market_date: str,
    *,
    explore_target: Optional[Dict[str, Any]],
    canonical_set_value: Optional[float],
    snapshot_problem: Optional[str] = None,
) -> SectionVerdict:
    """The Explore Top Rankings Set Value must equal canonical Set Value for D.

    ExploreTopRankings renders ``checklistSetValue`` straight off the persisted
    Explore targets payload; it never independently reads the set page. So a set
    page showing the promoted date while Explore still carries yesterday's number
    is invisible to every other section of this audit — which is exactly how
    Ascended Heroes advertised $6,444.06 on its set page and $6,535.55 in Explore
    on the same day.

    ``snapshot_problem`` carries a SNAPSHOT-WIDE defect (missing row, malformed
    payload, stale snapshot date) so it fails every set rather than passing
    silently on sets that happen to have no target.
    """
    verdict = SectionVerdict(section=SECTION_EXPLORE_SET_VALUE)
    if snapshot_problem:
        verdict.passed = False
        verdict.detail = snapshot_problem
        return verdict

    if explore_target is None:
        # The Explore cohort is narrower than the publication-required cohort
        # (opening/ranked sets only). A set outside it owes no Explore target.
        verdict.applicable = False
        verdict.detail = "set is not in the published Explore rankings cohort"
        return verdict

    raw_value = _first_present(explore_target, EXPLORE_SET_VALUE_KEYS)
    if raw_value is None:
        verdict.applicable = False
        verdict.detail = "Explore target publishes no checklist set value"
        return verdict

    as_of = _date_key(_first_present(explore_target, EXPLORE_SET_VALUE_AS_OF_KEYS))
    verdict.observed_date = as_of
    if as_of != market_date:
        verdict.passed = False
        verdict.detail = (
            f"Explore checklist set value is dated {as_of or 'nowhere'}, "
            f"not the promoted market date {market_date}"
        )
        return verdict

    value = _finite(raw_value)
    if value is None or value <= 0:
        verdict.passed = False
        verdict.detail = f"Explore checklist set value {raw_value!r} is not a finite positive number"
        return verdict

    if canonical_set_value is None:
        verdict.passed = False
        verdict.detail = (
            f"Explore advertises a checklist set value for {market_date} but no canonical "
            f"standard set-value row exists for that date"
        )
        return verdict

    if round(value, 2) != round(canonical_set_value, 2):
        verdict.passed = False
        verdict.detail = (
            f"Explore checklist set value {round(value, 2)} disagrees with the canonical "
            f"standard set value {round(canonical_set_value, 2)} for {market_date}"
        )
    return verdict


def explore_snapshot_problem(market_date: str, explore_row: Optional[Dict[str, Any]]) -> Optional[str]:
    """Snapshot-wide Explore defect, or ``None`` when the snapshot is publishable.

    Freshness is never inferred from ``updated_at``: only the payload's own
    authoritative market date counts.
    """
    if not explore_row:
        return "no published Explore rankings snapshot row (tcg=pokemon, scope=rip-statistics)"
    payload = explore_row.get("ranking_payload_json")
    if not isinstance(payload, dict) and not _as_obj(payload):
        return "Explore ranking_payload_json is not an object"
    if explore_targets(explore_row) is None:
        return "Explore ranking_payload_json.targets is not an array"
    observed = explore_snapshot_market_date(explore_row)
    if observed != market_date:
        return (
            f"Explore snapshot market date {observed or 'missing'} "
            f"does not match promoted market date {market_date}"
        )
    return None


def global_set_value_targets(snapshot_row: Optional[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
    """The persisted global Set Value rows, or ``None`` when malformed.

    ``None`` and ``[]`` are different answers, exactly as in ``explore_targets``:
    a payload whose ``sets`` is not an array is a MALFORMED publication, while an
    empty array is readable and simply publishes nobody.
    """
    if not snapshot_row:
        return None
    payload = snapshot_row.get("payload_json")
    if not isinstance(payload, dict):
        payload = _as_obj(payload)
        if not payload:
            return None
    sets = payload.get("sets")
    if not isinstance(sets, list):
        return None
    return [row for row in sets if isinstance(row, dict)]


def global_set_value_snapshot_problem(
    market_date: str,
    snapshot_row: Optional[Dict[str, Any]],
    *,
    expected_set_ids: Sequence[str] = (),
) -> Optional[str]:
    """Snapshot-wide defect in the global Market Set Value artifact, or ``None``.

    This is the artifact ExploreTopRankings now renders on /Market. The Explore
    RIP rankings snapshot is a DIFFERENT public surface and its health says
    nothing about this one — treating it as proof is how a completely absent
    global Set Value snapshot (row_count = 0) coexisted with a passing market
    publication audit while /Market showed "temporarily unavailable".
    """
    if not snapshot_row:
        return f"no published global Market Set Value snapshot row (tcg=pokemon, scope=market) in {GLOBAL_SET_VALUE_TABLE}"

    payload = snapshot_row.get("payload_json")
    if not isinstance(payload, dict) and not _as_obj(payload):
        return "global Market Set Value payload_json is not an object"

    targets = global_set_value_targets(snapshot_row)
    if targets is None:
        return "global Market Set Value payload_json.sets is not an array"

    # Freshness is taken from the row's own market_date AND the payload's own
    # advertised date; updated_at is never accepted, since a rebuild that
    # republishes yesterday's numbers still bumps it.
    row_date = _date_key(snapshot_row.get("market_date"))
    if row_date != market_date:
        return (
            f"global Market Set Value snapshot market_date {row_date or 'missing'} "
            f"does not match promoted market date {market_date}"
        )
    payload_date = _date_key(_dig(_as_obj(payload), "meta.snapshot.marketDate"))
    if payload_date != market_date:
        return (
            f"global Market Set Value payload meta.snapshot.marketDate {payload_date or 'missing'} "
            f"does not match promoted market date {market_date}"
        )

    declared = snapshot_row.get("set_count")
    if not isinstance(declared, int) or declared != len(targets):
        return (
            f"global Market Set Value set_count {declared!r} disagrees with the "
            f"{len(targets)} published set(s) in payload_json.sets"
        )

    seen: Dict[str, int] = {}
    for target in targets:
        identity = _to_text(target.get("setId") or target.get("set_id"))
        if not identity:
            return "global Market Set Value publishes a row with no setId"
        seen[identity] = seen.get(identity, 0) + 1
    duplicates = sorted(key for key, count in seen.items() if count > 1)
    if duplicates:
        return f"global Market Set Value publishes duplicate setId(s): {duplicates[:5]}"

    expected = {str(key) for key in expected_set_ids}
    if expected:
        unexpected = sorted(set(seen) - expected)
        if unexpected:
            return f"global Market Set Value publishes out-of-cohort setId(s): {unexpected[:5]}"
        absent = sorted(expected - set(seen))
        if absent:
            return (
                f"global Market Set Value is missing {len(absent)} eligible cohort set(s): {absent[:5]}"
            )
    return None


def _audit_global_set_value(
    market_date: str,
    *,
    target: Optional[Dict[str, Any]],
    canonical_set_value: Optional[float],
    in_cohort: bool,
    snapshot_problem: Optional[str] = None,
) -> SectionVerdict:
    """Per-set verdict on the compact global Market Set Value snapshot.

    ``in_cohort`` is the builder's OWN eligibility rule (simulation-supported and
    public-analytics eligible), so a publication-required set that the snapshot
    legitimately never covers is non-applicable rather than failed — while an
    eligible set that is absent is a hard failure.
    """
    verdict = SectionVerdict(section=SECTION_GLOBAL_SET_VALUE)
    if snapshot_problem:
        verdict.passed = False
        verdict.detail = snapshot_problem
        return verdict

    if not in_cohort:
        verdict.applicable = False
        verdict.detail = "set is outside the global Market Set Value cohort"
        return verdict

    if target is None:
        verdict.passed = False
        verdict.detail = "set is in the global Market Set Value cohort but publishes no snapshot row"
        return verdict

    as_of = _date_key(target.get("setValueAsOf") or target.get("set_value_as_of"))
    verdict.observed_date = as_of
    if as_of != market_date:
        verdict.passed = False
        verdict.detail = (
            f"global Set Value row is dated {as_of or 'nowhere'}, "
            f"not the promoted market date {market_date}"
        )
        return verdict

    value = _finite(target.get("currentSetValue") or target.get("current_set_value"))
    if value is None or value <= 0:
        verdict.passed = False
        verdict.detail = (
            f"global Set Value currentSetValue {target.get('currentSetValue')!r} "
            f"is not a finite positive number"
        )
        return verdict

    # Every window the client can select must already be present: the /Market
    # timeframe pills are pure client-side slices of this payload, so a missing
    # window key is a dead control, not a lazily-computed one.
    windows = target.get("windows")
    windows = windows if isinstance(windows, dict) else {}
    missing_windows = [key for key in EXPECTED_WINDOW_KEYS if key not in windows]
    if missing_windows:
        verdict.passed = False
        verdict.detail = f"global Set Value row is missing window metadata: {missing_windows}"
        return verdict

    if canonical_set_value is None:
        verdict.passed = False
        verdict.detail = (
            f"global Set Value advertises a value for {market_date} but no canonical "
            f"standard set-value row exists for that date"
        )
        return verdict

    if round(value, 2) != round(canonical_set_value, 2):
        verdict.passed = False
        verdict.detail = (
            f"global Set Value {round(value, 2)} disagrees with the canonical standard "
            f"set value {round(canonical_set_value, 2)} for {market_date}"
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
    sealed_source_latest_date: Optional[str] = None,
    explore_target: Optional[Dict[str, Any]] = None,
    explore_snapshot_problem_detail: Optional[str] = None,
    canonical_set_value: Optional[float] = None,
    global_set_value_target: Optional[Dict[str, Any]] = None,
    global_set_value_problem_detail: Optional[str] = None,
    in_global_set_value_cohort: bool = False,
    phase: str = PHASE_FULL,
) -> MarketSetAuditRow:
    """Pure per-set verdict across every publication-required market surface.

    Each section reads its OWN source table:
      set_value    -> pokemon_set_value_daily_history (+ page snapshot for the
                      displayed number)
      top_chase    -> pokemon_set_market_dashboard_snapshot_latest
      opvc         -> pokemon_set_market_dashboard_snapshot_latest
      sealed       -> pokemon_set_sealed_market_snapshot_latest
      card_prices  -> pokemon_set_cards_snapshot_latest
      explore      -> pokemon_explore_rankings_snapshot_latest (+ daily history)
      global_sv    -> pokemon_explore_set_value_snapshot_latest (+ daily history)
      header       -> pokemon_set_page_snapshot_latest
    """
    row = MarketSetAuditRow(canonical_key=canonical_key, set_id=set_id, set_name=set_name)

    explore_verdict = _audit_explore_set_value(
        market_date,
        explore_target=explore_target,
        canonical_set_value=canonical_set_value,
        snapshot_problem=explore_snapshot_problem_detail,
    )
    global_set_value_verdict = _audit_global_set_value(
        market_date,
        target=global_set_value_target,
        canonical_set_value=canonical_set_value,
        in_cohort=in_global_set_value_cohort,
        snapshot_problem=global_set_value_problem_detail,
    )

    if dashboard_row is None:
        # The dashboard row backs Top Chase and OPvC only. The other surfaces have
        # their own sources and are still audited truthfully rather than being
        # blanket-failed on a dependency they do not share.
        dependent = [
            _audit_set_value(market_date, value_history, page_row),
            SectionVerdict(section=SECTION_TOP_CHASE, passed=False, detail="no published market dashboard row"),
            SectionVerdict(
                section=SECTION_OPENING_PROFIT_VS_COST,
                applicable=supports_simulation and phase != PHASE_POST_SCRAPE,
                passed=not supports_simulation,
                deferred=supports_simulation and phase == PHASE_POST_SCRAPE,
                detail=(
                    "deferred in post-scrape phase: simulations have not run yet"
                    if supports_simulation and phase == PHASE_POST_SCRAPE
                    else "no published market dashboard row"
                    if supports_simulation
                    else "set does not support opening simulation"
                ),
            ),
            _audit_sealed(
                market_date, sealed_row, has_sealed_product,
                sealed_source_latest_date=sealed_source_latest_date,
            ),
            _audit_card_prices(market_date, cards_row),
            explore_verdict,
            global_set_value_verdict,
        ]
        row.sections.extend(dependent)
        row.sections.append(_audit_header_summary(market_date, page_row, dependent))
        return row

    dependent = [
        _audit_set_value(market_date, value_history, page_row),
        _audit_top_chase(market_date, dashboard_row, set_id),
        _audit_opvc(market_date, dashboard_row, supports_simulation, phase=phase),
        _audit_sealed(
            market_date, sealed_row, has_sealed_product,
            sealed_source_latest_date=sealed_source_latest_date,
        ),
        _audit_card_prices(market_date, cards_row),
        explore_verdict,
        global_set_value_verdict,
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
            # era_id is required: is_public_analytics_eligible gates on it, and the
            # global Set Value cohort is derived from that same rule.
            .select("id,name,canonical_key,era_id,supports_opening_simulation,has_sealed_details_url")
            .eq("ready_for_daily_scrape", True)
            .eq("catalog_only", False)
            .execute()
        )
        return list((result.data if result else []) or []), None
    except Exception as exc:
        return [], f"publication-required set lookup failed ({exc})"


def _load_rows(
    client: Any,
    table: str,
    columns: str,
    set_ids: Sequence[str],
    *,
    chunk_size: int = 200,
    **filters: Any,
) -> Dict[str, Dict[str, Any]]:
    by_set: Dict[str, Dict[str, Any]] = {}
    if not set_ids:
        return by_set
    for start in range(0, len(set_ids), chunk_size):
        query = client.table(table).select(columns).in_("set_id", list(set_ids[start:start + chunk_size]))
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


def _load_sealed_products(client: Any, set_ids: Sequence[str]) -> Dict[str, List[Dict[str, Any]]]:
    """Raw sealed-product rows per set, for the builder's own classifier.

    Read-only. A set with no rows here simply has no sealed products, which makes
    the sealed section non-applicable rather than failed.
    """
    by_set: Dict[str, List[Dict[str, Any]]] = {}
    if not set_ids:
        return by_set
    chunk = 200
    for start in range(0, len(set_ids), chunk):
        result = (
            client.table("sealed_products")
            .select("id,set_id,name")
            .in_("set_id", list(set_ids[start:start + chunk]))
            .execute()
        )
        for row in list((result.data if result else []) or []):
            set_id = _to_text(row.get("set_id"))
            if set_id:
                by_set.setdefault(set_id, []).append(row)
    return by_set


def _overview_eligible_product_ids(products: Sequence[Dict[str, Any]]) -> List[str]:
    """Product ids the SEALED BUILDER would actually publish, via its classifier."""
    from backend.domain.pokemon.sealed_product_classifier import classify_sealed_product

    eligible: List[str] = []
    for product in products or []:
        product_id = _to_text(product.get("id"))
        if not product_id:
            continue
        try:
            if classify_sealed_product(product.get("name")).get("isOverviewEligible"):
                eligible.append(product_id)
        except Exception:  # pragma: no cover - a broken name must not hide the rest
            continue
    return eligible


def _load_sealed_source_latest_dates(
    client: Any,
    products_by_set: Dict[str, List[Dict[str, Any]]],
    market_date: str,
) -> Dict[str, str]:
    """Newest SOURCE observation date per set, for overview-eligible products only.

    Reads ``sealed_product_price_observations`` — the sealed builder's own source —
    never a card, simulation, or dashboard timestamp. Restricted to observations on
    or after the promoted date, because the only question this answers is "does the
    source already carry the date the published snapshot is missing?".
    """
    set_id_by_product: Dict[str, str] = {}
    for set_id, products in products_by_set.items():
        for product_id in _overview_eligible_product_ids(products):
            set_id_by_product[product_id] = set_id

    latest_by_set: Dict[str, str] = {}
    product_ids = list(set_id_by_product)
    chunk = 200
    for start in range(0, len(product_ids), chunk):
        result = (
            client.table("sealed_product_price_observations")
            .select("sealed_product_id,captured_at")
            .in_("sealed_product_id", product_ids[start:start + chunk])
            .gte("captured_at", market_date)
            .execute()
        )
        for row in list((result.data if result else []) or []):
            set_id = set_id_by_product.get(_to_text(row.get("sealed_product_id")) or "")
            observed = _date_key(row.get("captured_at"))
            if set_id and observed and observed > latest_by_set.get(set_id, ""):
                latest_by_set[set_id] = observed
    return latest_by_set


def _load_explore_rankings_row(client: Any) -> Optional[Dict[str, Any]]:
    """The persisted Explore rankings payload ExploreTopRankings actually serves."""
    result = (
        client.table("pokemon_explore_rankings_snapshot_latest")
        .select("tcg,scope,ranking_payload_json,updated_at")
        .eq("tcg", "pokemon")
        .eq("scope", "rip-statistics")
        .limit(1)
        .execute()
    )
    rows = list((result.data if result else []) or [])
    return rows[0] if rows else None


def _load_global_set_value_row(client: Any) -> Optional[Dict[str, Any]]:
    """The persisted global Set Value payload /Market's ladder actually serves."""
    result = (
        client.table(GLOBAL_SET_VALUE_TABLE)
        .select("tcg,scope,payload_json,market_date,set_count,payload_size_bytes,updated_at")
        .eq("tcg", "pokemon")
        .eq("scope", "market")
        .limit(1)
        .execute()
    )
    rows = list((result.data if result else []) or [])
    return rows[0] if rows else None


def index_global_set_value_targets(targets: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Index published Set Value rows by every identity a set row can match on."""
    index: Dict[str, Dict[str, Any]] = {}
    for target in targets:
        for key in ("setId", "set_id", "canonicalKey", "canonical_key"):
            identity = _to_text(target.get(key))
            if identity:
                index.setdefault(identity, target)
    return index


def global_set_value_cohort_ids(sets: Sequence[Dict[str, Any]]) -> List[str]:
    """Set ids the global Set Value BUILDER would publish, via its own rule.

    Reuses ``is_public_analytics_eligible`` rather than restating the cohort, so
    the audit and the builder can never disagree about who is owed a row.
    """
    from backend.desirability.public_analytics_policy import is_public_analytics_eligible

    cohort: List[str] = []
    for set_row in sets or []:
        set_id = _to_text(set_row.get("id"))
        if not set_id or set_row.get("supports_opening_simulation") is not True:
            continue
        try:
            if is_public_analytics_eligible(set_row):
                cohort.append(set_id)
        except Exception:  # pragma: no cover - a broken row must not hide the rest
            continue
    return cohort


def run_market_publication_audit(
    client: Any,
    *,
    market_date: Optional[str] = None,
    canonical_keys: Optional[Sequence[str]] = None,
    phase: str = PHASE_FULL,
) -> MarketAuditReport:
    if phase not in ALL_PHASES:
        raise ValueError(f"unknown audit phase {phase!r}; expected one of {ALL_PHASES}")

    resolved_date, date_error = resolve_promoted_market_date(client, market_date)
    if date_error or not resolved_date:
        return MarketAuditReport(
            market_date=None, phase=phase, error=date_error or "no promoted market date resolved"
        )

    sets, set_error = _load_publication_required_sets(client)
    if set_error:
        return MarketAuditReport(market_date=resolved_date, phase=phase, error=set_error)
    # The global Set Value cohort is derived from the FULL publication-required
    # list, never the `--set` filtered view: auditing a single set must not be
    # able to make an incomplete global snapshot look complete.
    all_sets = list(sets)
    if canonical_keys is not None:
        wanted = {str(k) for k in canonical_keys}
        sets = [row for row in sets if _to_text(row.get("canonical_key")) in wanted]
    if not sets:
        return MarketAuditReport(
            market_date=resolved_date, phase=phase, error="no publication-required sets resolved"
        )

    set_ids = [text for row in sets if (text := _to_text(row.get("id")))]

    try:
        dashboards = _load_rows(
            client,
            "pokemon_set_market_dashboard_snapshot_latest",
            "set_id,window_key,latest_market_date,top_chase_cards_json,"
            "top_chase_card_histories_json,performance_vs_cost_history_json",
            set_ids,
            chunk_size=10,
            window_key=CANONICAL_DASHBOARD_WINDOW,
        )
        sealed = _load_rows(
            client, "pokemon_set_sealed_market_snapshot_latest", "set_id,market_date,product_count", set_ids,
            chunk_size=200,
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
            chunk_size=20,
        )
        # B: the header/set-page summary gets its OWN source too.
        pages = _load_rows(
            client,
            "pokemon_set_page_snapshot_latest",
            "set_id,payload_json,title_card_json,market_summary_json,as_of,updated_at",
            set_ids,
            chunk_size=200,
        )
        value_histories = _load_value_histories(client, set_ids, resolved_date)
        # D: sealed applicability comes from the builder's real mapping contract.
        sealed_products = _load_sealed_products(client, set_ids)
        sealed_source_dates = _load_sealed_source_latest_dates(client, sealed_products, resolved_date)
        # The persisted Explore payload ExploreTopRankings actually renders.
        explore_row = _load_explore_rankings_row(client)
        # The artifact /Market's Set Value ladder renders. The Explore RIP
        # rankings row above is a DIFFERENT public surface and proves nothing
        # about this one.
        global_set_value_row = _load_global_set_value_row(client)
    except Exception as exc:
        return MarketAuditReport(
            market_date=resolved_date, phase=phase, error=f"publication surface read failed ({exc})"
        )

    explore_problem = explore_snapshot_problem(resolved_date, explore_row)
    explore_index = index_explore_targets(explore_targets(explore_row) or [])

    global_cohort = set(global_set_value_cohort_ids(all_sets))
    global_problem = global_set_value_snapshot_problem(
        resolved_date, global_set_value_row, expected_set_ids=sorted(global_cohort)
    )
    global_index = index_global_set_value_targets(global_set_value_targets(global_set_value_row) or [])

    report = MarketAuditReport(market_date=resolved_date, phase=phase)
    for set_row in sorted(sets, key=lambda r: str(r.get("canonical_key") or "")):
        set_id = _to_text(set_row.get("id"))
        canonical_key = _to_text(set_row.get("canonical_key"))
        history = value_histories.get(set_id or "", [])
        canonical_value = next(
            (
                _finite(point.get("setValue"))
                for point in history
                if _date_key(point.get("date")) == resolved_date
            ),
            None,
        )
        report.rows.append(
            audit_market_set_row(
                canonical_key=canonical_key,
                set_id=set_id,
                set_name=_to_text(set_row.get("name")),
                market_date=resolved_date,
                dashboard_row=dashboards.get(set_id or ""),
                value_history=history,
                sealed_row=sealed.get(set_id or ""),
                cards_row=cards.get(set_id or ""),
                page_row=pages.get(set_id or ""),
                # Opening Profit vs Cost applies ONLY to sets the simulation
                # runner actually executes. The flag is authoritative since
                # migration 059; a missing/false value means not applicable.
                supports_simulation=bool(set_row.get("supports_opening_simulation")),
                has_sealed_product=set_has_supported_sealed_product(
                    [p.get("name") for p in sealed_products.get(set_id or "", [])]
                ),
                sealed_source_latest_date=sealed_source_dates.get(set_id or ""),
                explore_target=(
                    explore_index.get(set_id or "") or explore_index.get(canonical_key or "")
                ),
                explore_snapshot_problem_detail=explore_problem,
                canonical_set_value=canonical_value,
                global_set_value_target=(
                    global_index.get(set_id or "") or global_index.get(canonical_key or "")
                ),
                global_set_value_problem_detail=global_problem,
                in_global_set_value_cohort=(set_id or "") in global_cohort,
                phase=phase,
            )
        )
    return report


def format_report_lines(report: MarketAuditReport) -> List[str]:
    lines = [
        f"{AUDIT_TAG} phase={report.phase} market_date={report.market_date} sets={len(report.rows)} "
        f"failed={len(report.failed_rows)} passed={report.passed}"
    ]
    if report.error:
        lines.append(f"{AUDIT_TAG} authority_error={report.error}")

    # Deferred sections are stated once, not per set: they are not failures, but
    # silence would let "audit passed" read as "every surface is current".
    deferred_sets = [
        row.canonical_key or row.set_id or "?"
        for row in report.rows
        if any(v.deferred for v in row.sections)
    ]
    if deferred_sets:
        lines.append(
            f"{AUDIT_TAG} DEFERRED section={SECTION_OPENING_PROFIT_VS_COST} "
            f"phase={report.phase} sets={len(deferred_sets)} "
            f"(not current, not required in this phase): {deferred_sets[:10]}"
        )

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
    parser.add_argument(
        "--phase",
        choices=list(ALL_PHASES),
        default=PHASE_FULL,
        help=(
            "Publication phase being audited. 'full' (default) is the complete contract and "
            "requires Opening Profit vs Cost on the promoted date. 'post-scrape' audits the "
            "early market-pricing publication, where simulations have not run yet, so OPvC is "
            "reported as DEFERRED instead of required. Every other surface is required in both."
        ),
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    from backend.db.clients.supabase_client import supabase

    report = run_market_publication_audit(
        supabase, market_date=args.market_date, canonical_keys=args.sets, phase=args.phase
    )

    # Queue only whole-surface audits. Targeted --set diagnostics are operator
    # probes and must not claim the daily pipeline passed or failed globally.
    if not args.sets and report.market_date:
        try:
            from backend.alerts.pipeline_alerts import (
                alert_market_audit, alert_market_pipeline_complete_if_ready,
                alert_simulation_stage,
            )
            failing = [row.canonical_key or row.set_id or "unknown" for row in report.failed_rows]
            alert_market_audit(
                market_date=report.market_date, passed=report.passed,
                failing_surfaces=failing, expected_date=report.market_date,
                error=report.error,
            )
            if args.phase == PHASE_FULL:
                alert_simulation_stage(
                    market_date=report.market_date,
                    state="complete" if report.passed else "publication_failed",
                    set_count=len(report.rows), final_audit_status="PASS" if report.passed else "FAIL",
                )
            elif args.phase == PHASE_POST_SCRAPE:
                alert_market_pipeline_complete_if_ready(
                    supabase, market_date=report.market_date, audit_passed=report.passed)
        except Exception:  # pragma: no cover - an audit verdict never depends on alerting
            logger.exception("%s failed to queue publication audit alert", AUDIT_TAG)

    if args.as_json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        for line in format_report_lines(report):
            logger.info("%s", line)

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
