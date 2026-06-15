from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.desirability.composite import COMPOSITE_SCORING_VERSION  # noqa: E402
from backend.desirability.rarity_buckets import BUCKET_PRIORITY, HIT_POLICY_VERSION  # noqa: E402
from backend.desirability.set_components import SCORING_VERSION  # noqa: E402


V2_TABLE = "pokemon_set_desirability_component_scores"
DEFAULT_TARGET_SET_KEYS = [
    "prismaticEvolutions",
    "ascendedHeroes",
    "scarletAndViolet151",
    "evolvingSkies",
    "paldeanFates",
    "whiteFlare",
    "blackBolt",
    "celebrations",
    "celebrationsClassicCollection",
    "legendaryCollection",
    "base",
    "skyridge",
    "shroudedFable",
]

COMPONENT_FIELDS = [
    "chase_subject_strength",
    "chase_subject_depth",
    "accessible_favorite_hits",
    "special_pack_chase_appeal",
]

COVERAGE_AUDIT_FIELDS = [
    "canonical_card_count",
    "hit_like_card_count",
    "pokemon_linked_hit_count",
    "non_pokemon_hit_count",
    "unknown_rarity_count",
    "premium_chase_count",
    "major_hit_count",
    "accessible_hit_count",
    "rarity_override_count",
]


class DesirabilityV2ValidationError(RuntimeError):
    pass


class DesirabilityV2ValidationRepository:
    def __init__(self, client: Optional[Any] = None):
        if client is None:
            from backend.db.clients.supabase_client import supabase

            client = supabase
        self.client = client

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
                "composite_scoring_version,fan_popularity_snapshot_id,current_trend_snapshot_ids,"
                "config_fingerprint,set_desirability_score,chase_subject_strength,"
                "chase_subject_depth,accessible_favorite_hits,special_pack_chase_appeal,"
                "hit_eligible_card_count,scored_hit_eligible_card_count,unique_subject_count,"
                "duplicate_subject_count,premium_chase_subject_count,major_hit_subject_count,"
                "accessible_hit_count,trainer_hit_count,unmatched_hit_count,top_subjects_json,"
                "subject_rollups_json,rarity_bucket_counts_json,special_pack_summary_json,"
                "component_inputs_json,diagnostics_json,warnings_json,built_at,updated_at"
            )
            .eq("scoring_version", scoring_version)
            .eq("hit_policy_version", hit_policy_version)
            .eq("composite_scoring_version", composite_scoring_version)
            .order("built_at", desc=True)
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only Desirability V2 audit for selected Pokemon sets."
    )
    parser.add_argument(
        "--sets",
        nargs="+",
        default=DEFAULT_TARGET_SET_KEYS,
        help="sets.canonical_key values to audit. Defaults to the curated V2 validation list.",
    )
    parser.add_argument("--scoring-version", default=SCORING_VERSION)
    parser.add_argument("--hit-policy-version", default=HIT_POLICY_VERSION)
    parser.add_argument("--composite-scoring-version", default=COMPOSITE_SCORING_VERSION)
    parser.add_argument(
        "--output-dir",
        default="logs",
        help="Directory for desirability_v2_validation_<timestamp>.csv/json outputs.",
    )
    return parser


def load_backend_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(env_path, override=False)


def main() -> int:
    args = build_parser().parse_args()
    load_backend_env()
    report = build_validation_report(
        repository=DesirabilityV2ValidationRepository(),
        target_set_keys=args.sets,
        scoring_version=args.scoring_version,
        hit_policy_version=args.hit_policy_version,
        composite_scoring_version=args.composite_scoring_version,
    )
    print(format_terminal_table(report["rows"]))
    csv_path, json_path = write_outputs(report, output_dir=Path(args.output_dir))
    print(f"\nCSV written: {csv_path}")
    print(f"JSON written: {json_path}")
    return 1 if report["missing_set_keys"] else 0


