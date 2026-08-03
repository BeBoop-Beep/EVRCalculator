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
def _audit_set_value(market_date: str, value_history: Any, dashboard_row: Dict[str, Any]) -> SectionVerdict:
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

    # The value the page displays must agree with the final published point;
    # a header number sourced from somewhere else is a silent contradiction.
    final_point = None
    for point in _points(value_history):
        if _date_key(point.get("date") or point.get("snapshot_date")) == market_date:
            final_point = point
    displayed = _finite(dashboard_row.get("set_value") or dashboard_row.get("latest_set_value"))
    final_value = _finite((final_point or {}).get("setValue") or (final_point or {}).get("set_value"))
    if displayed is not None and final_value is not None and round(displayed, 2) != round(final_value, 2):
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

    priced = [c for c in cards if (_finite(c.get("marketPrice") or c.get("market_price")) or 0) > 0]
    if not priced:
        # No priced cards is a legitimate state (a set with no priced chase cards).
        verdict.applicable = False
        verdict.detail = "no priced Top Chase cards"
        return verdict

    if not cards:
        verdict.passed = False
        verdict.detail = "priced cards exist but no Top Chase card list is published"
        return verdict

    problems: List[str] = []
    latest_seen: Optional[str] = None

    for card in priced:
        keys = [
            _to_text(card.get(k))
            for k in ("cardVariantId", "card_variant_id", "cardId", "card_id", "id")
        ]
        keys = [k for k in keys if k]

        card_set_id = _to_text(card.get("setId") or card.get("set_id"))
        if set_id and card_set_id and card_set_id != set_id:
            problems.append(f"card {keys[:1]} carries foreign set_id {card_set_id}")
            continue

        series = _points(card.get("priceHistory") or card.get("price_history"))
        for key in keys:
            candidate = _points(histories.get(key))
            if len(candidate) > len(series):
                series = candidate

        usable = [p for p in series if _date_key(p.get("date")) and _finite(p.get("marketPrice") or p.get("market_price")) is not None]
        if len(usable) < MIN_GRAPH_POINTS:
            problems.append(f"card {keys[:1]} has {len(usable)} usable history point(s)")
            continue

        card_latest = max(_date_key(p.get("date")) for p in usable)
        latest_seen = card_latest if latest_seen is None or card_latest > latest_seen else latest_seen

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


def _audit_card_prices(market_date: str, dashboard_row: Dict[str, Any]) -> SectionVerdict:
    verdict = SectionVerdict(section=SECTION_CARD_PRICES)
    observed = _date_key(dashboard_row.get("latest_market_date"))
    verdict.observed_date = observed
    if observed != market_date:
        verdict.passed = False
        verdict.detail = (
            f"published card snapshot market date {observed or 'missing'} "
            f"does not match promoted date {market_date}"
        )
    return verdict


def _audit_header_summary(market_date: str, dashboard_row: Dict[str, Any], sections: Sequence[SectionVerdict]) -> SectionVerdict:
    """The header must never advertise a generation newer than its sections."""
    verdict = SectionVerdict(section=SECTION_HEADER_SUMMARY)
    header_date = _date_key(dashboard_row.get("latest_market_date"))
    verdict.observed_date = header_date
    if header_date is None:
        verdict.passed = False
        verdict.detail = "set page header has no market date"
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
    supports_simulation: bool = True,
    has_sealed_product: bool = False,
) -> MarketSetAuditRow:
    """Pure per-set verdict across every publication-required market surface."""
    row = MarketSetAuditRow(canonical_key=canonical_key, set_id=set_id, set_name=set_name)

    if dashboard_row is None:
        for section in ALL_SECTIONS:
            row.sections.append(
                SectionVerdict(section=section, passed=False, detail="no published market dashboard row")
            )
        return row

    dependent = [
        _audit_set_value(market_date, value_history, dashboard_row),
        _audit_top_chase(market_date, dashboard_row, set_id),
        _audit_opvc(market_date, dashboard_row, supports_simulation),
        _audit_sealed(market_date, sealed_row, has_sealed_product),
        _audit_card_prices(market_date, dashboard_row),
    ]
    row.sections.extend(dependent)
    row.sections.append(_audit_header_summary(market_date, dashboard_row, dependent))
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
        value_histories = _load_value_histories(client, set_ids, resolved_date)
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
                supports_simulation=set_row.get("supports_opening_simulation") is not False,
                has_sealed_product=bool(set_row.get("has_sealed_details_url")),
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
