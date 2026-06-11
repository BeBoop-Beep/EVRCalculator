from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from backend.desirability.google_trends import (  # noqa: E402
    DEFAULT_ANCHOR_TERM,
    DEFAULT_BATCH_SIZE,
    DEFAULT_GEO,
    DEFAULT_TIMEFRAMES,
    QUERY_TYPE_SEARCH_TERM,
    SOURCE_NAME,
    FixtureGoogleTrendsProvider,
    GoogleTrendsProvider,
    TrendTimeframe,
    fetch_timeframe_rows,
    make_provider,
)
from backend.desirability.pokeapi import generation_for_pokedex_number  # noqa: E402
from backend.desirability.repository import PokemonDesirabilityRepository  # noqa: E402
from backend.desirability.trends_normalization import (  # noqa: E402
    BASELINE_TIMEFRAME,
    CURRENT_TIMEFRAME,
    RECENT_TIMEFRAME,
    TREND_SCORING_VERSION,
    build_trend_diagnostics,
    calculate_derived_trend_scores,
    normalize_timeframe_rows,
)


logger = logging.getLogger(__name__)
DERIVE_REQUIRED_TIMEFRAMES = (RECENT_TIMEFRAME, CURRENT_TIMEFRAME, BASELINE_TIMEFRAME)
DERIVE_OPTIONAL_TIMEFRAMES = ("today 3-m",)
COMPLETE_REFERENCE_COUNT = 1025


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Ingest Pokemon Google Trends relative search-interest data. "
            "This does not estimate absolute search volume."
        )
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--dry-run", action="store_true", help="Preview without writing to Supabase")
    mode_group.add_argument("--commit", action="store_true", help="Write trend snapshots, rows, and scores to Supabase")

    parser.add_argument("--provider", choices=["auto", "pytrends", "fixture"], default="auto")
    parser.add_argument("--geo", default=DEFAULT_GEO)
    parser.add_argument("--query-type", choices=[QUERY_TYPE_SEARCH_TERM], default=QUERY_TYPE_SEARCH_TERM)
    parser.add_argument("--anchor-term", default=DEFAULT_ANCHOR_TERM)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Total terms per Trends request, including anchor")
    parser.add_argument("--offset", type=int, default=0, help="Skip this many selected Pokemon references after ordering/filtering")
    parser.add_argument("--limit", type=int, default=None, help="Limit selected Pokemon references for small validation/retry runs")
    parser.add_argument("--pokedex-start", type=int, default=None)
    parser.add_argument("--pokedex-end", type=int, default=None)
    parser.add_argument("--generation", type=int, default=None)
    parser.add_argument("--append-to-snapshot-id", type=int, default=None)
    parser.add_argument("--derive-from-existing", action="store_true")
    parser.add_argument(
        "--timeframe",
        action="append",
        nargs=2,
        metavar=("TODAY", "WINDOW"),
        help="Repeatable Google Trends timeframe, e.g. --timeframe today 12-m",
    )
    parser.add_argument("--delay-seconds", type=float, default=8.0)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--retry-backoff-seconds", type=float, default=20.0)
    parser.add_argument("--stop-after-consecutive-429s", type=int, default=3)
    parser.add_argument("--cooldown-after-429-seconds", type=float, default=900.0)
    parser.add_argument("--log-level", default="INFO")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s %(message)s")
    load_dotenv(REPO_ROOT / "backend" / ".env", override=False)

    dry_run = not args.commit
    if args.dry_run:
        dry_run = True

    timeframes = _parse_timeframes(args.timeframe)
    validation_error = _validate_args(args, timeframes)
    if validation_error:
        print(
            json.dumps(
                {
                    "dry_run": dry_run,
                    "status": "invalid_arguments",
                    "error": validation_error,
                    "measurement_note": "Google Trends reports relative search interest, not absolute search volume.",
                },
                indent=2,
            )
        )
        return 0

    try:
        repository = PokemonDesirabilityRepository()
        if args.derive_from_existing:
            provider_name = None if args.provider == "auto" else ("fixture_diagnostic" if args.provider == "fixture" else args.provider)
            report = derive_from_existing_snapshots(
                repository=repository,
                dry_run=dry_run,
                source_name=SOURCE_NAME,
                provider_name=provider_name,
                geo=args.geo,
            )
        else:
            try:
                provider = make_provider(args.provider, dry_run=dry_run)
            except Exception as exc:
                report = {
                    "dry_run": dry_run,
                    "status": "provider_unavailable",
                    "provider_requested": args.provider,
                    "error": f"{type(exc).__name__}: {exc}",
                    "measurement_note": "Google Trends reports relative search interest, not absolute search volume.",
                }
                print(json.dumps(report, indent=2))
                return 0

            if getattr(provider, "provider_name", "") == "unavailable":
                report = {
                    "dry_run": dry_run,
                    "status": "provider_unavailable",
                    "provider_requested": args.provider,
                    "provider": provider.provider_name,
                    "error": getattr(provider, "reason", "Google Trends provider is unavailable."),
                    "measurement_note": "Google Trends reports relative search interest, not absolute search volume.",
                }
                print(json.dumps(report, indent=2))
                return 0

            report = run_ingestion(
                repository=repository,
                provider=provider,
                dry_run=dry_run,
                geo=args.geo,
                query_type=args.query_type,
                anchor_term=args.anchor_term,
                batch_size=args.batch_size,
                offset=args.offset,
                limit=args.limit,
                pokedex_start=args.pokedex_start,
                pokedex_end=args.pokedex_end,
                generation=args.generation,
                append_to_snapshot_id=args.append_to_snapshot_id,
                timeframes=timeframes,
                delay_seconds=args.delay_seconds,
                max_retries=args.max_retries,
                retry_backoff_seconds=args.retry_backoff_seconds,
                stop_after_consecutive_429s=args.stop_after_consecutive_429s,
                cooldown_after_429_seconds=args.cooldown_after_429_seconds,
            )
    except Exception as exc:
        logger.exception("Pokemon trend ingestion failed gracefully")
        report = {
            "dry_run": dry_run,
            "status": "failed_gracefully",
            "provider": args.provider,
            "error": f"{type(exc).__name__}: {exc}",
            "measurement_note": "No absolute search-volume claim was made; Google Trends values are relative search interest.",
        }

    print(json.dumps(_jsonable(report), indent=2))
    return 0


