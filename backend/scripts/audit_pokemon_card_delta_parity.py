from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.scripts.pokemon_snapshot_builders import get_client, load_backend_env, resolve_set_row


WINDOWS = ("1D", "7D", "30D")


def _text(value: Any) -> Optional[str]:
    resolved = str(value or "").strip()
    return resolved or None


def _number(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _identity(card: Dict[str, Any]) -> Optional[str]:
    return _text(card.get("canonicalCardId") or card.get("canonical_card_id") or card.get("cardId") or card.get("id"))


def _cards_windows(payload: Any) -> Dict[Tuple[str, str], Dict[str, Any]]:
    results: Dict[Tuple[str, str], Dict[str, Any]] = {}
    cards = payload if isinstance(payload, list) else (payload.get("cards") or [])
    for card in cards:
        card_id = _identity(card)
        if not card_id:
            continue
        for key in ("7D", "30D"):
            movement = card.get(f"movement{key.lower()}") or card.get(f"movement_{key.lower()}")
            if isinstance(movement, dict):
                results[(card_id, key)] = movement
    return results


def _mover_windows(payload: Dict[str, Any]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    results: Dict[Tuple[str, str], Dict[str, Any]] = {}
    by_window = payload.get("marketMoversByWindow") or payload.get("market_movers_by_window") or {}
    for key, entry in by_window.items():
        cards = entry.get("all") if isinstance(entry, dict) else []
        if not isinstance(cards, list):
            cards = list((entry or {}).get("heatingUp") or []) + list((entry or {}).get("coolingOff") or [])
        for card in cards:
            card_id = _identity(card)
            if card_id and key in WINDOWS:
                results[(card_id, key)] = card
    return results


def _top_chase_windows(payload: Dict[str, Any]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    results: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for card in payload.get("topChaseCards") or payload.get("top_chase_cards") or []:
        card_id = _identity(card)
        windows = card.get("marketDeltaWindows") or card.get("market_delta_windows") or {}
        if not card_id:
            continue
        for key, movement in windows.items():
            if key in WINDOWS and isinstance(movement, dict):
                results[(card_id, key)] = movement
    return results


def _value(record: Dict[str, Any], camel: str, snake: str) -> Any:
    return record.get(camel) if camel in record else record.get(snake)


def audit_payloads(
    cards_payload: Any,
    dashboard_payload: Dict[str, Any],
    *,
    set_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    surfaces = {
        "cards": _cards_windows(cards_payload),
        "movers": _mover_windows(dashboard_payload),
        "top_chase": _top_chase_windows(dashboard_payload),
    }
    comparisons = (
        ("cards", "movers"),
        ("cards", "top_chase"),
        ("movers", "top_chase"),
    )
    mismatches: List[Dict[str, Any]] = []

    def report(kind: str, left_name: str, right_name: str, key: Tuple[str, str], left: Any, right: Any) -> None:
        mismatches.append({
            "setId": set_id,
            "type": kind,
            "canonicalCardId": key[0],
            "window": key[1],
            "leftSurface": left_name,
            "rightSurface": right_name,
            "left": left,
            "right": right,
        })

    for left_name, right_name in comparisons:
        left_rows = surfaces[left_name]
        right_rows = surfaces[right_name]
        left_by_market_identity = {
            (
                _value(record, "cardVariantId", "card_variant_id"),
                _value(record, "conditionId", "condition_id"),
                key[1],
            ): key[0]
            for key, record in left_rows.items()
        }
        right_by_market_identity = {
            (
                _value(record, "cardVariantId", "card_variant_id"),
                _value(record, "conditionId", "condition_id"),
                key[1],
            ): key[0]
            for key, record in right_rows.items()
        }
        for market_identity in set(left_by_market_identity).intersection(right_by_market_identity):
            left_card_id = left_by_market_identity[market_identity]
            right_card_id = right_by_market_identity[market_identity]
            if left_card_id != right_card_id:
                report(
                    "identity mismatch",
                    left_name,
                    right_name,
                    (left_card_id, market_identity[2]),
                    left_card_id,
                    right_card_id,
                )
        for key in sorted(set(left_rows).intersection(right_rows)):
            left = left_rows[key]
            right = right_rows[key]
            fields = (
                ("variant mismatch", "cardVariantId", "card_variant_id", None),
                ("condition mismatch", "conditionId", "condition_id", None),
                ("target-baseline-date mismatch", "targetStartDate", "target_start_date", None),
                ("as-of-date mismatch", "endDate", "end_date", None),
                ("baseline-date mismatch", "startDate", "start_date", None),
                ("current-price mismatch", "currentPrice", "current_price", 0.0),
                ("amount mismatch", "changeAmount", "change_amount", 0.0),
                ("percentage mismatch", "changePercent", "change_percent", 0.0),
                ("full-window mismatch", "fullWindowCoverage", "full_window_coverage", None),
                ("partial-window mismatch", "isPartialWindow", "is_partial_window", None),
                ("window-convention mismatch", "windowConvention", "window_convention", None),
            )
            for kind, camel, snake, tolerance in fields:
                left_value = _value(left, camel, snake)
                right_value = _value(right, camel, snake)
                if tolerance is None:
                    equal = left_value == right_value
                else:
                    left_number = _number(left_value)
                    right_number = _number(right_value)
                    equal = (
                        left_number is None and right_number is None
                    ) or (
                        left_number is not None and right_number is not None
                        and abs(left_number - right_number) <= tolerance
                    )
                if not equal:
                    report(kind, left_name, right_name, key, left_value, right_value)
    return mismatches


def _first_row(client: Any, table: str, select: str, set_id: str) -> Dict[str, Any]:
    result = client.table(table).select(select).eq("set_id", set_id).limit(1).execute()
    return (list(result.data or []) or [{}])[0]


def _set_ids(client: Any, requested: Optional[str], all_sets: bool) -> Iterable[str]:
    if requested:
        yield str(resolve_set_row(client, requested)["id"])
        return
    if all_sets:
        result = client.table("sets").select("id").order("name").execute()
        for row in result.data or []:
            if row.get("id"):
                yield str(row["id"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit canonical Pokemon card deltas across public snapshots.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--set-id")
    group.add_argument("--all", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    load_backend_env()
    client = get_client()
    mismatches: List[Dict[str, Any]] = []
    audited = 0
    for set_id in _set_ids(client, args.set_id, args.all):
        cards_row = _first_row(client, "pokemon_set_cards_snapshot_latest", "cards_json", set_id)
        dashboard_row = _first_row(client, "pokemon_set_market_dashboard_snapshot_latest", "payload_json", set_id)
        mismatches.extend(
            audit_payloads(
                cards_row.get("cards_json") or {},
                dashboard_row.get("payload_json") or {},
                set_id=set_id,
            )
        )
        audited += 1
    summary = {"setsAudited": audited, "mismatchCount": len(mismatches), "byType": dict(Counter(row["type"] for row in mismatches))}
    if args.json:
        print(json.dumps({"summary": summary, "mismatches": mismatches}, indent=2, sort_keys=True))
    else:
        print(json.dumps(summary, sort_keys=True))
        for mismatch in mismatches:
            print(json.dumps(mismatch, sort_keys=True))
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
