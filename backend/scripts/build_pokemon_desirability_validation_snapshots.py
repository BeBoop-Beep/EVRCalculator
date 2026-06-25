from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.desirability.set_validation import FORMULA_VERSION, build_desirability_validation_payload, build_opening_set_audit
from backend.scripts.pokemon_snapshot_builders import get_client, load_backend_env

logger = logging.getLogger(__name__)


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _reports_dir() -> Path:
    root = REPO_ROOT / "artifacts" / "reports"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _first_text(*values: Any) -> Optional[str]:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _read_page_snapshots(client: Any, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    query = client.table("pokemon_set_page_snapshot_latest").select("set_id,payload_json,updated_at")
    if limit:
        query = query.limit(limit)
    result = query.execute()
    return [row for row in result.data or [] if isinstance(row.get("payload_json"), dict)]


def _read_cards_snapshot(client: Any, set_id: str) -> Optional[Dict[str, Any]]:
    result = (
        client.table("pokemon_set_cards_snapshot_latest")
        .select("set_id,payload_json,updated_at")
        .eq("set_id", set_id)
        .limit(1)
        .execute()
    )
    row = (result.data or [None])[0]
    return row.get("payload_json") if isinstance(row, dict) and isinstance(row.get("payload_json"), dict) else None


def _target_rows(page_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    targets: List[Dict[str, Any]] = []
    for row in page_rows:
        payload = row.get("payload_json") or {}
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        market = payload.get("market") if isinstance(payload.get("market"), dict) else {}
        set_identity = payload.get("set") if isinstance(payload.get("set"), dict) else {}
        opening = payload.get("openingDesirability") or payload.get("opening_desirability") or {}
        target = {
            "id": row.get("set_id"),
            "set_id": row.get("set_id"),
            "name": set_identity.get("name") or row.get("set_id"),
            "canonical_key": set_identity.get("slug") or set_identity.get("canonical_key"),
            "is_opening_set": set_identity.get("is_opening_set"),
            "is_subset": set_identity.get("is_subset"),
            "parent_opening_set_id": set_identity.get("parent_opening_set_id"),
            "subset_type": set_identity.get("subset_type"),
            "summary": summary,
            "market": market,
            "openingDesirability": opening if isinstance(opening, dict) else {},
            "top_hits": payload.get("top_hits") or payload.get("topHits") or [],
        }
        targets.append(target)
    return targets


def _audit_row(validation: Dict[str, Any]) -> Dict[str, Any]:
    keys = [
        "set_name",
        "desirability_score",
        "desirability_rank",
        "card_appeal_score",
        "card_appeal_rank",
        "rip_core_score_without_desirability",
        "rip_core_rank_without_desirability",
        "final_rip_score_with_desirability",
        "final_rip_rank_with_desirability",
        "desirability_score_delta",
        "desirability_rank_delta",
        "desirability_alignment_score",
        "desirability_alignment_band",
        "strongest_supporting_signal",
        "biggest_conflicting_signal",
        "card_appeal_vs_market_price_correlation",
        "card_appeal_vs_market_price_spearman",
        "set_value_sample_size",
        "pack_cost_sample_size",
        "expected_value_sample_size",
        "p95_sample_size",
        "set_value_rank",
        "pack_cost_rank",
        "expected_value_rank",
        "p95_rank",
        "top_chase_value_rank",
        "top_10_card_value_rank",
        "avg_hit_value_rank",
        "median_hit_value_rank",
        "missing_data_flags",
    ]
    row = {key: validation.get(key) for key in keys}
    row["set_id"] = validation.get("set_id")
    row["formula_version"] = validation.get("formula_version")
    row["missing_data_flags"] = ",".join(validation.get("missing_data_flags") or [])
    return row


def _write_audit(rows: List[Dict[str, Any]]) -> tuple[Path, Path]:
    reports = _reports_dir()
    stamp = _now_stamp()
    json_path = reports / f"pokemon_desirability_validation_{stamp}.json"
    csv_path = reports / f"pokemon_desirability_validation_{stamp}.csv"
    json_path.write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return json_path, csv_path


def _print_top(label: str, rows: List[Dict[str, Any]], key: str, reverse: bool = True) -> None:
    ranked = sorted(
        [row for row in rows if row.get(key) is not None],
        key=lambda row: row.get(key),
        reverse=reverse,
    )[:20]
    print(f"\n{label}")
    for row in ranked:
        print(f"  {row.get('set_name') or row.get('set_id')}: {key}={row.get(key)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build Pokemon desirability validation payloads for set page snapshots")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Generate reports without updating snapshots")
    mode.add_argument("--commit", action="store_true", help="Update pokemon_set_page_snapshot_latest.payload_json")
    parser.add_argument("--limit", type=int, default=None, help="Limit processed set page snapshots")
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    load_backend_env()
    args = build_parser().parse_args()
    client = get_client()
    page_rows = _read_page_snapshots(client, limit=args.limit)
    targets = _target_rows(page_rows)
    opening_audit = build_opening_set_audit(targets)
    audit_rows: List[Dict[str, Any]] = []
    skipped: List[Dict[str, str]] = []

    for page_row in page_rows:
        set_id = _first_text(page_row.get("set_id"))
        payload = page_row.get("payload_json") or {}
        if not set_id:
            skipped.append({"set_id": "", "reason": "missing set_id"})
            continue
        try:
            cards_payload = _read_cards_snapshot(client, set_id)
            validation = build_desirability_validation_payload(
                set_id=set_id,
                set_payload=payload,
                target_rows=targets,
                cards_payload=cards_payload,
            )
            validation["generated_at"] = datetime.now(timezone.utc).isoformat()
            validation["formula_version"] = FORMULA_VERSION
            audit_rows.append(_audit_row(validation))
            if args.commit:
                next_payload = {
                    **payload,
                    "desirabilityValidation": validation,
                    "desirability_validation": validation,
                }
                client.table("pokemon_set_page_snapshot_latest").update({"payload_json": next_payload}).eq("set_id", set_id).execute()
        except Exception as exc:
            logger.exception("failed desirability validation set_id=%s", set_id)
            skipped.append({"set_id": set_id, "reason": str(exc)})

    json_path, csv_path = _write_audit(audit_rows)
    print(f"total sets processed: {len(audit_rows)}")
    print(f"sets skipped: {len(skipped)}")
    print(f"total raw Pokemon set rows: {opening_audit['total_raw_pokemon_set_rows']}")
    print(f"total opening sets: {opening_audit['total_opening_sets']}")
    print(f"total subset rows: {opening_audit['total_subset_rows']}")
    print(f"subset rows mapped to parent opening sets: {opening_audit['subset_rows_mapped_to_parent_opening_sets']}")
    print(f"subset rows missing parent mapping: {opening_audit['subset_rows_missing_parent_mapping']}")
    print(f"sets whose combined card count/value changes after rollup: {len(opening_audit['sets_whose_combined_card_count_or_value_changes_after_rollup'])}")
    print(f"validation sample size before opening-set rollup: {opening_audit['total_raw_pokemon_set_rows']}")
    print(f"validation sample size after opening-set rollup: {opening_audit['total_opening_sets']}")
    for item in skipped[:20]:
        print(f"  skipped {item['set_id']}: {item['reason']}")
    _print_top("top 20 desirability lifts", audit_rows, "desirability_rank_delta", reverse=True)
    _print_top("top 20 desirability drags", audit_rows, "desirability_rank_delta", reverse=False)
    _print_top("strongest alignment sets", audit_rows, "desirability_alignment_score", reverse=True)
    _print_top("weakest alignment sets", audit_rows, "desirability_alignment_score", reverse=False)
    _print_top("strongest card appeal alignment sets", audit_rows, "card_appeal_score", reverse=True)
    _print_top("weakest card appeal alignment sets", audit_rows, "card_appeal_score", reverse=False)
    print("\ncard appeal vs market price correlation summary: not available in v1 audit unless supplied by snapshot payload")
    print(f"audit json: {json_path}")
    print(f"audit csv: {csv_path}")


if __name__ == "__main__":
    main()
