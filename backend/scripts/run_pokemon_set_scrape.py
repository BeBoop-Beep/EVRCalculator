"""DB-backed Pokémon set scrape runner.

Selects scrape-ready sets from the database and triggers the existing TCGScraper
sequentially with conservative throttling, batching controls, and progress logging.

Usage examples:
    # Dry-run: list all scrape-ready sets without scraping
    python backend/scripts/run_pokemon_set_scrape.py

    # Scrape all ready sets (with DB ingestion)
    python backend/scripts/run_pokemon_set_scrape.py --run

    # Scrape one era only
    python backend/scripts/run_pokemon_set_scrape.py --run --era scarletAndVioletEra

    # Scrape one specific set
    python backend/scripts/run_pokemon_set_scrape.py --run --set blackBolt

    # Scrape first N sets from filtered targets
    python backend/scripts/run_pokemon_set_scrape.py --run --limit 5

    # Scrape without writing to DB (price data only)
    python backend/scripts/run_pokemon_set_scrape.py --run --no-db-ingest
"""

from __future__ import annotations

import argparse
import importlib
import json
import logging
import os
import random
import socket
import sys
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root is on path so backend.* imports resolve correctly.
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# The Scraper package contains a legacy path-relative import
# (`from helpers.card_helper import ...` in excel_writer.py) that requires
# backend/Scraper/ to be on sys.path — identical to how Scraper/main.py works
# when run directly (Python auto-adds the script directory).
_SCRAPER_ROOT = os.path.join(_PROJECT_ROOT, "backend", "Scraper")
if _SCRAPER_ROOT not in sys.path:
    sys.path.insert(0, _SCRAPER_ROOT)

from dotenv import load_dotenv


logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

RUNNER_TAG = "[scrape-runner]"

DEFAULT_REPORT_PATH = Path("backend/constants/tcg/pokemon/pokemon_set_scrape_run_report.json")
POKEMON_CONSTANTS_ROOT = Path("backend/constants/tcg/pokemon")
TCG_NAME_CANDIDATES = ("Pokemon", "Pokémon")

# ---------------------------------------------------------------------------
# Throttle / retry constants
# ---------------------------------------------------------------------------
THROTTLE_MIN_SECONDS = 0.8
THROTTLE_MAX_SECONDS = 1.5
BACKOFF_BASE_SECONDS = 2.0
RATE_LIMIT_PAUSE_SECONDS = 8.0
MAX_RETRIES = 3
SCRAPER_ENABLED_ENV = "SCRAPER_ENABLED"
MEMORY_LOG_INTERVAL_ENV = "SCRAPER_MEMORY_LOG_EVERY_SETS"

SAFE_DEFAULT_ENV: Dict[str, str] = {
    "PYTHONUNBUFFERED": "1",
    "SCRAPER_MAX_CONCURRENCY": "5",
    "HTTP_CONNECT_TIMEOUT_SECONDS": "8",
    "HTTP_READ_TIMEOUT_SECONDS": "20",
    "HTTP_MAX_RETRIES": "3",
    "HTTP_RESPONSE_CACHE_MAX_ENTRIES": "256",
    "PARSED_CACHE_MAX_ENTRIES": "2",
}

# ---------------------------------------------------------------------------
# Scrape diagnostics job identifiers
# ---------------------------------------------------------------------------
DIAG_JOB_NAME = "pokemon_set_scrape"
DIAG_SOURCE_SYSTEM = "tcgplayer"
DIAG_JOB_TYPE = "price_scrape"
DIAG_ENTITY_TYPE = "set"


def _get_host() -> str:
    try:
        return socket.gethostname()[:128]
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
def _load_backend_env() -> None:
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
    load_dotenv(env_path, override=False)


def _apply_safe_runtime_defaults() -> None:
    for key, value in SAFE_DEFAULT_ENV.items():
        os.environ.setdefault(key, value)


def _maybe_log_memory_progress(index: int, total: int, canonical_key: str) -> None:
    interval = max(1, int(os.getenv(MEMORY_LOG_INTERVAL_ENV, "5")))
    if index % interval != 0 and index != total:
        return
    if not tracemalloc.is_tracing():
        return

    current_bytes, peak_bytes = tracemalloc.get_traced_memory()
    logger.info(
        "%s memory checkpoint after %s (%d/%d): current=%.1fMB peak=%.1fMB",
        RUNNER_TAG,
        canonical_key,
        index,
        total,
        current_bytes / (1024 * 1024),
        peak_bytes / (1024 * 1024),
    )


