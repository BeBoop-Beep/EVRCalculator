"""Read-only publication audit for Pokemon opening analytics.

Answers, for every set supported by opening analytics, the two questions that
the daily pipeline could previously fail silently:

1. Did Opening Profit vs Cost actually advance with the market?
   Market snapshots are rebuilt from whatever simulation rows already exist, so
   a stopped simulation batch yields a snapshot whose ``latest_market_date`` is
   today while its ``performance_vs_cost_history_json`` ends days earlier. That
   is how production ran market date 2026-07-31 against an OPvC series ending
   2026-07-27 with nothing reporting a problem.

2. Do the published Top Chase cards still carry their canonical 1D/7D/30D
   movement windows? A card that loses them silently degrades to a
   reconstructed-from-history trend.

This command NEVER writes. It resolves nothing from wall-clock time: the market
date comes from the promoted scrape batch (or an explicit --market-date).

Exit codes
    0  every supported set passed
    1  at least one supported set failed the audit
    2  the audit could not run (no market date, unreadable authority)

Usage
    python backend/scripts/audit_opening_analytics_publication.py
    python backend/scripts/audit_opening_analytics_publication.py --market-date 2026-08-01
    python backend/scripts/audit_opening_analytics_publication.py --except-set chaosRising
    python backend/scripts/audit_opening_analytics_publication.py --json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

logger = logging.getLogger("audit_opening_analytics_publication")

AUDIT_TAG = "[opening-analytics-audit]"

# The canonical dashboard window every set is guaranteed to have been built
# under (see get_pokemon_set_top_chase_snapshot_payload's Phase 5D/5E notes).
CANONICAL_DASHBOARD_WINDOW = "365d"

# Movement windows the published Top Chase contract must carry.
REQUIRED_MOVEMENT_WINDOWS: Tuple[str, ...] = ("1D", "7D", "30D")

# The one window the UI defaults to, and therefore the one whose absence is a
# user-visible regression rather than a cosmetic gap.
REQUIRED_CANONICAL_WINDOW = "30D"


def _to_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _date_key(value: Any) -> Optional[str]:
    text = _to_text(value)
    return text[:10] if text else None


def _is_carried_forward(point: Dict[str, Any]) -> bool:
    return bool(point.get("isCarriedForward") or point.get("is_carried_forward"))


def latest_real_performance_date(history: Any) -> Optional[str]:
    """Last performance point backed by a real simulation run.

    Carried-forward points may exist for chart continuity but must never be
    reported as the history's freshness — that is precisely the confusion this
    audit is here to prevent.
    """
    latest: Optional[str] = None
    for point in history if isinstance(history, list) else []:
        if not isinstance(point, dict) or _is_carried_forward(point):
            continue
        date_key = _date_key(point.get("date") or point.get("snapshot_date") or point.get("snapshotDate"))
        if date_key and (latest is None or date_key > latest):
            latest = date_key
    return latest


def _card_windows(card: Dict[str, Any]) -> Dict[str, Any]:
    windows = card.get("marketDeltaWindows") or card.get("market_delta_windows")
    return windows if isinstance(windows, dict) else {}


def _has_window(card: Dict[str, Any], key: str) -> bool:
    return isinstance(_card_windows(card).get(key), dict)


def _has_canonical_identity(card: Dict[str, Any]) -> bool:
    return bool(_to_text(card.get("cardVariantId") or card.get("card_variant_id")))


@dataclass
class SetAuditRow:
    """One supported set's publication verdict."""

    canonical_key: Optional[str]
    set_id: Optional[str]
    set_name: Optional[str]
    simulation_status: str
    market_snapshot_latest_date: Optional[str] = None
    performance_history_latest_real_date: Optional[str] = None
    dates_match: bool = False
    top_chase_card_count: int = 0
    cards_with_1d_window: int = 0
    cards_with_7d_window: int = 0
    cards_with_30d_window: int = 0
    cards_missing_canonical_identity: int = 0
    cards_falling_back_to_history: int = 0
    skipped: bool = False
    failures: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.skipped or not self.failures


@dataclass
class AuditReport:
    market_date: Optional[str]
    rows: List[SetAuditRow] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def passed(self) -> bool:
        if self.error is not None:
            return False
        if not self.rows:
            return False
        return all(row.passed for row in self.rows)

    @property
    def failed_rows(self) -> List[SetAuditRow]:
        return [row for row in self.rows if not row.passed]


