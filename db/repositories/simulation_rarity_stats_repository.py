"""Repository for simulation_rarity_stats table operations"""
from ..clients.supabase_client import supabase

def insert_rarity_stat(stat_data: dict):
    """
    Insert a single rarity statistic for a simulation
    
    Args:
        stat_data: Dictionary with:
            - simulation_id (UUID)
            - rarity_name (str)
            - pull_count (int)
            - total_value (Decimal)
            - average_value (Decimal)
        
    Returns:
        Inserted rarity stat record
    """
    result = supabase.table("simulation_rarity_stats").insert(stat_data).execute()
    if result is None:
        raise RuntimeError("Insert rarity stat returned no response object")
    return result.data[0] if result.data else None

def insert_rarity_stats_batch(stats_data_list: list):
    """
    Insert multiple rarity statistics at once
    
    Args:
        stats_data_list: List of dictionaries with rarity stat data
        
    Returns:
        List of inserted records
    """
    result = supabase.table("simulation_rarity_stats").insert(stats_data_list).execute()
    if result is None:
        raise RuntimeError("Insert rarity stats batch returned no response object")
    return result.data if result.data else None

def get_rarity_stats_by_simulation_id(simulation_id: str):
    """Get all rarity statistics for a specific simulation"""
    result = supabase.table("simulation_rarity_stats").select("*").eq("simulation_id", simulation_id).execute()
    return result.data if result.data else None
