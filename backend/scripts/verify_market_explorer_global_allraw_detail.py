"""Paginate the full Global All Raw normalized detail set to verify uniqueness
and absence of retired-predecessor IDs (avoids PostgREST's 1000-row default cap)."""
import json
from backend.db.clients.supabase_client import create_service_role_client

FINGERPRINT = "66426743b657a45f4381f3a5b9a5f216158158d4dd3c6ba8b8da6ec56c53a8e6"


def page_all(client):
    ids = []
    page_size = 1000
    start = 0
    while True:
        rows = (client.table("pokemon_market_explorer_query_cache_constituents")
                .select("card_variant_id,rank").eq("query_fingerprint", FINGERPRINT)
                .order("rank").range(start, start + page_size - 1).execute()).data
        if not rows:
            break
        ids.extend(rows)
        if len(rows) < page_size:
            break
        start += page_size
    return ids


def main():
    client = create_service_role_client()
    rows = page_all(client)
    ids = [r["card_variant_id"] for r in rows]
    ranks = [r["rank"] for r in rows]
    unique_ids = set(ids)

    ledger = (client.table("pokemon_market_explorer_variant_merge_ledger")
              .select("predecessor_variant_id").execute()).data
    retired_ids = {r["predecessor_variant_id"] for r in ledger}
    retired_in_detail = unique_ids & retired_ids

    print(json.dumps({
        "total_rows": len(ids),
        "unique_ids_count": len(unique_ids),
        "duplicate_count": len(ids) - len(unique_ids),
        "ranks_sorted_and_sequential": ranks == sorted(ranks) and ranks == list(range(1, len(ranks) + 1)),
        "retired_ids_in_detail_count": len(retired_in_detail),
    }, indent=2))


if __name__ == "__main__":
    main()
