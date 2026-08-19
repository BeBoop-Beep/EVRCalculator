"""Coordinated daily publication for Pokemon opening analytics.

Why this exists
---------------
Simulation generation and snapshot publication are two different jobs with two
different clocks, and nothing used to reconcile them. The snapshot builders
re-serialize whatever simulation rows already exist — they never run a
simulation — so when the simulation batch stopped, the market dashboards kept
advancing while Opening Profit vs Cost silently froze. Production ran a
2026-07-31 market date against an OPvC series ending 2026-07-27 for five days
and no step in the pipeline was responsible for noticing.

This orchestrator makes the ordering explicit and the reconciliation mandatory:

    1. resolve the promoted market date from the scrape batch (never wall-clock)
    2. run opening simulations for every eligible set that is not already
       current for that date
    3. VERIFY every supported set now has a valid simulation for that date
    4. rebuild the coordinated market + set-page snapshots
    5. re-audit and refuse to report success when OPvC is still behind

Separation of responsibilities is preserved: the snapshot builders still never
run a simulation, and this script never writes snapshot rows itself. It only
sequences the existing commands and refuses to call a partial result "current".

Idempotency
-----------
``calculation_history_trend`` resolves to one row per (set, run date) — the
underlying view keeps only the latest run per day — so re-running a set on a
date it already covers replaces its point rather than duplicating it. On top of
that structural guarantee, step 2 skips sets already verified current, so a
rerun for the same market date does no simulation work at all.

Exit codes
    0  simulations current and snapshots published
    1  a simulation failed, or publication cannot claim full freshness
    2  the run could not start (no promoted market date, unreadable authority)
    3  publication DEFERRED by the scrape-cohort gate (propagated unchanged)
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.db.services.opening_simulation_gate import (  # noqa: E402
    OpeningSimulationFreshnessReport,
    evaluate_opening_simulation_freshness,
    sets_needing_simulation,
)
from backend.db.services.publication_gate import GATE_DEFERRED_EXIT_CODE  # noqa: E402

logger = logging.getLogger("run_daily_opening_publication")

TAG = "[daily-opening-publication]"

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_CANNOT_START = 2


@dataclass
class SimulationOutcome:
    canonical_key: str
    succeeded: bool
    skipped: bool = False
    reason: Optional[str] = None
    duration_seconds: float = 0.0


@dataclass
class PublicationSummary:
    market_date: Optional[str] = None
    eligible_set_count: int = 0
    simulation_succeeded: int = 0
    simulation_failed: int = 0
    skipped: List[Dict[str, str]] = field(default_factory=list)
    latest_simulation_date_by_set: Dict[str, Optional[str]] = field(default_factory=dict)
    snapshot_publication_status: str = "not_attempted"
    chase_snapshot_publication_status: str = "not_attempted"
    chase_audit_status: str = "not_attempted"
    chase_audit_failures: List[str] = field(default_factory=list)
    verification_passed: bool = False
    publication_audit_status: str = "not_attempted"
    publication_audit_failed_sets: List[str] = field(default_factory=list)
    market_audit_status: str = "not_attempted"
    market_audit_failed_sets: List[str] = field(default_factory=list)
    market_audit_report: Optional[Dict[str, Any]] = None
    rip_contract_audit_status: str = "not_attempted"
    rip_contract_audit_failures: List[str] = field(default_factory=list)
    rip_contract_audit_report: Optional[Dict[str, Any]] = None
    sealed_product_finalization_status: str = "not_attempted"
    sealed_product_finalization_report: Optional[Dict[str, Any]] = None
    rip_stats_publication_status: str = "not_attempted"
    rip_stats_audit_status: str = "not_attempted"
    rip_stats_market_date: Optional[str] = None
    rip_stats_set_count: int = 0
    rip_stats_source_run_fingerprint: Optional[str] = None
    rip_stats_failures: List[str] = field(default_factory=list)
    exit_code: int = EXIT_CANNOT_START
    error: Optional[str] = None

    def lines(self) -> List[str]:
        out = [
            f"{TAG} ===== daily opening publication summary =====",
            f"{TAG} market_date={self.market_date}",
            f"{TAG} eligible_sets={self.eligible_set_count}",
            f"{TAG} simulations_succeeded={self.simulation_succeeded}",
            f"{TAG} simulations_failed={self.simulation_failed}",
            f"{TAG} skipped_sets={len(self.skipped)}",
        ]
        for entry in self.skipped:
            out.append(f"{TAG}   skipped set={entry['set']} reason={entry['reason']}")
        out.append(f"{TAG} latest_simulation_date_by_set:")
        for set_key in sorted(self.latest_simulation_date_by_set):
            out.append(f"{TAG}   {set_key}={self.latest_simulation_date_by_set[set_key] or '-'}")
        out.append(
            f"{TAG} sealed_product_finalization_status={self.sealed_product_finalization_status}"
        )
        if self.sealed_product_finalization_report:
            report = self.sealed_product_finalization_report
            out.append(
                f"{TAG}   sealed_product_rows_considered={report.get('rowsConsidered')} "
                f"finalized={report.get('rowsFinalized')} "
                f"ca_unavailable={report.get('rowsCollectorAppealUnavailable')} "
                f"skipped={report.get('rowsSkipped')} sets={report.get('setCount')}"
            )
            out.append(
                f"{TAG}   collector_appeal_bundle_builds={report.get('collectorAppealBundleBuilds')} "
                f"bundle_ms={report.get('collectorAppealBundleMs')} "
                f"total_ms={report.get('elapsedMs')}"
            )
        out.append(f"{TAG} snapshot_publication_status={self.snapshot_publication_status}")
        out.append(f"{TAG} chase_snapshot_publication_status={self.chase_snapshot_publication_status}")
        out.append(f"{TAG} chase_audit_status={self.chase_audit_status}")
        for failure in self.chase_audit_failures:
            out.append(f"{TAG}   chase_audit_failed={failure}")
        out.append(f"{TAG} rip_stats_publication_status={self.rip_stats_publication_status}")
        out.append(f"{TAG} rip_stats_audit_status={self.rip_stats_audit_status}")
        out.append(f"{TAG} rip_stats_market_date={self.rip_stats_market_date}")
        out.append(f"{TAG} rip_stats_set_count={self.rip_stats_set_count}")
        out.append(f"{TAG} rip_stats_source_run_fingerprint={self.rip_stats_source_run_fingerprint}")
        for failure in self.rip_stats_failures:
            out.append(f"{TAG}   rip_stats_failure={failure}")
        out.append(f"{TAG} verification_passed={self.verification_passed}")
        out.append(f"{TAG} publication_audit_status={self.publication_audit_status}")
        if self.publication_audit_failed_sets:
            out.append(
                f"{TAG} publication_audit_failed_sets={','.join(self.publication_audit_failed_sets)}"
            )
        out.append(f"{TAG} market_audit_status={self.market_audit_status}")
        if self.market_audit_failed_sets:
            out.append(
                f"{TAG} market_audit_failed_sets={','.join(self.market_audit_failed_sets)}"
            )
        out.append(f"{TAG} rip_contract_audit_status={self.rip_contract_audit_status}")
        for failure in self.rip_contract_audit_failures:
            out.append(f"{TAG}   rip_contract_audit_failed={failure}")
        if self.market_audit_report:
            failed_by_section = self.market_audit_report.get("failed_by_section") or {}
            for section, sets in sorted(failed_by_section.items()):
                out.append(f"{TAG}   failed_section={section} sets={','.join(sets)}")
        if self.error:
            out.append(f"{TAG} error={self.error}")
        out.append(f"{TAG} exit_code={self.exit_code}")
        return out


def _run_command(command: Sequence[str], *, dry_run: bool) -> int:
    printable = " ".join(command)
    if dry_run:
        print(f"{TAG} DRY-RUN would run: {printable}")
        return 0
    print(f"{TAG} running: {printable}")
    completed = subprocess.run(command, cwd=str(REPO_ROOT))
    return int(completed.returncode)


def run_simulations_for_sets(
    set_keys: Sequence[str],
    *,
    python_executable: Optional[str] = None,
    dry_run: bool = False,
) -> List[SimulationOutcome]:
    """Run the existing V2 batch runner once per set that needs work.

    Per-set invocation is what makes the skip in step 2 meaningful: a set
    already current for the market date is never launched at all.
    """
    executable = python_executable or sys.executable
    outcomes: List[SimulationOutcome] = []
    for set_key in set_keys:
        started = time.perf_counter()
        code = _run_command(
            [executable, str(REPO_ROOT / "backend" / "scripts" / "run_all_v2_sets.py"), "--set", set_key],
            dry_run=dry_run,
        )
        outcomes.append(
            SimulationOutcome(
                canonical_key=set_key,
                succeeded=code == 0,
                reason=None if code == 0 else f"run_all_v2_sets exited {code}",
                duration_seconds=round(time.perf_counter() - started, 2),
            )
        )
    return outcomes


def refresh_public_snapshots(
    *,
    python_executable: Optional[str] = None,
    commit: bool = True,
    dry_run: bool = False,
    gate_wait_attempts: int = 6,
    gate_wait_seconds: int = 600,
) -> int:
    executable = python_executable or sys.executable
    command = [
        executable,
        str(REPO_ROOT / "backend" / "scripts" / "refresh_stale_public_snapshots.py"),
        "--strict",
        "--gate-wait-attempts",
        str(gate_wait_attempts),
        "--gate-wait-seconds",
        str(gate_wait_seconds),
    ]
    if commit:
        command.insert(2, "--commit")
    return _run_command(command, dry_run=dry_run)


def refresh_chase_economics_snapshots(
    *, python_executable: Optional[str] = None, dry_run: bool = False,
    market_date: Optional[str] = None,
) -> int:
    """Rebuild Chase only after coordinated snapshots establish run identity."""
    command = [
        python_executable or sys.executable,
        str(REPO_ROOT / "backend" / "scripts" / "build_pokemon_set_chase_economics_snapshots.py"),
        "--current-authorities",
        "--commit",
    ]
    if market_date:
        command.extend(["--market-date", market_date])
    return _run_command(command, dry_run=dry_run)


def _chase_capability_expected(client: Any) -> bool:
    """Do not force pre-Chase unit fakes to emulate newly audited relations."""
    tables = getattr(client, "_tables", None)
    if tables is None:
        tables = getattr(client, "tables", None)
    return not isinstance(tables, dict) or "pokemon_set_chase_economics_snapshot_latest" in tables


def _run_chase_audit(
    client: Any, summary: PublicationSummary, *, market_date: str,
    dry_run: bool, skip_snapshots: bool,
) -> str:
    if dry_run or skip_snapshots or not _chase_capability_expected(client):
        return "skipped"
    from backend.scripts.audit_chase_economics_publication import run_audit
    try:
        report = run_audit(client, market_date=market_date)
    except Exception as exc:  # fail closed
        return f"error:{exc}"
    summary.chase_audit_failures = report.failures
    return "passed" if report.passed else (f"error:{report.error}" if report.error else "failed")


def _latest_dates(report: OpeningSimulationFreshnessReport) -> Dict[str, Optional[str]]:
    return {
        status.canonical_key or (status.set_id or "?"): status.latest_simulation_date
        for status in report.statuses
    }


def _skipped_entries(report: OpeningSimulationFreshnessReport) -> List[Dict[str, str]]:
    from backend.db.services.opening_simulation_gate import STATUS_CURRENT, STATUS_UNSUPPORTED

    entries: List[Dict[str, str]] = []
    for status in report.statuses:
        if status.status == STATUS_UNSUPPORTED:
            entries.append(
                {
                    "set": status.canonical_key or "?",
                    "reason": status.reason or "explicitly excepted from opening analytics",
                }
            )
        elif status.status == STATUS_CURRENT:
            entries.append(
                {
                    "set": status.canonical_key or "?",
                    "reason": f"already current for {report.market_date}",
                }
            )
    return entries


def orchestrate(
    client: Any,
    *,
    market_date: Optional[str] = None,
    unsupported_keys: Sequence[str] = (),
    dry_run: bool = False,
    skip_snapshots: bool = False,
    python_executable: Optional[str] = None,
    gate_wait_attempts: int = 6,
    gate_wait_seconds: int = 600,
) -> PublicationSummary:
    summary = PublicationSummary()

    # ---- Step 1: the coordinated market date, never wall-clock -------------
    from backend.scripts.audit_opening_analytics_publication import resolve_market_date

    resolved_market_date, date_error = resolve_market_date(client, market_date)
    if date_error or not resolved_market_date:
        summary.error = date_error or "no promoted market date could be resolved"
        summary.exit_code = EXIT_CANNOT_START
        return summary
    summary.market_date = resolved_market_date

    # ---- Step 1b: this date must OWN publication authority -----------------
    # resolve_market_date deliberately still honours an explicit --market-date
    # so read-only audits can target any historical day. This orchestrator is
    # COMMIT-CAPABLE, so it must additionally prove the resolved date is
    # genuinely promoted before anything downstream mutates. Placed before
    # simulations, sealed-product finalization, RIP Stats aggregation and every
    # snapshot write - the 2026-08-18 incident got past this point because no
    # such check existed on this path.
    from backend.db.services.publication_gate import (
        MODE_REQUIRED,
        evaluate_publication_gate,
        gate_decision_report,
    )

    authority = evaluate_publication_gate(
        client, market_date=resolved_market_date, mode=MODE_REQUIRED
    )
    if not authority.allowed:
        for line in gate_decision_report(authority, entry_point="daily opening publication"):
            print(line)
        summary.error = (
            f"publication authority denied for {resolved_market_date}: {authority.reason} "
            f"(reason_code={authority.reason_code})"
        )
        summary.exit_code = GATE_DEFERRED_EXIT_CODE
        return summary

    # ---- Step 2: what still needs a simulation for that date ---------------
    before = evaluate_opening_simulation_freshness(
        client, market_date=resolved_market_date, unsupported_keys=unsupported_keys
    )
    if before.error:
        summary.error = before.error
        summary.exit_code = EXIT_CANNOT_START
        return summary

    summary.eligible_set_count = before.eligible_count
    summary.skipped = _skipped_entries(before)
    pending = sets_needing_simulation(before)
    print(f"{TAG} market_date={resolved_market_date} eligible={before.eligible_count} pending={len(pending)}")

    outcomes = run_simulations_for_sets(pending, python_executable=python_executable, dry_run=dry_run)
    summary.simulation_succeeded = sum(1 for outcome in outcomes if outcome.succeeded)
    summary.simulation_failed = sum(1 for outcome in outcomes if not outcome.succeeded)
    for outcome in outcomes:
        if not outcome.succeeded:
            print(f"{TAG} simulation FAILED set={outcome.canonical_key} reason={outcome.reason}")

    # ---- Step 3: verify BEFORE publishing ----------------------------------
    after = evaluate_opening_simulation_freshness(
        client, market_date=resolved_market_date, unsupported_keys=unsupported_keys
    )
    summary.latest_simulation_date_by_set = _latest_dates(after)
    summary.verification_passed = after.ok
    for line in after.report_lines(entry_point="daily opening publication"):
        print(line)

    # ---- Step 3b: finalize sealed-product Collector Appeal / Overall RIP ----
    # Placed at the narrowest correct point: AFTER every required simulation has
    # completed and freshness has been verified (so the cohort is whole), and
    # BEFORE snapshot publication (so nothing downstream can publish a product
    # row whose Overall RIP is still pending). It runs in ONE process, which is
    # the entire reason it exists - the per-set subprocesses no longer build the
    # Collector Appeal bundle at all, so this is the only build in the day.
    summary.sealed_product_finalization_status = _finalize_sealed_products(
        client,
        summary,
        market_date=resolved_market_date,
        unsupported_keys=unsupported_keys,
        dry_run=dry_run,
    )

    # ---- Step 3c: exact Pokemon-wide RIP Stats ----------------------------
    # This is Phase 2 only and is never attempted before the simulation gate.
    if skip_snapshots:
        summary.rip_stats_publication_status = "skipped_skip_snapshots"
    elif after.ok and not summary.simulation_failed and _rip_stats_capability_expected(client):
        summary.rip_stats_publication_status = _publish_rip_stats(
            client, summary, market_date=resolved_market_date, dry_run=dry_run
        )
        if summary.rip_stats_publication_status not in {"published", "validated_dry_run"}:
            summary.exit_code = EXIT_FAILED
            summary.error = "Pokemon RIP Stats publication failed; previous latest snapshot retained"
            return summary
    else:
        summary.rip_stats_publication_status = (
            "skipped_cohort_not_verified" if not after.ok or summary.simulation_failed
            else "skipped_legacy_test_client"
        )

    # ---- Step 4: publish snapshots ----------------------------------------
    # Snapshots still rebuild when verification failed: the market sections are
    # legitimately fresh and must not be held hostage to a stale simulation.
    # What must NOT happen is reporting the run as fully current, which step 5
    # enforces via the exit code.
    if skip_snapshots:
        summary.snapshot_publication_status = "skipped"
        summary.chase_snapshot_publication_status = "skipped"
    else:
        refresh_code = refresh_public_snapshots(
            python_executable=python_executable,
            dry_run=dry_run,
            gate_wait_attempts=gate_wait_attempts,
            gate_wait_seconds=gate_wait_seconds,
        )
        if refresh_code == 0:
            summary.snapshot_publication_status = "published"
        elif refresh_code == GATE_DEFERRED_EXIT_CODE:
            summary.snapshot_publication_status = "deferred_cohort_not_ready"
            summary.exit_code = GATE_DEFERRED_EXIT_CODE
            return summary
        else:
            summary.snapshot_publication_status = f"failed_exit_{refresh_code}"
            summary.exit_code = EXIT_FAILED
            return summary

        # The set-page rebuild above establishes the authoritative run identity.
        # Sealed-product finalization already completed in step 3b. This is the
        # narrow point where all four Chase inputs are authoritative together.
        chase_code = refresh_chase_economics_snapshots(
            python_executable=python_executable, dry_run=dry_run,
            market_date=resolved_market_date,
        )
        if chase_code != 0:
            summary.chase_snapshot_publication_status = f"failed_exit_{chase_code}"
            summary.exit_code = EXIT_FAILED
            summary.error = "Chase Economics snapshot rebuild failed"
            return summary
        summary.chase_snapshot_publication_status = "published"

    # ---- Step 5: refuse to claim freshness we do not have ------------------
    if summary.simulation_failed or not summary.verification_passed:
        summary.exit_code = EXIT_FAILED
        if not summary.error:
            failed = ", ".join(
                f"{status.canonical_key}:{status.status}" for status in after.failures
            )
            summary.error = (
                "Opening Profit vs Cost is NOT current for "
                f"{resolved_market_date}; refusing to report full freshness ({failed})"
            )
        return summary

    # Chase combines run-frozen inputs with current card/product prices. Its
    # dedicated audit is therefore a publication gate, not a best-effort
    # monitor: exit 0 means every represented clock can be proved current.
    summary.chase_audit_status = _run_chase_audit(
        client, summary, market_date=resolved_market_date,
        dry_run=dry_run, skip_snapshots=skip_snapshots,
    )
    if summary.chase_audit_status not in {"passed", "skipped"}:
        summary.exit_code = EXIT_FAILED
        detail = "; ".join(summary.chase_audit_failures[:5]) or summary.chase_audit_status
        summary.error = f"Chase Economics publication is stale or unverifiable ({detail})"
        return summary

    # ---- Step 6: the published artifact must agree, not just the sources ---
    # Current simulations are necessary but NOT sufficient. The market-dashboard
    # snapshot is what Overview actually reads, and it can lag the simulation it
    # was built from (its freshness never tracked the simulation sources, so a
    # newer run left it classified fresh). Consuming the read-only audit here is
    # what stops this command exiting 0 while Overview still serves yesterday's
    # Opening Profit vs Cost.
    summary.publication_audit_status = _run_publication_audit(
        client,
        summary,
        resolved_market_date=resolved_market_date,
        unsupported_keys=unsupported_keys,
        dry_run=dry_run,
        skip_snapshots=skip_snapshots,
    )
    if summary.publication_audit_status not in {"passed", "skipped"}:
        summary.exit_code = EXIT_FAILED
        if not summary.error:
            detail = ", ".join(summary.publication_audit_failed_sets) or summary.publication_audit_status
            summary.error = (
                "published market-dashboard Opening Profit vs Cost history did not reach "
                f"{resolved_market_date}; refusing to report full freshness ({detail})"
            )
        return summary

    # ---- Step 7: every OTHER public market surface must agree too -----------
    # The audit above covers simulation freshness and Opening Profit vs Cost for
    # simulation-supported sets. It says nothing about Set Value, Top Chase,
    # Sealed Market, card prices, or the set-page header, and nothing at all
    # about the sets that carry no simulation. Any of those can sit a generation
    # behind while this command still reports success. This step closes that gap
    # across every publication-required set.
    summary.market_audit_status = _run_market_publication_audit(
        client,
        summary,
        resolved_market_date=resolved_market_date,
        dry_run=dry_run,
        skip_snapshots=skip_snapshots,
    )
    if summary.market_audit_status not in {"passed", "skipped"}:
        summary.exit_code = EXIT_FAILED
        if not summary.error:
            detail = ", ".join(summary.market_audit_failed_sets[:10]) or summary.market_audit_status
            summary.error = (
                "one or more public market sections are behind the promoted market date "
                f"{resolved_market_date}; refusing to report success ({detail})"
            )
        return summary

    # ---- Step 8: the published leaderboard must be on the CANONICAL contract --
    # Steps 6 and 7 both check FRESHNESS - did the data reach the promoted market
    # date. Neither asks which formula scored it, and a scoring-version change
    # moves no timestamp. That is how a leaderboard published under Financial RIP
    # V2 / Overall RIP v4 stayed classified current while 22 Financial RIP V3
    # simulations sat underneath it. This step asserts the versions, the
    # authoritative cohort, contiguous ranks and the source runs.
    summary.rip_contract_audit_status = _run_rip_contract_audit(
        client, summary, dry_run=dry_run, skip_snapshots=skip_snapshots
    )
    if summary.rip_contract_audit_status not in {"passed", "skipped"}:
        summary.exit_code = EXIT_FAILED
        if not summary.error:
            detail = "; ".join(summary.rip_contract_audit_failures[:5]) or (
                summary.rip_contract_audit_status
            )
            summary.error = (
                "the published RIP leaderboard is not on the canonical scoring contract; "
                f"refusing to report success ({detail})"
            )
        return summary

    summary.rip_stats_audit_status = (_audit_rip_stats(
        client, summary, market_date=resolved_market_date, dry_run=dry_run
    ) if summary.rip_stats_publication_status in {"published", "validated_dry_run"} else "skipped")
    if summary.rip_stats_audit_status not in {"passed", "skipped"}:
        summary.exit_code = EXIT_FAILED
        summary.error = "published Pokemon RIP Stats failed its provenance audit"
        return summary

    summary.exit_code = EXIT_OK
    return summary


def _rip_stats_capability_expected(client: Any) -> bool:
    """Keep strict legacy query fakes usable until they declare new relations.

    Real Supabase clients do not expose ``_tables``. Repository unit fakes do;
    once extended for RIP Stats they include the artifact relation explicitly.
    """
    fake_tables = getattr(client, "_tables", None)
    if isinstance(fake_tables, dict):
        return "simulation_pack_outcome_artifacts" in fake_tables
    return True


def _publish_rip_stats(client: Any, summary: PublicationSummary, *, market_date: str, dry_run: bool) -> str:
    try:
        from backend.db.services.pokemon_rip_stats_service import build_pokemon_rip_stats_snapshot, publish_pokemon_rip_stats_snapshot
        built = build_pokemon_rip_stats_snapshot(client, market_date=market_date)
        summary.rip_stats_market_date = market_date
        summary.rip_stats_set_count = int(built["metrics"]["setCount"])
        summary.rip_stats_source_run_fingerprint = built["snapshot"]["source_run_fingerprint"]
        if dry_run:
            return "validated_dry_run"
        publish_pokemon_rip_stats_snapshot(client, built)
        return "published"
    except Exception as exc:
        summary.rip_stats_failures.append(str(exc))
        return "failed"


def _audit_rip_stats(client: Any, summary: PublicationSummary, *, market_date: str, dry_run: bool) -> str:
    if dry_run:
        return "skipped"
    try:
        from backend.scripts.audit_pokemon_rip_stats_publication import audit
        report = audit(client, market_date)
        if report.get("status") != "passed":
            summary.rip_stats_failures.extend(str(item) for item in report.get("failures") or [])
            return "failed"
        return "passed"
    except Exception as exc:
        summary.rip_stats_failures.append(str(exc))
        return "failed"


def _finalize_sealed_products(
    client: Any,
    summary: PublicationSummary,
    *,
    market_date: str,
    unsupported_keys: Sequence[str],
    dry_run: bool,
) -> str:
    """Attach Collector Appeal + Overall RIP to today's Stage 1 product rows.

    Deliberately NON-FATAL to the publication. Stage 1 sealed-product results
    have no public consumer yet, and Financial RIP - the part that IS complete
    after simulation - is already persisted and correct. Failing the whole daily
    opening publication over an enrichment pass would trade a live, working
    loose-pack publication for an internal table's completeness. The status is
    reported instead, so the failure is visible rather than absorbed.
    """
    if dry_run:
        print(f"{TAG} DRY-RUN would finalize sealed-product Collector Appeal / Overall RIP")
        return "skipped_dry_run"
    if summary.simulation_failed or not summary.verification_passed:
        # An incomplete cohort is not enriched as though it were complete.
        return "skipped_cohort_not_verified"

    from backend.db.services.sealed_product_rip_finalization_service import (
        finalize_sealed_product_rip,
    )

    try:
        report = finalize_sealed_product_rip(
            client, market_date=market_date, unsupported_keys=unsupported_keys
        )
    except Exception as exc:  # noqa: BLE001 - reported, never silently absorbed
        logger.warning("%s sealed-product finalization raised", TAG, exc_info=True)
        summary.sealed_product_finalization_report = None
        return f"failed_{type(exc).__name__}"

    summary.sealed_product_finalization_report = report
    return str(report.get("status") or "unknown")


def _run_rip_contract_audit(
    client: Any,
    summary: PublicationSummary,
    *,
    dry_run: bool,
    skip_snapshots: bool,
) -> str:
    """Assert the published leaderboard is on the canonical scoring contract.

    Returns ``passed``, ``skipped``, ``failed`` or ``error:<reason>``. An
    unreadable audit is never a pass - the previous last-known-good public data
    stays visible, which is the correct fail-closed outcome.
    """
    if dry_run or skip_snapshots:
        return "skipped"

    from backend.scripts.audit_public_rip_leaderboard_publication import run_audit

    try:
        report = run_audit(client)
    except Exception as exc:  # noqa: BLE001 - an unreadable audit must not read as success
        logger.warning("%s RIP contract audit raised", TAG, exc_info=True)
        return f"error:{exc}"

    if report.error:
        return f"error:{report.error}"

    summary.rip_contract_audit_failures = [
        f"{assertion.name}: {assertion.detail}" for assertion in report.failures
    ]
    summary.rip_contract_audit_report = report.to_dict()
    for line in report.lines():
        print(line)
    return "passed" if report.passed else "failed"


def _run_market_publication_audit(
    client: Any,
    summary: PublicationSummary,
    *,
    resolved_market_date: str,
    dry_run: bool,
    skip_snapshots: bool,
) -> str:
    """Verify every publication-required set on every user-facing market surface.

    Returns ``passed``, ``skipped``, ``failed`` or ``error:<reason>``. An
    unreadable audit is never a pass — the previous last-known-good public data
    stays visible, which is the correct fail-closed outcome.
    """
    if dry_run or skip_snapshots:
        return "skipped"

    from backend.scripts.audit_pokemon_market_publication import (
        format_report_lines,
        run_market_publication_audit,
    )

    try:
        report = run_market_publication_audit(client, market_date=resolved_market_date)
    except Exception as exc:  # noqa: BLE001 - an unreadable audit must not read as success
        logger.warning("%s market publication audit raised", TAG, exc_info=True)
        return f"error:{exc}"

    if report.error:
        return f"error:{report.error}"

    summary.market_audit_failed_sets = [
        row.canonical_key or row.set_id or "?" for row in report.failed_rows
    ]
    summary.market_audit_report = report.to_dict()
    for line in format_report_lines(report):
        print(line)
    return "passed" if report.passed else "failed"


def _run_publication_audit(
    client: Any,
    summary: PublicationSummary,
    *,
    resolved_market_date: str,
    unsupported_keys: Sequence[str],
    dry_run: bool,
    skip_snapshots: bool,
) -> str:
    """Re-read what was actually published and report whether OPvC reached the date.

    Returns one of: ``passed``, ``skipped``, ``failed``, or ``error:<reason>``.
    ``skipped`` only when nothing was published in this invocation.
    """
    if dry_run or skip_snapshots:
        return "skipped"

    from backend.scripts.audit_opening_analytics_publication import run_audit

    try:
        report = run_audit(
            client,
            market_date=resolved_market_date,
            unsupported_keys=unsupported_keys,
        )
    except Exception as exc:  # noqa: BLE001 - an unreadable audit must not read as success
        logger.warning("%s publication audit raised", TAG, exc_info=True)
        return f"error:{exc}"

    if report.error:
        return f"error:{report.error}"

    summary.publication_audit_failed_sets = [
        row.canonical_key or row.set_id or "?" for row in report.failed_rows
    ]
    for line in _format_audit_failures(report):
        print(line)
    return "passed" if report.passed else "failed"


def _format_audit_failures(report: Any) -> List[str]:
    lines: List[str] = []
    for row in report.failed_rows:
        lines.append(
            f"{TAG} publication audit FAILED set={row.canonical_key or row.set_id} "
            f"reasons={'; '.join(row.failures) if getattr(row, 'failures', None) else 'see audit log'}"
        )
    return lines


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Coordinated daily publication for Pokemon opening analytics. Enforces the "
            "order: promoted market date -> opening simulations -> simulation verification "
            "-> coordinated snapshot rebuild -> freshness verdict. Never claims Opening "
            "Profit vs Cost is current when the simulations did not advance."
        ),
        epilog=(
            "Production daily order (see backend/docs/public_snapshot_refresh_strategy.md):\n"
            "  1. create/reset the daily scrape batch\n"
            "  2. run the scrape workers\n"
            "  3. complete and promote the scrape batch\n"
            "  4. THIS COMMAND (simulations -> verify -> snapshots)\n"
            "  5. audit_opening_analytics_publication.py (read-only parity audit)\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--market-date",
        default=None,
        help="Override the market date (YYYY-MM-DD). Defaults to the promoted scrape batch's date.",
    )
    parser.add_argument(
        "--except-set",
        action="append",
        default=[],
        dest="except_sets",
        metavar="CANONICAL_KEY",
        help="Canonical key of a set intentionally unsupported by opening analytics. Repeatable.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the commands that would run without executing simulations or snapshot builds.",
    )
    parser.add_argument(
        "--skip-snapshots",
        action="store_true",
        help="Run and verify simulations only; do not rebuild snapshots.",
    )
    parser.add_argument(
        "--gate-wait-attempts",
        type=int,
        default=6,
        help=(
            "How many times to re-evaluate a closed scrape-cohort gate before deferring. "
            "Passed through to refresh_stale_public_snapshots.py."
        ),
    )
    parser.add_argument(
        "--gate-wait-seconds",
        type=int,
        default=600,
        help="Seconds between scrape-cohort gate re-evaluations.",
    )
    parser.add_argument("--json", action="store_true", help="Emit the summary as JSON.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from backend.scripts.pokemon_snapshot_builders import get_client

    summary = orchestrate(
        get_client(),
        market_date=args.market_date,
        unsupported_keys=args.except_sets,
        dry_run=args.dry_run,
        skip_snapshots=args.skip_snapshots,
        gate_wait_attempts=args.gate_wait_attempts,
        gate_wait_seconds=args.gate_wait_seconds,
    )

    if args.json:
        print(json.dumps(asdict(summary), indent=2, default=str))
    else:
        for line in summary.lines():
            print(line)

    return summary.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
