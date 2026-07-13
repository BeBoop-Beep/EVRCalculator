from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.scripts.pokemon_snapshot_builders import (
    DEFAULT_DASHBOARD_DAYS,
    DEFAULT_DASHBOARD_WINDOW,
    add_target_set_args,
    build_cards_snapshot_row,
    get_client,
    refresh_canonical_card_market_prices_for_set,
    resolve_target_sets,
    should_commit,
    upsert_row,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit and idempotently repair canonical card pricing and Cards movement snapshots"
    )
    add_target_set_args(parser)
    parser.add_argument("--days", type=int, default=DEFAULT_DASHBOARD_DAYS)
    parser.add_argument("--window", default=DEFAULT_DASHBOARD_WINDOW)
    parser.add_argument("--report", help="Optional JSON report path")
    parser.add_argument("--verbose", action="store_true")
    return parser


def _first_row(result: Any) -> Dict[str, Any]:
    rows = list(getattr(result, "data", None) or [])
    return rows[0] if rows else {}


def _card_stats(cards: Any) -> Dict[str, int]:
    rows = cards if isinstance(cards, list) else []

    def present(card: Dict[str, Any], *keys: str) -> bool:
        return any(card.get(key) is not None for key in keys)

    return {
        "cards": len(rows),
        "priced": sum(1 for card in rows if present(card, "marketPrice", "market_price", "currentPrice", "current_price")),
        "movement7dContracts": sum(1 for card in rows if isinstance(card.get("movement7d") or card.get("movement_7d"), dict)),
        "movement7d": sum(1 for card in rows if present(card, "change7dPercent", "change_7d_percent")),
        "reliableMovement7d": sum(
            1
            for card in rows
            if bool(card.get("movement7dReliable") or card.get("movement_7d_reliable"))
        ),
        "movement30dContracts": sum(1 for card in rows if isinstance(card.get("movement30d") or card.get("movement_30d"), dict)),
        "movement30d": sum(1 for card in rows if present(card, "change30dPercent", "change_30d_percent")),
    }


def _pricing_stats(client: Any, set_id: str, *, resolve: bool = True) -> Dict[str, int]:
    canonical_rows = list(
        client.table("pokemon_canonical_cards")
        .select("id")
        .eq("set_id", set_id)
        .execute()
        .data
        or []
    )
    selected_rows = list(
        client.table("pokemon_canonical_card_market_prices_latest")
        .select("canonical_card_id,market_price")
        .eq("set_id", set_id)
        .execute()
        .data
        or []
    )
    resolvable_rows = (
        list(
            client.rpc(
                "get_pokemon_canonical_card_market_prices_latest_for_set",
                {"target_set_id": set_id},
            ).execute().data
            or []
        )
        if resolve
        else []
    )
    return {
        "canonical": len(canonical_rows),
        "selected": sum(1 for row in selected_rows if row.get("market_price") is not None),
        "resolvable": (
            sum(1 for row in resolvable_rows if row.get("market_price") is not None)
            if resolve
            else 0
        ),
    }


def _cards_need_rebuild(cards: Dict[str, int], pricing: Dict[str, int]) -> bool:
    authoritative_priced = pricing["selected"]
    return bool(
        cards["cards"] != pricing["canonical"]
        or cards["priced"] != authoritative_priced
        or cards["movement7dContracts"] < authoritative_priced
        or cards["movement30dContracts"] < authoritative_priced
    )


def _history_end(histories: Any) -> str | None:
    dates = [
        str(point.get("date"))[:10]
        for history in (histories.values() if isinstance(histories, dict) else [])
        if isinstance(history, list)
        for point in history
        if isinstance(point, dict) and point.get("date")
    ]
    return max(dates, default=None)


def _history_source_end(histories: Any) -> str | None:
    dates = [
        str(point.get("sourceDate") or point.get("source_date"))[:10]
        for history in (histories.values() if isinstance(histories, dict) else [])
        if isinstance(history, list)
        for point in history
        if isinstance(point, dict) and (point.get("sourceDate") or point.get("source_date"))
    ]
    return max(dates, default=None)


