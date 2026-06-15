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
from backend.desirability.monetary_chase_appeal import compute_monetary_chase_appeal  # noqa: E402
from backend.desirability.opening_desirability_presenter import present_opening_desirability  # noqa: E402
from backend.desirability.rarity_buckets import HIT_POLICY_VERSION  # noqa: E402
from backend.desirability.rip_desirability import (  # noqa: E402
    SCORING_VERSION as RIP_DESIRABILITY_SCORING_VERSION,
    compute_rip_desirability,
)
from backend.desirability.set_components import SCORING_VERSION as V2_SCORING_VERSION  # noqa: E402


OPENING_DESIRABILITY_TABLE = "pokemon_set_opening_desirability_scores"
INSERT_BATCH_SIZE = 100
FINANCIAL_FIELDS = [
    "prob_big_hit",
    "p95_value_to_cost_ratio",
    "p99_value_to_cost_ratio",
    "hit_ev_per_pack",
    "mean_value_to_cost_ratio",
    "effective_chase_count",
    "hhi_ev_concentration",
    "top1_ev_share",
    "top3_ev_share",
    "top5_ev_share",
    "current_market_pack_cost",
    "pack_cost",
]


class RipDesirabilityPrototypeRepository:
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
            self.client.table("pokemon_set_desirability_component_scores")
            .select(
                "id,set_id,set_name,set_canonical_key,set_desirability_score,"
                "chase_subject_strength,chase_subject_depth,accessible_favorite_hits,"
                "special_pack_chase_appeal,scoring_version,hit_policy_version,"
                "composite_scoring_version,built_at,updated_at"
            )
            .eq("scoring_version", scoring_version)
            .eq("hit_policy_version", hit_policy_version)
            .eq("composite_scoring_version", composite_scoring_version)
            .order("built_at", desc=True)
        )

    def list_latest_rip_rows(self) -> List[Dict[str, Any]]:
        return _paged_select(
            self.client.table("explore_rip_statistics_latest")
            .select(
                "calculation_run_id,set_id,set_name,canonical_key,run_at,"
                "prob_big_hit,p95_value_to_cost_ratio,p99_value_to_cost_ratio,"
                "hit_ev_per_pack,mean_value_to_cost_ratio,effective_chase_count,"
                "hhi_ev_concentration,top1_ev_share,top3_ev_share,top5_ev_share,"
                "current_market_pack_cost,pack_cost"
            )
            .order("run_at", desc=True)
        )

    def list_top_simulation_cards_for_runs(self, run_ids: Sequence[str]) -> Dict[str, List[Dict[str, Any]]]:
        cards_by_run: Dict[str, List[Dict[str, Any]]] = {}
        for run_id in [str(value) for value in run_ids if value]:
            response = (
                self.client.table("simulation_input_cards")
                .select("calculation_run_id,card_name,price_used,ev_contribution,effective_pull_rate,rarity_bucket")
                .eq("calculation_run_id", run_id)
                .order("ev_contribution", desc=True)
                .limit(100)
                .execute()
            )
            cards_by_run[run_id] = response.data or []
        return cards_by_run

    def insert_opening_desirability_rows(
        self,
        rows: Sequence[Dict[str, Any]],
        *,
        scoring_version: str,
    ) -> List[Dict[str, Any]]:
        payload = build_opening_desirability_persistence_rows(
            rows,
            scoring_version=scoring_version,
        )
        written: List[Dict[str, Any]] = []
        for chunk in _chunked(payload, INSERT_BATCH_SIZE):
            response = self.client.table(OPENING_DESIRABILITY_TABLE).insert(list(chunk)).execute()
            written.extend(response.data or [])
        return written


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build Opening Desirability prototype outputs.")
    parser.add_argument("--output-dir", default="logs")
    parser.add_argument("--limit", type=int, default=None, help="Limit output rows after ranking.")
    parser.add_argument("--scoring-version", default=V2_SCORING_VERSION)
    parser.add_argument("--hit-policy-version", default=HIT_POLICY_VERSION)
    parser.add_argument("--composite-scoring-version", default=COMPOSITE_SCORING_VERSION)
    parser.add_argument(
        "--commit",
        action="store_true",
        help=(
            "Persist public-safe Opening Desirability rows to "
            "pokemon_set_opening_desirability_scores. Omit for read-only audit output."
        ),
    )
    return parser


def load_backend_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(env_path, override=False)


