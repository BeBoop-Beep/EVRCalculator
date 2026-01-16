"""Repository for simulation_top_hits table operations"""
from ..clients.supabase_client import supabase

def insert_top_hit(hit_data: dict):
    """
    Insert a single top hit card for a simulation
    
    Args:
        hit_data: Dictionary with:
            - simulation_id (UUID)
            - card_name (str)
            - price (Decimal)
            - effective_pull_rate (Decimal, optional)
            - rank (int) - ranking position (1-10)
        
    Returns:
        Inserted top hit record
    """
    result = supabase.table("simulation_top_hits").insert(hit_data).execute()
    if result is None:
        raise RuntimeError("Insert top hit returned no response object")
    return result.data[0] if result.data else None

def insert_top_hits_batch(hits_data_list: list):
    """
    Insert multiple top hit cards at once
    
    Args:
        hits_data_list: List of dictionaries with top hit data
        
    Returns:
        List of inserted records
    """
    result = supabase.table("simulation_top_hits").insert(hits_data_list).execute()
    if result is None:
        raise RuntimeError("Insert top hits batch returned no response object")
    return result.data if result.data else None

def get_top_hits_by_simulation_id(simulation_id: str):
    """Get all top hit cards for a specific simulation, ordered by rank"""
    result = supabase.table("simulation_top_hits").select("*").eq("simulation_id", simulation_id).order("rank").execute()
    return result.data if result.data else None
