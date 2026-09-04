"""Read-only coverage audit for EV Representativeness Tier A research.

Answers one question for the promoted market date: does every current
opening-supported set have exact-artifact Tier A research (or a legitimate
terminal non-resolved status) attached to its EXACT current
``calculation_run_id``?

This is deliberately summary-table only. It never reads
``ev_representativeness_curve`` or any curve/session data - only the one row
per (run, version) in ``ev_representativeness_run_summary`` that the daily
orchestrator (``run_daily_opening_publication._build_ev_representativeness_tier_a``)
already builds non-blocking, before the rankings/set-page snapshot rebuild.

Classification, from actual research semantics (not naming inference):

    healthy            - a summary row exists for the current run and
                          horizon_r80_c80_status is a resolved status
                          (anything other than the "exceeds_search_cap"
                          terminal state).
    legitimate_no_headline - a summary row exists for the current run but
                          horizon_r80_c80_status == exceeds_search_cap. This
                          is NOT a pipeline failure: the search never found a
                          stable pack count under the cap, so the UI correctly
                          has no pack count to show.
    missing             - no summary row at all for the current run.
    wrong_run           - a summary row exists for this set but keyed to a
                          DIFFERENT calculation_run_id than the one currently
                          published (stale research, never rebuilt for the
                          new run).
    version_mismatch    - a summary row exists for the current run but under
                          a different research_method_version than the
                          currently canonical one.

Usage:
    python -m backend.scripts.audit_ev_representativeness_coverage \
        [--market-date YYYY-MM-DD] [--json]

Exit codes: 0 always (read-only report; never a publication gate). Use --json
and inspect ``unhealthy_count`` for automation.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.db.services.opening_simulation_gate import (  # noqa: E402
    STATUS_CURRENT,
    evaluate_opening_simulation_freshness,
)
from backend.research.ev_representativeness.finite_sample import HORIZON_EXCEEDS_CAP  # noqa: E402
from backend.research.ev_representativeness.version import EV_REPRESENTATIVENESS_VERSION  # noqa: E402

TAG = "[ev-representativeness-coverage]"


@dataclass
class SetCoverageRow:
    canonical_key: str
    set_id: str
    current_run_id: Optional[str]
    status: str  # healthy | legitimate_no_headline | missing | wrong_run | version_mismatch
    horizon_r80_c80_status: Optional[str] = None
    research_run_id: Optional[str] = None
    research_version: Optional[str] = None


@dataclass
class CoverageReport:
    market_date: Optional[str] = None
    supported_current_set_count: int = 0
    healthy: List[str] = field(default_factory=list)
    legitimate_no_headline: List[str] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)
    wrong_run: List[str] = field(default_factory=list)
    version_mismatch: List[str] = field(default_factory=list)
    error: Optional[str] = None
    rows: List[SetCoverageRow] = field(default_factory=list)

    @property
    def unhealthy_count(self) -> int:
        return len(self.missing) + len(self.wrong_run) + len(self.version_mismatch)

    def lines(self) -> List[str]:
        out = [
            f"{TAG} market_date={self.market_date}",
            f"{TAG} supported_current_sets={self.supported_current_set_count}",
            f"{TAG} healthy={len(self.healthy)}",
            f"{TAG} legitimate_no_headline={len(self.legitimate_no_headline)}",
            f"{TAG} missing={len(self.missing)}",
            f"{TAG} wrong_run={len(self.wrong_run)}",
            f"{TAG} version_mismatch={len(self.version_mismatch)}",
        ]
        for label, keys in (
            ("missing", self.missing),
            ("wrong_run", self.wrong_run),
            ("version_mismatch", self.version_mismatch),
        ):
            for key in keys:
                out.append(f"{TAG}   {label}={key}")
        if self.error:
            out.append(f"{TAG} error={self.error}")
        return out


def _rows(response: Any) -> List[Dict[str, Any]]:
    return list((response.data if response else []) or [])


def run_audit(
    client: Any,
    market_date: Optional[str] = None,
    *,
    canonical_keys: Optional[Sequence[str]] = None,
) -> CoverageReport:
    report = CoverageReport(market_date=market_date)

    if not market_date:
        from backend.scripts.audit_opening_analytics_publication import resolve_market_date

        resolved, date_error = resolve_market_date(client, None)
        if date_error or not resolved:
            report.error = date_error or "no promoted market date could be resolved"
            return report
        market_date = resolved

    freshness = evaluate_opening_simulation_freshness(
        client, market_date=market_date, canonical_keys=canonical_keys
    )
    if freshness.error:
        report.error = freshness.error
        return report
    report.market_date = freshness.market_date

    current = [s for s in freshness.statuses if s.status == STATUS_CURRENT and s.calculation_run_id]
    report.supported_current_set_count = len(current)
    if not current:
        return report

    run_ids = sorted({str(s.calculation_run_id) for s in current})
    summary_by_run: Dict[str, Dict[str, Any]] = {}
    # Also index by set_id so a stale (wrong-run) research row is still found.
    summary_by_set: Dict[str, Dict[str, Any]] = {}
    for start in range(0, len(run_ids), 25):
        chunk = run_ids[start : start + 25]
        for row in _rows(
            client.table("ev_representativeness_run_summary")
            .select("calculation_run_id,set_id,research_method_version,horizon_r80_c80_status")
            .in_("calculation_run_id", chunk)
            .execute()
        ):
            summary_by_run[str(row["calculation_run_id"])] = row

    set_ids = sorted({str(s.set_id) for s in current if s.set_id})
    for start in range(0, len(set_ids), 25):
        chunk = set_ids[start : start + 25]
        for row in _rows(
            client.table("ev_representativeness_run_summary")
            .select("calculation_run_id,set_id,research_method_version,horizon_r80_c80_status")
            .in_("set_id", chunk)
            .order("calculation_run_id", desc=True)
            .execute()
        ):
            summary_by_set.setdefault(str(row["set_id"]), row)

    for item in current:
        run_id = str(item.calculation_run_id)
        set_id = str(item.set_id or "")
        key = item.canonical_key or set_id or "?"
        exact = summary_by_run.get(run_id)
        if exact is not None:
            if exact.get("research_method_version") != EV_REPRESENTATIVENESS_VERSION:
                status = "version_mismatch"
                report.version_mismatch.append(key)
            elif exact.get("horizon_r80_c80_status") == HORIZON_EXCEEDS_CAP:
                status = "legitimate_no_headline"
                report.legitimate_no_headline.append(key)
            else:
                status = "healthy"
                report.healthy.append(key)
            row = SetCoverageRow(
                canonical_key=key, set_id=set_id, current_run_id=run_id, status=status,
                horizon_r80_c80_status=exact.get("horizon_r80_c80_status"),
                research_run_id=str(exact.get("calculation_run_id")),
                research_version=exact.get("research_method_version"),
            )
        else:
            stale = summary_by_set.get(set_id)
            if stale is not None:
                status = "wrong_run"
                report.wrong_run.append(key)
                row = SetCoverageRow(
                    canonical_key=key, set_id=set_id, current_run_id=run_id, status=status,
                    horizon_r80_c80_status=stale.get("horizon_r80_c80_status"),
                    research_run_id=str(stale.get("calculation_run_id")),
                    research_version=stale.get("research_method_version"),
                )
            else:
                status = "missing"
                report.missing.append(key)
                row = SetCoverageRow(
                    canonical_key=key, set_id=set_id, current_run_id=run_id, status=status,
                )
        report.rows.append(row)

    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-date", default=None, help="Override the market date (YYYY-MM-DD).")
    parser.add_argument("--json", action="store_true", help="Emit the report as JSON.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    from backend.scripts.pokemon_snapshot_builders import get_client

    report = run_audit(get_client(), market_date=args.market_date)
    if args.json:
        print(json.dumps(asdict(report), indent=2, default=str))
    else:
        for line in report.lines():
            print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
