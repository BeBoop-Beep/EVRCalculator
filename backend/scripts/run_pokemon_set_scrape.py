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
import sys
import time
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


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
def _load_backend_env() -> None:
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
    load_dotenv(env_path, override=False)


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
    report_path: Path,
) -> Dict[str, Any]:
    """Orchestrate the full scrape run: select targets, execute, throttle, report."""
    from backend.Scraper.services.orchestrators.tcg_player_orchestrator import TCGScraper

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
    logger.info("%s  db ingestion  : %s", RUNNER_TAG, "enabled" if enable_db_ingestion else "disabled")
    logger.info("%s  targets       : %d sets", RUNNER_TAG, total)
    logger.info("%s -------------------------------------------", RUNNER_TAG)

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
            "sets_selected": total,
            "sets_attempted": 0,
            "sets_succeeded": 0,
            "sets_failed": 0,
            "sets_skipped_no_config": len(skipped_no_config),
            "skipped_no_config": skipped_no_config,
            "sets_era_filtered": skipped_era_filtered,
            "elapsed_seconds": 0,
            "retry_heavy_sets": [],
            "results": [
                {"canonical_key": t.get("canonical_key"), "status": "dry_run"}
                for t in targets
            ],
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

    for index, target in enumerate(targets, start=1):
        canonical_key = target["canonical_key"]
        config_cls = target["_config_cls"]

        result = _scrape_one_set(scraper, config_cls, canonical_key, index, total)
        results.append(result)

        if result["status"] == "success":
            succeeded += 1
        else:
            failed += 1

        # Throttle between sets; no pause needed after the final set
        if index < total:
            _jitter_sleep()

    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
    retry_heavy = [r["canonical_key"] for r in results if r.get("attempt", 1) > 1]

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
    logger.info("%s  elapsed            : %.1fs", RUNNER_TAG, elapsed)
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
        "sets_selected": total,
        "sets_attempted": len(results),
        "sets_succeeded": succeeded,
        "sets_failed": failed,
        "sets_skipped_no_config": len(skipped_no_config),
        "skipped_no_config": skipped_no_config,
        "sets_era_filtered": skipped_era_filtered,
        "elapsed_seconds": round(elapsed, 2),
        "retry_heavy_sets": retry_heavy,
        "results": results,
    }
    _write_report(report, report_path)
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
        "--report-path",
        default=str(DEFAULT_REPORT_PATH),
        help="Path to write the JSON scrape run report.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    _load_backend_env()

    report = run_scraper(
        dry_run=not args.run,
        era_filter=args.era,
        set_key_filter=args.set_key,
        limit=args.limit,
        enable_db_ingestion=not args.no_db_ingest,
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
                "elapsed_seconds": report.get("elapsed_seconds", 0),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