def run_ingestion(
    *,
    repository: PokemonDesirabilityRepository,
    provider: GoogleTrendsProvider,
    dry_run: bool,
    geo: str,
    query_type: str,
    anchor_term: str,
    batch_size: int,
    timeframes: List[TrendTimeframe],
    delay_seconds: float,
    max_retries: int,
    retry_backoff_seconds: float,
    offset: int = 0,
    limit: Optional[int] = None,
    pokedex_start: Optional[int] = None,
    pokedex_end: Optional[int] = None,
    generation: Optional[int] = None,
    append_to_snapshot_id: Optional[int] = None,
    stop_after_consecutive_429s: int = 3,
    cooldown_after_429_seconds: float = 900.0,
) -> Dict[str, Any]:
    all_references = repository.list_pokemon_references()
    append_snapshot = repository.get_trend_snapshot(append_to_snapshot_id) if append_to_snapshot_id is not None else None
    if append_to_snapshot_id is not None and append_snapshot is None:
        return {
            "source": SOURCE_NAME,
            "provider": provider.provider_name,
            "status": "append_snapshot_not_found",
            "dry_run": dry_run,
            "append_to_snapshot_id": append_to_snapshot_id,
        }

    if append_snapshot is not None:
        timeframe = TrendTimeframe(
            str(append_snapshot["timeframe"]),
            str(append_snapshot.get("window_role") or timeframes[0].window_role),
            "Append/fill existing Google Trends snapshot",
        )
        timeframes = [timeframe]
        geo = str(append_snapshot.get("geo") or geo)
        query_type = str(append_snapshot.get("query_type") or query_type)
        anchor_term = str(append_snapshot.get("anchor_term") or anchor_term)

    selected_references = _select_references(
        all_references,
        offset=offset,
        limit=limit,
        pokedex_start=pokedex_start,
        pokedex_end=pokedex_end,
        generation=generation,
    )
    existing_append_rows: List[Dict[str, Any]] = []
    existing_reference_ids: set[Any] = set()
    if append_snapshot is not None:
        existing_append_rows = repository.list_trend_source_rows_for_snapshot(append_to_snapshot_id)
        existing_reference_ids = {
            row.get("pokemon_reference_id")
            for row in existing_append_rows
            if row.get("pokemon_reference_id") is not None
        }
        selected_references = [
            reference
            for reference in selected_references
            if reference.get("id") not in existing_reference_ids
        ]

    if not selected_references:
        final_rows = len(existing_reference_ids) if append_snapshot is not None else 0
        final_status = _snapshot_status_for_count(final_rows)
        if append_snapshot is not None and not dry_run:
            repository.update_trend_snapshot_status(
                append_to_snapshot_id,
                final_status,
                f"Append/fill run found no missing Pokemon in selected range; final row count={final_rows}.",
            )
        return {
            "source": SOURCE_NAME,
            "provider": provider.provider_name,
            "status": final_status if append_snapshot is not None else "insufficient_reference_data",
            "dry_run": dry_run,
            "append_to_snapshot_id": append_to_snapshot_id,
            "pokemon_reference_rows_available": len(all_references),
            "pokemon_processed": 0,
            "selection": _selection_payload(
                offset=offset,
                limit=limit,
                pokedex_start=pokedex_start,
                pokedex_end=pokedex_end,
                generation=generation,
            ),
            "diagnostics": {
                "existing_rows_skipped": len(existing_reference_ids),
                "missing_rows_attempted": 0,
                "inserted_rows": 0,
                "final_snapshot_row_count": final_rows,
                "missing_pokemon_sample": _missing_pokemon_sample(all_references, existing_reference_ids),
            },
            "measurement_note": "Google Trends values would be relative search interest, not absolute search volume.",
        }

    logger.info(
        "Starting Pokemon Google Trends ingestion provider=%s dry_run=%s selected_references=%s available_references=%s append_snapshot=%s geo=%s timeframes=%s",
        provider.provider_name,
        dry_run,
        len(selected_references),
        len(all_references),
        append_to_snapshot_id,
        geo,
        [timeframe.timeframe for timeframe in timeframes],
    )

    timeframe_results: List[Dict[str, Any]] = []
    source_rows_by_timeframe: Dict[str, List[Dict[str, Any]]] = {}
    normalized_by_timeframe: Dict[str, List[Dict[str, Any]]] = {}
    snapshot_ids_by_timeframe: Dict[str, Any] = {}
    total_inserted_rows = 0

    for timeframe in timeframes:
        timeframe_result = fetch_timeframe_rows(
            provider=provider,
            references=selected_references,
            timeframe=timeframe,
            geo=geo,
            query_type=query_type,
            anchor_term=anchor_term,
            batch_size=batch_size,
            delay_seconds=delay_seconds,
            max_retries=max_retries,
            retry_backoff_seconds=retry_backoff_seconds,
            stop_after_consecutive_429s=stop_after_consecutive_429s,
            cooldown_after_429_seconds=cooldown_after_429_seconds,
        )
        rows = timeframe_result["rows"]
        source_rows_by_timeframe[timeframe.timeframe] = rows

        normalized_scores, normalization_summary = normalize_timeframe_rows(rows)
        normalized_by_timeframe[timeframe.timeframe] = normalized_scores
        status = _timeframe_status(timeframe_result, rows, normalized_scores)

        snapshot_id = append_to_snapshot_id
        inserted_rows: List[Dict[str, Any]] = []
        if not dry_run:
            if snapshot_id is None:
                snapshot = repository.create_trend_snapshot(
                    source_name=SOURCE_NAME,
                    provider_name=provider.provider_name,
                    geo=geo,
                    timeframe=timeframe.timeframe,
                    window_role=timeframe.window_role,
                    query_type=query_type,
                    anchor_term=anchor_term,
                    raw_payload_json={
                        "timeframe_result": _compact_timeframe_result(timeframe_result),
                        "normalization_summary": normalization_summary,
                        "measurement_note": "Google Trends values are normalized relative search interest, not total searches.",
                    },
                    status=status,
                    notes=_notes_for_timeframe(timeframe, provider, anchor_term),
                )
                snapshot_id = snapshot["id"]
            snapshot_ids_by_timeframe[timeframe.timeframe] = snapshot_id
            for row in rows:
                row["snapshot_id"] = snapshot_id
            inserted_rows = repository.insert_trend_source_rows(rows)
            total_inserted_rows += len(inserted_rows)

            if append_to_snapshot_id is not None:
                final_count = len(existing_reference_ids) + len(rows)
                repository.update_trend_snapshot_status(
                    append_to_snapshot_id,
                    _snapshot_status_for_count(final_count),
                    f"Append/fill attempted {len(rows)} missing row(s); final row count={final_count}.",
                )

        if snapshot_id is not None:
            for normalized_score in normalized_scores:
                normalized_score["snapshot_id"] = snapshot_id

        final_snapshot_row_count = len(existing_reference_ids) + len(rows) if append_to_snapshot_id is not None else len(rows)
        timeframe_results.append(
            {
                "timeframe": timeframe.timeframe,
                "window_role": timeframe.window_role,
                "status": status,
                "snapshot_id": snapshot_id,
                "source_rows": len(rows),
                "normalized_timeframe_scores": len(normalized_scores),
                "inserted_source_rows": len(inserted_rows),
                "batches_planned": timeframe_result["batches_planned"],
                "batches_attempted": timeframe_result["batches_attempted"],
                "batches_succeeded": timeframe_result["batches_succeeded"],
                "batches_failed": timeframe_result["batches_failed"],
                "rate_limited_batches": timeframe_result["rate_limited_batches"],
                "stopped_early": timeframe_result["stopped_early"],
                "stop_reason": timeframe_result["stop_reason"],
                "failed_query_sample": timeframe_result["failed_query_sample"],
                "existing_rows_skipped": len(existing_reference_ids) if append_to_snapshot_id is not None else 0,
                "missing_rows_attempted": len(selected_references) if append_to_snapshot_id is not None else len(rows),
                "final_snapshot_row_count": final_snapshot_row_count,
                "missing_pokemon_sample": _missing_pokemon_sample(
                    all_references,
                    existing_reference_ids.union({row.get("pokemon_reference_id") for row in rows}),
                )
                if append_to_snapshot_id is not None
                else [],
                "normalization_summary": normalization_summary,
                "top_relative_search_interest": _top_timeframe_scores(normalized_scores),
            }
        )
        if timeframe_result.get("stop_reason") == "rate_limited_gracefully":
            logger.warning("Stopping Google Trends run after graceful rate-limit stop in timeframe=%s.", timeframe.timeframe)
            break

    derived_scores, derived_summary = calculate_derived_trend_scores(normalized_by_timeframe)
    inserted_scores = []
    if not dry_run and derived_scores and append_to_snapshot_id is None:
        inserted_scores = repository.insert_trend_scores(derived_scores)

    diagnostics = build_trend_diagnostics(
        source_rows_by_timeframe=source_rows_by_timeframe,
        normalized_by_timeframe=normalized_by_timeframe,
        derived_scores=derived_scores,
    )
    diagnostics.update(
        {
            "existing_rows_skipped": len(existing_reference_ids) if append_to_snapshot_id is not None else 0,
            "missing_rows_attempted": len(selected_references) if append_to_snapshot_id is not None else len(selected_references),
            "inserted_rows": total_inserted_rows,
            "failed_batches": sum(result.get("batches_failed", 0) for result in timeframe_results),
            "rate_limited_batches": sum(result.get("rate_limited_batches", 0) for result in timeframe_results),
            "final_snapshot_row_count": timeframe_results[-1]["final_snapshot_row_count"] if timeframe_results else None,
            "missing_pokemon_sample": timeframe_results[-1]["missing_pokemon_sample"] if timeframe_results else [],
        }
    )

    provider_note = None
    if isinstance(provider, FixtureGoogleTrendsProvider):
        provider_note = "Fixture diagnostic provider used; output validates flow but is not live Google Trends data."

    return {
        "source": SOURCE_NAME,
        "provider": provider.provider_name,
        "provider_note": provider_note,
        "status": _overall_status(timeframe_results, derived_scores, append_to_snapshot_id=append_to_snapshot_id),
        "dry_run": dry_run,
        "mode": "append_to_snapshot" if append_to_snapshot_id is not None else "capture_new_snapshot",
        "append_to_snapshot_id": append_to_snapshot_id,
        "geo": geo,
        "query_type": query_type,
        "anchor_term": anchor_term,
        "selection": _selection_payload(
            offset=offset,
            limit=limit,
            pokedex_start=pokedex_start,
            pokedex_end=pokedex_end,
            generation=generation,
        ),
        "pokemon_reference_rows_available": len(all_references),
        "pokemon_processed": len(selected_references),
        "timeframes_requested": [timeframe.timeframe for timeframe in timeframes],
        "timeframes_processed": [result["timeframe"] for result in timeframe_results],
        "rate_limited_batches": sum(result.get("rate_limited_batches", 0) for result in timeframe_results),
        "snapshot_ids_by_timeframe": snapshot_ids_by_timeframe,
        "timeframe_results": timeframe_results,
        "derived_summary": derived_summary,
        "derived_scores_count": len(derived_scores),
        "inserted_trend_scores": len(inserted_scores),
        "search_popularity_score_preview": _top_derived_scores(derived_scores, "search_popularity_score"),
        "recent_trend_score_preview": _top_derived_scores(derived_scores, "recent_trend_score"),
        "trend_momentum_score_preview": _top_derived_scores(derived_scores, "trend_momentum_score"),
        "diagnostics": diagnostics,
        "guardrails": _guardrails(),
    }


