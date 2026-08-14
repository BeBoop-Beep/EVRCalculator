"""READ-ONLY strict audit of the published public RIP leaderboard.

WHAT THIS ANSWERS
-----------------
"Is what production is serving right now actually the canonical model, over the
authoritative cohort, from the latest simulations?" - as a set of named
assertions rather than a feeling about a market date.

Every assertion below exists because its absence let a real defect ship:

  * 22 eligible rows, and ranks contiguous 1..22
        - a leaderboard whose denominator disagrees with its own list.
  * every row sourced from Financial RIP V3, Collector Appeal V3, Overall RIP V7
    and the v7 public contract
        - the newest published leaderboard reported
          `overall_rip_v4_90_financial_10_ca7` / `financial_rip_v2_60_25_15`
          while V3 simulations already existed, and nothing noticed.
  * every source simulation is the latest eligible run
        - a re-run after a fix would otherwise never reach the public page.
  * no unsupported set is ranked
        - support comes from `supported_opening_set_keys()`, never from whether
          a score happens to exist.
  * publication_status=complete and published_at non-null
        - a failed publication must not read as a published one.
  * no public row falls back to Financial RIP V2 or legacy CA7
        - a fallback that renders is a fallback nobody investigates.

STRICTLY READ-ONLY. This script performs SELECTs only. It never rebuilds a
snapshot, never publishes, never writes a row, and never runs a simulation.

Exit codes
    0  every assertion passed
    1  one or more assertions failed
    2  the audit could not run (unreadable authority)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.db.services.public_rip_publication_contract import (  # noqa: E402
    canonical_publication_identity,
    evaluate_leaderboard_staleness,
    read_published_identity,
    supported_cohort_fingerprint,
)
from backend.desirability.scoring_config import (  # noqa: E402
    FINANCIAL_RIP_V2_VERSION,
)
from backend.desirability.collector_appeal import (  # noqa: E402
    COLLECTOR_APPEAL_CA7_VERSION,
)

logger = logging.getLogger("audit_public_rip_leaderboard_publication")

TAG = "[public-rip-leaderboard-audit]"

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_CANNOT_RUN = 2


@dataclass
class Assertion:
    name: str
    passed: bool
    detail: str

    def line(self) -> str:
        return f"{TAG} {'PASS' if self.passed else 'FAIL'} {self.name}: {self.detail}"


@dataclass
class AuditReport:
    assertions: List[Assertion] = field(default_factory=list)
    snapshot_id: Optional[str] = None
    market_date: Optional[str] = None
    ranked_row_count: int = 0
    expected_cohort_count: int = 0
    error: Optional[str] = None

    @property
    def passed(self) -> bool:
        # An unreadable authority is never a pass (fail-closed).
        return self.error is None and bool(self.assertions) and all(a.passed for a in self.assertions)

    @property
    def failures(self) -> List[Assertion]:
        return [a for a in self.assertions if not a.passed]

    def add(self, name: str, passed: bool, detail: str) -> None:
        self.assertions.append(Assertion(name=name, passed=bool(passed), detail=detail))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshotId": self.snapshot_id,
            "marketDate": self.market_date,
            "rankedRowCount": self.ranked_row_count,
            "expectedCohortCount": self.expected_cohort_count,
            "passed": self.passed,
            "error": self.error,
            "assertions": [
                {"name": a.name, "passed": a.passed, "detail": a.detail} for a in self.assertions
            ],
        }

    def lines(self) -> List[str]:
        out = [
            f"{TAG} ===== published RIP leaderboard audit =====",
            f"{TAG} snapshot_id={self.snapshot_id} market_date={self.market_date}",
            f"{TAG} ranked_rows={self.ranked_row_count} expected_cohort={self.expected_cohort_count}",
        ]
        if self.error:
            out.append(f"{TAG} error={self.error}")
        out.extend(assertion.line() for assertion in self.assertions)
        out.append(f"{TAG} passed={self.passed}")
        return out


def _rows(result: Any) -> List[Dict[str, Any]]:
    return list((result.data if result else []) or [])


def run_audit(client: Any) -> AuditReport:
    """Read what is published and assert it against the canonical contract."""
    report = AuditReport()
    canonical = canonical_publication_identity()
    supported = supported_cohort_fingerprint()
    report.expected_cohort_count = int(supported["count"] or 0)

    try:
        snapshots = _rows(
            client.table("pokemon_public_rip_leaderboard_snapshots")
            .select(
                "id,market_date,built_at,published_at,publication_status,eligible_cohort_count,"
                "cohort_version,cohort_fingerprint,overall_rip_version,financial_rip_version,"
                "ca7_version,diagnostics_json"
            )
            .eq("publication_status", "complete")
            .order("market_date", desc=True)
            .order("published_at", desc=True)
            .limit(1)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001 - unreadable authority is not a pass
        report.error = f"leaderboard snapshot read failed ({exc})"
        return report

    if not snapshots:
        report.error = "no complete published RIP leaderboard snapshot exists"
        return report

    snapshot = snapshots[0]
    report.snapshot_id = str(snapshot.get("id"))
    report.market_date = str(snapshot.get("market_date"))

    try:
        published_rows = _rows(
            client.table("pokemon_public_rip_leaderboard_rows")
            .select(
                "set_id,set_canonical_key,overall_rip_score,overall_rip_rank,"
                "financial_rip_score,financial_rip_rank,overall_ranked_cohort_count,"
                "simulation_calculation_run_id"
            )
            .eq("snapshot_id", report.snapshot_id)
            .execute()
        )
        # Only the three columns this audit actually consumes. The live view
        # exposes `canonical_key`, NOT `set_canonical_key`; requesting the latter
        # made PostgREST reject the whole SELECT, so the audit could not run at
        # all. The canonical key used below comes from
        # pokemon_public_rip_leaderboard_rows.set_canonical_key (a real column on
        # that table), so nothing here needs a key from this view.
        latest_rows = _rows(
            client.table("explore_rip_statistics_latest")
            .select("set_id,calculation_run_id,financial_rip_v3_score_version")
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        report.error = f"leaderboard row read failed ({exc})"
        return report

    report.ranked_row_count = len(published_rows)
    observed = read_published_identity(snapshot)

    # --- version assertions ------------------------------------------------
    for name, key in (
        ("financial_rip_is_v3", "financialRipVersion"),
        # Named for the QUESTION, not for a version number. The previous labels
        # hard-coded "v3"/"v7" while the value beside them was compared against
        # whatever `scoring_config` currently selects, so after the V4 cutover
        # the audit printed "PASS collector_appeal_is_v3: published='...v4...'".
        # A check whose name contradicts its own output teaches a reader to stop
        # reading the name.
        ("collector_appeal_is_canonical", "collectorAppealVersion"),
        ("overall_rip_is_canonical", "overallRipVersion"),
        ("public_contract_is_canonical", "publicRipContractVersion"),
    ):
        report.add(
            name,
            observed.get(key) == canonical[key],
            f"published={observed.get(key)!r} canonical={canonical[key]!r}",
        )

    report.add(
        "no_financial_rip_v2_fallback",
        observed.get("financialRipVersion") != FINANCIAL_RIP_V2_VERSION,
        f"published Financial RIP version={observed.get('financialRipVersion')!r}",
    )
    report.add(
        "no_legacy_ca7_fallback",
        observed.get("collectorAppealVersion") != COLLECTOR_APPEAL_CA7_VERSION,
        f"published Collector Appeal version={observed.get('collectorAppealVersion')!r}",
    )

    # --- publication state -------------------------------------------------
    report.add(
        "publication_status_complete",
        str(snapshot.get("publication_status") or "") == "complete",
        f"publication_status={snapshot.get('publication_status')!r}",
    )
    report.add(
        "published_at_present",
        bool(snapshot.get("published_at")),
        f"published_at={snapshot.get('published_at')!r}",
    )

    # --- cohort assertions -------------------------------------------------
    report.add(
        "row_count_matches_supported_cohort",
        report.ranked_row_count == report.expected_cohort_count,
        f"rows={report.ranked_row_count} expected={report.expected_cohort_count}",
    )
    report.add(
        "supported_cohort_fingerprint_matches",
        observed.get("supportedCohortFingerprint") == supported["fingerprint"],
        f"published={observed.get('supportedCohortFingerprint')!r} "
        f"current={supported['fingerprint']!r}",
    )

    ranks = sorted(
        int(row.get("overall_rip_rank"))
        for row in published_rows
        if row.get("overall_rip_rank") is not None
    )
    expected_ranks = list(range(1, len(published_rows) + 1))
    report.add(
        "ranks_contiguous_from_one",
        ranks == expected_ranks,
        f"ranks={ranks[:5]}...{ranks[-3:] if len(ranks) > 8 else ranks[5:]} expected 1..{len(published_rows)}",
    )

    supported_keys = set(supported["keys"])
    published_keys = {
        str(row.get("set_canonical_key")) for row in published_rows if row.get("set_canonical_key")
    }
    unsupported_ranked = sorted(published_keys - supported_keys)
    report.add(
        "no_unsupported_set_ranked",
        not unsupported_ranked,
        f"unsupported ranked keys={unsupported_ranked or 'none'}",
    )
    missing_supported = sorted(supported_keys - published_keys)
    report.add(
        "every_supported_set_ranked",
        not missing_supported,
        f"supported but unranked={missing_supported or 'none'}",
    )

    # --- source-run assertions ---------------------------------------------
    latest_by_set = {
        str(row.get("set_id")): str(row.get("calculation_run_id") or "")
        for row in latest_rows
        if row.get("set_id")
    }
    v3_version_by_set = {
        str(row.get("set_id")): row.get("financial_rip_v3_score_version")
        for row in latest_rows
        if row.get("set_id")
    }
    superseded = []
    for row in published_rows:
        set_id = str(row.get("set_id"))
        published_run = str(row.get("simulation_calculation_run_id") or "")
        latest_run = latest_by_set.get(set_id, "")
        if latest_run and published_run != latest_run:
            superseded.append(
                f"{row.get('set_canonical_key') or set_id}: published={published_run} latest={latest_run}"
            )
    report.add(
        "every_row_from_latest_eligible_run",
        not superseded,
        "; ".join(superseded) if superseded else "all rows on the latest eligible run",
    )

    non_v3_sources = sorted(
        str(row.get("set_canonical_key") or row.get("set_id"))
        for row in published_rows
        if v3_version_by_set.get(str(row.get("set_id"))) != canonical["financialRipVersion"]
    )
    report.add(
        "every_source_run_computed_financial_rip_v3",
        not non_v3_sources,
        f"sets whose latest run is not on {canonical['financialRipVersion']!r}: "
        f"{non_v3_sources or 'none'}",
    )

    # --- the shared staleness evaluator, as one rolled-up assertion --------
    reasons = evaluate_leaderboard_staleness(
        snapshot,
        ranked_row_count=report.ranked_row_count,
        latest_eligible_run_id_by_set={
            set_id: run for set_id, run in latest_by_set.items()
            if set_id in {str(row.get("set_id")) for row in published_rows}
        },
        published_run_id_by_set={
            str(row.get("set_id")): str(row.get("simulation_calculation_run_id") or "")
            for row in published_rows
        },
        cohort=supported,
    )
    report.add(
        "shared_staleness_evaluator_reports_current",
        not reasons,
        "; ".join(str(reason.get("code")) for reason in reasons) or "no staleness reasons",
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "READ-ONLY strict audit of the published public RIP leaderboard. Asserts the "
            "canonical Financial RIP V3 / Collector Appeal V3 / Overall RIP V7 / public "
            "contract v7 versions, the authoritative supported cohort, contiguous ranks, "
            "and that every row was built from the latest eligible simulation run. "
            "Performs SELECTs only: it never rebuilds, publishes, or simulates."
        )
    )
    parser.add_argument("--json", action="store_true", help="Emit the report as JSON.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from backend.scripts.pokemon_snapshot_builders import get_client

    try:
        report = run_audit(get_client())
    except Exception as exc:  # noqa: BLE001
        logger.exception("%s audit raised", TAG)
        print(f"{TAG} error={exc}")
        return EXIT_CANNOT_RUN

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, default=str))
    else:
        for line in report.lines():
            print(line)

    if report.error:
        return EXIT_CANNOT_RUN
    return EXIT_OK if report.passed else EXIT_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
