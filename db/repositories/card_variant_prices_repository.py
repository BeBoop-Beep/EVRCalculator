from ..clients.supabase_client import supabase
from typing import Dict, Any, Optional


def insert_card_variant_price(price_row: Dict[str, Any]) -> int:
    """
    Insert a price row into `card_variant_prices`.
    
    Args:
        price_row: Should include card_variant_id, condition_id, market_price, 
                   currency (optional), source, captured_at, high_price (optional), low_price (optional)
                   
    Returns:
        The id of the newly inserted price record
        
    Raises:
        RuntimeError: If insertion fails
    """
    res = supabase.table("card_variant_prices").insert(price_row).execute()
    if res.error:
        raise RuntimeError(f"Failed to insert card variant price: {res.error}")
    
    inserted = res.data
    if not inserted:
        raise RuntimeError("Insert returned no data")
    
    return inserted[0]["id"]


def get_latest_price(card_variant_id: int, condition_id: int) -> Optional[Dict[str, Any]]:
    """
    Get the most recent price record for a card variant and condition.
    
    Args:
        card_variant_id: The ID of the card variant
        condition_id: The ID of the condition
        
    Returns:
        The most recent price record, or None if not found
    """
    res = (
        supabase.table("card_variant_prices")
        .select("*")
        .eq("card_variant_id", card_variant_id)
        .eq("condition_id", condition_id)
        .order("captured_at", desc=True)
        .limit(1)
        .maybe_single()
        .execute()
    )
    return res.data if res.data else None