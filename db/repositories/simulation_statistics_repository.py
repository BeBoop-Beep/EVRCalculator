"""Repository for simulation_statistics table operations"""
from ..clients.supabase_client import supabase

def insert_simulation_statistics(stats_data: dict):
    """
    Insert statistical summary for a simulation
    
    Args:
        stats_data: Dictionary with:
            - simulation_id (UUID)
            - mean_value (Decimal)
            - std_dev (Decimal)
            - min_value (Decimal)
            - max_value (Decimal)
            - variance (Decimal, optional)
            - weighted_variance (Decimal, optional)
            - weighted_stddev (Decimal, optional)
        
    Returns:
        Inserted statistics record
    """
    result = supabase.table("simulation_statistics").insert(stats_data).execute()
    if result is None:
        raise RuntimeError("Insert simulation statistics returned no response object")
    return result.data[0] if result.data else None

def get_statistics_by_simulation_id(simulation_id: str):
    """Get statistics for a specific simulation"""
    result = supabase.table("simulation_statistics").select("*").eq("simulation_id", simulation_id).single().execute()
    return result.data if result.data else None
