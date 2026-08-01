"""Bounded lease-based runner for resumable Pokemon set onboarding."""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from backend.alerts.scrape_alerts import queue_alert
from backend.db.repositories import pokemon_set_onboarding_repository as repository
from backend.scripts.run_pokemon_set_scrape import _load_backend_env
from backend.services.pokemon_set_onboarding_service import OnboardingEngine, STEP_ORDER


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--commit", action="store_true")
    parser.add_argument("--job-id")
    parser.add_argument("--resume-all", action="store_true")
    parser.add_argument("--max-jobs", type=int, default=1)
    parser.add_argument("--through-step", choices=STEP_ORDER)
    parser.add_argument("--force-retry", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-git", action="store_true")
    parser.add_argument("--pull-rates-file", type=Path)
    parser.add_argument("--worker-id", default=f"{socket.gethostname()}:{os.getpid()}")
    parser.add_argument("--lease-seconds", type=int, default=1800)
    return parser


def _merge_metadata(job: Dict[str, Any], step: str, evidence: Dict[str, Any]) -> Dict[str, Any]:
    metadata = dict(job.get("metadata_json") or {})
    steps = dict(metadata.get("steps") or {})
    steps[step] = {
        **evidence, "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    metadata["steps"] = steps
    for key in ("canonical_key", "era_folder", "source_branch", "source_commit_sha",
                "source_pr_url", "source_pr_number", "pull_model_status"):
        if key in evidence:
            metadata[key] = evidence[key]
    return metadata


def main() -> int:
    args = build_parser().parse_args()
    _load_backend_env()
    engine = OnboardingEngine(
        execute=args.commit, no_git=args.no_git, pull_rates_file=args.pull_rates_file,
    )
    max_jobs = max(1, args.max_jobs)
    if args.dry_run:
        # Read-only by contract: do not claim, heartbeat, requeue, or update anything.
        jobs = [repository.get_job(args.job_id)] if args.job_id else repository.list_jobs(
            include_waiting=args.resume_all, include_manual_review=args.force_retry, limit=max_jobs,
        )
        results = []
        for job in [row for row in jobs if row]:
            outcome = engine.run_step(job)
            results.append({"job_id": job["id"], "current_step": job["current_step"], "outcome": outcome.__dict__})
        print(json.dumps({"mode": "dry_run", "jobs": results}, indent=2, default=str))
        return 0

    results = []
    exit_code = 0
    candidate_ids: list[str | None]
    if args.job_id:
        candidate_ids = [args.job_id]
    elif args.resume_all:
        candidate_ids = [
            str(row["id"]) for row in repository.list_jobs(
                include_waiting=True, include_manual_review=args.force_retry, limit=max_jobs,
            )
        ]
    else:
        candidate_ids = [None] * max_jobs

    for candidate_id in candidate_ids[:max_jobs]:
        job = repository.claim_next(
            args.worker_id, max(60, args.lease_seconds), job_id=candidate_id,
            force_retry=args.force_retry or args.resume_all,
        )
        if not job:
            continue
        original_step = str(job["current_step"])
        try:
            outcome = engine.run_step(job)
            metadata = _merge_metadata(job, original_step, outcome.evidence)
            common = {
                "metadata_json": metadata, "last_error_code": outcome.error_code,
                "last_error_message": outcome.evidence.get("error"),
                "worker_id": None, "lease_expires_at": None, "heartbeat_at": None,
            }
            source_fields = {
                key: outcome.evidence[key] for key in (
                    "canonical_key", "era_folder", "source_branch", "source_commit_sha",
                    "source_pr_url", "source_pr_number", "pull_model_status",
                ) if key in outcome.evidence
            }
            if outcome.kind == "advance":
                fields = {**common, **source_fields, "status": "retry", "current_step": outcome.step,
                          "next_attempt_at": datetime.now(timezone.utc).isoformat()}
            elif outcome.kind == "wait":
                fields = {**common, **source_fields, "status": "waiting", "current_step": outcome.step}
            elif outcome.kind == "manual_review":
                fields = {**common, "status": "manual_review", "current_step": outcome.step}
            elif outcome.kind == "complete":
                fields = {**common, "status": "completed", "completed_at": datetime.now(timezone.utc).isoformat()}
            else:
                repository.release_for_retry(
                    str(job["id"]), args.worker_id, code=outcome.error_code or "step_failed",
                    message=outcome.evidence.get("error", outcome.error_code or "step failed"),
                )
                fields = None
                exit_code = 2
            if fields is not None:
                repository.update_claimed(str(job["id"]), args.worker_id, fields)
            results.append({"job_id": job["id"], "step": original_step, "outcome": outcome.__dict__})
            if args.through_step == original_step:
                break
        except Exception as exc:
            repository.release_for_retry(
                str(job["id"]), args.worker_id, code="unhandled_worker_error", message=str(exc),
            )
            queue_alert(
                "pokemon_set_onboarding_failed", "Pokemon set onboarding worker failed", str(exc),
                severity="error", dedupe_key=f"pokemon-onboarding-failed:{job['id']}",
                payload={"job_id": job["id"], "source_set_id": job.get("source_set_id")},
            )
            results.append({"job_id": job["id"], "error": str(exc)})
            exit_code = 2
    print(json.dumps({"mode": "commit", "jobs": results}, indent=2, default=str))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