def audit_set_row(
    *,
    canonical_key: Optional[str],
    set_id: Optional[str],
    set_name: Optional[str],
    simulation_status: str,
    simulation_reason: Optional[str],
    market_date: str,
    dashboard_row: Optional[Dict[str, Any]],
    skipped: bool = False,
) -> SetAuditRow:
    """Pure per-set verdict. Kept free of I/O so it is directly testable."""
    row = SetAuditRow(
        canonical_key=canonical_key,
        set_id=set_id,
        set_name=set_name,
        simulation_status=simulation_status,
        skipped=skipped,
    )

    dashboard_row = dashboard_row or {}
    row.market_snapshot_latest_date = _date_key(dashboard_row.get("latest_market_date"))

    history = dashboard_row.get("performance_vs_cost_history_json")
    row.performance_history_latest_real_date = latest_real_performance_date(history)
    row.dates_match = bool(
        row.performance_history_latest_real_date
        and row.performance_history_latest_real_date == market_date
    )

    cards = dashboard_row.get("top_chase_cards_json")
    cards = cards if isinstance(cards, list) else []
    cards = [card for card in cards if isinstance(card, dict)]
    row.top_chase_card_count = len(cards)
    row.cards_with_1d_window = sum(1 for card in cards if _has_window(card, "1D"))
    row.cards_with_7d_window = sum(1 for card in cards if _has_window(card, "7D"))
    row.cards_with_30d_window = sum(1 for card in cards if _has_window(card, "30D"))
    row.cards_missing_canonical_identity = sum(1 for card in cards if not _has_canonical_identity(card))
    row.cards_falling_back_to_history = sum(
        1 for card in cards if not _has_window(card, REQUIRED_CANONICAL_WINDOW)
    )

    if skipped:
        return row

    if simulation_status != "current":
        row.failures.append(
            f"simulation {simulation_status} for {market_date}"
            + (f" ({simulation_reason})" if simulation_reason else "")
        )

    if not row.dates_match:
        row.failures.append(
            "market snapshot performance history ends "
            f"{row.performance_history_latest_real_date or 'nowhere'}, behind market date {market_date}"
        )

    if row.top_chase_card_count and row.cards_falling_back_to_history:
        row.failures.append(
            f"{row.cards_falling_back_to_history}/{row.top_chase_card_count} Top Chase cards "
            f"lack the canonical {REQUIRED_CANONICAL_WINDOW} window"
        )

    return row


def _load_dashboard_rows(client: Any, set_ids: Sequence[str]) -> Tuple[Dict[str, Dict[str, Any]], Optional[str]]:
    if not set_ids:
        return {}, None
    try:
        result = (
            client.table("pokemon_set_market_dashboard_snapshot_latest")
            .select(
                "set_id,window_key,latest_market_date,"
                "performance_vs_cost_history_json,top_chase_cards_json"
            )
            .eq("window_key", CANONICAL_DASHBOARD_WINDOW)
            .in_("set_id", list(set_ids))
            .execute()
        )
        rows = list((result.data if result else []) or [])
    except Exception as exc:
        logger.error("%s market dashboard read failed: %s", AUDIT_TAG, exc)
        return {}, f"market dashboard read failed ({exc})"

    by_set: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        set_id = _to_text(row.get("set_id"))
        if set_id:
            by_set[set_id] = row
    return by_set, None


def run_audit(
    client: Any,
    *,
    market_date: Optional[str] = None,
    unsupported_keys: Sequence[str] = (),
    canonical_keys: Optional[Sequence[str]] = None,
) -> AuditReport:
    """Build the full read-only audit report.

    ``canonical_keys`` overrides the supported-set list; production always
    leaves it unset so the audit and the simulation batch share one definition.
    """
    from backend.db.services.opening_simulation_gate import (
        STATUS_UNSUPPORTED,
        evaluate_opening_simulation_freshness,
    )

    freshness = evaluate_opening_simulation_freshness(
        client,
        market_date=market_date,
        unsupported_keys=unsupported_keys,
        canonical_keys=canonical_keys,
    )
    if freshness.error:
        return AuditReport(market_date=freshness.market_date, error=freshness.error)

    resolved_market_date = freshness.market_date or ""
    set_ids = [status.set_id for status in freshness.statuses if status.set_id]
    dashboard_by_set, dashboard_error = _load_dashboard_rows(client, set_ids)
    if dashboard_error:
        return AuditReport(market_date=resolved_market_date, error=dashboard_error)

    rows = [
        audit_set_row(
            canonical_key=status.canonical_key,
            set_id=status.set_id,
            set_name=status.set_name,
            simulation_status=status.status,
            simulation_reason=status.reason,
            market_date=resolved_market_date,
            dashboard_row=dashboard_by_set.get(status.set_id or ""),
            skipped=status.status == STATUS_UNSUPPORTED,
        )
        for status in freshness.statuses
    ]
    return AuditReport(market_date=resolved_market_date, rows=rows)