def _read_before(client: Any, set_id: str, window: str, *, resolve_pricing: bool = True) -> Dict[str, Any]:
    cards_row = _first_row(
        client.table("pokemon_set_cards_snapshot_latest")
        .select("cards_json,updated_at")
        .eq("set_id", set_id)
        .limit(1)
        .execute()
    )
    dashboard_row = _first_row(
        client.table("pokemon_set_market_dashboard_snapshot_latest")
        .select("latest_market_date,top_chase_card_histories_json,updated_at")
        .eq("set_id", set_id)
        .eq("window_key", window)
        .limit(1)
        .execute()
    )
    return {
        "cards": _card_stats(cards_row.get("cards_json")),
        "pricing": _pricing_stats(client, set_id, resolve=resolve_pricing),
        "latestMarketDate": dashboard_row.get("latest_market_date"),
        "topChaseHistoryEndDate": _history_end(dashboard_row.get("top_chase_card_histories_json")),
        "topChaseSourceEndDate": _history_source_end(dashboard_row.get("top_chase_card_histories_json")),
    }


def _write_report(path: str, report: Dict[str, Any]) -> None:
    report_path = Path(path).expanduser().resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")


def main() -> None:
    args = build_parser().parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")
    client = get_client()
    commit = should_commit(args)
    results: List[Dict[str, Any]] = []
    target_sets = resolve_target_sets(client, args)

    for set_row in target_sets:
        set_id = str(set_row["id"])
        result: Dict[str, Any] = {
            "setId": set_id,
            "setName": set_row.get("name"),
            "status": "pending",
        }
        try:
            before = _read_before(client, set_id, args.window, resolve_pricing=not commit)
            refreshed_price_rows = refresh_canonical_card_market_prices_for_set(
                client,
                set_id,
                commit=commit,
            )
            if commit:
                before["pricing"]["resolvable"] = int(refreshed_price_rows or 0)
                pricing_after_refresh = _pricing_stats(client, set_id, resolve=False)
                pricing_after_refresh["resolvable"] = int(refreshed_price_rows or 0)
            else:
                pricing_after_refresh = before["pricing"]
            cards_need_rebuild = _cards_need_rebuild(before["cards"], pricing_after_refresh)
            cards_row = build_cards_snapshot_row(set_row) if cards_need_rebuild else None
            after = {
                "cards": _card_stats(cards_row.get("cards_json")) if cards_row else before["cards"],
                "pricing": pricing_after_refresh,
                "latestMarketDate": before["latestMarketDate"],
                "topChaseHistoryEndDate": before["topChaseHistoryEndDate"],
                "topChaseSourceEndDate": before["topChaseSourceEndDate"],
            }
            selected_price_gap = pricing_after_refresh["selected"] < pricing_after_refresh["resolvable"]
            cards_still_unhealthy = _cards_need_rebuild(after["cards"], pricing_after_refresh)
            changed = before != after or cards_need_rebuild
            result.update(
                {
                    "status": (
                        "unhealthy"
                        if selected_price_gap or cards_still_unhealthy
                        else ("repaired" if changed else "healthy")
                    ),
                    "selectedPriceRowsRefreshed": refreshed_price_rows,
                    "before": before,
                    "after": after,
                }
            )
            if commit and changed:
                if cards_row:
                    upsert_row(
                        client,
                        "pokemon_set_cards_snapshot_latest",
                        cards_row,
                        on_conflict="set_id",
                        commit=True,
                    )
        except Exception as exc:
            logging.exception("pricing snapshot repair failed set_id=%s", set_id)
            result.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
        results.append(result)

    report = {
        "mode": "commit" if commit else "dry-run",
        "window": args.window,
        "setsAudited": len(results),
        "setsRepaired": sum(1 for row in results if row["status"] == "repaired"),
        "setsHealthy": sum(1 for row in results if row["status"] == "healthy"),
        "setsUnhealthy": sum(1 for row in results if row["status"] == "unhealthy"),
        "setsFailed": sum(1 for row in results if row["status"] == "failed"),
        "results": results,
    }
    if args.report:
        _write_report(args.report, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["setsFailed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