def derive_from_existing_snapshots(
    *,
    repository: PokemonDesirabilityRepository,
    dry_run: bool,
    source_name: str,
    provider_name: Optional[str],
    geo: str,
) -> Dict[str, Any]:
    requested_timeframes = [*DERIVE_REQUIRED_TIMEFRAMES, *DERIVE_OPTIONAL_TIMEFRAMES]
    snapshots_by_timeframe = repository.list_latest_usable_trend_snapshots(
        source_name=source_name,
        provider_name=provider_name,
        geo=geo,
        timeframes=requested_timeframes,
    )
    missing_required = [timeframe for timeframe in DERIVE_REQUIRED_TIMEFRAMES if timeframe not in snapshots_by_timeframe]
    if missing_required:
        return {
            "source": source_name,
            "provider": provider_name,
            "status": "missing_required_snapshots",
            "dry_run": dry_run,
            "missing_required_timeframes": missing_required,
            "available_timeframes": sorted(snapshots_by_timeframe),
            "guardrails": _guardrails(),
        }

    source_rows_by_timeframe: Dict[str, List[Dict[str, Any]]] = {}
    normalized_by_timeframe: Dict[str, List[Dict[str, Any]]] = {}
    normalization_summaries: Dict[str, Dict[str, Any]] = {}
    for timeframe, snapshot in snapshots_by_timeframe.items():
        rows = repository.list_trend_source_rows_for_snapshot(snapshot["id"])
        source_rows_by_timeframe[timeframe] = rows
        normalized_rows, summary = normalize_timeframe_rows(rows)
        normalized_by_timeframe[timeframe] = normalized_rows
        normalization_summaries[timeframe] = summary

    derived_scores, derived_summary = calculate_derived_trend_scores(normalized_by_timeframe)
    existing_keys = repository.list_trend_score_keys(scoring_version=TREND_SCORING_VERSION)
    scores_to_insert = [
        score
        for score in derived_scores
        if _derived_score_key(score) not in existing_keys
    ]
    inserted_scores = [] if dry_run else repository.insert_trend_scores(scores_to_insert)
    diagnostics = build_trend_diagnostics(
        source_rows_by_timeframe=source_rows_by_timeframe,
        normalized_by_timeframe=normalized_by_timeframe,
        derived_scores=derived_scores,
    )
    counts_by_score_name = _counts_by(derived_scores, "score_name")
    insert_counts_by_score_name = _counts_by(scores_to_insert, "score_name")

    return {
        "source": source_name,
        "provider": provider_name,
        "status": "dry_run" if dry_run else "derived_scores_inserted",
        "dry_run": dry_run,
        "mode": "derive_from_existing",
        "geo": geo,
        "snapshots_by_timeframe": snapshots_by_timeframe,
        "normalization_summaries": normalization_summaries,
        "derived_summary": derived_summary,
        "derived_scores_count": len(derived_scores),
        "scores_to_insert": len(scores_to_insert),
        "inserted_trend_scores": len(inserted_scores),
        "counts_by_score_name": counts_by_score_name,
        "insert_counts_by_score_name": insert_counts_by_score_name,
        "duplicates_skipped": len(derived_scores) - len(scores_to_insert),
        "diagnostics": diagnostics,
        "guardrails": _guardrails(),
    }