def main() -> int:
    args = build_parser().parse_args()
    load_backend_env()
    repository = RipDesirabilityPrototypeRepository()
    report = build_report(
        repository=repository,
        scoring_version=args.scoring_version,
        hit_policy_version=args.hit_policy_version,
        composite_scoring_version=args.composite_scoring_version,
        limit=args.limit,
    )
    persistence = maybe_persist_opening_desirability(
        report=report,
        repository=repository,
        commit=args.commit,
        scoring_version=RIP_DESIRABILITY_SCORING_VERSION,
    )
    report["read_only"] = not args.commit
    report["persistence"] = persistence
    print(_format_summary(report["rows"][:20]))
    csv_path, json_path = write_outputs(report, output_dir=Path(args.output_dir))
    print(f"\nCSV written: {csv_path}")
    print(f"JSON written: {json_path}")
    if args.commit:
        print(
            f"Persisted {persistence['written_rows_returned']} "
            f"of {persistence['rows_to_write']} Opening Desirability rows."
        )
    else:
        print(
            f"Read-only run; {persistence['rows_that_would_be_persisted']} "
            "rows would be persisted with --commit."
        )
    return 0


def build_report(
    *,
    repository: RipDesirabilityPrototypeRepository,
    scoring_version: str,
    hit_policy_version: str,
    composite_scoring_version: str,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    v2_by_set = _latest_by_set_id(
        repository.list_v2_rows(
            scoring_version=scoring_version,
            hit_policy_version=hit_policy_version,
            composite_scoring_version=composite_scoring_version,
        )
    )
    rip_by_set = _latest_by_set_id(repository.list_latest_rip_rows())
    run_ids = [str(row.get("calculation_run_id")) for row in rip_by_set.values() if row.get("calculation_run_id")]
    cards_by_run = repository.list_top_simulation_cards_for_runs(run_ids)

    rows: List[Dict[str, Any]] = []
    for set_id, v2_row in v2_by_set.items():
        rip_row = rip_by_set.get(set_id, {})
        run_id = str(rip_row.get("calculation_run_id") or "")
        top_values = _top_value_inputs(cards_by_run.get(run_id, []))
        monetary_inputs = {
            **{field: rip_row.get(field) for field in FINANCIAL_FIELDS},
            **top_values,
        }
        monetary = compute_monetary_chase_appeal(monetary_inputs)
        pure_score = _as_float(v2_row.get("set_desirability_score"))
        rip = compute_rip_desirability(
            pure_desirability_score=pure_score,
            monetary_chase_appeal_score=monetary["monetary_chase_appeal_score"],
        )
        rows.append(
            {
                "set_id": set_id,
                "set_name": v2_row.get("set_name") or rip_row.get("set_name"),
                "set_canonical_key": v2_row.get("set_canonical_key") or rip_row.get("canonical_key"),
                "v2_component_row_id": v2_row.get("id"),
                "v2_built_at": v2_row.get("built_at"),
                "calculation_run_id": run_id or None,
                "rip_run_at": rip_row.get("run_at"),
                "pure_desirability_score": pure_score,
                "monetary_chase_appeal_score": monetary["monetary_chase_appeal_score"],
                "monetary_data_quality": monetary["monetary_data_quality"],
                "rip_desirability_score_80_20": rip["rip_desirability_score_80_20"],
                "rip_desirability_score_70_30": rip["rip_desirability_score_70_30"],
                "rip_desirability_score_60_40": rip["rip_desirability_score_60_40"],
                "primary_rip_desirability_score": rip["primary_rip_desirability_score"],
                "chase_subject_strength": _as_float(v2_row.get("chase_subject_strength")),
                "chase_subject_depth": _as_float(v2_row.get("chase_subject_depth")),
                "accessible_favorite_hits": _as_float(v2_row.get("accessible_favorite_hits")),
                "special_pack_chase_appeal": _as_float(v2_row.get("special_pack_chase_appeal")),
                **{field: _as_float(rip_row.get(field)) for field in FINANCIAL_FIELDS},
                **top_values,
                "monetary_component_scores_json": monetary["component_scores_json"],
                "rip_component_scores_json": rip["component_scores_json"],
                "top_value_cards_json": top_values.get("top_value_cards_json", []),
                "top_ev_cards_json": top_values.get("top_ev_cards_json", []),
            }
        )

    rows.sort(
        key=lambda row: (
            row.get("primary_rip_desirability_score") is not None,
            row.get("primary_rip_desirability_score") or -1,
        ),
        reverse=True,
    )
    _add_rank(rows, "pure_desirability_score", "pure_desirability_rank")
    _add_rank(rows, "monetary_chase_appeal_score", "monetary_chase_appeal_rank")
    _add_rank(rows, "rip_desirability_score_70_30", "rip_desirability_rank_70_30")
    for row in rows:
        public = present_opening_desirability(row)
        row.update(
            {
                "opening_desirability_score": public["opening_desirability_score"],
                "opening_desirability_rank": public["opening_desirability_rank"],
                "collector_appeal_score": public["collector_appeal_score"],
                "collector_appeal_rank": public["collector_appeal_rank"],
                "chase_appeal_score": public["chase_appeal_score"],
                "chase_appeal_rank": public["chase_appeal_rank"],
                "chase_appeal_data_quality": public["chase_appeal_data_quality"],
                "opening_desirability_display_status": public["display_status"],
                "opening_desirability_summary": public["summary"],
                "public_tooltip_copy_json": public["tooltip_copy"],
            }
        )

    output_rows = rows[:limit] if limit is not None else rows
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "source_tables": [
            "pokemon_set_desirability_component_scores",
            "explore_rip_statistics_latest",
            "simulation_input_cards",
        ],
        "parameters": {
            "scoring_version": scoring_version,
            "hit_policy_version": hit_policy_version,
            "composite_scoring_version": composite_scoring_version,
            "opening_desirability_scoring_version": RIP_DESIRABILITY_SCORING_VERSION,
            "limit": limit,
        },
        "rows": output_rows,
    }


