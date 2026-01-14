from ..clients.supabase_client import supabase
from typing import Dict, Any, List, Optional


def get_all_conditions() -> List[Dict[str, Any]]:
    """
    Retrieve all available conditions from the conditions table.
    These are preset conditions like "Near Mint", "Lightly Played", etc.
    
    Returns:
        List of condition records with id, name, and abbreviation
    """
    res = supabase.table("conditions").select("*").execute()
    return res.data if res and res.data else []


def get_condition_by_name(name: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a condition by name.
    
    Args:
        name: The condition name (e.g., 'Near Mint', 'Lightly Played')
        
    Returns:
        The condition record, or None if not found
    """
    res = (
        supabase.table("conditions")
        .select("*")
        .eq("name", name)
        .maybe_single()
        .execute()
    )
    return res.data if res and res.data else None


def get_condition_by_id(condition_id: int) -> Optional[Dict[str, Any]]:
    """
    Retrieve a condition by ID.
    
    Args:
        condition_id: The ID of the condition
        
    Returns:
        The condition record, or None if not found
    """
    res = (
        supabase.table("conditions")
        .select("*")
        .eq("id", condition_id)
        .maybe_single()
        .execute()
    )
    return res.data if res and res.data else None
