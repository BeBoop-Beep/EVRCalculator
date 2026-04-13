from typing import Any, Dict, Optional
from ..clients.supabase_client import supabase


def get_latest_price(graded_card_variant_id: int) -> Optional[Dict[str, Any]]:
    """Return the latest market row for a graded card variant, if available."""
    response = (
        supabase.table("graded_card_market_latest")
        .select("*")
        .eq("graded_card_variant_id", graded_card_variant_id)
        .maybe_single()
        .execute()
    )
    return response.data if response and response.data else None
