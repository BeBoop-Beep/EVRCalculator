from ..clients.supabase_client import supabase
from typing import Dict, Any, Optional


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
    res = supabase.table("sealed_product_prices").insert(price_row).execute()
    if res.error:
        raise RuntimeError(f"Failed to insert sealed product price: {res.error}")
    
    inserted = res.data
    if not inserted:
        raise RuntimeError("Insert returned no data")
    
    return inserted[0]["id"]


def get_latest_price(sealed_product_id: int) -> Optional[Dict[str, Any]]:
    """
    Get the most recent price record for a sealed product.
    
    Args:
        sealed_product_id: The ID of the sealed product
        
    Returns:
        The most recent price record, or None if not found
    """
    res = (
        supabase.table("sealed_product_prices")
        .select("*")
        .eq("sealed_product_id", sealed_product_id)
        .order("captured_at", desc=True)
        .limit(1)
        .maybe_single()
        .execute()
    )
    return res.data if res.data else None
