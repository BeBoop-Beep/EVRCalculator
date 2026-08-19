from datetime import datetime, time, timezone, timedelta

from backend.db.clients.supabase_client import supabase

def reconcile_source_variant_keys(expected_variant_keys, observed_variant_keys):
    expected, observed = set(expected_variant_keys), set(observed_variant_keys)
    matched = expected & observed
    return {"acceptedVariantGroups": len(expected),
            "reconciledSourceVariantCount": len(matched),
            "sourceCoverageRatio": (len(matched) / len(expected)) if expected else 0.0,
            "missingSourceVariantKeys": sorted(expected - observed)[:20],
            "success": bool(expected) and matched == expected}


def verify_tcgplayer_source_variant_persistence(set_id, market_date, expected_variant_keys):
    """Reconcile accepted TCGplayer source variants to exact Phoenix-day NM rows."""
    expected = set(expected_variant_keys)
    cards = (supabase.table("cards").select("id").eq("set_id", set_id).execute().data or [])
    card_ids = [row["id"] for row in cards]
    variants = [] if not card_ids else (supabase.table("card_variants").select("id")
        .in_("card_id", card_ids).execute().data or [])
    variant_ids = [row["id"] for row in variants]
    conditions = (supabase.table("conditions").select("id").eq("name", "Near Mint").execute().data or [])
    nm_id = conditions[0]["id"] if len(conditions) == 1 else None
    # Arizona does not observe daylight saving time.
    phoenix = timezone(timedelta(hours=-7), "America/Phoenix")
    day = datetime.fromisoformat(str(market_date)).date()
    start = datetime.combine(day, time.min, phoenix).astimezone(timezone.utc).isoformat()
    end = datetime.combine(day, time.max, phoenix).astimezone(timezone.utc).isoformat()
    observations = []
    if variant_ids and nm_id:
        observations = (supabase.table("card_variant_price_observations")
            .select("card_variant_id").in_("card_variant_id", variant_ids)
            .eq("condition_id", nm_id).gt("market_price", 0)
            .gte("captured_at", start).lte("captured_at", end).execute().data or [])
    observed_variant_ids = sorted({row["card_variant_id"] for row in observations})
    identities = [] if not observed_variant_ids else (supabase.table("card_variant_external_identities")
        .select("external_product_id,external_variant_key").eq("provider", "tcgplayer")
        .in_("card_variant_id", observed_variant_ids).execute().data or [])
    observed = {f"{row['external_product_id']}|{row['external_variant_key']}" for row in identities}
    reconciliation = reconcile_source_variant_keys(expected, observed)
    return {"setId": set_id, "marketDate": str(market_date),
            "positiveNmObservationCount": len(observed_variant_ids),
            **reconciliation}