def maybe_persist_opening_desirability(
    *,
    report: Dict[str, Any],
    repository: Any,
    commit: bool,
    scoring_version: str,
) -> Dict[str, Any]:
    rows = list(report.get("rows") or [])
    if not commit:
        return {
            "committed": False,
            "target_table": OPENING_DESIRABILITY_TABLE,
            "rows_to_write": 0,
            "rows_that_would_be_persisted": len(rows),
            "written_rows_returned": 0,
            "scoring_version": scoring_version,
        }

    written = repository.insert_opening_desirability_rows(rows, scoring_version=scoring_version)
    return {
        "committed": True,
        "target_table": OPENING_DESIRABILITY_TABLE,
        "rows_to_write": len(rows),
        "rows_that_would_be_persisted": len(rows),
        "written_rows_returned": len(written),
        "scoring_version": scoring_version,
    }


def build_opening_desirability_persistence_rows(
    rows: Sequence[Dict[str, Any]],
    *,
    scoring_version: str,
    built_at: Optional[str] = None,
) -> List[Dict[str, Any]]:
    persisted_built_at = built_at or datetime.now(timezone.utc).isoformat()
    return [
        build_opening_desirability_persistence_row(
            row,
            scoring_version=scoring_version,
            built_at=persisted_built_at,
        )
        for row in rows
    ]


def build_opening_desirability_persistence_row(
    row: Dict[str, Any],
    *,
    scoring_version: str,
    built_at: str,
) -> Dict[str, Any]:
    public = present_opening_desirability(row)
    return {
        "set_id": row.get("set_id"),
        "set_name": row.get("set_name"),
        "set_canonical_key": row.get("set_canonical_key"),
        "opening_desirability_score": public["opening_desirability_score"],
        "opening_desirability_rank": public["opening_desirability_rank"],
        "collector_appeal_score": public["collector_appeal_score"],
        "collector_appeal_rank": public["collector_appeal_rank"],
        "chase_appeal_score": public["chase_appeal_score"],
        "chase_appeal_rank": public["chase_appeal_rank"],
        "chase_appeal_data_quality": public["chase_appeal_data_quality"],
        "opening_desirability_display_status": public["display_status"],
        "opening_desirability_summary": public["summary"],
        "public_tooltip_copy_json": public["tooltip_copy"],
        "source_v2_component_row_id": row.get("v2_component_row_id") or row.get("source_v2_component_row_id"),
        "source_rip_calculation_run_id": row.get("calculation_run_id") or row.get("source_rip_calculation_run_id"),
        "pure_desirability_score": _as_float(row.get("pure_desirability_score")),
        "monetary_chase_appeal_score": _as_float(row.get("monetary_chase_appeal_score")),
        "rip_desirability_score_80_20": _as_float(row.get("rip_desirability_score_80_20")),
        "rip_desirability_score_70_30": _as_float(row.get("rip_desirability_score_70_30")),
        "rip_desirability_score_60_40": _as_float(row.get("rip_desirability_score_60_40")),
        "scoring_version": scoring_version,
        "built_at": built_at,
    }


