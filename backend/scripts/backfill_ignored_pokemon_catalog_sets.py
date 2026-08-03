"""One-time historical TCGplayer Pokemon catalog backfill.

Turns the ``ignored`` / ``catalog_baseline`` rows recorded by the cold-start
catalog baseline into real source configs, ``public.sets`` rows, and scraped
market data. Normal new-set discovery and the nightly onboarding worker are
untouched: rows only ever move ignored -> completed, never to a claimable
status.

Required workflow (commit mode refuses to do all of it in one unreviewed run):

    configs -> review and merge the generated source files -> sync -> scrape

Usage:
    python backend/scripts/backfill_ignored_pokemon_catalog_sets.py --dry-run --stage all
    python backend/scripts/backfill_ignored_pokemon_catalog_sets.py --commit  --stage configs
    python backend/scripts/backfill_ignored_pokemon_catalog_sets.py --commit  --stage sync
    python backend/scripts/backfill_ignored_pokemon_catalog_sets.py --commit  --stage scrape --resume
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from backend.services import pokemon_historical_catalog_backfill_service as svc

logger = logging.getLogger(__name__)

TAG = "[catalog-backfill]"
STAGES = ("configs", "sync", "scrape", "all")
DEFAULT_POKEMON_ROOT = Path("backend/constants/tcg/pokemon")
# The Pokemon TCG API serves frequent transient 500s; retry before declaring failure.
API_LOOKUP_ATTEMPTS = 4
API_LOOKUP_BACKOFF_SECONDS = 1.5


class StageOrderError(RuntimeError):
    """Raised when --stage all is combined with --commit."""


@dataclass
class BackfillDeps:
    """Every side effect this script can perform, injected so it stays testable."""

    list_rows: Callable[[], List[Dict[str, Any]]]
    fetch_api_rows: Callable[[str], Optional[List[Dict[str, Any]]]]
    update_job: Callable[[str, Dict[str, Any]], Any]
    sync_set: Callable[[str], Dict[str, Any]]
    scrape_set: Callable[[str], Dict[str, Any]]
    verify_scrape: Callable[[str, Dict[str, Any]], Dict[str, Any]]


# ---------------------------------------------------------------------------
# Real dependency wiring
# ---------------------------------------------------------------------------
def _real_list_rows() -> List[Dict[str, Any]]:
    from backend.db.repositories import pokemon_set_onboarding_repository as repo

    return repo.list_baseline_catalog_jobs()


def fetch_api_rows_with_retry(
    source_set_name: str,
    *,
    api_key: str,
    fetch: Callable[[str, str], List[Dict[str, Any]]],
    attempts: int = API_LOOKUP_ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
) -> Optional[List[Dict[str, Any]]]:
    """Return API candidates, or None when every attempt failed.

    None is deliberately distinct from an empty list. The Pokemon TCG API serves
    frequent transient 500s, and a failed call must never be read as "no match"
    (which would file an API-backed set into otherEra with no metadata). An empty
    result is a real answer and is never retried.
    """
    last_error: Optional[Exception] = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            return fetch(source_set_name, api_key)
        except Exception as exc:  # noqa: BLE001 - any failure means "unknown", not "absent"
            last_error = exc
            logger.warning(
                "%s Pokemon API lookup failed for %r (attempt %d/%d): %s",
                TAG, source_set_name, attempt, attempts, exc,
            )
            if attempt < attempts:
                sleep(API_LOOKUP_BACKOFF_SECONDS * attempt)
    logger.error(
        "%s Pokemon API lookup exhausted for %r: %s", TAG, source_set_name, last_error
    )
    return None


def _real_fetch_api_rows(source_set_name: str) -> Optional[List[Dict[str, Any]]]:
    from backend.services.pokemon_tcg_api_set_service import fetch_targeted_sets

    return fetch_api_rows_with_retry(
        source_set_name,
        api_key=os.getenv("POKEMON_TCG_API_KEY", ""),
        fetch=fetch_targeted_sets,
    )


def _real_update_job(job_id: str, fields: Dict[str, Any]) -> Any:
    from backend.db.repositories import pokemon_set_onboarding_repository as repo

    return repo.update_baseline_job(job_id, fields)


def _real_sync_set(canonical_key: str) -> Dict[str, Any]:
    """Delegate to the existing constants -> public.sets sync; no duplicated logic."""
    from backend.db.repositories.sets_repository import get_set_by_canonical_key
    from backend.db.services.pokemon_era_set_sync_service import sync_pokemon_era_and_set_metadata

    sync_pokemon_era_and_set_metadata(apply_changes=True, target_set_key=canonical_key)
    return get_set_by_canonical_key(canonical_key) or {}


def _real_scrape_set(canonical_key: str) -> Dict[str, Any]:
    """Invoke the existing targeted scraper for exactly one canonical key."""
    from backend.scripts.run_pokemon_set_scrape import run_scraper

    report = run_scraper(
        dry_run=False,
        era_filter=None,
        set_key_filter=canonical_key,
        limit=None,
        enable_db_ingestion=True,
        shuffle_within_date=False,
    )
    results = report.get("results") or []
    mine = [row for row in results if row.get("canonical_key") == canonical_key]
    status = mine[0].get("status") if mine else "failed"
    return {
        "status": status,
        "cards_scraped": sum(int(row.get("cards_scraped") or 0) for row in mine),
        "sealed_scraped": sum(int(row.get("sealed_scraped") or 0) for row in mine),
        "error": (mine[0].get("error") if mine else report.get("error")) or None,
        "touched_keys": [row.get("canonical_key") for row in results if row.get("canonical_key")],
    }


def _real_verify_scrape(canonical_key: str, scrape_report: Dict[str, Any]) -> Dict[str, Any]:
    """Database evidence that the intended set — and only it — received data."""
    from backend.db.repositories.cards_repository import get_all_cards_for_set
    from backend.db.repositories.sets_repository import get_set_by_canonical_key

    set_row = get_set_by_canonical_key(canonical_key)
    cards = get_all_cards_for_set(set_row["id"]) if set_row else []
    cards_written = len(cards)
    return {
        "set_row_exists": bool(set_row),
        "cards_written": cards_written,
        "canonical_keys_touched": list(scrape_report.get("touched_keys") or []),
        # The scraper already reports zero-card runs as failures whenever the
        # config declares a PRINTED_TOTAL, so a successful zero-card run here
        # means TCGplayer genuinely served an empty catalog.
        "empty_catalog": cards_written == 0,
    }


def default_deps() -> BackfillDeps:
    return BackfillDeps(
        list_rows=_real_list_rows,
        fetch_api_rows=_real_fetch_api_rows,
        update_job=_real_update_job,
        sync_set=_real_sync_set,
        scrape_set=_real_scrape_set,
        verify_scrape=_real_verify_scrape,
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def _blank_summary(dry_run: bool) -> Dict[str, Any]:
    return {
        "selected": 0,
        "already_completed": 0,
        "configs_generated": 0,
        "api_backed": 0,
        "catalog_only": 0,
        "synced": 0,
        "scraped_successfully": 0,
        "empty_catalogs": 0,
        "failed": 0,
        "remaining": 0,
        "dry_run": dry_run,
    }


def _run_configs_stage(
    rows: List[Dict[str, Any]], *, pokemon_root: Path, deps: BackfillDeps, commit: bool,
    summary: Dict[str, Any], report_rows: Dict[str, Dict[str, Any]],
) -> None:
    taken_keys = svc.existing_canonical_keys(pokemon_root)
    for row in rows:
        source_set_name = str(row.get("source_set_name") or "")
        lookup_name = svc.api_lookup_name_for(row.get("source_set_id"), source_set_name)
        api_rows = deps.fetch_api_rows(lookup_name) if source_set_name else []
        outcome = svc.generate_config_for_row(
            row, pokemon_root=pokemon_root, api_rows=api_rows,
            taken_keys=taken_keys, commit=commit,
        )
        report_row = outcome.as_report_row()
        report_row["stage"] = "configs"
        report_rows[str(row.get("id"))] = report_row

        if outcome.error:
            summary["failed"] += 1
        else:
            summary["configs_generated"] += 1
            if outcome.api_match_status == "resolved":
                summary["api_backed"] += 1
            else:
                summary["catalog_only"] += 1

        if not commit:
            continue
        deps.update_job(row["id"], svc.build_progress_fields(row, {
            "config_status": "failed" if outcome.error else "generated",
            "canonical_key": outcome.canonical_key,
            "era_folder": outcome.era_folder,
            "api_match_status": outcome.api_match_status,
            "pokemon_api_set_id": outcome.pokemon_api_set_id,
            "config_path": outcome.config_path,
            "set_map_path": outcome.set_map_path,
            "card_details_url": outcome.card_details_url,
            "sealed_details_url": outcome.sealed_details_url,
            "collision": outcome.collision,
            "error": outcome.error,
        }))


def _verify_synced_row(
    canonical_key: str, set_row: Dict[str, Any], api_match_status: str
) -> List[str]:
    problems: List[str] = []
    if str(set_row.get("canonical_key") or "") != canonical_key:
        problems.append("public.sets row canonical_key does not match the generated key")
    if not set_row.get("source_config_path"):
        problems.append("missing source_config_path")
    if not set_row.get("card_details_url"):
        problems.append("missing card_details_url")
    if not set_row.get("sealed_details_url"):
        problems.append("missing sealed_details_url")
    if not set_row.get("ready_for_daily_scrape"):
        problems.append("ready_for_daily_scrape is not true")
    if set_row.get("pokemon_api_set_id") and api_match_status != "resolved":
        problems.append("pokemon_api_set_id is set without an authoritative API match")
    return problems


def _run_sync_stage(
    rows: List[Dict[str, Any]], *, deps: BackfillDeps, commit: bool,
    summary: Dict[str, Any], report_rows: Dict[str, Dict[str, Any]],
) -> None:
    for row in rows:
        state = svc.backfill_state(row)
        canonical_key = state.get("canonical_key")
        report_row = report_rows.setdefault(str(row.get("id")), {
            "source_set_id": row.get("source_set_id"),
            "source_set_name": row.get("source_set_name"),
            "canonical_key": canonical_key,
        })
        report_row["stage"] = "sync"
        if not canonical_key:
            report_row["sync_status"] = "skipped_not_generated"
            continue
        if not commit:
            report_row["sync_status"] = "would_sync"
            continue

        set_row = deps.sync_set(canonical_key) or {}
        problems = _verify_synced_row(canonical_key, set_row, state.get("api_match_status") or "")
        report_row["sync_status"] = "synced" if not problems else "failed"
        report_row["sync_problems"] = problems
        if problems:
            summary["failed"] += 1
            deps.update_job(row["id"], svc.build_progress_fields(row, {
                "sync_status": "failed", "error": "; ".join(problems),
            }))
            continue
        summary["synced"] += 1
        deps.update_job(row["id"], svc.build_progress_fields(row, {
            "sync_status": "synced", "public_set_id": set_row.get("id"), "error": None,
        }))


def _run_scrape_stage(
    rows: List[Dict[str, Any]], *, deps: BackfillDeps, commit: bool,
    summary: Dict[str, Any], report_rows: Dict[str, Dict[str, Any]],
) -> None:
    for row in rows:
        state = svc.backfill_state(row)
        canonical_key = state.get("canonical_key")
        report_row = report_rows.setdefault(str(row.get("id")), {
            "source_set_id": row.get("source_set_id"),
            "source_set_name": row.get("source_set_name"),
            "canonical_key": canonical_key,
        })
        report_row["stage"] = "scrape"
        if not canonical_key:
            report_row["scrape_status"] = "skipped_not_generated"
            continue
        if not commit:
            report_row["scrape_status"] = "would_scrape"
            continue

        # Sequential by construction: one set per loop iteration, never concurrent.
        scrape_report = deps.scrape_set(canonical_key) or {}
        problems: List[str] = []
        if str(scrape_report.get("status") or "") != "success":
            problems.append(scrape_report.get("error") or "scrape did not report success")
            evidence: Dict[str, Any] = {}
        else:
            evidence = deps.verify_scrape(canonical_key, scrape_report) or {}
            if not evidence.get("set_row_exists"):
                problems.append("no public.sets row found after the scrape")
            unrelated = [
                key for key in (evidence.get("canonical_keys_touched") or [])
                if key != canonical_key
            ]
            if unrelated:
                problems.append(f"scrape touched unrelated sets: {sorted(unrelated)}")
            if not evidence.get("cards_written") and not evidence.get("empty_catalog"):
                problems.append("no card rows were written and the catalog was not empty")

        report_row["scrape_status"] = "failed" if problems else "success"
        report_row["scrape_problems"] = problems
        report_row["cards_written"] = evidence.get("cards_written")
        report_row["empty_catalog"] = bool(evidence.get("empty_catalog"))

        if problems:
            summary["failed"] += 1
            # Stays ignored so --resume can retry it and the worker still cannot claim it.
            deps.update_job(row["id"], svc.build_progress_fields(row, {
                "scrape_status": "failed", "error": "; ".join(problems),
            }))
            continue

        summary["scraped_successfully"] += 1
        if evidence.get("empty_catalog"):
            summary["empty_catalogs"] += 1
        deps.update_job(row["id"], svc.build_completion_fields(row, {
            "scrape_status": "success",
            "canonical_key": canonical_key,
            "cards_written": evidence.get("cards_written"),
            "empty_catalog": bool(evidence.get("empty_catalog")),
            "error": None,
        }))


def run_backfill(
    *,
    commit: bool,
    stage: str = "configs",
    resume: bool = False,
    max_sets: Optional[int] = None,
    source_set_ids: Sequence[str] = (),
    pokemon_root: Path = DEFAULT_POKEMON_ROOT,
    deps: Optional[BackfillDeps] = None,
    report_path: Optional[Path] = None,
) -> Dict[str, Any]:
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage!r}; expected one of {STAGES}")
    if stage == "all" and commit:
        raise StageOrderError(
            "--stage all is preview-only. Generated source files must be reviewed and merged "
            "before syncing or scraping. Run --commit --stage configs, review, then "
            "--commit --stage sync, then --commit --stage scrape."
        )

    deps = deps or default_deps()
    dry_run = not commit
    summary = _blank_summary(dry_run)

    all_rows = list(deps.list_rows() or [])
    candidates = svc.select_baseline_rows(all_rows, source_set_ids=source_set_ids)
    summary["already_completed"] = sum(1 for row in candidates if svc.is_already_completed(row))

    selected = svc.select_baseline_rows(
        all_rows, source_set_ids=source_set_ids, max_sets=max_sets, resume=resume,
    )
    summary["selected"] = len(selected)

    report_rows: Dict[str, Dict[str, Any]] = {}
    stages = ("configs", "sync", "scrape") if stage == "all" else (stage,)
    for current_stage in stages:
        if current_stage == "configs":
            _run_configs_stage(
                selected, pokemon_root=Path(pokemon_root), deps=deps, commit=commit,
                summary=summary, report_rows=report_rows,
            )
        elif current_stage == "sync":
            _run_sync_stage(
                selected, deps=deps, commit=commit, summary=summary, report_rows=report_rows,
            )
        else:
            _run_scrape_stage(
                selected, deps=deps, commit=commit, summary=summary, report_rows=report_rows,
            )

    summary["remaining"] = max(len(selected) - summary["scraped_successfully"], 0)

    result = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "resume": resume,
        "summary": summary,
        "rows": list(report_rows.values()),
    }
    if report_path is not None:
        report_path = Path(report_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="One-time historical TCGplayer Pokemon catalog backfill."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Plan only; no source, DB, or scrape writes.")
    mode.add_argument("--commit", action="store_true", help="Perform the selected stage for real.")
    parser.add_argument("--stage", choices=STAGES, default="configs")
    parser.add_argument("--resume", action="store_true", help="Skip rows a previous run already scraped.")
    parser.add_argument("--max-sets", type=int, default=None, metavar="N")
    parser.add_argument(
        "--source-set-id", action="append", default=[], dest="source_set_ids", metavar="ID",
        help="Restrict to specific TCGplayer set ids. Repeatable.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON only.")
    parser.add_argument("--report-path", default=None, help="Write the full JSON report here.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.json:
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    from backend.scripts.run_pokemon_set_scrape import _load_backend_env

    _load_backend_env()

    try:
        result = run_backfill(
            commit=bool(args.commit),
            stage=args.stage,
            resume=bool(args.resume),
            max_sets=args.max_sets,
            source_set_ids=args.source_set_ids,
            report_path=Path(args.report_path) if args.report_path else None,
        )
    except StageOrderError as exc:
        print(json.dumps({"status": "refused", "error": str(exc)}, indent=2))
        return 2

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(json.dumps(result["summary"], indent=2, default=str))
    return 0 if result["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
