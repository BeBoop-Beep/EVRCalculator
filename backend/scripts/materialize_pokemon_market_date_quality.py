"""Materialize Market Date Quality verdicts for the Pokemon Market surface.

Operator tool around the already-approved Market quality service. It computes
nothing itself: every status comes from ``classify_market_date`` and every write
goes through ``persist_market_date_quality``.

Why this exists
---------------
The 2026-08-20 rollout drove this workflow from an ad-hoc script and surfaced a
hazard worth encoding permanently. Once the read/build paths enforce quality, a
date with NO quality row is not accepted. So materializing only recent dates in
an environment whose older history has never been evaluated silently drops that
older history out of the accepted chain - the index would restart from its
earliest surviving accepted date. This CLI refuses to create that state: a
partial run that would leave persisted Market history uncovered fails closed and
tells the operator to use ``--all-history``.

Two things the service cannot do per-date, which this driver supplies:

* ``has_later_accepted_date`` distinguishes a terminal DEGRADED date from a
  still-recoverable INCOMPLETE one. It is only knowable after every candidate is
  evaluated, so evaluation runs in two passes.
* The explicit historical verification path. Pre-cutoff dates are OFFERED to the
  legacy allowlist; the service still independently requires complete Market
  valuation evidence before granting LEGACY_VERIFIED, so an offered date with
  bad evidence is still refused.

This tool never publishes Market artifacts, never consults the 167-set scrape
batch, and has no force/override flag.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.db.services.market_date_quality import (
    ACCEPTED_STATUSES,
    MARKET_QUALITY_ENFORCEMENT_START,
    STATUS_DEGRADED,
    STATUS_LEGACY_VERIFIED,
    STATUS_READY,
    PAGE_SIZE,
    REQUIRED_VALUE_SCOPES,
    SOURCE_TABLE,
    classify_market_date,
    cohort_set_ids_for_date,
    persist_market_date_quality,
    read_market_date_quality_history,
    valuation_set_ids_for_date,
)
from backend.db.services.market_run_evidence import qualifying_set_ids_for_date
from backend.db.services.pokemon_market_index_service import (
    read_raw_index_history_for_audit, resolve_market_entry_dates_for_client,
)
from backend.scripts.pokemon_snapshot_builders import get_client

logger = logging.getLogger(__name__)

TAG = "[market-quality-materialize]"

# Exit codes. 0 success, 1 genuine failure, 2 refused-unsafe (fail closed).
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_UNSAFE_PARTIAL = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate and persist Market Date Quality verdicts (service-computed).")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--market-date", help="Evaluate one America/Phoenix market date (YYYY-MM-DD)")
    scope.add_argument("--all-history", action="store_true",
                       help="Evaluate every date the Market surface has source data for")
    scope.add_argument("--from-date", help="Evaluate an explicit range start (YYYY-MM-DD); use with --to-date")
    parser.add_argument("--to-date", help="Explicit range end (YYYY-MM-DD); defaults to the newest source date")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True,
                      help="Evaluate and report without writing (default)")
    mode.add_argument("--commit", action="store_true", help="Persist service-computed verdicts")
    parser.add_argument("--json", action="store_true", help="Emit the report as JSON")
    return parser


def _paged(query_factory) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = list((query_factory().range(offset, offset + PAGE_SIZE - 1).execute()).data or [])
        rows.extend(dict(row) for row in page)
        if len(page) < PAGE_SIZE:
            return rows
        offset += PAGE_SIZE


def all_market_source_dates(client: Any) -> list[str]:
    """Every date the Market surface has source valuation data for. Paginated."""
    rows = _paged(lambda: client.table(SOURCE_TABLE).select("snapshot_date")
                  .in_("value_scope", list(REQUIRED_VALUE_SCOPES))
                  .order("snapshot_date", desc=False))
    return sorted({str(r["snapshot_date"])[:10] for r in rows if r.get("snapshot_date")})


def persisted_index_dates(client: Any) -> set[str]:
    """Market dates that already have persisted index history. Paginated."""
    return {str(r["market_date"])[:10]
            for r in read_raw_index_history_for_audit(client)
            if r.get("market_date")}


def already_covered_dates(client: Any) -> set[str]:
    """Market dates that already carry a quality verdict. Paginated."""
    return {str(r["market_date"])[:10]
            for r in read_market_date_quality_history(client) if r.get("market_date")}


def evaluate_dates(
    client: Any,
    days: Sequence[str],
    *,
    legacy_allowlist: Iterable[str],
) -> dict[str, dict[str, Any]]:
    """Two-pass evaluation. Every verdict is produced by the service."""
    market_entry_dates = resolve_market_entry_dates_for_client(client)
    evidence: dict[str, tuple] = {}
    for day in days:
        cohort = cohort_set_ids_for_date(client, day, market_entry_dates=market_entry_dates)
        evidence[day] = (cohort,
                         qualifying_set_ids_for_date(client, day),
                         valuation_set_ids_for_date(client, day, cohort))

    def classify(day: str, later: bool) -> dict[str, Any]:
        cohort, qualifying, valuation = evidence[day]
        return classify_market_date(
            market_date=day, cohort_set_ids=cohort, qualifying_set_ids=qualifying,
            valuation_set_ids=valuation, has_later_accepted_date=later,
            legacy_allowlist=legacy_allowlist)

    # Pass 1: provisional, with no knowledge of later dates.
    provisional = {day: classify(day, False)["status"] for day in days}
    accepted = sorted(d for d in days if provisional[d] in ACCEPTED_STATUSES)
    newest_accepted = accepted[-1] if accepted else None

    # Pass 2: a failing date with a later accepted date is terminal => DEGRADED.
    return {day: classify(day, bool(newest_accepted and newest_accepted > day))
            for day in days}


def assess_coverage_safety(
    client: Any, selected: Sequence[str], *, all_history: bool
) -> tuple[bool, list[str], str]:
    """Refuse a partial run that would drop covered history out of acceptance.

    Returns (safe, uncovered_dates, message).
    """
    if all_history:
        return True, [], "full-history run: every source date is evaluated"

    index_dates = persisted_index_dates(client)
    if not index_dates:
        return True, [], "no persisted Market index history to endanger"

    covered = already_covered_dates(client) | set(selected)
    uncovered = sorted(index_dates - covered)
    if uncovered:
        return False, uncovered, (
            f"{len(uncovered)} date(s) of persisted Market index history would have no "
            f"quality verdict after this run and would therefore drop out of accepted "
            f"history (earliest {uncovered[0]}, latest {uncovered[-1]}). "
            f"Re-run with --all-history.")
    return True, [], "all persisted Market index history is or will be covered"


def _summarize(results: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for verdict in results.values():
        counts[verdict["status"]] = counts.get(verdict["status"], 0) + 1
    accepted = sorted(d for d, v in results.items() if v["status"] in ACCEPTED_STATUSES)
    market_index_accepted = sorted(
        d for d, v in results.items()
        if (v.get("evidence") or {}).get("marketIndexAccepted") is True)
    known = {STATUS_READY, STATUS_LEGACY_VERIFIED, STATUS_DEGRADED}
    return {
        "totalDates": len(results),
        "readyCount": counts.get(STATUS_READY, 0),
        "legacyVerifiedCount": counts.get(STATUS_LEGACY_VERIFIED, 0),
        "degradedCount": counts.get(STATUS_DEGRADED, 0),
        "otherCount": sum(n for s, n in counts.items() if s not in known),
        "acceptedTotal": len(accepted),
        "firstAccepted": accepted[0] if accepted else None,
        "lastAccepted": accepted[-1] if accepted else None,
        "marketIndexAcceptedTotal": len(market_index_accepted),
        "firstMarketIndexAccepted": market_index_accepted[0] if market_index_accepted else None,
        "lastMarketIndexAccepted": market_index_accepted[-1] if market_index_accepted else None,
    }


def _row(day: str, verdict: Mapping[str, Any]) -> dict[str, Any]:
    evidence = verdict.get("evidence") or {}
    missing = list(verdict.get("missingSetIds") or [])
    if verdict["status"] in ACCEPTED_STATUSES:
        reason = ("full cohort qualified" if verdict["status"] == STATUS_READY
                  else "pre-enforcement date verified through the legacy path")
    elif verdict["status"] == STATUS_DEGRADED:
        reason = f"terminal: {len(missing)} set(s) unqualified and a later date is accepted"
    else:
        reason = f"recoverable: {len(missing)} set(s) not yet qualified"
    return {
        "market_date": day,
        "status": verdict["status"],
        "qualifying_count": verdict["qualifyingSetCount"],
        "expected_count": verdict["cohortSetCount"],
        "accepted": verdict["status"] in ACCEPTED_STATUSES,
        "market_index_accepted": evidence.get("marketIndexAccepted") is True,
        "market_index_reason": ("complete tracked-cohort standard/top10 valuations"
                                if evidence.get("marketIndexAccepted") is True
                                else "tracked-cohort valuation incomplete"),
        "reason": reason,
        "pre_enforcement": bool(evidence.get("preEnforcement")),
        "has_later_accepted_date": bool(evidence.get("hasLaterAcceptedDate")),
    }


def run(client: Any, args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    commit = bool(args.commit)
    source_dates = all_market_source_dates(client)
    if not source_dates:
        return EXIT_FAILED, {"error": "no Market source dates found"}

    if args.all_history:
        selected = source_dates
    elif args.market_date:
        day = str(args.market_date)[:10]
        if day not in source_dates:
            return EXIT_FAILED, {"error": f"{day} has no Market source data"}
        selected = [day]
    else:
        start = str(args.from_date)[:10]
        end = str(args.to_date)[:10] if args.to_date else source_dates[-1]
        selected = [d for d in source_dates if start <= d <= end]
        if not selected:
            return EXIT_FAILED, {"error": f"no Market source dates in {start}..{end}"}

    safe, uncovered, coverage_message = assess_coverage_safety(
        client, selected, all_history=bool(args.all_history))

    # The service still independently requires complete valuation evidence.
    legacy_allowlist = frozenset(d for d in source_dates
                                 if d < MARKET_QUALITY_ENFORCEMENT_START)

    if not safe:
        return EXIT_UNSAFE_PARTIAL, {
            "status": "refused_unsafe_partial",
            "selectedDates": len(selected),
            "uncoveredHistoryDates": uncovered[:50],
            "uncoveredHistoryDateCount": len(uncovered),
            "coverage": coverage_message,
            "wrote": False,
        }

    results = evaluate_dates(client, selected, legacy_allowlist=legacy_allowlist)
    report = {
        "status": "committed" if commit else "dry_run",
        "mode": "commit" if commit else "dry-run",
        "enforcementStart": MARKET_QUALITY_ENFORCEMENT_START,
        "coverage": coverage_message,
        "summary": _summarize(results),
        "dates": [_row(day, results[day]) for day in selected],
        "wrote": False,
        "rowsPersisted": 0,
    }

    if not commit:
        return EXIT_OK, report

    persisted = 0
    for day in selected:
        persisted += persist_market_date_quality(client, results[day])
        try:
            from backend.alerts.pipeline_alerts import alert_market_quality
            verdict = results[day]
            alert_market_quality(
                market_date=day, status=str(verdict["status"]),
                qualifying_set_count=int(verdict["qualifyingSetCount"]),
                cohort_set_count=int(verdict["cohortSetCount"]),
                missing_canonical_keys=list(verdict.get("missingCanonicalKeys") or
                                            verdict.get("missingSetIds") or []),
                missing_valuation_sets=list(verdict.get("missingValuationSetIds") or []),
                missing_run_evidence=list(verdict.get("missingRunEvidenceSetIds") or []),
                previous_accepted_market_date=report["summary"].get("lastAccepted"),
            )
        except Exception:  # pragma: no cover - persistence remains authoritative
            logger.exception("%s failed to queue Market Quality alert for %s", TAG, day)
    report["wrote"] = True
    report["rowsPersisted"] = persisted
    return EXIT_OK, report


def main() -> int:
    args = build_parser().parse_args()
    exit_code, report = run(get_client(), args)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return exit_code

    if report.get("status") == "refused_unsafe_partial":
        print(f"{TAG} REFUSED - unsafe partial materialization")
        print(f"{TAG} {report['coverage']}")
        print(f"{TAG} no rows were written")
        return exit_code
    if "error" in report:
        print(f"{TAG} ERROR: {report['error']}")
        return exit_code

    print(f"{TAG} mode={report['mode']} enforcementStart={report['enforcementStart']}")
    print(f"{TAG} {report['coverage']}")
    header = f"{'market_date':<12} {'status':<16} {'qual':>6} {'exp':>5} {'accepted':>9}  reason"
    print(header)
    print("-" * len(header))
    for row in report["dates"]:
        print(f"{row['market_date']:<12} {row['status']:<16} "
              f"{row['qualifying_count']:>6} {row['expected_count']:>5} "
              f"{str(row['accepted']):>9}  {row['reason']}")
    summary = report["summary"]
    print(f"\n{TAG} totalDates={summary['totalDates']} READY={summary['readyCount']} "
          f"LEGACY_VERIFIED={summary['legacyVerifiedCount']} "
          f"DEGRADED={summary['degradedCount']} other={summary['otherCount']}")
    print(f"{TAG} acceptedTotal={summary['acceptedTotal']} "
          f"({summary['firstAccepted']} .. {summary['lastAccepted']})")
    if report["wrote"]:
        print(f"{TAG} persisted {report['rowsPersisted']} quality rows")
    else:
        print(f"{TAG} DRY RUN - nothing written")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