def build_validation_report(
    *,
    repository: Any,
    target_set_keys: Sequence[str],
    scoring_version: str,
    hit_policy_version: str,
    composite_scoring_version: str,
) -> Dict[str, Any]:
    raw_rows = repository.list_v2_rows(
        scoring_version=scoring_version,
        hit_policy_version=hit_policy_version,
        composite_scoring_version=composite_scoring_version,
    )
    latest_by_set = _latest_by_set(raw_rows)
    ranks = _rank_rows(latest_by_set.values())
    latest_by_key = {
        str(row.get("set_canonical_key") or "").lower(): row
        for row in latest_by_set.values()
        if row.get("set_canonical_key")
    }

    rows: List[Dict[str, Any]] = []
    missing_set_keys: List[str] = []
    for set_key in target_set_keys:
        row = latest_by_key.get(str(set_key).lower())
        if not row:
            missing_set_keys.append(set_key)
            rows.append(_missing_row(set_key))
            continue
        rows.append(_audit_row(row, rank=ranks.get(str(row.get("set_id")))))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_table": V2_TABLE,
        "read_only": True,
        "scoring_version": scoring_version,
        "hit_policy_version": hit_policy_version,
        "composite_scoring_version": composite_scoring_version,
        "target_set_keys": list(target_set_keys),
        "v2_rows_loaded": len(raw_rows),
        "latest_v2_sets_ranked": len(latest_by_set),
        "missing_set_keys": missing_set_keys,
        "rows": rows,
    }


def format_terminal_table(rows: Sequence[Dict[str, Any]]) -> str:
    if not rows:
        return "No Desirability V2 validation rows found."
    headers = [
        "Set",
        "V2",
        "Rank",
        "Str",
        "Depth",
        "Access",
        "Spec",
        "Coverage",
        "Issue Signals",
        "Top Subjects",
    ]
    widths = [28, 7, 5, 6, 7, 7, 6, 31, 34, 42]
    lines = [" ".join(header.ljust(width) for header, width in zip(headers, widths))]
    lines.append(" ".join("-" * width for width in widths))
    for row in rows:
        coverage = row.get("coverage_audit_summary") or {}
        values = [
            str(row.get("set_name") or row.get("set_canonical_key") or "")[:28],
            _fmt(row.get("v2_score")),
            _rank(row.get("v2_rank")),
            _fmt(row.get("chase_subject_strength")),
            _fmt(row.get("chase_subject_depth")),
            _fmt(row.get("accessible_favorite_hits")),
            _fmt(row.get("special_pack_chase_appeal")),
            _coverage_summary(coverage)[:31],
            str(row.get("audit_issue_signals") or "")[:34],
            ", ".join(subject.get("subject_name") or "" for subject in row.get("top_10_subject_rollups") or [])[:42],
        ]
        lines.append(" ".join(value.ljust(width) for value, width in zip(values, widths)))

    return "\n".join(lines)


