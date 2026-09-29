"""Read-only PkmnPrices historical NM price probe for vintage edition gaps.

Purpose: determine whether PkmnPrices' TCGPlayer daily aggregates preserve an
explicit edition dimension even when current listings collapse to generic
"Holofoil". No database writes and no Set Value authority changes.
"""
from __future__ import annotations

import argparse
import json
from typing import Any

from backend.db.clients.supabase_client import create_service_role_client
from backend.pricing_pipeline.pkmnprices_client import PkmnPricesClient
from backend.pricing_pipeline.pkmnprices_credentials import load_pkmnprices_credentials
from backend.pricing_pipeline.pkmnprices_sold import parse_provider_variant
from backend.pricing_pipeline.pkmnprices_targets import (
    discover_vintage_gap_rows,
    latest_approved_market_date,
    resolve_targets,
)


def _matches_gap(row: dict[str, Any], gap: dict[str, Any]) -> bool:
    parsed = parse_provider_variant(row.get("variant"))
    return (
        parsed.get("edition") == str(gap.get("effective_edition") or "")
        and (
            not gap.get("printing_type")
            or parsed.get("printing_type") == str(gap.get("printing_type"))
        )
    )


def probe(db: Any, provider: PkmnPricesClient, market_date: str) -> dict[str, Any]:
    targets = resolve_targets(db, discover_vintage_gap_rows(db, market_date))
    out = []
    resolved = 0
    for target in targets:
        cards = provider.cards_by_tcgplayer_id(
            target["tcgplayer_product_id"], language="English", per_page=5
        )
        cards = [
            row for row in cards
            if str(row.get("tcg_player_id") or "") == str(target["tcgplayer_product_id"])
        ]
        if len(cards) != 1:
            out.append({
                "canonical_card_id": target["canonical_card_id"],
                "card_name": target["card_name"],
                "provider_identity_count": len(cards),
                "variants": [],
            })
            continue

        provider_id = cards[0]["id"]
        payload = provider.price_history_page(
            provider_id,
            currency="usd",
            period="30d",
            condition="Near Mint",
            limit=60,
            page=1,
        )
        rows = [
            dict(row) for row in (payload.get("data") or [])
            if isinstance(row, dict)
            and str(row.get("source") or "").casefold() == "tcgplayer"
            and str(row.get("condition") or "").casefold() == "near mint"
            and str(row.get("currency") or "").upper() == "USD"
        ]
        observed_variants = sorted({str(row.get("variant") or "") for row in rows})
        gaps = []
        for gap in target.get("gap_variants") or []:
            matches = [row for row in rows if _matches_gap(row, dict(gap))]
            if matches:
                resolved += 1
            gaps.append({
                "card_variant_id": gap.get("card_variant_id"),
                "market_scope": gap.get("market_scope"),
                "effective_edition": gap.get("effective_edition"),
                "printing_type": gap.get("printing_type"),
                "matching_history_rows": len(matches),
                "latest_match": max(
                    (
                        {
                            "date": str(row.get("date") or ""),
                            "avg": row.get("avg"),
                            "low": row.get("low"),
                            "high": row.get("high"),
                            "variant": row.get("variant"),
                        }
                        for row in matches
                    ),
                    key=lambda row: row["date"],
                    default=None,
                ),
            })
        out.append({
            "canonical_card_id": target["canonical_card_id"],
            "card_name": target["card_name"],
            "card_number": target["card_number"],
            "set_name": target["set_name"],
            "tcgplayer_product_id": target["tcgplayer_product_id"],
            "provider_card_id": provider_id,
            "history_row_count": len(rows),
            "observed_variants": observed_variants,
            "gaps": gaps,
        })

    gap_count = sum(len(row.get("gap_variants") or []) for row in targets)
    return {
        "market_date": market_date,
        "target_count": len(targets),
        "gap_variant_count": gap_count,
        "resolved_gap_variant_count": resolved,
        "unresolved_gap_variant_count": gap_count - resolved,
        "credits_used": provider.credits_charged,
        "credit_limit": provider.credits_limit,
        "rate_remaining": provider.rate_remaining,
        "database_writes": 0,
        "targets": out,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-date")
    args = parser.parse_args()
    db = create_service_role_client()
    market_date = args.market_date or latest_approved_market_date(db)
    credentials = load_pkmnprices_credentials(allow_frontend_fallback=False)
    result = probe(db, PkmnPricesClient(credentials.api_key), market_date)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