def _validate_args(args: argparse.Namespace, timeframes: List[TrendTimeframe]) -> Optional[str]:
    if args.append_to_snapshot_id is not None and args.derive_from_existing:
        return "--append-to-snapshot-id and --derive-from-existing cannot be combined."
    if args.append_to_snapshot_id is not None and len(timeframes) != 1:
        return "--append-to-snapshot-id requires exactly one --timeframe."
    return None


def _parse_timeframes(raw_timeframes: Optional[List[List[str]]]) -> List[TrendTimeframe]:
    if not raw_timeframes:
        return list(DEFAULT_TIMEFRAMES)

    role_by_timeframe = {timeframe.timeframe: timeframe.window_role for timeframe in DEFAULT_TIMEFRAMES}
    label_by_timeframe = {timeframe.timeframe: timeframe.label for timeframe in DEFAULT_TIMEFRAMES}
    parsed: List[TrendTimeframe] = []
    for today_token, window_token in raw_timeframes:
        timeframe = f"{today_token} {window_token}".strip()
        parsed.append(
            TrendTimeframe(
                timeframe=timeframe,
                window_role=role_by_timeframe.get(timeframe, "validation"),
                label=label_by_timeframe.get(timeframe, "Custom validation window"),
            )
        )
    return parsed


def _select_references(
    references: List[Dict[str, Any]],
    *,
    offset: int,
    limit: Optional[int],
    pokedex_start: Optional[int],
    pokedex_end: Optional[int],
    generation: Optional[int],
) -> List[Dict[str, Any]]:
    if offset < 0:
        raise ValueError("--offset must be >= 0")
    if limit is not None and limit < 0:
        raise ValueError("--limit must be >= 0")
    if pokedex_start is not None and pokedex_end is not None and pokedex_start > pokedex_end:
        raise ValueError("--pokedex-start must be <= --pokedex-end")

    selected = sorted(references, key=lambda row: _as_int(row.get("pokedex_number")) or 0)
    if pokedex_start is not None:
        selected = [row for row in selected if (_as_int(row.get("pokedex_number")) or -1) >= pokedex_start]
    if pokedex_end is not None:
        selected = [row for row in selected if (_as_int(row.get("pokedex_number")) or 10**9) <= pokedex_end]
    if generation is not None:
        selected = [row for row in selected if _reference_generation(row) == generation]
    if offset:
        selected = selected[offset:]
    if limit is not None:
        selected = selected[:limit]
    return selected


