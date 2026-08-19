from backend.db.clients.supabase_client import supabase

POSTGREST_IN_CHUNK_SIZE = 100
POSTGREST_PAGE_SIZE = 500

def _chunks(values, size=POSTGREST_IN_CHUNK_SIZE):
    ordered = list(dict.fromkeys(values))
    return [ordered[index:index + size] for index in range(0, len(ordered), size)]

def _fetch_all_pages(query_factory):
    rows, start = [], 0
    while True:
        page = query_factory().range(start, start + POSTGREST_PAGE_SIZE - 1).execute().data or []
        rows.extend(page)
        if len(page) < POSTGREST_PAGE_SIZE:
            return rows
        start += POSTGREST_PAGE_SIZE

def _fetch_by_chunks(values, query_factory):
    rows = []
    for chunk in _chunks(values):
        rows.extend(_fetch_all_pages(lambda chunk=chunk: query_factory(chunk)))
    return rows

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
    cards = _fetch_all_pages(
        lambda: supabase.table("cards").select("id").eq("set_id", set_id))
    card_ids = [row["id"] for row in cards]
    variants = (_fetch_by_chunks(card_ids, lambda chunk: supabase.table("card_variants")
        .select("id").in_("card_id", chunk)) if card_ids else [])
    variant_ids = [row["id"] for row in variants]
    conditions = (supabase.table("conditions").select("id").eq("name", "Near Mint").execute().data or [])
    nm_id = conditions[0]["id"] if len(conditions) == 1 else None
    # Arizona does not observe daylight saving time.
    observations = []
    if variant_ids and nm_id:
        observations = _fetch_by_chunks(variant_ids, lambda chunk: supabase.table("card_variant_price_observations")
            .select("card_variant_id").in_("card_variant_id", chunk)
            .eq("condition_id", nm_id).gt("market_price", 0)
            .eq("captured_at", str(market_date)))
    observed_variant_ids = sorted({row["card_variant_id"] for row in observations})
    identities = (_fetch_by_chunks(observed_variant_ids, lambda chunk: supabase.table("card_variant_external_identities")
        .select("external_product_id,external_variant_key").eq("provider", "tcgplayer")
        .in_("card_variant_id", chunk)) if observed_variant_ids else [])
    observed = {f"{row['external_product_id']}|{row['external_variant_key']}" for row in identities}
    reconciliation = reconcile_source_variant_keys(expected, observed)
    return {"setId": set_id, "marketDate": str(market_date),
            "positiveNmObservationCount": len(observed_variant_ids),
            "extraPersistedSourceVariantCount": len(observed - expected),
            **reconciliation}
