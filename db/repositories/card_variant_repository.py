from ..clients.supabase_client import supabase
from typing import Optional, Dict, Any, List


def insert_card_variant(card_variant_row: Dict[str, Any]) -> int:
    """
    Insert a card variant row into `card_variants` and return the new id.
    
    Args:
        card_variant_row: Should include card_id, printing_type, special_type (optional), edition (optional)
        
    Returns:
        The id of the newly inserted card variant
        
    Raises:
        RuntimeError: If insertion fails
    """
    res = supabase.table("card_variants").insert(card_variant_row).execute()
    if res.error:
        raise RuntimeError(f"Failed to insert card variant: {res.error}")
    
    inserted = res.data
    if not inserted:
        raise RuntimeError("Insert returned no data")
    
    return inserted[0]["id"]


def get_card_variant_by_card_and_type(
    card_id: int, 
    printing_type: str, 
    special_type: Optional[str] = None,
    edition: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Retrieve a card variant by card_id and printing characteristics.
    
    Args:
        card_id: The ID of the card
        printing_type: The printing type (e.g., 'holo', 'reverse-holo', 'non-holo')
        special_type: Optional special type (e.g., 'ex', 'v', 'vmax')
        edition: Optional edition info
        
    Returns:
        The card variant record, or None if not found
    """
    query = (
        supabase.table("card_variants")
        .select("*")
        .eq("card_id", card_id)
        .eq("printing_type", printing_type)
    )
    
    if special_type:
        query = query.eq("special_type", special_type)
    if edition:
        query = query.eq("edition", edition)
    
    res = query.maybe_single().execute()
    return res.data if res.data else None


def get_card_variants_by_card_id(card_id: int) -> List[Dict[str, Any]]:
    """
    Retrieve all card variants for a given card.
    
    Args:
        card_id: The ID of the card
        
    Returns:
        List of card variant records
    """
    res = supabase.table("card_variants").select("*").eq("card_id", card_id).execute()
    return res.data if res.data else []