def _selection_payload(
    *,
    offset: int,
    limit: Optional[int],
    pokedex_start: Optional[int],
    pokedex_end: Optional[int],
    generation: Optional[int],
) -> Dict[str, Any]:
    return {
        "offset": offset,
        "limit": limit,
        "pokedex_start": pokedex_start,
        "pokedex_end": pokedex_end,
        "generation": generation,
        "production_note": (
            "For live pytrends production, prefer small Pokedex ranges or one generation/timeframe per job; "
            "a full 1025-Pokemon multi-timeframe run is not recommended."
        ),
    }


def _reference_generation(row: Dict[str, Any]) -> Optional[int]:
    explicit_generation = _as_int(row.get("generation"))
    if explicit_generation is not None:
        return explicit_generation
    pokedex_number = _as_int(row.get("pokedex_number"))
    return generation_for_pokedex_number(pokedex_number) if pokedex_number is not None else None


def _timeframe_status(
    timeframe_result: Dict[str, Any],
    rows: List[Dict[str, Any]],
    normalized_scores: List[Dict[str, Any]],
) -> str:
    if timeframe_result.get("stop_reason") == "rate_limited_gracefully":
        return "rate_limited_gracefully"
    if timeframe_result["batches_failed"] and timeframe_result["batches_succeeded"]:
        return "captured_partial"
    if timeframe_result["batches_failed"] and not timeframe_result["batches_succeeded"]:
        return "failed"
    return "captured_relative_search_interest" if rows and normalized_scores else "insufficient_data"


