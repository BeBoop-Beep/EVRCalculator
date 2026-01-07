from ..clients.supabase_client import supabase, SUPABASE_URL, SUPABASE_KEY
from supabase import create_client
from typing import Dict, Any, Optional
import time


def insert_sealed_product_price(price_row: Dict[str, Any]) -> int:
    """
    Insert a price row into `sealed_product_prices`.
    
    Args:
        price_row: Should include sealed_product_id, market_price, source, captured_at.
                   Optional: currency (defaults to USD in DB)
        
    Returns:
        The id of the newly inserted price record
        
    Raises:
        RuntimeError: If insertion fails
    """
    # Retry mechanism for schema cache issues
    max_retries = 3
    for attempt in range(max_retries):
        try:
            fresh_client = create_client(SUPABASE_URL, SUPABASE_KEY)
            res = fresh_client.table("sealed_product_prices").insert(price_row).execute()
            if res is None:
                raise RuntimeError("Insert sealed product price returned no response object")
            if res.error:
                error_msg = str(res.error)
                if "schema cache" in error_msg.lower():
                    print(f"[WARN]  Schema cache error on attempt {attempt + 1}/{max_retries}, retrying...")
                    if attempt < max_retries - 1:
                        time.sleep(1)
                        continue
                raise RuntimeError(f"Failed to insert sealed product price: {res.error}")
            
            inserted = res.data
            if not inserted:
                raise RuntimeError("Insert returned no data")
            
            return inserted[0]["id"]
        except RuntimeError as e:
            if "schema cache" in str(e).lower() and attempt < max_retries - 1:
                time.sleep(1)
                continue
            raise
    raise RuntimeError("Failed to insert sealed product price after retries")


def get_latest_price(sealed_product_id: int) -> Optional[Dict[str, Any]]:
    """
    Get the most recent price record for a sealed product.
    
    Args:
        sealed_product_id: The ID of the sealed product
        
    Returns:
        The most recent price record, or None if not found
    """
    fresh_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    res = (
        fresh_client.table("sealed_product_prices")
        .eq("sealed_product_id", sealed_product_id)
        .order("captured_at", desc=True)
        .limit(1)
        .maybe_single()
        .execute()
    )
    return res.data if res and res.data else None
