from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from backend.desirability.favoritepokemon_scraper import (  # noqa: E402
    SOURCE_NAME as FAVORITEPOKEMON_SOURCE_NAME,
    STATS_URL,
    FavoritePokemonRenderedPageScraper,
)
from backend.desirability.normalization import (  # noqa: E402
    SCORING_VERSION,
    match_source_row_to_reference,
    normalize_source_rows,
)
from backend.desirability.pokeapi import DEFAULT_POKEMON_LIMIT, PokeAPIClient  # noqa: E402
from backend.desirability.repository import PokemonDesirabilityRepository  # noqa: E402


logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ingest Pokemon desirability source data for future scoring."
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--source", choices=["pokeapi", "favoritepokemon"])
    source_group.add_argument("--all", action="store_true", help="Run PokeAPI reference ingest, then favoritepokemon")
    source_group.add_argument(
        "--backfill-snapshot-id",
        type=int,
        help="Re-match an existing desirability source snapshot and insert missing scores",
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--dry-run", action="store_true", help="Preview without writing to Supabase")
    mode_group.add_argument("--commit", action="store_true", help="Write rows to Supabase")

    parser.add_argument("--pokemon-limit", type=int, default=DEFAULT_POKEMON_LIMIT)
    parser.add_argument("--pokeapi-delay", type=float, default=0.05)
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "tmp" / "pokemon_desirability")
    parser.add_argument("--no-screenshots", action="store_true")
    parser.add_argument("--headed", action="store_true", help="Run Playwright with a visible browser")
    parser.add_argument("--log-level", default="INFO")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s %(message)s")
    load_dotenv(REPO_ROOT / "backend" / ".env", override=False)

    dry_run = not args.commit
    if args.dry_run:
        dry_run = True

    logger.info("Starting Pokemon desirability ingestion dry_run=%s", dry_run)
    repository: Optional[PokemonDesirabilityRepository] = (
        PokemonDesirabilityRepository() if args.backfill_snapshot_id is not None or not dry_run else None
    )
    reference_rows: List[Dict[str, Any]] = []
    report: Dict[str, Any] = {"dry_run": dry_run, "results": []}

    if args.backfill_snapshot_id is not None:
        assert repository is not None
        report["results"].append(
            backfill_snapshot_matches(
                repository=repository,
                snapshot_id=args.backfill_snapshot_id,
                dry_run=dry_run,
            )
        )
        print(json.dumps(report, indent=2))
        return 0

    if args.all or args.source == "pokeapi":
        pokeapi_result = ingest_pokeapi(
            repository=repository,
            dry_run=dry_run,
            limit=args.pokemon_limit,
            delay_seconds=args.pokeapi_delay,
        )
        reference_rows = pokeapi_result.get("reference_rows", [])
        report["results"].append({k: v for k, v in pokeapi_result.items() if k != "reference_rows"})

    if args.all or args.source == "favoritepokemon":
        favorite_result = ingest_favoritepokemon(
            repository=repository,
            dry_run=dry_run,
            output_dir=args.output_dir,
            save_screenshots=not args.no_screenshots,
            headless=not args.headed,
            reference_rows=reference_rows,
        )
        report["results"].append(favorite_result)

    print(json.dumps(report, indent=2))
    return 0


def ingest_pokeapi(
    *,
    repository: Optional[PokemonDesirabilityRepository],
    dry_run: bool,
    limit: int,
    delay_seconds: float,
) -> Dict[str, Any]:
    client = PokeAPIClient()
    reference_rows = client.fetch_reference_rows(limit=limit, delay_seconds=delay_seconds)
    result = {
        "source": "pokeapi",
        "status": "dry_run" if dry_run else "committed",
        "fetched_rows": len(reference_rows),
        "sample": reference_rows[:5],
        "reference_rows": reference_rows,
    }
    if dry_run:
        logger.info("Dry-run: fetched %s PokeAPI reference row(s); no database writes.", len(reference_rows))
        return result

    assert repository is not None
    upserted = repository.upsert_pokemon_references(reference_rows)
    result["upserted_rows"] = len(upserted)
    logger.info("Committed %s canonical Pokemon reference upsert(s).", len(upserted))
    return result


