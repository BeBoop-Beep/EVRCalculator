"""One-time (and rerunnable) reconciliation of stale scrape queue + diagnostic rows.

Phase 9 — existing data reconciliation. Safe to run repeatedly.

What it does:
  1. Runs the database lease watchdog (``reconcile_stale_scrape_jobs``), which
     terminally fails stale prior-day ``running`` queue jobs and closes their
     linked diagnostic runs.
  2. Closes ORPHANED stale ``scrape_job_runs`` (status ``running`` with no
     ``queue_job_id`` link and an old ``started_at``) that the watchdog cannot
     reach via the queue-job association.
  3. Explicitly reports the four July-17 incident sets:
       neoGenesis, pokMonGO, scarletAndViolet151, journeyTogether.

What it will NOT do:
  * delete or modify any price observations,
  * fabricate a successful scrape,
  * trigger a full 166-set rescrape.

Dry-run by default. Pass ``--commit`` to apply.

Usage:
    python backend/scripts/reconcile_stale_scrape_jobs.py                # dry-run
    python backend/scripts/reconcile_stale_scrape_jobs.py --commit       # apply
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from backend.db.clients.supabase_client import supabase
from backend.db.repositories.scrape_jobs_repository import reconcile_stale_scrape_jobs
from backend.scripts.run_pokemon_set_scrape import _load_backend_env

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

RECON_TAG = "[scrape-reconcile]"

INCIDENT_SET_KEYS = ["neoGenesis", "pokMonGO", "scarletAndViolet151", "journeyTogether"]

# Orphaned diagnostic runs older than this are considered abandoned.
ORPHAN_RUN_GRACE_HOURS = 6


def _fetch_stale_active_jobs() -> list[dict]:
    result = (
        supabase.table("scrape_jobs")
        .select("id, set_id, status, attempts, max_attempts, started_at, lease_expires_at, market_date")
        .in_("status", ["pending", "running"])
        .execute()
    )
    return result.data if result and result.data else []


def _fetch_orphaned_stale_runs(cutoff_iso: str) -> list[dict]:
    result = (
        supabase.table("scrape_job_runs")
        .select("id, job_name, status, started_at, queue_job_id, metadata")
        .eq("status", "running")
        .is_("queue_job_id", "null")
        .lt("started_at", cutoff_iso)
        .execute()
    )
    return result.data if result and result.data else []


def _close_orphaned_run(run_id: str, now_iso: str) -> None:
    supabase.table("scrape_job_runs").update({
        "status": "failed",
        "aborted": True,
        "completed_at": now_iso,
        "error_summary": "reconciled_orphaned_stale_run: no queue_job_id link, abandoned",
    }).eq("id", run_id).eq("status", "running").execute()


def _report_incident_sets() -> list[dict]:
    sets_res = (
        supabase.table("sets")
        .select("id, name, canonical_key")
        .in_("canonical_key", INCIDENT_SET_KEYS)
        .execute()
    )
    rows = sets_res.data if sets_res and sets_res.data else []
    report = []
    for s in rows:
        jobs_res = (
            supabase.table("scrape_jobs")
            .select("id, status, attempts, error_message, market_date")
            .eq("set_id", s["id"])
            .order("created_at", desc=True)
            .limit(3)
            .execute()
        )
        report.append({
            "canonical_key": s.get("canonical_key"),
            "set_id": s["id"],
            "recent_jobs": jobs_res.data if jobs_res and jobs_res.data else [],
        })
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile stale scrape queue + diagnostic rows (safe, rerunnable).")
    parser.add_argument("--commit", action="store_true", help="Apply changes (default: dry-run).")
    args = parser.parse_args()

    _load_backend_env()
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    cutoff_iso = (now - timedelta(hours=ORPHAN_RUN_GRACE_HOURS)).isoformat()

    stale_jobs = _fetch_stale_active_jobs()
    orphan_runs = _fetch_orphaned_stale_runs(cutoff_iso)

    logger.info("%s %s active queue job(s); %s orphaned stale diagnostic run(s)",
                RECON_TAG, len(stale_jobs), len(orphan_runs))

    summary = {
        "mode": "commit" if args.commit else "dry-run",
        "active_jobs_before": len(stale_jobs),
        "orphaned_runs_found": len(orphan_runs),
        "jobs_reconciled": 0,
        "orphaned_runs_closed": 0,
    }

    if not args.commit:
        logger.info("%s DRY-RUN — no changes applied. Re-run with --commit to apply.", RECON_TAG)
        summary["incident_sets"] = _report_incident_sets()
        print(json.dumps(summary, indent=2, default=str))
        return 0

    # 1. Database lease watchdog: fails stale prior-day jobs, closes linked runs.
    summary["jobs_reconciled"] = reconcile_stale_scrape_jobs()

    # 2. Close orphaned stale diagnostic runs (no queue link).
    closed = 0
    for run in orphan_runs:
        try:
            _close_orphaned_run(run["id"], now_iso)
            closed += 1
        except Exception as exc:
            logger.error("%s failed to close orphaned run %s: %s", RECON_TAG, run.get("id"), exc)
    summary["orphaned_runs_closed"] = closed

    # 3. Explicit incident-set report (post-reconciliation).
    summary["incident_sets"] = _report_incident_sets()

    logger.info("%s reconciliation complete: %s", RECON_TAG, {
        k: v for k, v in summary.items() if k != "incident_sets"
    })
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