def _snapshot_status_for_count(row_count: int) -> str:
    return "captured_relative_search_interest" if row_count >= COMPLETE_REFERENCE_COUNT else "captured_partial"


def _compact_timeframe_result(timeframe_result: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "timeframe": timeframe_result.get("timeframe"),
        "window_role": timeframe_result.get("window_role"),
        "batches_planned": timeframe_result.get("batches_planned"),
        "batches_attempted": timeframe_result.get("batches_attempted"),
        "batches_succeeded": timeframe_result.get("batches_succeeded"),
        "batches_failed": timeframe_result.get("batches_failed"),
        "rate_limited_batches": timeframe_result.get("rate_limited_batches"),
        "stopped_early": timeframe_result.get("stopped_early"),
        "stop_reason": timeframe_result.get("stop_reason"),
        "failed_query_sample": timeframe_result.get("failed_query_sample"),
        "source_rows": len(timeframe_result.get("rows") or []),
        "batch_reports_sample": (timeframe_result.get("batch_reports") or [])[:10],
    }


def _notes_for_timeframe(timeframe: TrendTimeframe, provider: GoogleTrendsProvider, anchor_term: str) -> str:
    return (
        f"{timeframe.label}. Values are Google Trends relative search interest for Pokemon name search terms, "
        f"anchor-normalized to {anchor_term}; provider={provider.provider_name}."
    )


