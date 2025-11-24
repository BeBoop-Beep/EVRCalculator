from ..clients.supabase_client import supabase
from typing import Optional, Dict, Any

def insert_card(card_row: Dict[str, Any]) -> int:
    """Insert a card row into `cards` and return the new id.
        card_row should include: set_id, name, rarity, copies_in_pack (optional)
    """
    res = supabase.table("cards").insert(card_row).execute()
    if res.error:
        raise RuntimeError(f"Failed to insert card: {res.error}")
    # Supabase returns list of inserted rows
    inserted = res.data
    if not inserted:
        raise RuntimeError("Insert returned no data")
    return inserted[0]["id"]


def get_card_by_name_and_set(name: str, set_id: int) -> Optional[Dict[str, Any]]:
    """Return a single card record matching name+set_id, or None."""
    res = (
        supabase.table("cards")
        .select("*")
        .eq("name", name)
        .eq("set_id", set_id)
        .maybe_single()
        .execute()
    )
    return res.data if res.data else None