def write_outputs(report: Dict[str, Any], *, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    csv_path = output_dir / f"desirability_v2_validation_{timestamp}.csv"
    json_path = output_dir / f"desirability_v2_validation_{timestamp}.json"
    write_csv(report["rows"], csv_path)
    json_path.write_text(json.dumps(_jsonable(report), indent=2, sort_keys=True), encoding="utf-8")
    return csv_path, json_path


def write_csv(rows: Sequence[Dict[str, Any]], path: Path) -> None:
    fieldnames = [
        "set_name",
        "set_canonical_key",
        "v2_score",
        "v2_rank",
        *COMPONENT_FIELDS,
        "top_10_subject_rollups_json",
        "rarity_bucket_counts_json",
        "hit_link_category_counts_json",
        "warning_summary",
        "warnings_json",
        "audit_issue_signals",
        *COVERAGE_AUDIT_FIELDS,
        "top_hit_like_rows_json",
        "built_at",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            coverage = row.get("coverage_audit_summary") or {}
            payload = {
                **{field: row.get(field) for field in fieldnames},
                "top_10_subject_rollups_json": json.dumps(
                    _jsonable(row.get("top_10_subject_rollups") or []),
                    sort_keys=True,
                ),
                "rarity_bucket_counts_json": json.dumps(
                    _jsonable(row.get("rarity_bucket_counts_json") or {}),
                    sort_keys=True,
                ),
                "hit_link_category_counts_json": json.dumps(
                    _jsonable(row.get("hit_link_category_counts") or {}),
                    sort_keys=True,
                ),
                "warnings_json": json.dumps(_jsonable(row.get("warnings") or []), sort_keys=True),
                "top_hit_like_rows_json": json.dumps(
                    _jsonable(coverage.get("top_hit_like_rows") or []),
                    sort_keys=True,
                ),
            }
            for field in COVERAGE_AUDIT_FIELDS:
                payload[field] = coverage.get(field)
            writer.writerow({field: payload.get(field) for field in fieldnames})


def _audit_row(row: Dict[str, Any], *, rank: Optional[int]) -> Dict[str, Any]:
    diagnostics = row.get("diagnostics_json") if isinstance(row.get("diagnostics_json"), dict) else {}
    coverage_audit = diagnostics.get("coverage_audit") if isinstance(diagnostics, dict) else {}
    if not isinstance(coverage_audit, dict):
        coverage_audit = {}
    hit_link_counts = diagnostics.get("hit_link_category_counts") if isinstance(diagnostics, dict) else {}
    if not isinstance(hit_link_counts, dict):
        hit_link_counts = {}

    warnings = row.get("warnings_json") if isinstance(row.get("warnings_json"), list) else []
    top_subjects = _top_subject_rollups(row.get("subject_rollups_json") or [], limit=10)
    coverage_summary = {
        field: coverage_audit.get(field)
        for field in COVERAGE_AUDIT_FIELDS
    }
    coverage_summary["top_hit_like_rows"] = coverage_audit.get("top_hit_like_rows") or []

    return {
        "set_name": row.get("set_name"),
        "set_canonical_key": row.get("set_canonical_key"),
        "v2_score": _float_or_none(row.get("set_desirability_score")),
        "v2_rank": rank,
        "chase_subject_strength": _float_or_none(row.get("chase_subject_strength")),
        "chase_subject_depth": _float_or_none(row.get("chase_subject_depth")),
        "accessible_favorite_hits": _float_or_none(row.get("accessible_favorite_hits")),
        "special_pack_chase_appeal": _float_or_none(row.get("special_pack_chase_appeal")),
        "top_10_subject_rollups": top_subjects,
        "rarity_bucket_counts_json": row.get("rarity_bucket_counts_json") or {},
        "hit_link_category_counts": {str(key): int(value or 0) for key, value in sorted(hit_link_counts.items())},
        "warning_summary": _warning_summary(warnings, hit_link_counts, coverage_audit),
        "warnings": warnings,
        "audit_issue_signals": _audit_issue_signals(hit_link_counts, coverage_audit),
        "coverage_audit_summary": coverage_summary,
        "built_at": row.get("built_at"),
        "source": {
            "set_id": row.get("set_id"),
            "fan_popularity_snapshot_id": row.get("fan_popularity_snapshot_id"),
            "current_trend_snapshot_ids": row.get("current_trend_snapshot_ids"),
            "config_fingerprint": row.get("config_fingerprint"),
            "diagnostics_json": diagnostics,
            "component_inputs_json": row.get("component_inputs_json") or {},
            "special_pack_summary_json": row.get("special_pack_summary_json") or {},
        },
    }


def _top_subject_rollups(value: Any, *, limit: int) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows = [row for row in value if isinstance(row, dict)]
    rows.sort(key=_subject_sort_key, reverse=True)
    return [
        {
            "subject_name": row.get("subject_name"),
            "max_desirability_score": _float_or_none(row.get("max_desirability_score")),
            "best_rarity_bucket": row.get("best_rarity_bucket"),
            "representative_card_name": row.get("representative_card_name"),
            "representative_rarity": row.get("representative_rarity"),
            "premium_chase_card_count": int(row.get("premium_chase_card_count") or 0),
            "major_hit_card_count": int(row.get("major_hit_card_count") or 0),
            "accessible_hit_card_count": int(row.get("accessible_hit_card_count") or 0),
            "rarity_buckets_present": row.get("rarity_buckets_present") or [],
        }
        for row in rows[:limit]
    ]


def _subject_sort_key(row: Dict[str, Any]) -> tuple[Any, ...]:
    return (
        _float_or_none(row.get("max_desirability_score")) or -1.0,
        BUCKET_PRIORITY.get(str(row.get("best_rarity_bucket")), 0),
        int(row.get("premium_chase_card_count") or 0),
        int(row.get("major_hit_card_count") or 0),
        int(row.get("accessible_hit_card_count") or 0),
        str(row.get("subject_name") or ""),
    )


def _warning_summary(
    warnings: Sequence[Any],
    hit_link_counts: Dict[str, Any],
    coverage_audit: Dict[str, Any],
) -> str:
    parts: List[str] = []
    if warnings:
        parts.append("; ".join(str(item) for item in warnings))
    signal_counts = {
        "unknown_rarity": coverage_audit.get("unknown_rarity_count"),
        "unsupported_subject_hit": hit_link_counts.get("unsupported_subject_hit_count"),
        "unmatched_pokemon_hit": hit_link_counts.get("unmatched_pokemon_hit_count"),
        "true_missing_link": hit_link_counts.get("true_missing_link_count"),
        "unknown_or_unclassified_hit": hit_link_counts.get("unknown_or_unclassified_hit_count"),
    }
    non_zero = _compact_counts({key: value for key, value in signal_counts.items() if int(value or 0)})
    if non_zero:
        parts.append(non_zero)
    return " | ".join(parts) if parts else "no actionable warnings"


def _audit_issue_signals(hit_link_counts: Dict[str, Any], coverage_audit: Dict[str, Any]) -> str:
    missing_link_count = int(hit_link_counts.get("unmatched_pokemon_hit_count") or 0) + int(
        hit_link_counts.get("true_missing_link_count") or 0
    )
    signals = {
        "unk_rarity": coverage_audit.get("unknown_rarity_count"),
        "missing_link": missing_link_count,
        "unsupported": hit_link_counts.get("unsupported_subject_hit_count"),
        "non_pokemon": hit_link_counts.get("expected_non_pokemon_hit_count"),
    }
    non_zero = {key: value for key, value in signals.items() if int(value or 0)}
    return _compact_counts(non_zero) if non_zero else "none"


def _coverage_summary(coverage: Dict[str, Any]) -> str:
    return (
        f"c={_dash(coverage.get('canonical_card_count'))} "
        f"h={_dash(coverage.get('hit_like_card_count'))} "
        f"l={_dash(coverage.get('pokemon_linked_hit_count'))} "
        f"unk={_dash(coverage.get('unknown_rarity_count'))} "
        f"ovr={_dash(coverage.get('rarity_override_count'))}"
    )


def _missing_row(set_key: str) -> Dict[str, Any]:
    return {
        "set_name": None,
        "set_canonical_key": set_key,
        "v2_score": None,
        "v2_rank": None,
        "chase_subject_strength": None,
        "chase_subject_depth": None,
        "accessible_favorite_hits": None,
        "special_pack_chase_appeal": None,
        "top_10_subject_rollups": [],
        "rarity_bucket_counts_json": {},
        "hit_link_category_counts": {},
        "warning_summary": "missing latest V2 component row for requested set",
        "warnings": ["missing latest V2 component row for requested set"],
        "audit_issue_signals": "missing_v2_row=1",
        "coverage_audit_summary": {},
        "built_at": None,
        "source": {},
    }


def _latest_by_set(rows: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    latest: Dict[str, Dict[str, Any]] = {}
    for row in sorted(rows, key=_built_at_sort_key, reverse=True):
        set_id = str(row.get("set_id") or "")
        if set_id and set_id not in latest:
            latest[set_id] = row
    return latest


def _rank_rows(rows: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    ranked = [
        row
        for row in rows
        if row.get("set_id") is not None and _float_or_none(row.get("set_desirability_score")) is not None
    ]
    ranked.sort(key=lambda item: _float_or_none(item.get("set_desirability_score")) or 0.0, reverse=True)
    return {str(row["set_id"]): index for index, row in enumerate(ranked, start=1)}


def _built_at_sort_key(row: Dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("built_at") or ""), str(row.get("updated_at") or ""))


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


def _fmt(value: Any) -> str:
    parsed = _float_or_none(value)
    return "-" if parsed is None else f"{parsed:.1f}"


def _rank(value: Any) -> str:
    return "-" if value is None else str(value)


def _dash(value: Any) -> str:
    return "-" if value is None else str(value)


def _compact_counts(counts: Dict[str, Any]) -> str:
    return "; ".join(f"{key}={int(value or 0)}" for key, value in sorted(counts.items()))


def _float_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
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
    try:
        raise SystemExit(main())
    except DesirabilityV2ValidationError as exc:
        print(f"[desirability-v2-validation][ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
