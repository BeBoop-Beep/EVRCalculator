from ..clients.supabase_client import supabase
from typing import Optional, Dict, Any


def insert_sealed_product(sealed_product_row: Dict[str, Any]) -> int:
    """
    Insert a sealed product row into `sealed_products` and return the new id.
    
    Args:
        sealed_product_row: Should include set_id, name, product_type
        
    Returns:
        The id of the newly inserted sealed product
        
    Raises:
        RuntimeError: If insertion fails
    """
    res = supabase.table("sealed_products").insert(sealed_product_row).execute()
    if res.error:
        raise RuntimeError(f"Failed to insert sealed product: {res.error}")
    
    inserted = res.data
    if not inserted:
        raise RuntimeError("Insert returned no data")
    
    return inserted[0]["id"]


def get_sealed_product_by_name_and_set(name: str, set_id: int) -> Optional[Dict[str, Any]]:
    """
    Retrieve a sealed product by name and set.
    
    Args:
        name: The name of the sealed product
        set_id: The ID of the set
        
    Returns:
        The sealed product record, or None if not found
    """
    res = (
        supabase.table("sealed_products")
        .select("*")
        .eq("name", name)
        .eq("set_id", set_id)
        .maybe_single()
        .execute()
    )
    return res.data if res.data else None