def ingest_favoritepokemon(
    *,
    repository: Optional[PokemonDesirabilityRepository],
    dry_run: bool,
    output_dir: Path,
    save_screenshots: bool,
    headless: bool,
    reference_rows: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    scraper = FavoritePokemonRenderedPageScraper(headless=headless)
    scrape_result = scraper.scrape(output_dir=output_dir, save_screenshots=save_screenshots)
    raw_payload = scrape_result.raw_payload()

    references = reference_rows or []
    if repository is not None:
        references = repository.list_pokemon_references()

    matched_rows = _attach_reference_matches(scrape_result.rows, references)
    normalized_scores, normalization_summary = normalize_source_rows(matched_rows)
    matching_diagnostics = _matching_diagnostics(matched_rows)

    status = scrape_result.status
    if not normalized_scores:
        status = "insufficient_data"

    result: Dict[str, Any] = {
        "source": FAVORITEPOKEMON_SOURCE_NAME,
        "status": status,
        "notes": scrape_result.notes,
        "raw_rows_extracted": len(scrape_result.rows),
        "matched_reference_rows": sum(1 for row in matched_rows if row.get("pokemon_reference_id") is not None),
        "unmatched_source_rows_count": matching_diagnostics["unmatched_source_rows_count"],
        "unmatched_source_rows_sample": matching_diagnostics["unmatched_source_rows_sample"],
        "normalized_scores": len(normalized_scores),
        "normalization_summary": normalization_summary,
        "diagnostic_pages": [
            {
                "source_url": page.source_url,
                "loaded_url": page.loaded_url,
                "title": page.title,
                "candidate_count": len(page.candidates),
                "screenshot_path": page.screenshot_path,
            }
            for page in scrape_result.pages
        ],
        "sample_rows": matched_rows[:10],
    }

    if dry_run:
        logger.info(
            "Dry-run: favoritepokemon status=%s rows=%s normalized_scores=%s; no database writes.",
            status,
            len(matched_rows),
            len(normalized_scores),
        )
        return result

    assert repository is not None
    snapshot = repository.create_snapshot(
        source_name=FAVORITEPOKEMON_SOURCE_NAME,
        source_url=STATS_URL,
        capture_method="playwright_rendered_page",
        raw_payload_json=raw_payload,
        status=scrape_result.status,
        notes=scrape_result.notes,
    )
    snapshot_id = snapshot["id"]
    source_rows = [_source_row_payload(row, snapshot_id) for row in matched_rows]
    inserted_rows = repository.insert_source_rows(source_rows)

    for score in normalized_scores:
        score["snapshot_id"] = snapshot_id
    inserted_scores = repository.insert_scores(normalized_scores)

    final_status = status if inserted_scores or status == "insufficient_data" else "insufficient_data"
    repository.update_snapshot_status(snapshot_id, final_status, scrape_result.notes)

    result["snapshot_id"] = snapshot_id
    result["inserted_source_rows"] = len(inserted_rows)
    result["inserted_scores"] = len(inserted_scores)
    logger.info(
        "Committed favoritepokemon snapshot=%s source_rows=%s scores=%s status=%s",
        snapshot_id,
        len(inserted_rows),
        len(inserted_scores),
        final_status,
    )
    return result


def backfill_snapshot_matches(
    *,
    repository: PokemonDesirabilityRepository,
    snapshot_id: int,
    dry_run: bool,
) -> Dict[str, Any]:
    source_rows = repository.list_source_rows_for_snapshot(snapshot_id)
    references = repository.list_pokemon_references()
    matched_rows = _attach_reference_matches(source_rows, references)
    normalized_scores, normalization_summary = normalize_source_rows(matched_rows)
    matching_diagnostics = _matching_diagnostics(matched_rows)
    existing_reference_ids = repository.list_score_reference_ids(snapshot_id, SCORING_VERSION)
    scores_to_insert = [
        score
        for score in normalized_scores
        if score.get("pokemon_reference_id") is not None
        and score.get("pokemon_reference_id") not in existing_reference_ids
    ]

    result: Dict[str, Any] = {
        "source": "snapshot_backfill",
        "snapshot_id": snapshot_id,
        "status": "dry_run" if dry_run else "committed",
        "source_rows": len(source_rows),
        "matched_reference_rows": sum(1 for row in matched_rows if row.get("pokemon_reference_id") is not None),
        "unmatched_source_rows_count": matching_diagnostics["unmatched_source_rows_count"],
        "unmatched_source_rows_sample": matching_diagnostics["unmatched_source_rows_sample"],
        "normalized_scores": len(normalized_scores),
        "existing_scores": len(existing_reference_ids),
        "missing_scores_to_insert": len(scores_to_insert),
        "normalization_summary": normalization_summary,
    }

    if dry_run:
        logger.info(
            "Dry-run: snapshot=%s matched=%s unmatched=%s missing_scores=%s; no database writes.",
            snapshot_id,
            result["matched_reference_rows"],
            result["unmatched_source_rows_count"],
            result["missing_scores_to_insert"],
        )
        return result

    updated_source_rows = 0
    for row in matched_rows:
        if row.get("id") and row.get("pokemon_reference_id") is not None:
            repository.update_source_row_reference(
                row["id"],
                row["pokemon_reference_id"],
                row.get("pokedex_number"),
            )
            updated_source_rows += 1

    inserted_scores = repository.insert_scores(scores_to_insert)
    result["updated_source_rows"] = updated_source_rows
    result["inserted_scores"] = len(inserted_scores)
    logger.info(
        "Committed snapshot=%s backfill updated_source_rows=%s inserted_scores=%s unmatched=%s",
        snapshot_id,
        updated_source_rows,
        len(inserted_scores),
        result["unmatched_source_rows_count"],
    )
    return result


def _attach_reference_matches(
    rows: List[Dict[str, Any]],
    references: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    matched: List[Dict[str, Any]] = []
    for row in rows:
        next_row = dict(row)
        reference = match_source_row_to_reference(next_row, references)
        if reference:
            next_row["pokemon_reference_id"] = reference.get("id")
            next_row["pokedex_number"] = next_row.get("pokedex_number") or reference.get("pokedex_number")
        matched.append(next_row)
    return matched


def _matching_diagnostics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    unmatched = [
        {
            "pokemon_name": row.get("pokemon_name"),
            "raw_rank": row.get("raw_rank"),
            "raw_vote_count": row.get("raw_vote_count"),
        }
        for row in rows
        if row.get("pokemon_reference_id") is None
    ]
    return {
        "unmatched_source_rows_count": len(unmatched),
        "unmatched_source_rows_sample": unmatched[:25],
    }


def _source_row_payload(row: Dict[str, Any], snapshot_id: Any) -> Dict[str, Any]:
    return {
        "snapshot_id": snapshot_id,
        "source_name": row.get("source_name") or FAVORITEPOKEMON_SOURCE_NAME,
        "pokemon_reference_id": row.get("pokemon_reference_id"),
        "pokedex_number": row.get("pokedex_number"),
        "pokemon_name": row.get("pokemon_name"),
        "raw_rank": row.get("raw_rank"),
        "raw_vote_count": row.get("raw_vote_count"),
        "raw_score": row.get("raw_score"),
        "raw_tier": row.get("raw_tier"),
        "source_detail_url": row.get("source_detail_url"),
        "extraction_confidence": row.get("extraction_confidence") or "low",
        "raw_row_json": row.get("raw_row_json") or {},
    }


if __name__ == "__main__":
    raise SystemExit(main())