def resolve_market_date(client: Any, explicit: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Explicit date wins; otherwise take the promoted scrape batch's date.

    Never wall-clock: an audit that invented "today" would pass on a day the
    pipeline never actually published.
    """
    resolved = _date_key(explicit)
    if resolved:
        return resolved, None
    try:
        from backend.db.services.publication_gate import resolve_latest_promoted_market_date

        # A BLOCKED gate decision still carries the batch's market_date, so
        # consuming decision.market_date published an unpromoted date on
        # 2026-08-18. Resolution must come from the latest genuinely PROMOTED
        # batch, which a newer incomplete batch must not hide.
        resolved_date, error = resolve_latest_promoted_market_date(client)
        if error or not resolved_date:
            return None, error or "no promoted market date available"
        return _date_key(resolved_date), None
    except Exception as exc:
        return None, f"could not resolve the promoted market date ({exc})"


def _format_text_report(report: AuditReport) -> List[str]:
    lines: List[str] = []
    lines.append(f"{AUDIT_TAG} market_date={report.market_date}")
    if report.error:
        lines.append(f"{AUDIT_TAG} ERROR {report.error}")
        return lines

    header = (
        f"{'set':<24} {'sim':<10} {'mkt_date':<11} {'perf_real':<11} {'match':<6} "
        f"{'cards':<6} {'1D':<4} {'7D':<4} {'30D':<4} {'no_id':<6} {'hist_fb':<8} status"
    )
    lines.append(header)
    lines.append("-" * len(header))
    for row in sorted(report.rows, key=lambda item: (item.passed, item.canonical_key or "")):
        lines.append(
            f"{(row.canonical_key or row.set_id or '?'):<24} "
            f"{row.simulation_status:<10} "
            f"{(row.market_snapshot_latest_date or '-'):<11} "
            f"{(row.performance_history_latest_real_date or '-'):<11} "
            f"{('yes' if row.dates_match else 'no'):<6} "
            f"{row.top_chase_card_count:<6} "
            f"{row.cards_with_1d_window:<4} "
            f"{row.cards_with_7d_window:<4} "
            f"{row.cards_with_30d_window:<4} "
            f"{row.cards_missing_canonical_identity:<6} "
            f"{row.cards_falling_back_to_history:<8} "
            f"{'SKIP' if row.skipped else ('PASS' if row.passed else 'FAIL')}"
        )

    for row in report.failed_rows:
        for failure in row.failures:
            lines.append(f"{AUDIT_TAG} FAIL {row.canonical_key or row.set_id}: {failure}")

    passed = sum(1 for row in report.rows if row.passed and not row.skipped)
    skipped = sum(1 for row in report.rows if row.skipped)
    lines.append(
        f"{AUDIT_TAG} result={'PASS' if report.passed else 'FAIL'} "
        f"sets={len(report.rows)} passed={passed} failed={len(report.failed_rows)} skipped={skipped}"
    )
    return lines


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only audit: verify every supported opening-analysis set has a simulation "
            "for the promoted market date, that its market snapshot's Opening Profit vs Cost "
            "history reaches that date, and that its Top Chase cards kept their canonical "
            "1D/7D/30D movement windows. Never writes."
        )
    )
    parser.add_argument(
        "--market-date",
        default=None,
        help="Market date to audit (YYYY-MM-DD). Defaults to the promoted scrape batch's date.",
    )
    parser.add_argument(
        "--except-set",
        action="append",
        default=[],
        dest="except_sets",
        metavar="CANONICAL_KEY",
        help="Canonical key of a set intentionally unsupported by opening analytics. Repeatable.",
    )
    parser.add_argument("--json", action="store_true", help="Emit the report as JSON.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from backend.scripts.pokemon_snapshot_builders import get_client

    client = get_client()

    market_date, date_error = resolve_market_date(client, args.market_date)
    if date_error or not market_date:
        message = date_error or "no market date could be resolved"
        print(f"{AUDIT_TAG} ERROR {message}")
        return 2

    report = run_audit(client, market_date=market_date, unsupported_keys=args.except_sets)

    if args.json:
        print(
            json.dumps(
                {
                    "marketDate": report.market_date,
                    "error": report.error,
                    "passed": report.passed,
                    "sets": [asdict(row) for row in report.rows],
                },
                indent=2,
                default=str,
            )
        )
    else:
        for line in _format_text_report(report):
            print(line)

    if report.error:
        return 2
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
