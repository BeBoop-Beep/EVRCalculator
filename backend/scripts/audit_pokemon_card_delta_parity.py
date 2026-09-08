from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

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
    # The identity-ownership subset check below relies on "top_chase" only
    # ever appearing as the RIGHT-hand element of a comparison pair (it is
    # the one subset surface among the three). If a future edit reorders
    # comparisons so top_chase appears on the left, the subset direction
    # would silently invert and weaken the gate — guard that invariant here.
    assert all(left != "top_chase" for left, _right in comparisons), (
        "top_chase must never be the left-hand surface in `comparisons`; "
        "the identity subset check assumes it is always the subset side"
    )
    mismatches: List[Dict[str, Any]] = []

    def _context(record: Any) -> Dict[str, Any]:
        record = record if isinstance(record, dict) else {}
        return {
            "cardVariantId": _value(record, "cardVariantId", "card_variant_id"),
            "conditionId": _value(record, "conditionId", "condition_id"),
            "targetStartDate": _value(record, "targetStartDate", "target_start_date"),
            "startDate": _value(record, "startDate", "start_date"),
            "endDate": _value(record, "endDate", "end_date"),
            "startSourceDate": _value(record, "startSourceDate", "start_source_date"),
            "endSourceDate": _value(record, "endSourceDate", "end_source_date"),
            "currentPrice": _value(record, "currentPrice", "current_price"),
            "changeAmount": _value(record, "changeAmount", "change_amount"),
            "changePercent": _value(record, "changePercent", "change_percent"),
        }

    def report(
        kind: str,
        left_name: str,
        right_name: str,
        key: Tuple[str, str],
        left: Any,
        right: Any,
        *,
        left_record: Any = None,
        right_record: Any = None,
    ) -> None:
        mismatches.append({
            "setId": set_id,
            "type": kind,
            "canonicalCardId": key[0],
            "window": key[1],
            "leftSurface": left_name,
            "rightSurface": right_name,
            "left": left,
            "right": right,
            # Full identity/date context so a single mismatch line names the
            # card, window, variant, condition, source dates, and values.
            "leftContext": _context(left_record),
            "rightContext": _context(right_record),
        })

    for left_name, right_name in comparisons:
        left_rows = surfaces[left_name]
        right_rows = surfaces[right_name]

        # Market identity (variant + condition + window) is one-to-MANY with
        # canonical identity: production legitimately has multiple canonical
        # checklist cards sharing one selected card_variant_id+condition_id
        # (see the PR #166 fan-out fix). Collect every canonical owner per
        # market identity on each surface rather than keeping only the last
        # one seen — a plain dict comprehension here would silently overwrite
        # earlier owners and make the mismatch verdict depend on row order.
        left_owners_by_market_identity: Dict[Tuple[Any, Any, str], Set[str]] = {}
        for key, record in left_rows.items():
            market_identity = (
                _value(record, "cardVariantId", "card_variant_id"),
                _value(record, "conditionId", "condition_id"),
                key[1],
            )
            left_owners_by_market_identity.setdefault(market_identity, set()).add(key[0])
        right_owners_by_market_identity: Dict[Tuple[Any, Any, str], Set[str]] = {}
        for key, record in right_rows.items():
            market_identity = (
                _value(record, "cardVariantId", "card_variant_id"),
                _value(record, "conditionId", "condition_id"),
                key[1],
            )
            right_owners_by_market_identity.setdefault(market_identity, set()).add(key[0])

        # Top Chase is a subset surface (only the chase-worthy cards make the
        # cut), so it is never required to enumerate every canonical owner
        # that Cards/Movers carry for a shared market identity — only that
        # whatever owners it DOES carry are genuine (a subset), not relabeled.
        # Cards vs Movers are both full movement surfaces, so their owner
        # sets must match exactly.
        right_is_subset_surface = right_name == "top_chase"

        for market_identity in set(left_owners_by_market_identity).intersection(
            right_owners_by_market_identity
        ):
            left_owners = left_owners_by_market_identity[market_identity]
            right_owners = right_owners_by_market_identity[market_identity]
            if right_is_subset_surface:
                identity_diverges = not right_owners.issubset(left_owners)
            else:
                identity_diverges = left_owners != right_owners
            if identity_diverges:
                sorted_left_owners = sorted(left_owners)
                sorted_right_owners = sorted(right_owners)
                sample_left_id = sorted_left_owners[0]
                sample_right_id = sorted_right_owners[0]
                report(
                    "identity mismatch",
                    left_name,
                    right_name,
                    (sample_left_id, market_identity[2]),
                    sorted_left_owners,
                    sorted_right_owners,
                    left_record=left_rows.get((sample_left_id, market_identity[2])),
                    right_record=right_rows.get((sample_right_id, market_identity[2])),
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
                    report(
                        kind,
                        left_name,
                        right_name,
                        key,
                        left_value,
                        right_value,
                        left_record=left,
                        right_record=right,
                    )
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
