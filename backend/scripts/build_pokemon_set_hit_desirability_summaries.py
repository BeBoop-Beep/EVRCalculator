from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.desirability.composite import COMPOSITE_SCORING_VERSION  # noqa: E402
from backend.scripts.build_pokemon_card_desirability_links import (  # noqa: E402
    DEFAULT_HIT_POLICY_VERSION,
)
from backend.scripts.run_pokemon_set_scrape import (  # noqa: E402
    build_valid_set_key_registry,
    normalize_set_key_filter,
)


logger = logging.getLogger(__name__)


SUMMARY_TABLE = "pokemon_set_hit_desirability_summaries"
LINK_TABLE = "pokemon_card_desirability_links"
DEFAULT_AGGREGATION_VERSION = "pokemon_set_hit_desirability_v1"
FALLBACK_MATCH_METHOD = "normalized_name_fallback"
UPSERT_BATCH_SIZE = 250


class PokemonSetHitDesirabilitySummariesError(RuntimeError):
    pass


class PokemonSetHitDesirabilitySummariesRepository:
    def __init__(self, client: Optional[Any] = None):
        if client is None:
            from backend.db.clients.supabase_client import supabase

            client = supabase
        self.client = client

    def list_sets(self, *, set_key: Optional[str]) -> List[Dict[str, Any]]:
        query = self.client.table("sets").select("id,name,canonical_key").order("name")
        if set_key:
            query = query.eq("canonical_key", set_key)
        response = query.execute()
        return list(response.data or [])

    def list_pokemon_references(self) -> List[Dict[str, Any]]:
        return _paged_select(
            self.client.table("pokemon_reference")
            .select("id,pokedex_number,canonical_name,display_name")
            .order("pokedex_number")
        )

    def list_composite_scores(self, *, scoring_version: str) -> List[Dict[str, Any]]:
        return _paged_select(
            self.client.table("pokemon_desirability_composite_scores")
            .select(
                "id,pokemon_reference_id,pokedex_number,pokemon_name,"
                "fan_popularity_snapshot_id,current_trend_snapshot_id,"
                "desirability_score,desirability_rank,desirability_tier,"
                "scoring_version,created_at,updated_at"
            )
            .eq("scoring_version", scoring_version)
        )

    def list_canonical_cards(self, set_ids: Sequence[str]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for chunk in _chunked(list(set_ids), 200):
            rows.extend(
                _paged_select(
                    self.client.table("pokemon_canonical_cards")
                    .select(
                        "id,set_id,name,supertype,subtypes,rarity,number,printed_number,"
                        "image_small_url,image_large_url"
                    )
                    .in_("set_id", list(chunk))
                    .order("number")
                    .order("name")
                )
            )
        return rows

    def list_hit_links(
        self,
        *,
        card_ids: Sequence[str],
        hit_policy_version: str,
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for chunk in _chunked(list(card_ids), 200):
            rows.extend(
                _paged_select(
                    self.client.table(LINK_TABLE)
                    .select(
                        "id,pokemon_canonical_card_id,pokemon_reference_id,pokedex_number,"
                        "link_position,link_count,contribution_weight,match_method,"
                        "match_confidence,is_hit_eligible,hit_policy_version,source,notes"
                    )
                    .in_("pokemon_canonical_card_id", list(chunk))
                    .eq("is_hit_eligible", True)
                    .eq("hit_policy_version", hit_policy_version)
                )
            )
        return rows

    def list_existing_summaries(
        self,
        *,
        set_ids: Sequence[str],
        aggregation_version: str,
        hit_policy_version: str,
        composite_scoring_version: str,
        fan_popularity_snapshot_id: Any,
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for chunk in _chunked(list(set_ids), 200):
            rows.extend(
                _paged_select(
                    self.client.table(SUMMARY_TABLE)
                    .select(
                        "id,set_id,aggregation_version,hit_policy_version,"
                        "composite_scoring_version,fan_popularity_snapshot_id"
                    )
                    .in_("set_id", list(chunk))
                    .eq("aggregation_version", aggregation_version)
                    .eq("hit_policy_version", hit_policy_version)
                    .eq("composite_scoring_version", composite_scoring_version)
                    .eq("fan_popularity_snapshot_id", fan_popularity_snapshot_id)
                )
            )
        return rows

    def upsert_summaries(self, rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        written: List[Dict[str, Any]] = []
        if not rows:
            return written
        on_conflict = (
            "set_id,aggregation_version,hit_policy_version,"
            "composite_scoring_version,fan_popularity_snapshot_id"
        )
        for chunk in _chunked(list(rows), UPSERT_BATCH_SIZE):
            response = (
                self.client.table(SUMMARY_TABLE)
                .upsert(list(chunk), on_conflict=on_conflict)
                .execute()
            )
            written.extend(response.data or [])
        return written


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build materialized Pokemon set hit-card desirability summaries."
    )
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument("--set-key", help="sets.canonical_key to process")
    selector.add_argument("--all", action="store_true", help="Process all sets")

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--dry-run", action="store_true", help="Preview without writing summaries")
    mode_group.add_argument("--commit", action="store_true", help="Write summaries to Supabase")

    parser.add_argument("--aggregation-version", default=DEFAULT_AGGREGATION_VERSION)
    parser.add_argument("--hit-policy-version", default=DEFAULT_HIT_POLICY_VERSION)
    parser.add_argument("--composite-scoring-version", default=COMPOSITE_SCORING_VERSION)
    parser.add_argument("--min-composite-coverage", type=float, default=0.95)
    parser.add_argument("--log-level", default="INFO")
    return parser


def load_backend_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(env_path, override=False)


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    load_backend_env()

    dry_run = not args.commit
    if args.dry_run:
        dry_run = True

    repository = PokemonSetHitDesirabilitySummariesRepository()
    report = build_set_hit_desirability_summaries_report(
        repository=repository,
        set_key=args.set_key,
        process_all=bool(args.all or not args.set_key),
        aggregation_version=args.aggregation_version,
        hit_policy_version=args.hit_policy_version,
        composite_scoring_version=args.composite_scoring_version,
        min_composite_coverage=args.min_composite_coverage,
        dry_run=dry_run,
    )
    print(json.dumps(_jsonable(report), indent=2, sort_keys=True))
    return 0 if report.get("status") in {"dry_run", "committed"} else 1


def build_set_hit_desirability_summaries_report(
    *,
    repository: Any,
    set_key: Optional[str],
    process_all: bool,
    aggregation_version: str,
    hit_policy_version: str,
    composite_scoring_version: str,
    min_composite_coverage: float,
    dry_run: bool,
) -> Dict[str, Any]:
    if not set_key and not process_all:
        process_all = True

    registry = build_valid_set_key_registry()
    set_resolution = normalize_set_key_filter(set_key, registry) if set_key else None
    resolved_set_key = set_resolution.get("resolved_set_key_filter") if set_resolution else None
    if set_key and not resolved_set_key:
        raise PokemonSetHitDesirabilitySummariesError(f"Unknown set key {set_key!r}")

    references = repository.list_pokemon_references()
    reference_count = len({row.get("id") for row in references if row.get("id") is not None})
    composite_rows = repository.list_composite_scores(scoring_version=composite_scoring_version)
    selection = select_latest_complete_composite_score_group(
        composite_rows=composite_rows,
        reference_count=reference_count,
        scoring_version=composite_scoring_version,
        min_coverage=min_composite_coverage,
    )
    if selection is None:
        candidates = describe_composite_score_groups(
            composite_rows=composite_rows,
            reference_count=reference_count,
            scoring_version=composite_scoring_version,
        )
        return {
            "status": "missing_acceptable_composite_score_group",
            "dry_run": dry_run,
            "requested_set_key": set_key,
            "resolved_set_key": resolved_set_key,
            "aggregation_version": aggregation_version,
            "hit_policy_version": hit_policy_version,
            "composite_scoring_version": composite_scoring_version,
            "min_composite_coverage": min_composite_coverage,
            "reference_count": reference_count,
            "candidate_composite_groups": candidates,
        }

    sets = repository.list_sets(set_key=resolved_set_key)
    if not sets:
        return {
            "status": "no_sets_found",
            "dry_run": dry_run,
            "requested_set_key": set_key,
            "resolved_set_key": resolved_set_key,
            "aggregation_version": aggregation_version,
            "hit_policy_version": hit_policy_version,
            "composite_scoring_version": composite_scoring_version,
            "selected_composite_group": selection["metadata"],
        }

    set_by_id = {str(row.get("id")): row for row in sets if row.get("id") is not None}
    cards = repository.list_canonical_cards(sorted(set_by_id.keys()))
    for card in cards:
        set_row = set_by_id.get(str(card.get("set_id"))) or {}
        card["set_name"] = set_row.get("name")
        card["set_canonical_key"] = set_row.get("canonical_key")

    card_ids = [str(row.get("id")) for row in cards if row.get("id") is not None]
    links = repository.list_hit_links(card_ids=card_ids, hit_policy_version=hit_policy_version)
    summaries = build_summary_rows(
        sets=sets,
        cards=cards,
        links=links,
        composite_scores=selection["rows"],
        aggregation_version=aggregation_version,
        hit_policy_version=hit_policy_version,
        composite_scoring_version=composite_scoring_version,
        composite_metadata=selection["metadata"],
    )

    summary_set_ids = [str(row["set_id"]) for row in summaries]
    existing_rows = repository.list_existing_summaries(
        set_ids=summary_set_ids,
        aggregation_version=aggregation_version,
        hit_policy_version=hit_policy_version,
        composite_scoring_version=composite_scoring_version,
        fan_popularity_snapshot_id=selection["metadata"].get("fan_popularity_snapshot_id"),
    ) if summaries else []
    existing_set_ids = {str(row.get("set_id")) for row in existing_rows if row.get("set_id") is not None}
    insert_count = len([row for row in summaries if str(row.get("set_id")) not in existing_set_ids])
    update_count = len([row for row in summaries if str(row.get("set_id")) in existing_set_ids])

    written_rows: List[Dict[str, Any]] = []
    if not dry_run and summaries:
        written_rows = repository.upsert_summaries(summaries)

    ranked_by_average = _top_sets_by_metric(summaries, "weighted_average_hit_desirability_score", limit=10)
    ranked_by_concentration = _top_sets_by_metric(
        summaries,
        "desirability_concentration_top_1_share",
        limit=10,
    )
    sets_with_missing_scores = [
        {
            "set_id": row.get("set_id"),
            "set_name": row.get("set_name"),
            "set_canonical_key": row.get("set_canonical_key"),
            "missing_score_count": row.get("missing_score_count"),
        }
        for row in summaries
        if int(row.get("missing_score_count") or 0) > 0
    ][:25]

    return {
        "status": "dry_run" if dry_run else "committed",
        "dry_run": dry_run,
        "requested_set_key": set_key,
        "resolved_set_key": resolved_set_key,
        "sets_loaded": len(sets),
        "sets_with_summaries": len(summaries),
        "links_loaded": len(links),
        "aggregation_version": aggregation_version,
        "hit_policy_version": hit_policy_version,
        "composite_scoring_version": composite_scoring_version,
        "selected_composite_group": selection["metadata"],
        "diagnostics": {
            "reference_count": reference_count,
            "canonical_cards_loaded": len(cards),
            "hit_eligible_links_loaded": len(links),
            "summary_rows_generated": len(summaries),
            "summary_rows_inserted": 0 if dry_run else insert_count,
            "summary_rows_updated": 0 if dry_run else update_count,
            "written_rows_returned": len(written_rows),
            "sets_with_missing_scores": len(sets_with_missing_scores),
            "fallback_link_count": sum(int(row.get("fallback_link_count") or 0) for row in summaries),
            "multi_pokemon_card_count": sum(int(row.get("multi_pokemon_card_count") or 0) for row in summaries),
        },
        "top_10_sets_by_weighted_average_hit_desirability": ranked_by_average,
        "sets_with_highest_concentration": ranked_by_concentration,
        "sets_with_missing_scores": sets_with_missing_scores,
    }


def select_latest_complete_composite_score_group(
    *,
    composite_rows: Sequence[Dict[str, Any]],
    reference_count: int,
    scoring_version: str,
    min_coverage: float,
) -> Optional[Dict[str, Any]]:
    candidates = describe_composite_score_groups(
        composite_rows=composite_rows,
        reference_count=reference_count,
        scoring_version=scoring_version,
        include_rows=True,
    )
    acceptable = [row for row in candidates if float(row.get("coverage_ratio") or 0.0) >= min_coverage]
    if not acceptable:
        return None

    selected = sorted(
        acceptable,
        key=lambda row: (
            _timestamp_sort_value(row.get("latest_row_timestamp")),
            _int_sort_value(row.get("fan_popularity_snapshot_id")),
            int(row.get("score_row_count") or 0),
        ),
        reverse=True,
    )[0]
    rows = selected.pop("_rows")
    return {"rows": rows, "metadata": selected}


def describe_composite_score_groups(
    *,
    composite_rows: Sequence[Dict[str, Any]],
    reference_count: int,
    scoring_version: str,
    include_rows: bool = False,
) -> List[Dict[str, Any]]:
    groups: Dict[Tuple[Any, str], List[Dict[str, Any]]] = defaultdict(list)
    for row in composite_rows:
        if str(row.get("scoring_version") or "") != scoring_version:
            continue
        groups[(row.get("fan_popularity_snapshot_id"), str(row.get("scoring_version")))].append(row)

    candidates: List[Dict[str, Any]] = []
    for (fan_snapshot_id, group_scoring_version), rows in groups.items():
        reference_ids = {
            row.get("pokemon_reference_id")
            for row in rows
            if row.get("pokemon_reference_id") is not None
        }
        trend_snapshot_ids = sorted(
            {
                int(row.get("current_trend_snapshot_id"))
                for row in rows
                if _as_int(row.get("current_trend_snapshot_id")) is not None
            }
        )
        latest_timestamp = max((_timestamp_text(row) for row in rows), default=None)
        candidate = {
            "fan_popularity_snapshot_id": fan_snapshot_id,
            "scoring_version": group_scoring_version,
            "score_row_count": len(reference_ids),
            "raw_row_count": len(rows),
            "coverage_ratio": round(len(reference_ids) / reference_count, 8) if reference_count > 0 else 0.0,
            "current_trend_snapshot_ids": trend_snapshot_ids,
            "latest_row_timestamp": latest_timestamp,
        }
        if include_rows:
            candidate["_rows"] = list(rows)
        candidates.append(candidate)

    return sorted(
        candidates,
        key=lambda row: (
            _timestamp_sort_value(row.get("latest_row_timestamp")),
            _int_sort_value(row.get("fan_popularity_snapshot_id")),
            int(row.get("score_row_count") or 0),
        ),
        reverse=True,
    )


def build_summary_rows(
    *,
    sets: Sequence[Dict[str, Any]],
    cards: Sequence[Dict[str, Any]],
    links: Sequence[Dict[str, Any]],
    composite_scores: Sequence[Dict[str, Any]],
    aggregation_version: str,
    hit_policy_version: str,
    composite_scoring_version: str,
    composite_metadata: Dict[str, Any],
) -> List[Dict[str, Any]]:
    cards_by_id = {str(card.get("id")): card for card in cards if card.get("id") is not None}
    links_by_set: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for link in links:
        card = cards_by_id.get(str(link.get("pokemon_canonical_card_id")))
        if not card:
            continue
        links_by_set[str(card.get("set_id"))].append(link)

    scores_by_reference = {
        int(row["pokemon_reference_id"]): row
        for row in composite_scores
        if row.get("pokemon_reference_id") is not None
    }

    built_at = datetime.now(timezone.utc).isoformat()
    rows: List[Dict[str, Any]] = []
    for set_row in sets:
        set_id = str(set_row.get("id") or "")
        if not set_id:
            continue
        set_links = links_by_set.get(set_id, [])
        if not set_links:
            continue
        rows.append(
            build_set_summary_row(
                set_row=set_row,
                links=set_links,
                cards_by_id=cards_by_id,
                scores_by_reference=scores_by_reference,
                aggregation_version=aggregation_version,
                hit_policy_version=hit_policy_version,
                composite_scoring_version=composite_scoring_version,
                composite_metadata=composite_metadata,
                built_at=built_at,
            )
        )
    return rows


def build_set_summary_row(
    *,
    set_row: Dict[str, Any],
    links: Sequence[Dict[str, Any]],
    cards_by_id: Dict[str, Dict[str, Any]],
    scores_by_reference: Dict[int, Dict[str, Any]],
    aggregation_version: str,
    hit_policy_version: str,
    composite_scoring_version: str,
    composite_metadata: Dict[str, Any],
    built_at: str,
) -> Dict[str, Any]:
    hit_card_ids = {
        str(link.get("pokemon_canonical_card_id"))
        for link in links
        if link.get("pokemon_canonical_card_id") is not None
    }
    unique_reference_ids = {
        int(link.get("pokemon_reference_id"))
        for link in links
        if link.get("pokemon_reference_id") is not None
    }
    fallback_links = [
        link for link in links if str(link.get("match_method") or "") == FALLBACK_MATCH_METHOD
    ]
    multi_pokemon_card_ids = {
        str(link.get("pokemon_canonical_card_id"))
        for link in links
        if int(_as_float(link.get("link_count")) or 0) > 1
    }

    scored_links: List[Dict[str, Any]] = []
    missing_links: List[Dict[str, Any]] = []
    card_scores: Dict[str, float] = defaultdict(float)
    card_scored_weight: Dict[str, float] = defaultdict(float)
    card_link_details: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    pokemon_rollup: Dict[int, Dict[str, Any]] = {}

    for link in links:
        card_id = str(link.get("pokemon_canonical_card_id") or "")
        reference_id = _as_int(link.get("pokemon_reference_id"))
        weight = _as_float(link.get("contribution_weight"))
        if reference_id is None or weight is None:
            missing_links.append(link)
            continue

        score_row = scores_by_reference.get(reference_id)
        score = _as_float((score_row or {}).get("desirability_score"))
        if score is None:
            missing_links.append(link)
            continue

        scored_links.append(link)
        weighted_score = score * weight
        card_scores[card_id] += weighted_score
        card_scored_weight[card_id] += weight
        card_link_details[card_id].append(
            {
                "pokemon_reference_id": reference_id,
                "pokedex_number": score_row.get("pokedex_number") or link.get("pokedex_number"),
                "pokemon_name": score_row.get("pokemon_name"),
                "desirability_score": _round_metric(score),
                "contribution_weight": _round_metric(weight, 8),
                "weighted_score": _round_metric(weighted_score),
                "match_method": link.get("match_method"),
                "match_confidence": _round_metric(_as_float(link.get("match_confidence")), 8),
            }
        )

        rollup = pokemon_rollup.setdefault(
            reference_id,
            {
                "pokemon_reference_id": reference_id,
                "pokedex_number": score_row.get("pokedex_number") or link.get("pokedex_number"),
                "pokemon_name": score_row.get("pokemon_name"),
                "desirability_score": _round_metric(score),
                "appearance_weight": 0.0,
                "hit_card_ids": set(),
                "weighted_score_total": 0.0,
                "cards": [],
            },
        )
        rollup["appearance_weight"] += weight
        rollup["hit_card_ids"].add(card_id)
        rollup["weighted_score_total"] += weighted_score
        card = cards_by_id.get(card_id) or {}
        if len(rollup["cards"]) < 5:
            rollup["cards"].append(_card_json(card, card_score=None))

    scored_card_ids = {card_id for card_id, score in card_scores.items() if score is not None}
    card_score_values = sorted([score for score in card_scores.values() if score is not None], reverse=True)
    total_card_score = sum(card_score_values)
    scored_weight_sum = sum(_as_float(link.get("contribution_weight")) or 0.0 for link in scored_links)
    link_score_sum = 0.0
    weighted_score_sum = 0.0
    for link in scored_links:
        reference_id = _as_int(link.get("pokemon_reference_id"))
        score = _as_float((scores_by_reference.get(reference_id or -1) or {}).get("desirability_score"))
        weight = _as_float(link.get("contribution_weight")) or 0.0
        if score is not None:
            link_score_sum += score
            weighted_score_sum += score * weight

    weighted_average = (
        weighted_score_sum / scored_weight_sum
        if scored_weight_sum > 0
        else None
    )
    shares = [score / total_card_score for score in card_score_values if total_card_score > 0]
    hhi = sum(share * share for share in shares)

    missing_reference_ids = sorted(
        {
            int(link.get("pokemon_reference_id"))
            for link in missing_links
            if link.get("pokemon_reference_id") is not None
        }
    )
    fallback_confidences = [
        value for value in (_as_float(link.get("match_confidence")) for link in fallback_links) if value is not None
    ]
    missing_samples = [
        _missing_link_sample(link, cards_by_id.get(str(link.get("pokemon_canonical_card_id"))) or {})
        for link in missing_links[:25]
    ]

    top_cards = build_top_desirable_cards_json(
        card_scores=card_scores,
        cards_by_id=cards_by_id,
        card_link_details=card_link_details,
        all_links=links,
    )
    top_pokemon = build_top_desirable_pokemon_json(pokemon_rollup)

    warnings: List[str] = []
    if missing_links:
        warnings.append("One or more hit-eligible links are missing composite desirability scores.")
    if not scored_links:
        warnings.append("Set has hit-eligible links but no scored hit links.")

    return {
        "set_id": set_row.get("id"),
        "set_name": set_row.get("name"),
        "set_canonical_key": set_row.get("canonical_key"),
        "aggregation_version": aggregation_version,
        "hit_policy_version": hit_policy_version,
        "composite_scoring_version": composite_scoring_version,
        "fan_popularity_snapshot_id": composite_metadata.get("fan_popularity_snapshot_id"),
        "current_trend_snapshot_ids": composite_metadata.get("current_trend_snapshot_ids") or [],
        "composite_score_row_count": composite_metadata.get("score_row_count"),
        "composite_score_coverage_ratio": composite_metadata.get("coverage_ratio"),
        "built_at": built_at,
        "hit_eligible_card_count": len(hit_card_ids),
        "scored_hit_eligible_card_count": len(scored_card_ids),
        "linked_pokemon_count": len(links),
        "unique_linked_pokemon_count": len(unique_reference_ids),
        "scored_link_count": len(scored_links),
        "missing_score_count": len(missing_links),
        "fallback_link_count": len(fallback_links),
        "multi_pokemon_card_count": len(multi_pokemon_card_ids),
        "average_hit_desirability_score": _round_metric(link_score_sum / len(scored_links) if scored_links else None),
        "weighted_average_hit_desirability_score": _round_metric(weighted_average),
        "max_hit_desirability_score": _round_metric(card_score_values[0] if card_score_values else None),
        "top_3_hit_desirability_score": _round_metric(_average_top_n(card_score_values, 3)),
        "top_5_hit_desirability_score": _round_metric(_average_top_n(card_score_values, 5)),
        "desirability_concentration_top_1_share": _round_metric(
            card_score_values[0] / total_card_score if total_card_score > 0 and card_score_values else None,
            8,
        ),
        "desirability_concentration_top_3_share": _round_metric(
            sum(card_score_values[:3]) / total_card_score if total_card_score > 0 and card_score_values else None,
            8,
        ),
        "desirability_depth_score": _round_metric(sum(card_score_values[:10]) / 10 if card_score_values else None),
        "effective_desirable_card_count": _round_metric(1 / hhi if hhi > 0 else None),
        "top_desirable_pokemon_json": top_pokemon,
        "top_desirable_cards_json": top_cards,
        "missing_score_reference_ids_json": missing_reference_ids,
        "diagnostics_json": {
            "fallback_average_match_confidence": _round_metric(
                sum(fallback_confidences) / len(fallback_confidences) if fallback_confidences else None,
                8,
            ),
            "fallback_link_samples": [
                _missing_link_sample(link, cards_by_id.get(str(link.get("pokemon_canonical_card_id"))) or {})
                for link in fallback_links[:25]
            ],
            "missing_score_samples": missing_samples,
            "scored_weight_sum": _round_metric(scored_weight_sum, 8),
            "total_card_score": _round_metric(total_card_score),
        },
        "warnings_json": warnings,
        "updated_at": built_at,
    }


def build_top_desirable_cards_json(
    *,
    card_scores: Dict[str, float],
    cards_by_id: Dict[str, Dict[str, Any]],
    card_link_details: Dict[str, List[Dict[str, Any]]],
    all_links: Sequence[Dict[str, Any]],
    limit: int = 25,
) -> List[Dict[str, Any]]:
    links_by_card: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for link in all_links:
        links_by_card[str(link.get("pokemon_canonical_card_id"))].append(link)

    rows: List[Dict[str, Any]] = []
    for card_id, score in card_scores.items():
        card = cards_by_id.get(card_id) or {}
        card_links = links_by_card.get(card_id, [])
        rows.append(
            {
                **_card_json(card, card_score=score),
                "linked_pokemon": sorted(
                    card_link_details.get(card_id, []),
                    key=lambda item: item.get("weighted_score") or 0.0,
                    reverse=True,
                ),
                "match_methods": sorted(
                    {
                        str(link.get("match_method"))
                        for link in card_links
                        if link.get("match_method")
                    }
                ),
                "has_fallback_link": any(
                    str(link.get("match_method") or "") == FALLBACK_MATCH_METHOD
                    for link in card_links
                ),
            }
        )
    return sorted(
        rows,
        key=lambda row: (row.get("card_desirability_score") or 0.0, row.get("name") or ""),
        reverse=True,
    )[:limit]


def build_top_desirable_pokemon_json(
    pokemon_rollup: Dict[int, Dict[str, Any]],
    *,
    limit: int = 25,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for rollup in pokemon_rollup.values():
        rows.append(
            {
                "pokemon_reference_id": rollup.get("pokemon_reference_id"),
                "pokedex_number": rollup.get("pokedex_number"),
                "pokemon_name": rollup.get("pokemon_name"),
                "desirability_score": rollup.get("desirability_score"),
                "appearance_weight": _round_metric(rollup.get("appearance_weight"), 8),
                "hit_card_count": len(rollup.get("hit_card_ids") or []),
                "weighted_score_total": _round_metric(rollup.get("weighted_score_total")),
                "representative_cards": rollup.get("cards") or [],
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            row.get("weighted_score_total") or 0.0,
            row.get("desirability_score") or 0.0,
            row.get("hit_card_count") or 0,
        ),
        reverse=True,
    )[:limit]


def _card_json(card: Dict[str, Any], *, card_score: Optional[float]) -> Dict[str, Any]:
    payload = {
        "pokemon_canonical_card_id": card.get("id"),
        "name": card.get("name"),
        "number": card.get("number"),
        "printed_number": card.get("printed_number"),
        "rarity": card.get("rarity"),
        "image_small_url": card.get("image_small_url"),
        "image_large_url": card.get("image_large_url"),
    }
    if card_score is not None:
        payload["card_desirability_score"] = _round_metric(card_score)
    return payload


def _missing_link_sample(link: Dict[str, Any], card: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "pokemon_canonical_card_id": link.get("pokemon_canonical_card_id"),
        "pokemon_reference_id": link.get("pokemon_reference_id"),
        "pokedex_number": link.get("pokedex_number"),
        "card_name": card.get("name"),
        "number": card.get("number"),
        "rarity": card.get("rarity"),
        "match_method": link.get("match_method"),
        "match_confidence": link.get("match_confidence"),
    }


def _average_top_n(values: Sequence[float], n: int) -> Optional[float]:
    selected = list(values[:n])
    if not selected:
        return None
    return sum(selected) / len(selected)


def _top_sets_by_metric(rows: Sequence[Dict[str, Any]], metric: str, *, limit: int) -> List[Dict[str, Any]]:
    ranked = [row for row in rows if _as_float(row.get(metric)) is not None]
    return [
        {
            "set_id": row.get("set_id"),
            "set_name": row.get("set_name"),
            "set_canonical_key": row.get("set_canonical_key"),
            metric: row.get(metric),
            "hit_eligible_card_count": row.get("hit_eligible_card_count"),
            "missing_score_count": row.get("missing_score_count"),
        }
        for row in sorted(ranked, key=lambda item: _as_float(item.get(metric)) or 0.0, reverse=True)[:limit]
    ]


def _paged_select(query: Any, *, page_size: int = 1000) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    start = 0
    while True:
        response = query.range(start, start + page_size - 1).execute()
        page_rows = list(response.data or [])
        rows.extend(page_rows)
        if len(page_rows) < page_size:
            break
        start += page_size
    return rows


def _chunked(values: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for index in range(0, len(values), size):
        yield values[index:index + size]


def _round_metric(value: Any, digits: int = 4) -> Optional[float]:
    number = _as_float(value)
    if number is None:
        return None
    return round(number, digits)


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _int_sort_value(value: Any) -> int:
    parsed = _as_int(value)
    return parsed if parsed is not None else -1


def _timestamp_text(row: Dict[str, Any]) -> Optional[str]:
    return str(row.get("updated_at") or row.get("created_at") or "") or None


def _timestamp_sort_value(value: Any) -> str:
    return str(value or "")


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
    try:
        raise SystemExit(main())
    except PokemonSetHitDesirabilitySummariesError as exc:
        print(f"[pokemon-set-hit-desirability-summaries][ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