def _top_value_inputs(cards: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    normalized_cards = [
        {
            "card_name": card.get("card_name"),
            "rarity_bucket": card.get("rarity_bucket"),
            "price_used": _as_float(card.get("price_used")) or 0.0,
            "ev_contribution": _as_float(card.get("ev_contribution")) or 0.0,
            "effective_pull_rate": _as_float(card.get("effective_pull_rate")),
        }
        for card in cards
    ]
    priced_cards = sorted(normalized_cards, key=lambda row: row["price_used"], reverse=True)
    ev_cards = sorted(normalized_cards, key=lambda row: row["ev_contribution"], reverse=True)
    values = [row["price_used"] for row in priced_cards if row["price_used"] > 0]
    return {
        "top_card_value": values[0] if values else None,
        "top_3_card_value": sum(values[:3]) if values else None,
        "top_5_card_value": sum(values[:5]) if values else None,
        "top_value_candidate_pool_size": len(cards),
        "top_value_source_note": (
            "Top card values are highest price_used cards within the top 100 "
            "simulation_input_cards rows ordered by EV contribution."
        ),
        "top_value_cards_json": priced_cards[:10],
        "top_ev_cards_json": ev_cards[:10],
    }


def write_outputs(report: Dict[str, Any], *, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    csv_path = output_dir / f"rip_desirability_prototype_{timestamp}.csv"
    json_path = output_dir / f"rip_desirability_prototype_{timestamp}.json"

    fieldnames = [
        "set_name",
        "set_canonical_key",
        "pure_desirability_score",
        "pure_desirability_rank",
        "opening_desirability_score",
        "opening_desirability_rank",
        "collector_appeal_score",
        "collector_appeal_rank",
        "chase_appeal_score",
        "chase_appeal_rank",
        "chase_appeal_data_quality",
        "opening_desirability_display_status",
        "opening_desirability_summary",
        "public_tooltip_copy_json",
        "monetary_chase_appeal_score",
        "monetary_data_quality",
        "monetary_chase_appeal_rank",
        "rip_desirability_score_80_20",
        "rip_desirability_score_70_30",
        "rip_desirability_score_60_40",
        "rip_desirability_rank_70_30",
        "top_card_value",
        "top_3_card_value",
        "top_5_card_value",
        "top_value_candidate_pool_size",
        "top_value_source_note",
        *FINANCIAL_FIELDS,
        "monetary_component_scores_json",
        "rip_component_scores_json",
        "top_value_cards_json",
        "top_ev_cards_json",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in report["rows"]:
            writer.writerow({field: _csv_value(row.get(field)) for field in fieldnames})

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, default=str)

    return csv_path, json_path


def _format_summary(rows: Sequence[Dict[str, Any]]) -> str:
    header = f"{'Rank':>4}  {'Set':<34} {'Collector':>9} {'Chase':>7} {'Quality':>8} {'Opening':>9}"
    lines = [header, "-" * len(header)]
    for row in rows:
        lines.append(
            f"{str(row.get('opening_desirability_rank') or ''):>4}  "
            f"{str(row.get('set_name') or '')[:34]:<34} "
            f"{_fmt(row.get('collector_appeal_score')):>9} "
            f"{_fmt(row.get('chase_appeal_score')):>7} "
            f"{str(row.get('chase_appeal_data_quality') or ''):>8} "
            f"{_fmt(row.get('opening_desirability_score')):>9}"
        )
    return "\n".join(lines)


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


def _latest_by_set_id(rows: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    latest: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        set_id = str(row.get("set_id") or "")
        if not set_id:
            continue
        current = latest.get(set_id)
        row_time = str(row.get("built_at") or row.get("run_at") or row.get("updated_at") or "")
        current_time = str((current or {}).get("built_at") or (current or {}).get("run_at") or (current or {}).get("updated_at") or "")
        if current is None or row_time > current_time:
            latest[set_id] = row
    return latest


def _add_rank(rows: List[Dict[str, Any]], score_field: str, rank_field: str) -> None:
    ranked = sorted(
        [row for row in rows if row.get(score_field) is not None],
        key=lambda row: row.get(score_field),
        reverse=True,
    )
    previous_score: Optional[float] = None
    previous_rank = 0
    for position, row in enumerate(ranked, start=1):
        score = row.get(score_field)
        rank = previous_rank if previous_score is not None and score == previous_score else position
        row[rank_field] = rank
        previous_score = score
        previous_rank = rank


def _as_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _csv_value(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def _fmt(value: Any) -> str:
    parsed = _as_float(value)
    return "N/A" if parsed is None else f"{parsed:.2f}"


if __name__ == "__main__":
    raise SystemExit(main())