# ---------------------------------------------------------------------------
# Throttle helpers
# ---------------------------------------------------------------------------
def _jitter_sleep() -> None:
    delay = random.uniform(THROTTLE_MIN_SECONDS, THROTTLE_MAX_SECONDS)
    logger.info("%s throttling pause %.1fs", RUNNER_TAG, delay)
    time.sleep(delay)


def _backoff_sleep(attempt: int) -> None:
    delay = BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)) + random.uniform(0.0, 0.5)
    logger.info("%s backoff %.1fs (attempt %d)", RUNNER_TAG, delay, attempt)
    time.sleep(delay)


def _rate_limit_sleep() -> None:
    delay = RATE_LIMIT_PAUSE_SECONDS + random.uniform(0.0, 2.0)
    logger.info("%s rate-limit pause %.1fs", RUNNER_TAG, delay)
    time.sleep(delay)


def _is_rate_limit_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "rate limit" in msg or "too many requests" in msg


def _is_scraper_enabled() -> bool:
    raw = os.getenv(SCRAPER_ENABLED_ENV, "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _dedupe_targets(targets: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], int]:
    """Remove duplicate canonical_key targets while preserving first-seen order."""
    seen: set[str] = set()
    deduped: List[Dict[str, Any]] = []
    removed = 0
    for target in targets:
        key = (target.get("canonical_key") or "").strip().lower()
        if not key:
            deduped.append(target)
            continue
        if key in seen:
            removed += 1
            continue
        seen.add(key)
        deduped.append(target)
    return deduped, removed


def _shuffle_targets_within_release_date(targets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Shuffle targets only within each release_date bucket, preserving chronology."""
    if not targets:
        return targets

    shuffled: List[Dict[str, Any]] = []
    bucket: List[Dict[str, Any]] = []
    current_date = None

    for target in targets:
        release_date = target.get("release_date")
        if current_date is None:
            current_date = release_date

        if release_date != current_date:
            random.shuffle(bucket)
            shuffled.extend(bucket)
            bucket = [target]
            current_date = release_date
        else:
            bucket.append(target)

    if bucket:
        random.shuffle(bucket)
        shuffled.extend(bucket)

    return shuffled


# ---------------------------------------------------------------------------
# Constants config map
# ---------------------------------------------------------------------------
def _build_constants_config_map(era_filter: Optional[str] = None) -> Dict[str, Any]:
    """Build a flat canonical_key → config_cls mapping from all era setMaps.

    Mirrors how pokemon_era_set_sync_service discovers sets via importlib so
    that every era is covered regardless of the current working directory.

    Args:
        era_filter: If given, only load from the era folder whose name matches
                    (case-insensitive). E.g. "scarletAndVioletEra".
    """
    if not POKEMON_CONSTANTS_ROOT.exists():
        raise RuntimeError(f"Pokemon constants root not found: {POKEMON_CONSTANTS_ROOT}")

    config_map: Dict[str, Any] = {}
    era_dirs = sorted(
        (p for p in POKEMON_CONSTANTS_ROOT.iterdir() if p.is_dir() and p.name != "__pycache__"),
        key=lambda p: p.name.lower(),
    )

    loaded_eras: List[str] = []
    for era_dir in era_dirs:
        if era_filter and era_dir.name.lower() != era_filter.lower():
            continue
        try:
            set_map_module = importlib.import_module(
                f"backend.constants.tcg.pokemon.{era_dir.name}.setMap"
            )
        except ModuleNotFoundError:
            logger.debug("%s no setMap in %s — skipping", RUNNER_TAG, era_dir.name)
            continue

        set_config_map: Dict[str, Any] = getattr(set_map_module, "SET_CONFIG_MAP", {})
        config_map.update(set_config_map)
        loaded_eras.append(era_dir.name)

    logger.info(
        "%s loaded config map: %d sets across %d era(s): %s",
        RUNNER_TAG,
        len(config_map),
        len(loaded_eras),
        ", ".join(loaded_eras) if loaded_eras else "none",
    )
    return config_map


# ---------------------------------------------------------------------------
# DB target loading
# ---------------------------------------------------------------------------
def _load_scrape_targets(
    set_key_filter: Optional[str],
) -> List[Dict[str, Any]]:
    """Query the database for all scrape-ready Pokémon sets.

    Applies only the exact set_key_filter here; era filtering and limit are
    applied downstream after the config map intersection so they cooperate
    correctly (e.g. --era scarletAndVioletEra --limit 3 returns 3 SV sets,
    not 3 alphabetically-first sets that happen not to be SV).
    """
    from backend.db.repositories.tcgs_repository import get_tcg_by_name
    from backend.db.repositories.sets_repository import get_scrape_ready_sets_by_tcg_id

    tcg_row: Optional[Dict[str, Any]] = None
    for candidate in TCG_NAME_CANDIDATES:
        tcg_row = get_tcg_by_name(candidate)
        if tcg_row:
            break

    if not tcg_row:
        raise RuntimeError(
            f"Cannot resolve Pokémon TCG row from candidates {TCG_NAME_CANDIDATES}"
        )

    tcg_id: str = tcg_row["id"]
    sets = get_scrape_ready_sets_by_tcg_id(tcg_id)
    logger.info("%s %d scrape-ready sets found in DB (tcg_id=%s)", RUNNER_TAG, len(sets), tcg_id)

    if set_key_filter:
        sets = [s for s in sets if s.get("canonical_key", "").lower() == set_key_filter.lower()]
        logger.info("%s filtered to set: %s (%d match)", RUNNER_TAG, set_key_filter, len(sets))

    return sets


# ---------------------------------------------------------------------------
# Per-set scrape execution with retries
# ---------------------------------------------------------------------------
def _scrape_one_set(
    scraper: Any,
    config_cls: Any,
    canonical_key: str,
    index: int,
    total: int,
) -> Dict[str, Any]:
    """Attempt to scrape one set with up to MAX_RETRIES, with backoff on failures.

    Returns a result dict describing the outcome.
    """
    # excel_path is accepted by the scraper but save_to_excel is currently
    # commented out, so this path is a no-op placeholder.
    excel_path = str(Path("data/exports") / f"{canonical_key}_scrape.xlsx")

    attempt = 0
    last_error: Optional[str] = None

    from backend.Scraper.clients.tcgplayer_client import (
        RequestCapExceededError,
        SustainedRateLimitError,
    )

    while attempt < MAX_RETRIES:
        attempt += 1

        if attempt > 1:
            logger.info("%s retry %d for %s", RUNNER_TAG, attempt, canonical_key)

        logger.info("%s starting %d/%d: %s", RUNNER_TAG, index, total, canonical_key)

        try:
            payload = scraper.scrape(config_cls, excel_path)
            data = payload.get("data", {})
            cards_count = len(data.get("cards", []))
            sealed_count = len(data.get("sealed_products", []))
            logger.info(
                "%s completed %s — cards: %d, sealed: %d",
                RUNNER_TAG,
                canonical_key,
                cards_count,
                sealed_count,
            )
            return {
                "canonical_key": canonical_key,
                "status": "success",
                "attempt": attempt,
                "cards_scraped": cards_count,
                "sealed_scraped": sealed_count,
                "error": None,
            }
        except (RequestCapExceededError, SustainedRateLimitError):
            raise
        except Exception as exc:
            last_error = str(exc)
            logger.warning(
                "%s error on %s (attempt %d/%d): %s",
                RUNNER_TAG,
                canonical_key,
                attempt,
                MAX_RETRIES,
                exc,
            )
            if _is_rate_limit_error(exc):
                _rate_limit_sleep()
            elif attempt < MAX_RETRIES:
                _backoff_sleep(attempt)

    logger.error(
        "%s failed %s after %d attempts: %s",
        RUNNER_TAG,
        canonical_key,
        MAX_RETRIES,
        last_error,
    )
    return {
        "canonical_key": canonical_key,
        "status": "failed",
        "attempt": attempt,
        "cards_scraped": 0,
        "sealed_scraped": 0,
        "error": last_error,
    }


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------
def _write_report(report: Dict[str, Any], report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    logger.info("%s report written to %s", RUNNER_TAG, report_path)


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------
def run_scraper(
    dry_run: bool,
    era_filter: Optional[str],
    set_key_filter: Optional[str],
    limit: Optional[int],
    enable_db_ingestion: bool,
    shuffle_within_date: bool,
    report_path: Path,
) -> Dict[str, Any]:
    """Orchestrate the full scrape run: select targets, execute, throttle, report."""
    from backend.db.repositories.scrape_diagnostics_repository import (
        create_scrape_job_run,
        insert_scrape_job_run_failures,
        update_scrape_job_run,
    )
    from backend.Scraper.clients.tcgplayer_client import (
        RequestCapExceededError,
        SustainedRateLimitError,
    )
    from backend.Scraper.services.orchestrators.tcg_player_orchestrator import TCGScraper

    if not tracemalloc.is_tracing():
        tracemalloc.start()

    started_at = datetime.now(timezone.utc)

    # 1. Fetch targets from DB
    db_sets = _load_scrape_targets(set_key_filter)

    # 2. Build constants config index (used to resolve config_cls from canonical_key)
    config_map = _build_constants_config_map(era_filter)

    # 3. Resolve each DB row to a config class; warn on any missing.
    #    era filtering is implicit: the config_map only contains sets from the
    #    requested era when era_filter is set, so non-era sets are skipped.
    targets: List[Dict[str, Any]] = []
    skipped_no_config: List[str] = []    # genuinely missing from constants
    skipped_era_filtered: int = 0         # expected: other-era sets when era_filter active
    for row in db_sets:
        canonical_key: str = row.get("canonical_key", "")
        if canonical_key in config_map:
            targets.append({**row, "_config_cls": config_map[canonical_key]})
        elif era_filter:
            # Expected: sets from other eras won't be in the filtered config map.
            skipped_era_filtered += 1
        else:
            skipped_no_config.append(canonical_key)
            logger.warning(
                "%s no config class found for canonical_key=%r — skipping",
                RUNNER_TAG,
                canonical_key,
            )

    targets, deduped_targets_removed = _dedupe_targets(targets)
    if deduped_targets_removed:
        logger.info(
            "%s removed %d duplicate target(s) from queue",
            RUNNER_TAG,
            deduped_targets_removed,
        )

    if shuffle_within_date and len(targets) > 1:
        targets = _shuffle_targets_within_release_date(targets)
        logger.info("%s set execution order shuffled within each release_date bucket", RUNNER_TAG)

    if era_filter and skipped_era_filtered:
        logger.debug(
            "%s %d sets from other eras excluded by era filter",
            RUNNER_TAG,
            skipped_era_filtered,
        )

    # 4. Apply limit AFTER era intersection so --era + --limit behaves intuitively.
    if limit is not None:
        targets = targets[:limit]
        logger.info("%s limited to first %d sets after era filter", RUNNER_TAG, limit)

    total = len(targets)

    logger.info("%s -------------------------------------------", RUNNER_TAG)
    logger.info("%s  Pokémon Set Scrape Runner", RUNNER_TAG)
    logger.info("%s  mode          : %s", RUNNER_TAG, "DRY-RUN" if dry_run else "APPLY")
    logger.info("%s  era filter    : %s", RUNNER_TAG, era_filter or "all")
    logger.info("%s  set filter    : %s", RUNNER_TAG, set_key_filter or "all")
    logger.info("%s  limit         : %s", RUNNER_TAG, str(limit) if limit else "none")
    logger.info("%s  shuffle/date  : %s", RUNNER_TAG, "enabled" if shuffle_within_date else "disabled")
    logger.info("%s  db ingestion  : %s", RUNNER_TAG, "enabled" if enable_db_ingestion else "disabled")
    logger.info("%s  targets       : %d sets", RUNNER_TAG, total)
    logger.info("%s -------------------------------------------", RUNNER_TAG)

    kill_switch_enabled = _is_scraper_enabled()

    # ------------------------------------------------------------------
    # DB diagnostics — insert run row at apply-mode start
    # ------------------------------------------------------------------
    diag_run_id: Optional[str] = None
    if not dry_run:
        trigger_source = os.getenv("SCRAPE_TRIGGER_SOURCE", "manual")
        run_row = create_scrape_job_run({
            "job_name": DIAG_JOB_NAME,
            "source_system": DIAG_SOURCE_SYSTEM,
            "job_type": DIAG_JOB_TYPE,
            "entity_type": DIAG_ENTITY_TYPE,
            "status": "running",
            "trigger_source": trigger_source,
            "host": _get_host(),
            "started_at": started_at.isoformat(),
            "kill_switch_enabled": kill_switch_enabled,
            "metadata": {
                "era_filter": era_filter,
                "set_filter": set_key_filter,
                "limit": limit,
                "shuffle_within_date": shuffle_within_date,
                "db_ingestion_enabled": enable_db_ingestion,
                "items_selected": total,
            },
        })
        if run_row:
            diag_run_id = run_row.get("id")

    if not dry_run and not kill_switch_enabled:
        logger.warning(
            "%s scraping is disabled by %s=false; exiting before outbound HTTP",
            RUNNER_TAG,
            SCRAPER_ENABLED_ENV,
        )
        report: Dict[str, Any] = {
            "generated_at_utc": started_at.isoformat(),
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "mode": "apply",
            "era_filter": era_filter,
            "set_filter": set_key_filter,
            "limit": limit,
            "db_ingestion_enabled": enable_db_ingestion,
            "shuffle_within_date": shuffle_within_date,
            "sets_selected": total,
            "sets_attempted": 0,
            "sets_succeeded": 0,
            "sets_failed": 0,
            "sets_skipped_no_config": len(skipped_no_config),
            "skipped_no_config": skipped_no_config,
            "sets_era_filtered": skipped_era_filtered,
            "deduped_targets_removed": deduped_targets_removed,
            "elapsed_seconds": 0,
            "retry_heavy_sets": [],
            "results": [],
            "http_requests_total": 0,
            "http_requests_cache_hits": 0,
            "http_requests_cache_misses": 0,
            "http_requests_skipped_redundant": 0,
            "rate_limit_events": 0,
            "retry_count_total": 0,
            "aborted_due_to_request_cap": False,
            "aborted_due_to_rate_limit": False,
            "kill_switch_enabled": False,
            "run_aborted_early": True,
            "run_abort_reason": "kill_switch_disabled",
        }
        if diag_run_id:
            update_scrape_job_run(diag_run_id, {
                "status": "aborted",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "elapsed_seconds": 0,
                "aborted": True,
                "error_summary": "kill_switch_disabled",
                "report_path": str(report_path),
            })
        _write_report(report, report_path)
        return report

    # ------------------------------------------------------------------
    # DRY-RUN: just list what would be scraped
    # ------------------------------------------------------------------
    if dry_run:
        for i, target in enumerate(targets, start=1):
            logger.info(
                "%s [dry-run] would scrape %d/%d: %s  (%s)",
                RUNNER_TAG,
                i,
                total,
                target.get("canonical_key"),
                target.get("name", ""),
            )
        report: Dict[str, Any] = {
            "generated_at_utc": started_at.isoformat(),
            "mode": "dry_run",
            "era_filter": era_filter,
            "set_filter": set_key_filter,
            "limit": limit,
            "shuffle_within_date": shuffle_within_date,
            "sets_selected": total,
            "sets_attempted": 0,
            "sets_succeeded": 0,
            "sets_failed": 0,
            "sets_skipped_no_config": len(skipped_no_config),
            "skipped_no_config": skipped_no_config,
            "sets_era_filtered": skipped_era_filtered,
            "deduped_targets_removed": deduped_targets_removed,
            "elapsed_seconds": 0,
            "retry_heavy_sets": [],
            "results": [
                {"canonical_key": t.get("canonical_key"), "status": "dry_run"}
                for t in targets
            ],
            "http_requests_total": 0,
            "http_requests_cache_hits": 0,
            "http_requests_cache_misses": 0,
            "http_requests_skipped_redundant": 0,
            "rate_limit_events": 0,
            "retry_count_total": 0,
            "aborted_due_to_request_cap": False,
            "aborted_due_to_rate_limit": False,
            "kill_switch_enabled": kill_switch_enabled,
            "run_aborted_early": False,
            "run_abort_reason": None,
        }
        _write_report(report, report_path)
        return report

    # ------------------------------------------------------------------
    # APPLY: scrape each target sequentially with throttling
    # ------------------------------------------------------------------
    scraper = TCGScraper(enable_db_ingestion=enable_db_ingestion)
    results: List[Dict[str, Any]] = []
    succeeded = 0
    failed = 0
    run_aborted_early = False
    run_abort_reason: Optional[str] = None
    _crash_error: Optional[str] = None

    try:
        for index, target in enumerate(targets, start=1):
            canonical_key = target["canonical_key"]
            config_cls = target["_config_cls"]

            try:
                result = _scrape_one_set(scraper, config_cls, canonical_key, index, total)
            except RequestCapExceededError as exc:
                run_aborted_early = True
                run_abort_reason = "request_cap_exceeded"
                logger.error("%s aborting run due to request cap: %s", RUNNER_TAG, exc)
                result = {
                    "canonical_key": canonical_key,
                    "status": "aborted",
                    "attempt": 1,
                    "cards_scraped": 0,
                    "sealed_scraped": 0,
                    "error": str(exc),
                }
                results.append(result)
                failed += 1
                break
            except SustainedRateLimitError as exc:
                run_aborted_early = True
                run_abort_reason = "sustained_rate_limit"
                logger.error("%s aborting run due to sustained rate-limit events: %s", RUNNER_TAG, exc)
                result = {
                    "canonical_key": canonical_key,
                    "status": "aborted",
                    "attempt": 1,
                    "cards_scraped": 0,
                    "sealed_scraped": 0,
                    "error": str(exc),
                }
                results.append(result)
                failed += 1
                break

            results.append(result)

            if result["status"] == "success":
                succeeded += 1
            else:
                failed += 1

            _maybe_log_memory_progress(index=index, total=total, canonical_key=canonical_key)

            # Throttle between sets; no pause needed after the final set
            if index < total:
                _jitter_sleep()

    except BaseException as _exc:
        # Catches unexpected errors AND keyboard interrupts — update run row before re-raising.
        _crash_error = str(_exc) or type(_exc).__name__
        run_aborted_early = True
        run_abort_reason = "unexpected_crash"
        logger.error("%s unexpected crash in run loop: %s", RUNNER_TAG, _exc)
        if diag_run_id:
            update_scrape_job_run(diag_run_id, {
                "status": "failed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "elapsed_seconds": round((datetime.now(timezone.utc) - started_at).total_seconds(), 2),
                "aborted": True,
                "error_summary": _crash_error,
                "items_selected": total,
                "items_attempted": len(results),
                "items_succeeded": succeeded,
                "items_failed": failed,
                "report_path": str(report_path),
            })
        raise

    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
    retry_heavy = [r["canonical_key"] for r in results if r.get("attempt", 1) > 1]
    request_metrics = scraper.get_request_metrics()
    attempted_sets = len(results)
    requests_per_set = (
        request_metrics.get("http_requests_total", 0) / attempted_sets
        if attempted_sets > 0
        else 0.0
    )
    cache_hits = request_metrics.get("http_requests_cache_hits", 0)
    cache_misses = request_metrics.get("http_requests_cache_misses", 0)
    cache_hit_ratio = (
        cache_hits / (cache_hits + cache_misses)
        if (cache_hits + cache_misses) > 0
        else 0.0
    )

    # ------------------------------------------------------------------
    # Final summary log
    # ------------------------------------------------------------------
    logger.info("%s -------------------------------------------", RUNNER_TAG)
    logger.info("%s  Run Complete", RUNNER_TAG)
    logger.info("%s  total selected     : %d", RUNNER_TAG, total)
    logger.info("%s  attempted          : %d", RUNNER_TAG, len(results))
    logger.info("%s  succeeded          : %d", RUNNER_TAG, succeeded)
    logger.info("%s  failed             : %d", RUNNER_TAG, failed)
    logger.info(
        "%s  skipped (no config): %d", RUNNER_TAG, len(skipped_no_config)
    )
    logger.info("%s  deduped targets    : %d", RUNNER_TAG, deduped_targets_removed)
    logger.info("%s  elapsed            : %.1fs", RUNNER_TAG, elapsed)
    logger.info("%s  http requests      : %d", RUNNER_TAG, request_metrics.get("http_requests_total", 0))
    logger.info("%s  avg req/set        : %.2f", RUNNER_TAG, requests_per_set)
    logger.info("%s  cache hit ratio    : %.2f", RUNNER_TAG, cache_hit_ratio)
    logger.info("%s  req skipped redun. : %d", RUNNER_TAG, request_metrics.get("http_requests_skipped_redundant", 0))
    logger.info("%s  retries total      : %d", RUNNER_TAG, request_metrics.get("retry_count_total", 0))
    logger.info("%s  rate-limit events  : %d", RUNNER_TAG, request_metrics.get("rate_limit_events", 0))
    logger.info("%s  global stop        : %s", RUNNER_TAG, run_abort_reason or "none")
    if retry_heavy:
        logger.info("%s  retry-heavy sets   : %s", RUNNER_TAG, retry_heavy)
    logger.info("%s -------------------------------------------", RUNNER_TAG)

    report = {
        "generated_at_utc": started_at.isoformat(),
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "apply",
        "era_filter": era_filter,
        "set_filter": set_key_filter,
        "limit": limit,
        "db_ingestion_enabled": enable_db_ingestion,
        "shuffle_within_date": shuffle_within_date,
        "sets_selected": total,
        "sets_attempted": len(results),
        "sets_succeeded": succeeded,
        "sets_failed": failed,
        "sets_skipped_no_config": len(skipped_no_config),
        "skipped_no_config": skipped_no_config,
        "sets_era_filtered": skipped_era_filtered,
        "deduped_targets_removed": deduped_targets_removed,
        "elapsed_seconds": round(elapsed, 2),
        "retry_heavy_sets": retry_heavy,
        "results": results,
        "http_requests_total": request_metrics.get("http_requests_total", 0),
        "http_requests_cache_hits": cache_hits,
        "http_requests_cache_misses": cache_misses,
        "http_requests_skipped_redundant": request_metrics.get("http_requests_skipped_redundant", 0),
        "rate_limit_events": request_metrics.get("rate_limit_events", 0),
        "retry_count_total": request_metrics.get("retry_count_total", 0),
        "aborted_due_to_request_cap": request_metrics.get("aborted_due_to_request_cap", False),
        "aborted_due_to_rate_limit": request_metrics.get("aborted_due_to_rate_limit", False),
        "kill_switch_enabled": kill_switch_enabled,
        "run_aborted_early": run_aborted_early,
        "run_abort_reason": run_abort_reason,
    }
    _write_report(report, report_path)

    # ------------------------------------------------------------------
    # DB diagnostics — update run row at completion
    # ------------------------------------------------------------------
    if diag_run_id:
        if run_aborted_early:
            final_status = "aborted"
        elif failed > 0:
            final_status = "partial_failure"
        else:
            final_status = "success"

        update_scrape_job_run(diag_run_id, {
            "status": final_status,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": round(elapsed, 2),
            "items_selected": total,
            "items_attempted": len(results),
            "items_succeeded": succeeded,
            "items_failed": failed,
            "items_skipped": len(skipped_no_config),
            "http_requests_total": request_metrics.get("http_requests_total", 0),
            "http_requests_cache_hits": cache_hits,
            "http_requests_cache_misses": cache_misses,
            "http_requests_skipped_redundant": request_metrics.get("http_requests_skipped_redundant", 0),
            "rate_limit_events": request_metrics.get("rate_limit_events", 0),
            "retry_count_total": request_metrics.get("retry_count_total", 0),
            "aborted": run_aborted_early,
            "aborted_due_to_request_cap": request_metrics.get("aborted_due_to_request_cap", False),
            "aborted_due_to_rate_limit": request_metrics.get("aborted_due_to_rate_limit", False),
            "kill_switch_enabled": kill_switch_enabled,
            "report_path": str(report_path),
            "error_summary": run_abort_reason if run_aborted_early else None,
        })

        # Insert failure detail rows for every set that did not succeed
        failed_results = [r for r in results if r.get("status") not in ("success",)]
        if failed_results:
            failure_rows = []
            for r in failed_results:
                ckey = r.get("canonical_key", "")
                # Look up display name from matched target list
                display_name = next(
                    (t.get("name") for t in targets if t.get("canonical_key") == ckey),
                    None,
                )
                error_msg = r.get("error") or r.get("status") or "unknown"
                is_rate_limit = any(
                    token in (error_msg or "").lower()
                    for token in ("429", "rate limit", "too many", "rate_limit")
                )
                failure_rows.append({
                    "run_id": diag_run_id,
                    "source_system": DIAG_SOURCE_SYSTEM,
                    "job_type": DIAG_JOB_TYPE,
                    "entity_type": DIAG_ENTITY_TYPE,
                    "entity_key": ckey,
                    "entity_name": display_name,
                    "attempt_count": r.get("attempt", 1),
                    "rate_limit_like": is_rate_limit,
                    "error_message": error_msg[:2000],
                    "metadata": {
                        "cards_scraped": r.get("cards_scraped", 0),
                        "sealed_scraped": r.get("sealed_scraped", 0),
                        "result_status": r.get("status"),
                    },
                })
            insert_scrape_job_run_failures(failure_rows)

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "DB-backed Pokémon set scrape runner. "
            "Selects scrape-ready sets from the database and triggers the existing "
            "TCGScraper sequentially with conservative throttling."
        )
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Execute scrapes. Omit to run in dry-run (listing only) mode.",
    )
    parser.add_argument(
        "--era",
        default=None,
        metavar="ERA_FOLDER",
        help=(
            "Only scrape sets from this era folder "
            "(e.g. scarletAndVioletEra, blackAndWhiteEra)."
        ),
    )
    parser.add_argument(
        "--set",
        dest="set_key",
        default=None,
        metavar="CANONICAL_KEY",
        help="Only scrape a single set by its canonical key (e.g. blackBolt).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Cap the number of sets scraped from the filtered target list.",
    )
    parser.add_argument(
        "--no-db-ingest",
        action="store_true",
        help="Disable database ingestion. Scrape price data but do not write to DB.",
    )
    parser.add_argument(
        "--shuffle-within-date",
        action="store_true",
        help="Shuffle execution order only within identical release_date groups.",
    )
    parser.add_argument(
        "--report-path",
        default=str(DEFAULT_REPORT_PATH),
        help="Path to write the JSON scrape run report.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    _load_backend_env()
    _apply_safe_runtime_defaults()

    report = run_scraper(
        dry_run=not args.run,
        era_filter=args.era,
        set_key_filter=args.set_key,
        limit=args.limit,
        enable_db_ingestion=not args.no_db_ingest,
        shuffle_within_date=args.shuffle_within_date,
        report_path=Path(args.report_path),
    )

    print(
        json.dumps(
            {
                "mode": report["mode"],
                "sets_selected": report["sets_selected"],
                "sets_attempted": report.get("sets_attempted", 0),
                "sets_succeeded": report.get("sets_succeeded", 0),
                "sets_failed": report.get("sets_failed", 0),
                "sets_skipped_no_config": report.get("sets_skipped_no_config", 0),
                "http_requests_total": report.get("http_requests_total", 0),
                "http_requests_cache_hits": report.get("http_requests_cache_hits", 0),
                "http_requests_cache_misses": report.get("http_requests_cache_misses", 0),
                "rate_limit_events": report.get("rate_limit_events", 0),
                "retry_count_total": report.get("retry_count_total", 0),
                "run_aborted_early": report.get("run_aborted_early", False),
                "elapsed_seconds": report.get("elapsed_seconds", 0),
            },
            indent=2,
        )
    )

    # Send pending alerts (apply mode only, non-fatal)
    if args.run:
        try:
            from backend.alerts.dispatcher import send_pending_alerts
            alert_summary = send_pending_alerts()
            if alert_summary.get("failed_count", 0) > 0:
                logger.warning(
                    "%s alert dispatch completed with failures: sent=%d failed=%d",
                    RUNNER_TAG,
                    alert_summary.get("sent_count", 0),
                    alert_summary.get("failed_count", 0),
                )
        except ImportError:
            logger.debug("%s alert dispatcher not available, skipping", RUNNER_TAG)
        except ValueError as exc:
            logger.warning("%s alert dispatcher config error: %s", RUNNER_TAG, exc)
        except Exception as exc:
            logger.exception("%s alert dispatcher failed, but scraper completed: %s", RUNNER_TAG, exc)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