def _overall_status(
    timeframe_results: List[Dict[str, Any]],
    derived_scores: List[Dict[str, Any]],
    *,
    append_to_snapshot_id: Optional[int] = None,
) -> str:
    if any(result["status"] == "rate_limited_gracefully" for result in timeframe_results):
        return "rate_limited_gracefully"
    if append_to_snapshot_id is not None:
        final_count = timeframe_results[-1].get("final_snapshot_row_count", 0) if timeframe_results else 0
        return _snapshot_status_for_count(int(final_count or 0))
    if derived_scores:
        if any(result["status"] in {"failed", "captured_partial"} for result in timeframe_results):
            return "captured_partial_with_derived_relative_search_interest_scores"
        return "captured_derived_relative_search_interest_scores"
    if any(result["status"] == "failed" for result in timeframe_results):
        return "failed_gracefully"
    return "insufficient_data"


def _missing_pokemon_sample(
    references: Iterable[Dict[str, Any]],
    present_reference_ids: set[Any],
    limit: int = 25,
) -> List[Dict[str, Any]]:
    missing: List[Dict[str, Any]] = []
    for reference in sorted(references, key=lambda row: _as_int(row.get("pokedex_number")) or 0):
        if reference.get("id") in present_reference_ids:
            continue
        missing.append(
            {
                "pokemon_reference_id": reference.get("id"),
                "pokedex_number": reference.get("pokedex_number"),
                "pokemon_name": reference.get("display_name") or reference.get("canonical_name"),
            }
        )
        if len(missing) >= limit:
            break
    return missing


def _derived_score_key(score: Dict[str, Any]) -> tuple[Any, str, str, tuple[Any, ...]]:
    return (
        score.get("pokemon_reference_id"),
        str(score.get("score_name")),
        str(score.get("scoring_version")),
        tuple(score.get("contributing_snapshot_ids") or []),
    )


def _counts_by(rows: Iterable[Dict[str, Any]], key: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return counts


def _top_timeframe_scores(rows: List[Dict[str, Any]], limit: int = 10) -> List[Dict[str, Any]]:
    return [
        {
            "pokemon_name": row.get("pokemon_name"),
            "query_term": row.get("query_term"),
            "relative_search_interest_score": row.get("normalized_relative_search_interest_score"),
            "rank": row.get("normalized_rank"),
            "confidence": row.get("confidence"),
        }
        for row in rows[:limit]
    ]


def _top_derived_scores(rows: List[Dict[str, Any]], score_name: str, limit: int = 10) -> List[Dict[str, Any]]:
    return [
        {
            "pokemon_name": row.get("pokemon_name"),
            "query_term": row.get("query_term"),
            "relative_search_interest_score": row.get("score_value"),
            "rank": row.get("normalized_rank"),
            "confidence": row.get("confidence"),
            "components": row.get("score_components"),
        }
        for row in rows
        if row.get("score_name") == score_name
    ][:limit]


def _guardrails() -> Dict[str, Any]:
    return {
        "input_scope": "pokemon_reference canonical Pokemon names only; no individual card names queried.",
        "measurement_note": "Google Trends values are relative search interest, not absolute total search volume.",
        "not_modified": [
            "favoritepokemon scores",
            "RIP Score",
            "Opening Experience",
            "frontend UI",
            "simulation logic",
            "card-hit desirability mapping",
        ],
    }


def _as_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, set):
        return sorted(_jsonable(item) for item in value)
    return value


if __name__ == "__main__":
    raise SystemExit(main())
