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
from datetime import date, datetime, timezone
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
from backend.db.services.rankings_publication_lifecycle import (  # noqa: E402
    CLASSIFICATION_DEFERRED_WITH_ATTEMPT,
    CLASSIFICATION_EXPLICIT_OPERATOR_SKIP,
    CLASSIFICATION_FAILED_WITH_ATTEMPT,
    CLASSIFICATION_PIPELINE_FAILED_BEFORE_RANKINGS_DECISION,
    CLASSIFICATION_PUBLISHED,
    CLASSIFICATION_UNCHANGED_NOT_REQUIRED,
    RankingsPublicationOutcome,
    rankings_publication_legacy_status,
)

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
    transient: bool = False
    attempts: int = 1


@dataclass
class PublicationSummary:
    market_date: Optional[str] = None
    eligible_set_count: int = 0
    simulation_succeeded: int = 0
    simulation_failed: int = 0
    skipped: List[Dict[str, str]] = field(default_factory=list)
    latest_simulation_date_by_set: Dict[str, Optional[str]] = field(default_factory=dict)
    snapshot_publication_status: str = "not_attempted"
    chase_accessibility_publication_status: str = "not_attempted"
    chase_snapshot_publication_status: str = "not_attempted"
    chase_efficiency_publication_status: str = "not_attempted"
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
    rankings_publication_status: str = "not_attempted"
    rankings_readiness_reason_code: Optional[str] = None
    # THE canonical, end-to-end Rankings result: the same
    # `RankingsPublicationOutcome` object threaded up from
    # `refresh_stale_public_snapshots.py`'s `RefreshSummary` where the
    # publisher was actually invoked in that subprocess, or constructed
    # directly here for the states this orchestrator resolves before ever
    # reaching that subprocess (deferred-with-attempt, explicit skip,
    # pipeline-failed-before-decision). `rankings_publication_status` is kept
    # only as the legacy projection of THIS field's classification (see
    # `_set_rankings_outcome` below) - never set independently.
    rankings_publication_outcome: Optional[Dict[str, Any]] = None
    rip_stats_publication_status: str = "not_attempted"
    ev_representativeness_status: str = "not_attempted"
    rip_stats_audit_status: str = "not_attempted"
    rip_stats_market_date: Optional[str] = None
    rankings_market_date: Optional[str] = None
    simulation_execution_date: Optional[str] = None
    rip_stats_set_count: int = 0
    rip_stats_source_run_fingerprint: Optional[str] = None
    rip_stats_failures: List[str] = field(default_factory=list)
    historical_rip_status: str = "not_attempted"
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
        out.append(f"{TAG} rankings_publication_status={self.rankings_publication_status}")
        out.append(f"{TAG} rankings_readiness_reason_code={self.rankings_readiness_reason_code}")
        rankings_outcome = self.rankings_publication_outcome or {}
        out.append(
            f"{TAG} Rankings: {rankings_outcome.get('classification', 'UNKNOWN')} "
            f"reason={rankings_outcome.get('reason_code')} "
            f"attempt={rankings_outcome.get('attempt_id')} "
            f"publication={rankings_outcome.get('publication_id')} "
            f"mode={rankings_outcome.get('publication_mode')}"
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
        out.append(
            f"{TAG} chase_accessibility_publication_status={self.chase_accessibility_publication_status}"
        )
        out.append(f"{TAG} chase_snapshot_publication_status={self.chase_snapshot_publication_status}")
        out.append(f"{TAG} chase_efficiency_publication_status={self.chase_efficiency_publication_status}")
        out.append(f"{TAG} chase_audit_status={self.chase_audit_status}")
        for failure in self.chase_audit_failures:
            out.append(f"{TAG}   chase_audit_failed={failure}")
        out.append(f"{TAG} rip_stats_publication_status={self.rip_stats_publication_status}")
        out.append(f"{TAG} ev_representativeness_status={self.ev_representativeness_status}")
        out.append(f"{TAG} rip_stats_audit_status={self.rip_stats_audit_status}")
        out.append(f"{TAG} rip_stats_market_date={self.rip_stats_market_date}")
        out.append(f"{TAG} rankings_market_date={self.rankings_market_date}")
        out.append(f"{TAG} simulation_execution_date={self.simulation_execution_date}")
        out.append(f"{TAG} rip_stats_set_count={self.rip_stats_set_count}")
        out.append(f"{TAG} rip_stats_source_run_fingerprint={self.rip_stats_source_run_fingerprint}")
        out.append(f"{TAG} historical_rip_status={self.historical_rip_status}")
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
    market_date: Optional[str] = None,
    sleep=time.sleep,
    max_attempts: int = 3,
) -> List[SimulationOutcome]:
    """Run the existing V2 batch runner once per set that needs work.

    Per-set invocation is what makes the skip in step 2 meaningful: a set
    already current for the market date is never launched at all.
    """
    executable = python_executable or sys.executable
    outcomes: List[SimulationOutcome] = []
    for set_key in set_keys:
        started = time.perf_counter()
        command = [executable, str(REPO_ROOT / "backend" / "scripts" / "run_all_v2_sets.py"), "--set", set_key]
        if market_date:
            command.extend(["--market-date", market_date])
        attempts = 0
        while True:
            attempts += 1
            code = _run_command(command, dry_run=dry_run)
            if code != 75 or attempts >= max(1, max_attempts) or dry_run:
                break
            delay = float(15 * (2 ** (attempts - 1)))
            print(f"{TAG} transient simulation failure set={set_key} attempt={attempts}/{max_attempts} retry_in={delay:.0f}s")
            sleep(delay)
        outcomes.append(
            SimulationOutcome(
                canonical_key=set_key,
                succeeded=code == 0,
                reason=None if code == 0 else f"run_all_v2_sets exited {code}",
                duration_seconds=round(time.perf_counter() - started, 2),
                transient=code == 75,
                attempts=attempts,
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
    skip_explore_rankings: bool = False,
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
    if skip_explore_rankings:
        command.append("--skip-explore-rankings")
    return _run_command(command, dry_run=dry_run)


def refresh_chase_accessibility_snapshots(
    *, python_executable: Optional[str] = None, market_date: str, dry_run: bool = False,
) -> int:
    """Rebuild Chase Accessibility V1 from the CURRENT simulation cohort's exact run ids.

    Must run AFTER the current-day simulation cohort is verified and BEFORE
    sealed-product finalization / public snapshot refresh, because V12 refuses
    an Accessibility row whose ``calculation_run_id`` does not match the
    product cohort's own current run. This is intentionally NOT
    ``refresh_chase_economics_snapshots`` (a different, legacy system keyed on
    the PUBLISHED Set-page run identity) - see
    ``rebuild_chase_accessibility_snapshots.py`` for the authority contract.
    """
    command = [
        python_executable or sys.executable,
        str(REPO_ROOT / "backend" / "scripts" / "rebuild_chase_accessibility_snapshots.py"),
        "--market-date",
        market_date,
    ]
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


def _chase_efficiency_capability_expected(client: Any) -> bool:
    """Allow old schemas/test doubles to run until migration 20260827090000."""
    tables = getattr(client, "_tables", None)
    if tables is None:
        tables = getattr(client, "tables", None)
    return not isinstance(tables, dict) or "pokemon_card_chase_efficiency_latest" in tables


def publish_chase_efficiency(*, client: Any, market_date: str, dry_run: bool) -> str:
    if not _chase_efficiency_capability_expected(client):
        return "skipped_schema_unavailable"
    from backend.db.services.chase_efficiency_service import load_candidate, publish_candidate, validate_candidate
    candidate = load_candidate(client, market_date=market_date)
    failures = validate_candidate(candidate)
    if failures:
        raise RuntimeError("Chase Efficiency candidate audit failed: " + "; ".join(failures))
    if dry_run:
        return "validated_dry_run"
    publish_candidate(client, candidate)
    return "published"


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


def _persist_rankings_deferral(client: Any, report: Any) -> Optional[str]:
    """Persist a no-publish Rankings decision before independent surfaces continue.

    Returns the persisted attempt id (or None when persistence is skipped for
    a strict pre-audit unit fake that has not declared the attempts table) so
    the caller can build a `RankingsPublicationOutcome` carrying the ACTUAL
    attempt id rather than omitting it.
    """
    fake_tables = getattr(client, "_tables", None)
    if isinstance(fake_tables, dict) and "pokemon_rankings_publication_attempts" not in fake_tables:
        return None
    from backend.db.services.rankings_publication_lifecycle import (
        finish_rankings_publication_attempt,
        read_active_publication,
        start_rankings_publication_attempt,
    )
    prior = read_active_publication(client)
    attempt_id = start_rankings_publication_attempt(client, report, prior=prior)
    finish_rankings_publication_attempt(
        client, attempt_id, status="deferred", reason_code=report.reason_code,
        detail=report.detail,
    )
    return attempt_id


def _load_post_refresh_rankings_outcome(
    client: Any, *, market_date: str, rankings_branch_ready: bool,
) -> RankingsPublicationOutcome:
    """The canonical Rankings outcome AFTER `refresh_public_snapshots` ran as a subprocess.

    `refresh_stale_public_snapshots.py` runs out-of-process (a `subprocess.run`
    call in `refresh_public_snapshots`), so its `RefreshSummary` object -
    including `RefreshSummary.rankings_publication_outcome` - never crosses
    back into this process directly. The publication attempts table is the
    one thing both processes agree on, so this reads the newest attempt
    persisted for `market_date` (written by `start_rankings_publication_attempt`/
    `finish_rankings_publication_attempt` inside the publisher the subprocess
    invoked) and reconstructs the same classification from it, rather than
    inferring anything from the subprocess exit code alone.

    No attempt row for this date, with the branch marked ready, means the
    refresh subprocess evaluated Rankings and found the active publication
    already current (CLASSIFICATION_UNCHANGED_NOT_REQUIRED) - the publisher is
    never invoked, and therefore never starts an attempt, on that path.
    """
    if not rankings_branch_ready:
        return RankingsPublicationOutcome(
            classification=CLASSIFICATION_EXPLICIT_OPERATOR_SKIP,
            reason_code="RANKINGS_BRANCH_NOT_READY",
            reason_detail=(
                "Rankings branch was not ready before the coordinated refresh ran; "
                "--skip-explore-rankings was passed to refresh_stale_public_snapshots.py"
            ),
            publication_required=False, publication_attempted=False,
        )
    try:
        rows = list(
            client.table("pokemon_rankings_publication_attempts")
            .select(
                "id,status,reason_code,reason_detail,resulting_publication_id,diagnostics,"
                "attempted_market_date,completed_at"
            )
            .eq("attempted_market_date", market_date)
            .order("completed_at", desc=True)
            .limit(1)
            .execute()
            .data or []
        )
    except Exception as exc:  # fail closed to a reportable, never a silent "published"
        return RankingsPublicationOutcome(
            classification=CLASSIFICATION_FAILED_WITH_ATTEMPT,
            reason_code="RANKINGS_ATTEMPT_LOOKUP_FAILED", reason_detail=str(exc),
            publication_required=True, publication_attempted=True,
        )
    if not rows:
        return RankingsPublicationOutcome(
            classification=CLASSIFICATION_UNCHANGED_NOT_REQUIRED,
            reason_code="CANONICAL_RANKINGS_CURRENT",
            reason_detail=(
                f"no Rankings publication attempt was persisted for {market_date}; the active "
                "canonical publication was already current"
            ),
            publication_required=False, publication_attempted=False,
        )
    row = rows[0]
    status = str(row.get("status") or "")
    diagnostics = row.get("diagnostics") if isinstance(row.get("diagnostics"), dict) else {}
    publication_mode = diagnostics.get("publicationMode")
    attempt_id = str(row.get("id")) if row.get("id") else None
    publication_id = str(row.get("resulting_publication_id")) if row.get("resulting_publication_id") else None
    reason_code = str(row.get("reason_code") or "")
    reason_detail = str(row.get("reason_detail") or "")
    if status == "published":
        return RankingsPublicationOutcome(
            classification=CLASSIFICATION_PUBLISHED, reason_code=reason_code or "READY",
            reason_detail=reason_detail, attempt_id=attempt_id, publication_id=publication_id,
            publication_mode=publication_mode, publication_required=True, publication_attempted=True,
        )
    if status == "deferred":
        return RankingsPublicationOutcome(
            classification=CLASSIFICATION_DEFERRED_WITH_ATTEMPT, reason_code=reason_code,
            reason_detail=reason_detail, attempt_id=attempt_id, publication_mode=publication_mode,
            publication_required=True, publication_attempted=False,
        )
    # "failed" and any other terminal status the attempts table's
    # externally-owned status vocabulary may carry.
    return RankingsPublicationOutcome(
        classification=CLASSIFICATION_FAILED_WITH_ATTEMPT, reason_code=reason_code or status,
        reason_detail=reason_detail, attempt_id=attempt_id, publication_mode=publication_mode,
        publication_required=True, publication_attempted=True,
    )


def _resolve_upstream_refresh_failure_outcome(
    client: Any, *, market_date: str, reason_code: str,
) -> RankingsPublicationOutcome:
    """Classify Rankings after `refresh_public_snapshots` itself failed/deferred.

    Fixes the Sept-9 hole where a `refresh_stale_public_snapshots.py` failure
    left `rankings_publication_status=not_attempted` / `Rankings: UNKNOWN` even
    though the pipeline had already failed. Two cases:

    Case A - refresh failed and there is NO same-date Rankings attempt: the
    failure happened before any Rankings decision was made. Classify as
    ``CLASSIFICATION_PIPELINE_FAILED_BEFORE_RANKINGS_DECISION`` with
    ``publication_attempted=False`` and no attempt id.

    Case B - refresh failed but the subprocess DID persist a same-date
    Rankings attempt before it died (e.g. the publisher ran and reached a
    terminal state, then a later step in that subprocess failed): read back
    the real lifecycle result and preserve it verbatim - never overwrite real
    lifecycle history with the generic upstream-failure classification.
    """
    try:
        rows = list(
            client.table("pokemon_rankings_publication_attempts")
            .select(
                "id,status,reason_code,reason_detail,resulting_publication_id,diagnostics,"
                "attempted_market_date,completed_at"
            )
            .eq("attempted_market_date", market_date)
            .order("completed_at", desc=True)
            .limit(1)
            .execute()
            .data or []
        )
    except Exception as exc:  # fail closed - never silently "published"
        return RankingsPublicationOutcome(
            classification=CLASSIFICATION_PIPELINE_FAILED_BEFORE_RANKINGS_DECISION,
            reason_code=reason_code,
            reason_detail=f"upstream refresh failed and the attempt lookup itself raised: {exc}",
            publication_required=True, publication_attempted=False,
        )
    if not rows:
        # Case A: no real Rankings attempt exists for this date - the failure
        # happened before any Rankings decision was made.
        return RankingsPublicationOutcome(
            classification=CLASSIFICATION_PIPELINE_FAILED_BEFORE_RANKINGS_DECISION,
            reason_code=reason_code,
            reason_detail=(
                f"public snapshot refresh failed for {market_date} before any Rankings "
                "publication attempt was persisted"
            ),
            publication_required=True, publication_attempted=False,
        )
    # Case B: a same-date attempt DOES exist - preserve its real terminal state.
    return _load_post_refresh_rankings_outcome(
        client, market_date=market_date, rankings_branch_ready=True,
    )


def _set_rankings_outcome(summary: "PublicationSummary", outcome: RankingsPublicationOutcome) -> None:
    """The ONE place `rankings_publication_status` is derived, from the outcome.

    Never hand-write `summary.rankings_publication_status = "..."` at a call
    site - always go through this so the legacy string can never drift from
    the canonical classification.
    """
    summary.rankings_publication_outcome = outcome.to_dict()
    summary.rankings_publication_status = rankings_publication_legacy_status(outcome.classification)
    summary.rankings_readiness_reason_code = outcome.reason_code


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
    simulation_execution_date: Optional[str] = None,
) -> PublicationSummary:
    summary = PublicationSummary()

    # ---- Step 1: the coordinated market date, never wall-clock -------------
    from backend.scripts.audit_opening_analytics_publication import resolve_market_date

    resolved_market_date, date_error = resolve_market_date(client, market_date)
    if date_error or not resolved_market_date:
        summary.error = date_error or "no promoted market date could be resolved"
        summary.exit_code = EXIT_CANNOT_START
        _set_rankings_outcome(summary, RankingsPublicationOutcome(
            classification=CLASSIFICATION_PIPELINE_FAILED_BEFORE_RANKINGS_DECISION,
            reason_code="NO_PROMOTED_MARKET_DATE", reason_detail=summary.error,
        ))
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
        _set_rankings_outcome(summary, RankingsPublicationOutcome(
            classification=CLASSIFICATION_PIPELINE_FAILED_BEFORE_RANKINGS_DECISION,
            reason_code=authority.reason_code, reason_detail=summary.error,
        ))
        return summary

    # ---- Step 2: what still needs a simulation for that date ---------------
    before = evaluate_opening_simulation_freshness(
        client, market_date=resolved_market_date, unsupported_keys=unsupported_keys
    )
    if before.error:
        summary.error = before.error
        summary.exit_code = EXIT_CANNOT_START
        _set_rankings_outcome(summary, RankingsPublicationOutcome(
            classification=CLASSIFICATION_PIPELINE_FAILED_BEFORE_RANKINGS_DECISION,
            reason_code="SIMULATION_FRESHNESS_UNREADABLE", reason_detail=summary.error,
        ))
        return summary

    summary.eligible_set_count = before.eligible_count
    summary.skipped = _skipped_entries(before)
    pending = sets_needing_simulation(before)
    from backend.Scraper.helpers.market_date_helper import resolve_phoenix_market_date
    current_simulation_date = simulation_execution_date or resolve_phoenix_market_date()
    summary.simulation_execution_date = current_simulation_date
    print(f"{TAG} market_date={resolved_market_date} eligible={before.eligible_count} pending={len(pending)}")

    # Simulation history is dated from actual Phoenix execution time. After a
    # rollover, running yesterday's missing work can only create today's point;
    # it can never repair yesterday's promoted cohort.
    if pending and current_simulation_date != resolved_market_date:
        from backend.db.services.rankings_publication_lifecycle import (
            deferred_simulation_rollover_readiness,
        )
        report = deferred_simulation_rollover_readiness(
            market_date=resolved_market_date,
            simulation_date=current_simulation_date,
            expected_count=before.eligible_count,
            current_count=sum(1 for item in before.statuses if item.status == "current"),
            pending_keys=pending,
        )
        summary.latest_simulation_date_by_set = _latest_dates(before)
        summary.error = report.detail
        summary.exit_code = GATE_DEFERRED_EXIT_CODE
        attempt_id = _persist_rankings_deferral(client, report) if not dry_run else None
        _set_rankings_outcome(summary, RankingsPublicationOutcome(
            classification=CLASSIFICATION_DEFERRED_WITH_ATTEMPT,
            reason_code=report.reason_code, reason_detail=report.detail,
            attempt_id=attempt_id, publication_required=True, publication_attempted=False,
        ))
        return summary

    outcomes = run_simulations_for_sets(
        pending,
        python_executable=python_executable,
        dry_run=dry_run,
        market_date=resolved_market_date,
    )
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

    # ---- Step 3a2: rebuild Chase Accessibility V1 from the CURRENT run ids ----
    # Must happen AFTER the current-day simulation cohort is verified (so the
    # exact calculation_run_id per set is known) and BEFORE sealed-product
    # finalization / public snapshot refresh, because V12 refuses an
    # Accessibility row whose calculation_run_id does not match the product
    # cohort's own current run. This is NOT the legacy Chase Economics system
    # (see refresh_chase_economics_snapshots, which stays keyed on the
    # PUBLISHED Set-page run identity and stays where it already was).
    if after.ok and not summary.simulation_failed:
        if dry_run:
            refresh_chase_accessibility_snapshots(
                python_executable=python_executable,
                market_date=resolved_market_date,
                dry_run=True,
            )
            summary.chase_accessibility_publication_status = "validated_dry_run"
        else:
            accessibility_code = refresh_chase_accessibility_snapshots(
                python_executable=python_executable,
                market_date=resolved_market_date,
                dry_run=False,
            )
            if accessibility_code == 0:
                summary.chase_accessibility_publication_status = "published"
            else:
                summary.chase_accessibility_publication_status = f"failed_exit_{accessibility_code}"
                summary.exit_code = EXIT_FAILED
                summary.error = (
                    "Chase Accessibility V1 rebuild failed for the current simulation "
                    f"cohort at {resolved_market_date}; refusing sealed-product finalization "
                    "and public snapshot refresh so previous Sept-8-style public state is retained"
                )
                _set_rankings_outcome(summary, RankingsPublicationOutcome(
                    classification=CLASSIFICATION_PIPELINE_FAILED_BEFORE_RANKINGS_DECISION,
                    reason_code="CHASE_ACCESSIBILITY_REFRESH_FAILED",
                    reason_detail=summary.error,
                ))
                return summary
    else:
        summary.chase_accessibility_publication_status = "skipped_cohort_not_verified"

    # ---- Step 3b: finalize sealed-product Collector Appeal / Overall RIP ----
    # Placed at the narrowest correct point: AFTER every required simulation has
    # completed and freshness has been verified (so the cohort is whole), AFTER
    # Chase Accessibility V1 has been rebuilt from that exact cohort's run ids
    # (so V12 authority is current, not stale), and BEFORE snapshot publication
    # (so nothing downstream can publish a product row whose Overall RIP is
    # still pending). It runs in ONE process, which is the entire reason it
    # exists - the per-set subprocesses no longer build the Collector Appeal
    # bundle at all, so this is the only build in the day.
    summary.sealed_product_finalization_status = _finalize_sealed_products(
        client,
        summary,
        market_date=resolved_market_date,
        unsupported_keys=unsupported_keys,
        dry_run=dry_run,
    )
    rankings_branch_ready = (
        after.ok
        and not summary.simulation_failed
        and summary.sealed_product_finalization_status in {"ok", "skipped_dry_run"}
    )
    if not after.ok or summary.simulation_failed:
        from backend.db.services.rankings_publication_lifecycle import (
            deferred_simulation_readiness,
        )
        report = deferred_simulation_readiness(
            market_date=resolved_market_date,
            expected_count=after.eligible_count,
            verified_count=sum(1 for item in after.statuses if item.status == "current"),
            failures=[f"{item.canonical_key}:{item.status}" for item in after.failures],
        )
        attempt_id = _persist_rankings_deferral(client, report) if not dry_run else None
        _set_rankings_outcome(summary, RankingsPublicationOutcome(
            classification=CLASSIFICATION_DEFERRED_WITH_ATTEMPT,
            reason_code=report.reason_code, reason_detail=report.detail,
            attempt_id=attempt_id, publication_required=True, publication_attempted=False,
        ))
    elif summary.sealed_product_finalization_status not in {"ok", "skipped_dry_run"}:
        from backend.db.services.rankings_publication_lifecycle import (
            DEFERRED_SEALED_PRODUCT_FINALIZATION_INCOMPLETE,
            RankingsReadinessReport,
        )
        report = RankingsReadinessReport(
            status=DEFERRED_SEALED_PRODUCT_FINALIZATION_INCOMPLETE,
            reason_code=DEFERRED_SEALED_PRODUCT_FINALIZATION_INCOMPLETE,
            detail=f"sealed-product finalization status={summary.sealed_product_finalization_status}",
            market_date=resolved_market_date,
            expected_supported_cohort_count=after.eligible_count,
            verified_simulation_cohort_count=after.eligible_count,
            sealed_product_finalized_set_count=int((summary.sealed_product_finalization_report or {}).get("setCount") or 0),
            sealed_product_finalized_product_row_count=int((summary.sealed_product_finalization_report or {}).get("rowsFinalized") or 0),
        )
        attempt_id = _persist_rankings_deferral(client, report) if not dry_run else None
        _set_rankings_outcome(summary, RankingsPublicationOutcome(
            classification=CLASSIFICATION_DEFERRED_WITH_ATTEMPT,
            reason_code=report.reason_code, reason_detail=report.detail,
            attempt_id=attempt_id, publication_required=True, publication_attempted=False,
        ))

    # ---- Step 3c: optional exact-artifact research -------------------------
    # Current run ids are authoritative now, and every downstream public
    # snapshot may project their same-run research.  Failures are isolated per
    # set and are observability only: this is deliberately NOT a publication
    # gate.
    summary.ev_representativeness_status = _build_ev_representativeness_tier_a(
        client, after, dry_run=dry_run
    )

    # ---- Step 3d: exact Pokemon-wide RIP Stats ----------------------------
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
        summary.chase_efficiency_publication_status = "skipped"
    else:
        refresh_code = refresh_public_snapshots(
            python_executable=python_executable,
            dry_run=dry_run,
            gate_wait_attempts=gate_wait_attempts,
            gate_wait_seconds=gate_wait_seconds,
            skip_explore_rankings=not rankings_branch_ready,
        )
        if refresh_code == 0:
            summary.snapshot_publication_status = "published"
            # A DEFERRED_WITH_ATTEMPT outcome may already have been set above
            # (rollover / cohort-incomplete / sealed-product-finalization
            # branches, none of which `return` early) - that is the accurate,
            # already-persisted-attempt classification for why rankings_branch_ready
            # is False, and must never be overwritten by the weaker "operator
            # skip" inference below just because this orchestrator was the one
            # that passed --skip-explore-rankings downstream.
            if summary.rankings_publication_outcome is None:
                if not dry_run:
                    _set_rankings_outcome(summary, _load_post_refresh_rankings_outcome(
                        client, market_date=resolved_market_date,
                        rankings_branch_ready=rankings_branch_ready,
                    ))
                elif not rankings_branch_ready:
                    _set_rankings_outcome(summary, RankingsPublicationOutcome(
                        classification=CLASSIFICATION_EXPLICIT_OPERATOR_SKIP,
                        reason_code="RANKINGS_BRANCH_NOT_READY",
                        reason_detail="Rankings branch was not ready before the coordinated refresh dry-run",
                        publication_required=False, publication_attempted=False,
                    ))
        elif refresh_code == GATE_DEFERRED_EXIT_CODE:
            summary.snapshot_publication_status = "deferred_cohort_not_ready"
            summary.exit_code = GATE_DEFERRED_EXIT_CODE
            if summary.rankings_publication_outcome is None and not dry_run:
                _set_rankings_outcome(summary, _resolve_upstream_refresh_failure_outcome(
                    client, market_date=resolved_market_date,
                    reason_code="SNAPSHOT_REFRESH_DEFERRED_COHORT_NOT_READY",
                ))
            return summary
        else:
            summary.snapshot_publication_status = f"failed_exit_{refresh_code}"
            summary.exit_code = EXIT_FAILED
            if summary.rankings_publication_outcome is None and not dry_run:
                _set_rankings_outcome(summary, _resolve_upstream_refresh_failure_outcome(
                    client, market_date=resolved_market_date,
                    reason_code=f"SNAPSHOT_REFRESH_FAILED_EXIT_{refresh_code}",
                ))
            return summary

        # The set-page rebuild above establishes the PUBLISHED Set-page run
        # identity that this legacy Chase Economics system reads
        # (`_current_run_id()` in build_pokemon_set_chase_economics_snapshots.py
        # resolves pokemon_set_page_snapshot_latest.payload_json.ripDecision.
        # sourceCalculationRunId), which only exists once Set-page publication
        # has happened above. It is deliberately NOT moved earlier: Chase
        # Accessibility V1 (the system V12 depends on) already rebuilt from the
        # current SIMULATION run ids in step 3a2, before sealed-product
        # finalization - this step is the separate, legacy Chase system and
        # stays keyed on the published Set-page authority instead.
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

        # This normalized exact-printing ranking consumes the same established
        # run/price authority but publishes independently from legacy Chase.
        try:
            summary.chase_efficiency_publication_status = publish_chase_efficiency(
                client=client, market_date=resolved_market_date, dry_run=dry_run,
            )
        except Exception as exc:
            summary.chase_efficiency_publication_status = f"failed:{exc}"
            summary.exit_code = EXIT_FAILED
            summary.error = "Chase Efficiency publication failed; previous latest remains unchanged"
            return summary

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

    if (
        not dry_run
        and not skip_snapshots
        and summary.rip_stats_publication_status == "published"
        and (
            summary.rip_stats_market_date != resolved_market_date
            or summary.rankings_market_date != resolved_market_date
        )
    ):
        summary.exit_code = EXIT_FAILED
        summary.error = (
            "Rankings page publication clocks disagree with promoted authority: "
            f"expected={resolved_market_date} rip_stats={summary.rip_stats_market_date} "
            f"explore_rankings={summary.rankings_market_date}"
        )
        return summary

    # Final step of the existing scheduler-owned chain: append/confirm today's
    # exact Collector observation.  This planner makes zero provider calls and
    # fails closed when source refresh is due.
    declared_tables = getattr(client, "_tables", None)
    if isinstance(declared_tables, dict) and "pokemon_rip_temporal_history" not in declared_tables:
        summary.historical_rip_status = "skipped_legacy_test_client"
    else:
        from backend.scripts.operationalize_historical_rip import execute as append_historical_rip
        history = append_historical_rip(
            client,
            as_of=date.fromisoformat(resolved_market_date),
            now=datetime.now(timezone.utc),
            commit=not dry_run,
        )
        summary.historical_rip_status = str(history["status"])
        if summary.historical_rip_status == "SOURCE_REFRESH_REQUIRED":
            summary.exit_code = EXIT_FAILED
            summary.error = "Collector source refresh is due before historical append"
            return summary
    summary.exit_code = EXIT_OK
    return summary


def _build_ev_representativeness_tier_a(client: Any, freshness: Any, *, dry_run: bool) -> str:
    eligible = sum(
        1 for item in freshness.statuses
        if item.status == "current" and item.calculation_run_id
    )
    if dry_run:
        return f"validated_dry_run eligible={eligible} existing=0 built=0 failed=0"
    from backend.db.services.ev_representativeness_service import build_tier_a_for_run
    failures = []
    built = 0
    existing = 0
    for item in freshness.statuses:
        if item.status != "current" or not item.calculation_run_id:
            continue
        try:
            result = build_tier_a_for_run(client, str(item.calculation_run_id))
            if result.get("status") == "research_built":
                built += 1
            elif result.get("status") == "already_built":
                existing += 1
        except Exception as exc:  # explicitly non-fatal before publication
            failures.append(f"{item.canonical_key}:{exc}")
            logger.exception("%s Tier A pre-snapshot build failed non-blocking set=%s", TAG, item.canonical_key)
    if failures:
        return (f"research_partial eligible={eligible} existing={existing} "
                f"built={built} failed={len(failures)}")
    return (f"research_complete eligible={eligible} existing={existing} "
            f"built={built} failed=0")


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
    summary.rankings_market_date = report.market_date
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
