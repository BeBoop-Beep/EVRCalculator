from .supabase_client import supabase
from typing import Dict, Any

def insert_price(price_row: Dict[str, Any]) -> Dict[str, Any]:
    """Insert a price row into `card_prices`.
    Expected keys: card_id, grade_value, market_price, reverse_variant_price,
    holo_variant_price, currency (optional), source, captured_at
    """
    res = supabase.table("card_prices").insert(price_row).execute()
    if res.error:
        raise RuntimeError(f"Failed to insert price row: {res.error}")
    return res.data