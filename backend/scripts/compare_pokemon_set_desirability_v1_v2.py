from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.desirability.composite import COMPOSITE_SCORING_VERSION  # noqa: E402
from backend.desirability.rarity_buckets import HIT_POLICY_VERSION  # noqa: E402
from backend.desirability.set_components import SCORING_VERSION  # noqa: E402


V1_TABLE = "pokemon_set_hit_desirability_summaries"
V2_TABLE = "pokemon_set_desirability_component_scores"
DEFAULT_FOCUSED_SET_KEYS = [
    "scarletAndViolet151",
    "perfectOrder",
    "shroudedFable",
    "journeyTogether",
    "prismaticEvolutions",
    "blackBolt",
    "whiteFlare",
    "ascendedHeroes",
]


class ComparisonRepository:
    def __init__(self, client: Optional[Any] = None):
        if client is None:
            from backend.db.clients.supabase_client import supabase

            client = supabase
        self.client = client

    def list_v1_rows(self, *, composite_scoring_version: str) -> List[Dict[str, Any]]:
        return _paged_select(
            self.client.table(V1_TABLE)
            .select(
                "set_id,set_name,set_canonical_key,aggregation_version,hit_policy_version,"
                "composite_scoring_version,fan_popularity_snapshot_id,"
                "weighted_average_hit_desirability_score,built_at,updated_at"
            )
            .eq("composite_scoring_version", composite_scoring_version)
            .order("built_at", desc=True)
        )

    def list_v2_rows(
        self,
        *,
        scoring_version: str,
        hit_policy_version: str,
        composite_scoring_version: str,
    ) -> List[Dict[str, Any]]:
        return _paged_select(
            self.client.table(V2_TABLE)
            .select(
                "set_id,set_name,set_canonical_key,scoring_version,hit_policy_version,"
                "composite_scoring_version,fan_popularity_snapshot_id,set_desirability_score,"
                "chase_subject_strength,chase_subject_depth,accessible_favorite_hits,"
                "special_pack_chase_appeal,top_subjects_json,diagnostics_json,warnings_json,built_at"
            )
            .eq("scoring_version", scoring_version)
            .eq("hit_policy_version", hit_policy_version)
            .eq("composite_scoring_version", composite_scoring_version)
            .order("built_at", desc=True)
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare Pokemon set Desirability V1 and V2 scores.")
    parser.add_argument("--scoring-version", default=SCORING_VERSION)
    parser.add_argument("--hit-policy-version", default=HIT_POLICY_VERSION)
    parser.add_argument("--composite-scoring-version", default=COMPOSITE_SCORING_VERSION)
    parser.add_argument("--all", action="store_true", help="Report all sets instead of the focused review list")
    parser.add_argument("--csv", action="store_true", help="Also write logs/desirability_v2_comparison_<timestamp>.csv")
    return parser


def load_backend_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(env_path, override=False)


def main() -> int:
    args = build_parser().parse_args()
    load_backend_env()
    report = build_comparison_report(
        repository=ComparisonRepository(),
        focused_set_keys=None if args.all else DEFAULT_FOCUSED_SET_KEYS,
        scoring_version=args.scoring_version,
        hit_policy_version=args.hit_policy_version,
        composite_scoring_version=args.composite_scoring_version,
    )
    print(format_comparison_table(report["rows"]))
    if args.csv:
        path = write_csv(report["rows"])
        print(f"\nCSV written: {path}")
    return 0


def build_comparison_report(
    *,
    repository: Any,
    focused_set_keys: Optional[Sequence[str]],
    scoring_version: str,
    hit_policy_version: str,
    composite_scoring_version: str,
) -> Dict[str, Any]:
    v1_latest = _latest_by_set(repository.list_v1_rows(composite_scoring_version=composite_scoring_version))
    v2_latest = _latest_by_set(
        repository.list_v2_rows(
            scoring_version=scoring_version,
            hit_policy_version=hit_policy_version,
            composite_scoring_version=composite_scoring_version,
        )
    )
    v1_ranks = _rank_rows(v1_latest.values(), "weighted_average_hit_desirability_score")
    v2_ranks = _rank_rows(v2_latest.values(), "set_desirability_score")

    set_ids = sorted(set(v1_latest) | set(v2_latest))
    if focused_set_keys is not None:
        focused = {key.lower() for key in focused_set_keys}
        set_ids = [
            set_id
            for set_id in set_ids
            if str((v1_latest.get(set_id) or v2_latest.get(set_id) or {}).get("set_canonical_key") or "").lower() in focused
        ]

    rows = []
    for set_id in set_ids:
        v1 = v1_latest.get(set_id) or {}
        v2 = v2_latest.get(set_id) or {}
        v1_rank = v1_ranks.get(set_id)
        v2_rank = v2_ranks.get(set_id)
        rows.append(
            {
                "set_name": v2.get("set_name") or v1.get("set_name"),
                "set_canonical_key": v2.get("set_canonical_key") or v1.get("set_canonical_key"),
                "v1_score": _float_or_none(v1.get("weighted_average_hit_desirability_score")),
                "v2_score": _float_or_none(v2.get("set_desirability_score")),
                "v1_rank": v1_rank,
                "v2_rank": v2_rank,
                "rank_delta": (v1_rank - v2_rank) if v1_rank is not None and v2_rank is not None else None,
                "chase_subject_strength": _float_or_none(v2.get("chase_subject_strength")),
                "chase_subject_depth": _float_or_none(v2.get("chase_subject_depth")),
                "accessible_favorite_hits": _float_or_none(v2.get("accessible_favorite_hits")),
                "special_pack_chase_appeal": _float_or_none(v2.get("special_pack_chase_appeal")),
                "top_3_v2_subjects": [
                    row.get("subject_name")
                    for row in (v2.get("top_subjects_json") or [])[:3]
                    if isinstance(row, dict)
                ],
                "warning_category_counts": _hit_link_category_counts(v2),
                "warning_summary": _warning_summary(v2),
                "warnings": v2.get("warnings_json") or [],
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "focused_set_keys": list(focused_set_keys) if focused_set_keys is not None else None,
        "rows": sorted(rows, key=lambda row: (row.get("v2_rank") is None, row.get("v2_rank") or 999999, row.get("set_name") or "")),
    }


def format_comparison_table(rows: Sequence[Dict[str, Any]]) -> str:
    if not rows:
        return "No V1/V2 comparison rows found."
    headers = ["Set", "V1", "V2", "V1 Rank", "V2 Rank", "Delta", "Str", "Depth", "Access", "Special", "Top V2 Subjects", "Warning Categories", "Warnings"]
    widths = [24, 7, 7, 8, 8, 7, 6, 7, 7, 8, 32, 34, 24]
    lines = [" ".join(header.ljust(width) for header, width in zip(headers, widths))]
    lines.append(" ".join("-" * width for width in widths))
    for row in rows:
        values = [
            str(row.get("set_name") or row.get("set_canonical_key") or "")[:24],
            _fmt(row.get("v1_score")),
            _fmt(row.get("v2_score")),
            _rank(row.get("v1_rank")),
            _rank(row.get("v2_rank")),
            _signed(row.get("rank_delta")),
            _fmt(row.get("chase_subject_strength")),
            _fmt(row.get("chase_subject_depth")),
            _fmt(row.get("accessible_favorite_hits")),
            _fmt(row.get("special_pack_chase_appeal")),
            ", ".join(row.get("top_3_v2_subjects") or [])[:32],
            row.get("warning_summary", "")[:34],
            "; ".join(row.get("warnings") or [])[:24],
        ]
        lines.append(" ".join(value.ljust(width) for value, width in zip(values, widths)))
    return "\n".join(lines)


def write_csv(rows: Sequence[Dict[str, Any]]) -> Path:
    output_dir = Path("logs")
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = output_dir / f"desirability_v2_comparison_{timestamp}.csv"
    fieldnames = [
        "set_name",
        "set_canonical_key",
        "v1_score",
        "v2_score",
        "v1_rank",
        "v2_rank",
        "rank_delta",
        "chase_subject_strength",
        "chase_subject_depth",
        "accessible_favorite_hits",
        "special_pack_chase_appeal",
        "top_3_v2_subjects",
        "warning_category_counts",
        "warning_summary",
        "warnings",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            payload = dict(row)
            payload["top_3_v2_subjects"] = ", ".join(row.get("top_3_v2_subjects") or [])
            payload["warning_category_counts"] = _compact_counts(row.get("warning_category_counts") or {})
            payload["warnings"] = "; ".join(row.get("warnings") or [])
            writer.writerow({field: payload.get(field) for field in fieldnames})
    return path


def _latest_by_set(rows: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    latest = {}
    for row in rows:
        set_id = str(row.get("set_id") or "")
        if set_id and set_id not in latest:
            latest[set_id] = row
    return latest


def _rank_rows(rows: Iterable[Dict[str, Any]], metric: str) -> Dict[str, int]:
    ranked = [
        row for row in rows
        if row.get("set_id") is not None and _float_or_none(row.get(metric)) is not None
    ]
    ranked.sort(key=lambda row: _float_or_none(row.get(metric)) or 0.0, reverse=True)
    return {str(row["set_id"]): index for index, row in enumerate(ranked, start=1)}


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


def _float_or_none(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt(value: Any) -> str:
    parsed = _float_or_none(value)
    return "-" if parsed is None else f"{parsed:.1f}"


def _rank(value: Any) -> str:
    return "-" if value is None else str(value)


def _signed(value: Any) -> str:
    if value is None:
        return "-"
    return f"{int(value):+d}"


def _hit_link_category_counts(v2_row: Dict[str, Any]) -> Dict[str, int]:
    diagnostics = v2_row.get("diagnostics_json") or {}
    counts = diagnostics.get("hit_link_category_counts") if isinstance(diagnostics, dict) else {}
    if not isinstance(counts, dict):
        return {}
    return {str(key): int(value or 0) for key, value in sorted(counts.items())}


def _warning_summary(v2_row: Dict[str, Any]) -> str:
    counts = _hit_link_category_counts(v2_row)
    if not counts:
        return ""
    return _compact_counts({key: value for key, value in counts.items() if value})


def _compact_counts(counts: Dict[str, Any]) -> str:
    return "; ".join(f"{key}={int(value or 0)}" for key, value in sorted(counts.items()))


if __name__ == "__main__":
    raise SystemExit(main())
