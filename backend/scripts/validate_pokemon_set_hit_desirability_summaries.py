from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.desirability.composite import COMPOSITE_SCORING_VERSION  # noqa: E402
from backend.scripts.build_pokemon_card_desirability_links import DEFAULT_HIT_POLICY_VERSION  # noqa: E402
from backend.scripts.build_pokemon_set_hit_desirability_summaries import (  # noqa: E402
    DEFAULT_AGGREGATION_VERSION,
    SUMMARY_TABLE,
)
from backend.scripts.run_pokemon_set_scrape import (  # noqa: E402
    build_valid_set_key_registry,
    normalize_set_key_filter,
)


class PokemonSetHitDesirabilitySummariesValidationError(RuntimeError):
    pass


def load_backend_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(env_path, override=False)


def get_supabase_client():
    from backend.db.clients.supabase_client import supabase

    return supabase


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate Pokemon set hit-card desirability summaries."
    )
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument("--set-key", help="sets.canonical_key to validate")
    selector.add_argument("--all", action="store_true", help="Validate all sets")
    parser.add_argument("--aggregation-version", default=DEFAULT_AGGREGATION_VERSION)
    parser.add_argument("--hit-policy-version", default=DEFAULT_HIT_POLICY_VERSION)
    parser.add_argument("--composite-scoring-version", default=COMPOSITE_SCORING_VERSION)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    load_backend_env()
    report = validate_summaries(
        set_key=args.set_key,
        process_all=bool(args.all or not args.set_key),
        aggregation_version=args.aggregation_version,
        hit_policy_version=args.hit_policy_version,
        composite_scoring_version=args.composite_scoring_version,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if report["failure_summary"]["total_failures"] else 0


def validate_summaries(
    *,
    set_key: Optional[str],
    process_all: bool,
    aggregation_version: str,
    hit_policy_version: str,
    composite_scoring_version: str,
) -> Dict[str, Any]:
    if not set_key and not process_all:
        process_all = True

    client = get_supabase_client()
    registry = build_valid_set_key_registry()
    resolved_set_key = None
    if set_key:
        resolution = normalize_set_key_filter(set_key, registry)
        resolved_set_key = resolution.get("resolved_set_key_filter")
        if not resolved_set_key:
            raise PokemonSetHitDesirabilitySummariesValidationError(f"Unknown set key {set_key!r}")

    sets = _load_sets(client, resolved_set_key)
    set_by_id = {str(row.get("id")): row for row in sets if row.get("id") is not None}
    requested_set_ids = set(set_by_id.keys())
    all_links = _load_hit_links(client, hit_policy_version=hit_policy_version)
    linked_card_ids = sorted(
        {
            str(link.get("pokemon_canonical_card_id"))
            for link in all_links
            if link.get("pokemon_canonical_card_id") is not None
        }
    )
    cards = _load_cards_by_ids(client, linked_card_ids)
    card_by_id = {str(row.get("id")): row for row in cards if row.get("id") is not None}
    links = [
        link
        for link in all_links
        if str(
            (card_by_id.get(str(link.get("pokemon_canonical_card_id"))) or {}).get("set_id")
        )
        in requested_set_ids
    ]
    summaries = _load_summaries(
        client,
        sorted(set_by_id.keys()),
        aggregation_version=aggregation_version,
        hit_policy_version=hit_policy_version,
        composite_scoring_version=composite_scoring_version,
    )

    hit_set_ids = {
        str((card_by_id.get(str(link.get("pokemon_canonical_card_id"))) or {}).get("set_id"))
        for link in links
        if link.get("pokemon_canonical_card_id") is not None
    }
    hit_set_ids.discard("")
    summaries_by_set: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for summary in summaries:
        if summary.get("set_id") is not None:
            summaries_by_set[str(summary["set_id"])].append(summary)

    sets_with_hit_links_but_no_summary = [
        _set_sample(set_by_id.get(set_id) or {"id": set_id})
        for set_id in sorted(hit_set_ids)
        if not summaries_by_set.get(set_id)
    ]
    summary_rows_with_zero_hit_cards = [
        _summary_sample(row)
        for row in summaries
        if int(row.get("hit_eligible_card_count") or 0) <= 0
    ]
    summaries_missing_composite_metadata = [
        _summary_sample(row)
        for row in summaries
        if row.get("fan_popularity_snapshot_id") is None
        or row.get("composite_score_row_count") is None
        or row.get("composite_score_coverage_ratio") is None
        or not _is_json_array(row.get("current_trend_snapshot_ids"))
    ]
    summaries_with_missing_scores = [
        _summary_sample(row)
        for row in summaries
        if int(row.get("missing_score_count") or 0) > 0
    ]
    weighted_average_null_with_scored_links = [
        _summary_sample(row)
        for row in summaries
        if int(row.get("scored_link_count") or 0) > 0
        and _as_float(row.get("weighted_average_hit_desirability_score")) is None
    ]
    top_json_shape_issues = [
        _summary_sample(row)
        for row in summaries
        if not _is_json_array(row.get("top_desirable_cards_json"))
        or not _is_json_array(row.get("top_desirable_pokemon_json"))
    ]
    metric_bound_issues = [
        {**_summary_sample(row), "issues": _metric_bound_issues(row)}
        for row in summaries
        if _metric_bound_issues(row)
    ]

    summary_count_by_set = [
        {
            **_set_sample(set_by_id.get(set_id) or {"id": set_id}),
            "summary_count": count,
        }
        for set_id, count in sorted(Counter(str(row.get("set_id")) for row in summaries).items())
    ]

    failures = {
        "sets_with_hit_links_but_no_summary": len(sets_with_hit_links_but_no_summary),
        "summary_rows_with_zero_hit_cards": len(summary_rows_with_zero_hit_cards),
        "summaries_missing_composite_metadata": len(summaries_missing_composite_metadata),
        "summaries_with_missing_scores": len(summaries_with_missing_scores),
        "weighted_average_null_with_scored_links": len(weighted_average_null_with_scored_links),
        "top_json_shape_issues": len(top_json_shape_issues),
        "metric_bound_issues": len(metric_bound_issues),
    }
    failures["total_failures"] = sum(failures.values())

    return {
        "status": "validated",
        "requested_set_key": set_key,
        "resolved_set_key": resolved_set_key,
        "aggregation_version": aggregation_version,
        "hit_policy_version": hit_policy_version,
        "composite_scoring_version": composite_scoring_version,
        "summary": {
            "sets_checked": len(sets),
            "hit_eligible_links_checked": len(links),
            "sets_with_hit_eligible_links": len(hit_set_ids),
            "summary_rows_checked": len(summaries),
        },
        "failure_summary": failures,
        "samples": {
            "sets_with_hit_links_but_no_summary": sets_with_hit_links_but_no_summary[:50],
            "summary_rows_with_zero_hit_cards": summary_rows_with_zero_hit_cards[:50],
            "summaries_missing_composite_metadata": summaries_missing_composite_metadata[:50],
            "summaries_with_missing_scores": summaries_with_missing_scores[:50],
            "weighted_average_null_with_scored_links": weighted_average_null_with_scored_links[:50],
            "top_json_shape_issues": top_json_shape_issues[:50],
            "metric_bound_issues": metric_bound_issues[:50],
        },
        "summary_count_by_set": summary_count_by_set,
        "highest_weighted_average_sets": _rank_summaries(
            summaries,
            metric="weighted_average_hit_desirability_score",
            reverse=True,
            limit=10,
        ),
        "lowest_weighted_average_sets": _rank_summaries(
            summaries,
            metric="weighted_average_hit_desirability_score",
            reverse=False,
            limit=10,
        ),
        "highest_concentration_sets": _rank_summaries(
            summaries,
            metric="desirability_concentration_top_1_share",
            reverse=True,
            limit=10,
        ),
    }


def _load_sets(client: Any, set_key: Optional[str]) -> List[Dict[str, Any]]:
    query = client.table("sets").select("id,name,canonical_key").order("name")
    if set_key:
        query = query.eq("canonical_key", set_key)
    return _paged_select(query)


def _load_cards_by_ids(client: Any, card_ids: Sequence[str]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for chunk in _chunked(list(card_ids), 200):
        rows.extend(
            _paged_select(
                client.table("pokemon_canonical_cards")
                .select("id,set_id,name,number,rarity")
                .in_("id", list(chunk))
            )
        )
    return rows


def _load_hit_links(client: Any, *, hit_policy_version: str) -> List[Dict[str, Any]]:
    return _paged_select(
        client.table("pokemon_card_desirability_links")
        .select("id,pokemon_canonical_card_id,pokemon_reference_id,is_hit_eligible,hit_policy_version")
        .eq("is_hit_eligible", True)
        .eq("hit_policy_version", hit_policy_version)
    )


def _load_summaries(
    client: Any,
    set_ids: Sequence[str],
    *,
    aggregation_version: str,
    hit_policy_version: str,
    composite_scoring_version: str,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    selected = (
        "id,set_id,set_name,set_canonical_key,aggregation_version,hit_policy_version,"
        "composite_scoring_version,fan_popularity_snapshot_id,current_trend_snapshot_ids,"
        "composite_score_row_count,composite_score_coverage_ratio,hit_eligible_card_count,"
        "scored_hit_eligible_card_count,linked_pokemon_count,unique_linked_pokemon_count,"
        "scored_link_count,missing_score_count,fallback_link_count,multi_pokemon_card_count,"
        "average_hit_desirability_score,weighted_average_hit_desirability_score,"
        "max_hit_desirability_score,top_3_hit_desirability_score,top_5_hit_desirability_score,"
        "desirability_concentration_top_1_share,desirability_concentration_top_3_share,"
        "desirability_depth_score,effective_desirable_card_count,top_desirable_pokemon_json,"
        "top_desirable_cards_json,missing_score_reference_ids_json,built_at"
    )
    for chunk in _chunked(list(set_ids), 200):
        rows.extend(
            _paged_select(
                client.table(SUMMARY_TABLE)
                .select(selected)
                .in_("set_id", list(chunk))
                .eq("aggregation_version", aggregation_version)
                .eq("hit_policy_version", hit_policy_version)
                .eq("composite_scoring_version", composite_scoring_version)
            )
        )
    return rows


def _metric_bound_issues(row: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    for field in (
        "average_hit_desirability_score",
        "weighted_average_hit_desirability_score",
        "max_hit_desirability_score",
        "top_3_hit_desirability_score",
        "top_5_hit_desirability_score",
        "desirability_depth_score",
    ):
        value = _as_float(row.get(field))
        if value is not None and not 0 <= value <= 100:
            issues.append(f"{field}_out_of_bounds")
    for field in ("desirability_concentration_top_1_share", "desirability_concentration_top_3_share"):
        value = _as_float(row.get(field))
        if value is not None and not 0 <= value <= 1:
            issues.append(f"{field}_out_of_bounds")
    effective_count = _as_float(row.get("effective_desirable_card_count"))
    if effective_count is not None and effective_count < 1:
        issues.append("effective_desirable_card_count_below_1")
    return issues


def _rank_summaries(
    summaries: Sequence[Dict[str, Any]],
    *,
    metric: str,
    reverse: bool,
    limit: int,
) -> List[Dict[str, Any]]:
    rows = [row for row in summaries if _as_float(row.get(metric)) is not None]
    return [
        {
            **_summary_sample(row),
            metric: _as_float(row.get(metric)),
        }
        for row in sorted(rows, key=lambda item: _as_float(item.get(metric)) or 0.0, reverse=reverse)[:limit]
    ]


def _set_sample(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "set_id": row.get("id"),
        "set_name": row.get("name"),
        "set_canonical_key": row.get("canonical_key"),
    }


def _summary_sample(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row.get("id"),
        "set_id": row.get("set_id"),
        "set_name": row.get("set_name"),
        "set_canonical_key": row.get("set_canonical_key"),
        "hit_eligible_card_count": row.get("hit_eligible_card_count"),
        "scored_link_count": row.get("scored_link_count"),
        "missing_score_count": row.get("missing_score_count"),
        "weighted_average_hit_desirability_score": row.get("weighted_average_hit_desirability_score"),
        "desirability_concentration_top_1_share": row.get("desirability_concentration_top_1_share"),
    }


def _is_json_array(value: Any) -> bool:
    return isinstance(value, list)


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PokemonSetHitDesirabilitySummariesValidationError as exc:
        print(f"[pokemon-set-hit-desirability-summaries-validate][ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
