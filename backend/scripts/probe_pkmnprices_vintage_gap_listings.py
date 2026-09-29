"""Read-only calibration probe for exact vintage TCGplayer listings via PkmnPrices.

This does not write database prices. It asks PkmnPrices for live Near Mint
TCGplayer offers and checks whether each missing inDex edition/printing variant
is represented explicitly by the provider's `printing` field.
"""
from __future__ import annotations

import argparse
import json
from decimal import Decimal
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


def _money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def _matching_rows(rows: list[dict[str, Any]], gap_variant: dict[str, Any]) -> list[dict[str, Any]]:
    edition = str(gap_variant.get("effective_edition") or "")
    printing_type = str(gap_variant.get("printing_type") or "")
    out = []
    for row in rows:
        parsed = parse_provider_variant(row.get("printing"))
        if parsed.get("edition") != edition:
            continue
        if printing_type and parsed.get("printing_type") != printing_type:
            continue
        out.append(row)
    return out


def probe(db: Any, provider: PkmnPricesClient, market_date: str) -> dict[str, Any]:
    targets = resolve_targets(db, discover_vintage_gap_rows(db, market_date))
    results = []
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
            results.append({
                "canonical_card_id": target["canonical_card_id"],
                "card_name": target["card_name"],
                "tcgplayer_product_id": target["tcgplayer_product_id"],
                "provider_identity_count": len(cards),
                "variants": [],
            })
            continue

        provider_card_id = cards[0]["id"]
        page = provider.tcgplayer_listings_page(
            provider_card_id,
            condition="Near Mint",
            language="English",
            sort="total_asc",
            limit=20,
        )
        listings = [dict(row) for row in (page.get("data") or []) if isinstance(row, dict)]
        variants = []
        for gap in target.get("gap_variants") or []:
            matches = _matching_rows(listings, dict(gap))
            totals = sorted(
                _money(row.get("price")) + _money(row.get("shipping_price"))
                for row in matches
                if row.get("price") is not None
            )
            if matches:
                resolved += 1
            variants.append({
                "card_variant_id": gap.get("card_variant_id"),
                "market_scope": gap.get("market_scope"),
                "effective_edition": gap.get("effective_edition"),
                "printing_type": gap.get("printing_type"),
                "matching_listing_count": len(matches),
                "cheapest_total": str(totals[0]) if totals else None,
                "median_first_page_total": str(totals[len(totals)//2]) if totals else None,
                "observed_printings": sorted({
                    str(row.get("printing") or "") for row in listings if row.get("printing")
                }),
                "snapshot_at": max(
                    (str(row.get("snapshot_at") or "") for row in matches),
                    default=None,
                ),
            })
        results.append({
            "canonical_card_id": target["canonical_card_id"],
            "card_name": target["card_name"],
            "card_number": target["card_number"],
            "set_name": target["set_name"],
            "tcgplayer_product_id": target["tcgplayer_product_id"],
            "provider_card_id": provider_card_id,
            "near_mint_listing_count_first_page": len(listings),
            "variants": variants,
        })

    expected_variants = sum(len(t.get("gap_variants") or []) for t in targets)
    return {
        "market_date": market_date,
        "target_count": len(targets),
        "gap_variant_count": expected_variants,
        "resolved_gap_variant_count": resolved,
        "unresolved_gap_variant_count": expected_variants - resolved,
        "credits_used": provider.credits_charged,
        "credit_limit": provider.credits_limit,
        "rate_remaining": provider.rate_remaining,
        "database_writes": 0,
        "targets": results,
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
