"""Audit latest standard Set Value against the canonical card-day RPC.

Read-only and fail-closed: exits 1 when any comparable set differs by more than
one cent. Intended for CI against an ephemeral migrated database and for the
post-deploy/pre-snapshot publication gate.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Dict, List

from backend.db.clients.supabase_client import supabase


TOLERANCE = Decimal("0.01")


def audit_latest_reconciliation(client: Any = supabase) -> Dict[str, Any]:
    history = (
        client.table("pokemon_set_value_daily_history")
        .select("set_id,snapshot_date,set_value")
        .eq("value_scope", "standard")
        .order("snapshot_date", desc=True)
        .execute()
        .data
        or []
    )
    latest_by_set: Dict[str, Dict[str, Any]] = {}
    for row in history:
        latest_by_set.setdefault(str(row["set_id"]), row)

    findings: List[Dict[str, Any]] = []
    for set_id, expected in sorted(latest_by_set.items()):
        market_date = str(expected["snapshot_date"])
        rows = (
            client.rpc(
                "get_pokemon_cards_daily_constituents",
                {
                    "p_set_ids": [set_id],
                    "p_start_date": market_date,
                    "p_end_date": market_date,
                    "p_card_ids": None,
                },
            ).execute().data
            or []
        )
        if not rows:
            continue
        basket = sum((Decimal(str(row["market_price"])) for row in rows), Decimal(0))
        set_value = Decimal(str(expected["set_value"]))
        difference = basket - set_value
        findings.append(
            {
                "set_id": set_id,
                "market_date": market_date,
                "basket_value": str(basket),
                "set_value": str(set_value),
                "difference": str(difference),
                "within_tolerance": abs(difference) <= TOLERANCE,
            }
        )

    failures = [row for row in findings if not row["within_tolerance"]]
    return {
        "ok": not failures,
        "tolerance": str(TOLERANCE),
        "sets_compared": len(findings),
        "failed_set_count": len(failures),
        "failures": failures,
    }


def main() -> int:
    report = audit_latest_reconciliation()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
