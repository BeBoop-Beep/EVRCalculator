"""Read-only probe of PkmnPrices TCGplayer condition/variant rows for vintage gaps."""
from __future__ import annotations

import argparse
import json
from typing import Any

from backend.db.clients.supabase_client import create_service_role_client
from backend.pricing_pipeline.pkmnprices_client import PkmnPricesClient
from backend.pricing_pipeline.pkmnprices_credentials import load_pkmnprices_credentials
from backend.pricing_pipeline.pkmnprices_targets import (
    discover_vintage_gap_rows,
    latest_approved_market_date,
    resolve_targets,
)


def probe(db: Any, provider: PkmnPricesClient, market_date: str) -> dict[str, Any]:
    gaps = discover_vintage_gap_rows(db, market_date)
    targets = resolve_targets(db, gaps)
    out = []
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
                "tcgplayer_product_id": target["tcgplayer_product_id"],
                "provider_identity_count": len(cards),
                "gap_variants": target["gap_variants"],
                "near_mint_usd_rows": [],
            })
            continue
        provider_id = cards[0]["id"]
        detail = provider.card(provider_id, currency="usd")
        prices = detail.get("prices") or []
        nm = [
            {
                "source": row.get("source"),
                "condition": row.get("condition"),
                "variant": row.get("variant"),
                "market_price": row.get("market_price"),
                "created_at": row.get("created_at"),
            }
            for row in prices
            if str(row.get("source") or "").casefold() == "tcgplayer"
            and str(row.get("currency") or "").upper() == "USD"
            and str(row.get("condition") or "").casefold() == "near mint"
        ]
        out.append({
            "canonical_card_id": target["canonical_card_id"],
            "card_name": target["card_name"],
            "card_number": target["card_number"],
            "tcgplayer_product_id": target["tcgplayer_product_id"],
            "provider_card_id": provider_id,
            "gap_variants": target["gap_variants"],
            "near_mint_usd_rows": nm,
        })
    return {
        "market_date": market_date,
        "target_count": len(targets),
        "credits_used": provider.credits_charged,
        "credit_limit": provider.credits_limit,
        "targets": out,
        "database_writes": 0,
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
